import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from core.performance import TTLCache, knowledge_index_hash, rag_query_hash
from core.rag.documents import load_rag_documents
from core.rag.embeddings import DEFAULT_MODEL, EmbeddingProvider, build_embedding_provider
from core.rag.models import RagDocument, RagIndexReport, RagSearchResult
from core.rag.reranker import Reranker, build_reranker

RAG_COLLECTIONS = [
    "telecom_rules",
    "asset_manifests",
    "scene_templates",
    "validation_cases",
    "design_patterns",
    "blender_generation_guides",
]

RUNTIME_MEMORY_COLLECTIONS = [
    "design_memory",
    "error_memory",
    "document_pack_memory",
]

STATIC_INDEX_STATE_FILENAME = "qdrant_static_index_state.json"


class RagIndexCompatibilityError(RuntimeError):
    """Raised when a persisted Qdrant index was built with another embedding dimension."""


class RagService:
    def __init__(
        self,
        project_root: Path,
        qdrant_path: Path,
        qdrant_url: str | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_provider_name: str = "nvidia",
        embedding_model: str = DEFAULT_MODEL,
        reranker: Reranker | None = None,
        reranker_provider_name: str = "nvidia",
        reranker_model: str = "nvidia/llama-nemotron-rerank-1b-v2",
        reranker_api_key: str | None = None,
        reranker_base_url: str = "https://ai.api.nvidia.com/v1",
        query_cache_ttl_s: float = 30.0,
    ) -> None:
        self.project_root = project_root
        self.qdrant_path = qdrant_path
        self.qdrant_url = qdrant_url
        self.embedding_provider = embedding_provider or build_embedding_provider(
            embedding_provider_name, embedding_model
        )
        self._reranker = reranker
        self._reranker_provider_name = reranker_provider_name
        self._reranker_model = reranker_model
        self._reranker_api_key = reranker_api_key
        self._reranker_base_url = reranker_base_url
        self._client: QdrantClient | None = None
        self.query_cache: TTLCache[list[RagSearchResult]] = TTLCache(ttl_s=query_cache_ttl_s)

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            if self.qdrant_url:
                self._client = QdrantClient(url=self.qdrant_url)
            else:
                self.qdrant_path.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(self.qdrant_path))
        return self._client

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            self._reranker = build_reranker(
                self._reranker_model,
                provider_name=self._reranker_provider_name,
                api_key=self._reranker_api_key,
                base_url=self._reranker_base_url,
            )
        return self._reranker

    def reindex(self) -> RagIndexReport:
        documents = load_rag_documents(self.project_root)
        grouped = _group_documents(documents)

        indexed_counts: dict[str, int] = {}
        for collection in RAG_COLLECTIONS:
            collection_docs = grouped.get(collection, [])
            self._replace_collection(collection)
            if collection_docs:
                self.client.upsert(
                    collection_name=collection,
                    points=[self._point_for_document(document) for document in collection_docs],
                )
            indexed_counts[collection] = len(collection_docs)

        self.query_cache.clear()
        self._write_static_index_state(indexed_counts)
        return RagIndexReport(
            status="indexed",
            collections=indexed_counts,
            total_documents=sum(indexed_counts.values()),
            embedding_provider=self.embedding_provider.name,
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        collection: str | None = None,
        filters: dict[str, str | int | float | bool | None] | None = None,
    ) -> list[RagSearchResult]:
        if collection not in RUNTIME_MEMORY_COLLECTIONS:
            self._ensure_static_index_current()
        collections = [collection] if collection else RAG_COLLECTIONS
        cacheable = collection not in RUNTIME_MEMORY_COLLECTIONS
        query_hash = ""
        if cacheable:
            query_hash = rag_query_hash(
                query=query,
                limit=limit,
                collection=collection,
                filters=filters,
                embedding_provider_name=self.embedding_provider.name,
                index_hash=knowledge_index_hash(self.project_root),
            )
            cached = self.query_cache.get(query_hash)
            if cached is not None:
                return cached
        vector = self.embedding_provider.embed(query)
        query_tokens = _tokenize(query)
        results: list[RagSearchResult] = []
        for collection_name in collections:
            if not self.client.collection_exists(collection_name):
                continue
            try:
                response = self.client.query_points(
                    collection_name=collection_name,
                    query=vector,
                    limit=limit,
                    with_payload=True,
                    query_filter=_build_filter(filters),
                )
            except ValueError as exc:
                if _is_vector_dimension_mismatch(exc):
                    raise RagIndexCompatibilityError(
                        "RAG index vector dimension is incompatible with the active "
                        f"embedding provider ({self.embedding_provider.name}, "
                        f"{self.embedding_provider.dimensions} dimensions). Run /rag/reindex."
                    ) from exc
                raise
            for point in response.points:
                payload = point.payload or {}
                text = str(payload.get("text", ""))
                results.append(
                    RagSearchResult(
                        collection=collection_name,
                        doc_id=str(payload.get("doc_id", point.id)),
                        score=_hybrid_score(float(point.score), query_tokens, text),
                        text=text,
                        payload={key: value for key, value in payload.items() if key != "text"},
                    )
                )
        sorted_results = sorted(results, key=lambda result: result.score, reverse=True)
        reranked = self.reranker.rerank(query, sorted_results, top_k=limit)
        if cacheable:
            self.query_cache.set(query_hash, reranked)
        return reranked

    def cache_stats(self) -> dict[str, int]:
        stats = self.query_cache.snapshot()
        return {"rag_cache_hits": stats["hits"], "rag_cache_misses": stats["misses"]}

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def upsert_runtime_document(
        self,
        collection: str,
        doc_id: str,
        text: str,
        payload: dict,
    ) -> None:
        if collection not in RUNTIME_MEMORY_COLLECTIONS:
            raise ValueError(f"unsupported runtime collection: {collection}")
        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=self.embedding_provider.dimensions,
                    distance=Distance.COSINE,
                ),
            )
        document = RagDocument(
            doc_id=doc_id,
            collection=collection,
            text=text,
            payload=payload,
        )
        self.query_cache.clear()
        self.client.upsert(
            collection_name=collection,
            points=[self._point_for_document(document)],
        )

    def _replace_collection(self, collection: str) -> None:
        if self.client.collection_exists(collection):
            self.client.delete_collection(collection)
        self.client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(
                size=self.embedding_provider.dimensions,
                distance=Distance.COSINE,
            ),
        )

    def _point_for_document(self, document: RagDocument) -> PointStruct:
        payload = document.payload | {
            "doc_id": document.doc_id,
            "collection": document.collection,
            "text": document.text,
        }
        return PointStruct(
            id=_stable_point_id(document.doc_id),
            vector=self.embedding_provider.embed(document.text),
            payload=payload,
        )

    def _ensure_static_index_current(self) -> None:
        expected = self._static_index_identity()
        current = self._read_static_index_state()
        if _static_index_matches(current, expected) and self._static_collections_exist(current):
            return
        self.reindex()

    def _static_index_identity(self) -> dict:
        return {
            "knowledge_index_hash": knowledge_index_hash(self.project_root),
            "embedding_provider": self.embedding_provider.name,
            "embedding_dimensions": self.embedding_provider.dimensions,
            "collections": RAG_COLLECTIONS,
        }

    def _static_index_state_path(self) -> Path:
        return self.qdrant_path / STATIC_INDEX_STATE_FILENAME

    def _read_static_index_state(self) -> dict | None:
        path = self._static_index_state_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_static_index_state(self, indexed_counts: dict[str, int]) -> None:
        path = self._static_index_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._static_index_identity() | {"indexed_counts": indexed_counts}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _static_collections_exist(self, state: dict | None) -> bool:
        if not state:
            return False
        counts = state.get("indexed_counts")
        if not isinstance(counts, dict):
            return False
        return all(
            count == 0 or self.client.collection_exists(collection)
            for collection, count in counts.items()
            if collection in RAG_COLLECTIONS
        )


def _group_documents(documents: list[RagDocument]) -> dict[str, list[RagDocument]]:
    grouped: dict[str, list[RagDocument]] = defaultdict(list)
    for document in documents:
        grouped[document.collection].append(document)
    return dict(grouped)


def _stable_point_id(doc_id: str) -> int:
    digest = hashlib.blake2b(doc_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def _static_index_matches(current: dict | None, expected: dict) -> bool:
    if not current:
        return False
    return all(current.get(key) == value for key, value in expected.items())


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def _hybrid_score(vector_score: float, query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return vector_score
    text_tokens = _tokenize(text)
    lexical_score = len(query_tokens & text_tokens) / len(query_tokens)
    return vector_score + (0.35 * lexical_score)


def _build_filter(filters: dict[str, str | int | float | bool | None] | None) -> Filter | None:
    if not filters:
        return None
    conditions = []
    for key, value in filters.items():
        if value is None:
            continue
        if key in {"network_type", "tower_type"}:
            conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchAny(any=[value]),
                )
            )
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    if not conditions:
        return None
    return Filter(must=conditions)


def _is_vector_dimension_mismatch(exc: ValueError) -> bool:
    message = str(exc)
    return "shapes" in message and "not aligned" in message
