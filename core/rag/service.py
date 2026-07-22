import contextvars
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
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

from core.performance import (
    TTLCache,
    asset_manifest_hash,
    knowledge_index_hash,
    qualified_asset_library_hash,
    rag_query_hash,
)
from core.rag.documents import load_rag_documents
from core.rag.embeddings import DEFAULT_MODEL, EmbeddingProvider, build_embedding_provider
from core.rag.models import RagDocument, RagIndexReport, RagSearchResult
from core.rag.reranker import RerankDiagnostics, Reranker, RerankOutcome, build_reranker
from core.rag.text import normalized_tokens

logger = logging.getLogger(__name__)

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
_INDEX_BUILD_MARKER = "__build_"
_POINT_UPSERT_BATCH_SIZE = 128
_OBSOLETE_COLLECTION_WAIT_S = 2.0


class RagIndexCompatibilityError(RuntimeError):
    """Raised when a persisted Qdrant index was built with another embedding dimension."""


@dataclass(frozen=True, slots=True)
class _CachedRagSearch:
    results: list[RagSearchResult]
    diagnostics: RerankDiagnostics | None


@dataclass(slots=True)
class _ReindexFlight:
    completed: threading.Event = field(default_factory=threading.Event)
    report: RagIndexReport | None = None
    error: BaseException | None = None


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
        self.query_cache: TTLCache[_CachedRagSearch] = TTLCache(ttl_s=query_cache_ttl_s)
        self._client_lock = threading.Lock()
        self._reranker_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._runtime_collection_lock = threading.Lock()
        self._reindex_lock = threading.Lock()
        self._reindex_flight: _ReindexFlight | None = None
        self._collection_condition = threading.Condition()
        self._collection_readers: dict[str, int] = defaultdict(int)
        self._last_rerank_diagnostics: contextvars.ContextVar[RerankDiagnostics | None] = (
            contextvars.ContextVar(
                f"rag_service_rerank_diagnostics_{id(self)}",
                default=None,
            )
        )

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            with self._client_lock:
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
            with self._reranker_lock:
                if self._reranker is None:
                    self._reranker = build_reranker(
                        self._reranker_model,
                        provider_name=self._reranker_provider_name,
                        api_key=self._reranker_api_key,
                        base_url=self._reranker_base_url,
                    )
        return self._reranker

    def reindex(self) -> RagIndexReport:
        with self._reindex_lock:
            flight = self._reindex_flight
            if flight is None or flight.completed.is_set():
                flight = _ReindexFlight()
                self._reindex_flight = flight
                leader = True
            else:
                leader = False

        if not leader:
            flight.completed.wait()
            if flight.error is not None:
                raise RuntimeError("Concurrent RAG reindex failed") from flight.error
            if flight.report is None:
                raise RuntimeError("Concurrent RAG reindex completed without a report")
            return flight.report

        try:
            report = self._reindex_once()
        except BaseException as exc:
            flight.error = exc
            flight.completed.set()
            raise

        flight.report = report
        flight.completed.set()
        return report

    def _reindex_once(self) -> RagIndexReport:
        index_identity = self._static_index_identity()
        documents = load_rag_documents(self.project_root)
        grouped = _group_documents(documents)
        indexed_counts: dict[str, int] = {}
        build_id = uuid.uuid4().hex[:16]
        staged_collections = {
            collection: f"{collection}{_INDEX_BUILD_MARKER}{build_id}"
            for collection in RAG_COLLECTIONS
        }
        created_collections: list[str] = []

        try:
            for collection in RAG_COLLECTIONS:
                collection_docs = grouped.get(collection, [])
                staged_name = staged_collections[collection]
                self._create_collection(staged_name)
                created_collections.append(staged_name)
                points = self._points_for_documents(collection_docs)
                for point_batch in _batches(points, _POINT_UPSERT_BATCH_SIZE):
                    self.client.upsert(
                        collection_name=staged_name,
                        points=point_batch,
                        wait=True,
                    )
                indexed_counts[collection] = len(collection_docs)

            if self._static_index_identity() != index_identity:
                raise RuntimeError("RAG source documents changed while the index was being built")

            old_state = self._read_static_index_state()
            old_mapping = _physical_collection_map(old_state)
            old_physical = set(old_mapping.values())
            if old_state and not old_mapping:
                old_physical.update(
                    collection
                    for collection in RAG_COLLECTIONS
                    if self.client.collection_exists(collection)
                )
            old_obsolete = set(_obsolete_collections(old_state))
            new_physical = set(staged_collections.values())
            obsolete = sorted((old_physical | old_obsolete) - new_physical)
            with self._collection_condition:
                self._write_static_index_state(
                    indexed_counts,
                    physical_collections=staged_collections,
                    obsolete_collections=obsolete,
                    index_identity=index_identity,
                )
        except Exception:
            self._delete_collections(created_collections)
            raise

        with self._cache_lock:
            self.query_cache.clear()
        self._cleanup_obsolete_collections(indexed_counts, staged_collections, index_identity)
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
            with self._cache_lock:
                cached = self.query_cache.get(query_hash)
            if cached is not None:
                self._restore_rerank_diagnostics(cached.diagnostics)
                return cached.results
        vector = _embed_query(self.embedding_provider, query)
        query_tokens = _tokenize(query)
        results: list[RagSearchResult] = []
        static_collections = [name for name in collections if name in RAG_COLLECTIONS]
        with self._static_collection_snapshot(static_collections) as physical_names:
            for collection_name in collections:
                physical_name = physical_names.get(collection_name, collection_name)
                if not self.client.collection_exists(physical_name):
                    continue
                try:
                    response = self.client.query_points(
                        collection_name=physical_name,
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
        reranked = self._rerank(query, sorted_results, top_k=limit)
        diagnostics = self.last_rerank_diagnostics
        if cacheable:
            with self._cache_lock:
                self.query_cache.set(
                    query_hash,
                    _CachedRagSearch(results=reranked, diagnostics=diagnostics),
                )
        return reranked

    def cache_stats(self) -> dict[str, int]:
        with self._cache_lock:
            stats = self.query_cache.snapshot()
        return {"rag_cache_hits": stats["hits"], "rag_cache_misses": stats["misses"]}

    def close(self) -> None:
        if self._reranker is not None:
            close_reranker = getattr(self._reranker, "close", None)
            if callable(close_reranker):
                close_reranker()
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
        with self._runtime_collection_lock:
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
        with self._cache_lock:
            self.query_cache.clear()
        self.client.upsert(
            collection_name=collection,
            points=[self._point_for_document(document)],
        )

    @property
    def last_rerank_diagnostics(self) -> RerankDiagnostics | None:
        """Diagnostics isolated to the current thread or asynchronous task context."""
        return self._last_rerank_diagnostics.get()

    def _create_collection(self, collection: str) -> None:
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
            vector=_embed_passages(self.embedding_provider, [document.text])[0],
            payload=payload,
        )

    def _points_for_documents(self, documents: Sequence[RagDocument]) -> list[PointStruct]:
        if not documents:
            return []
        vectors = _embed_passages(
            self.embedding_provider,
            [document.text for document in documents],
        )
        if len(vectors) != len(documents):
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        points: list[PointStruct] = []
        for document, vector in zip(documents, vectors, strict=True):
            if len(vector) != self.embedding_provider.dimensions:
                raise RuntimeError(
                    f"Embedding dimension mismatch for {document.doc_id}: "
                    f"expected {self.embedding_provider.dimensions}, got {len(vector)}"
                )
            payload = document.payload | {
                "doc_id": document.doc_id,
                "collection": document.collection,
                "text": document.text,
            }
            points.append(
                PointStruct(
                    id=_stable_point_id(document.doc_id),
                    vector=vector,
                    payload=payload,
                )
            )
        return points

    def _rerank(
        self,
        query: str,
        results: list[RagSearchResult],
        *,
        top_k: int,
    ) -> list[RagSearchResult]:
        reranker = self.reranker
        rerank_with_diagnostics = getattr(reranker, "rerank_with_diagnostics", None)
        if callable(rerank_with_diagnostics):
            outcome = rerank_with_diagnostics(query, results, top_k)
            if isinstance(outcome, RerankOutcome):
                self._last_rerank_diagnostics.set(outcome.diagnostics)
                return list(outcome.results)
        self._last_rerank_diagnostics.set(None)
        return reranker.rerank(query, results, top_k=top_k)

    def _restore_rerank_diagnostics(self, diagnostics: RerankDiagnostics | None) -> None:
        self._last_rerank_diagnostics.set(diagnostics)
        if diagnostics is None:
            return
        restore = getattr(self.reranker, "restore_diagnostics", None)
        if callable(restore):
            restore(diagnostics)

    def _ensure_static_index_current(self) -> None:
        expected = self._static_index_identity()
        current = self._read_static_index_state()
        if _static_index_matches(current, expected) and self._static_collections_exist(current):
            return
        self.reindex()

    def _static_index_identity(self) -> dict:
        return {
            "knowledge_index_hash": knowledge_index_hash(self.project_root),
            "asset_manifest_hash": asset_manifest_hash(self.project_root / "assets" / "manifests"),
            "qualified_asset_library_hash": qualified_asset_library_hash(
                self.project_root / "assets" / "library" / "index" / "catalog.jsonl"
            ),
            "embedding_provider": self.embedding_provider.name,
            "embedding_dimensions": self.embedding_provider.dimensions,
            "embedding_input_profile": getattr(
                self.embedding_provider,
                "input_profile",
                "legacy_generic_v1",
            ),
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

    def _write_static_index_state(
        self,
        indexed_counts: dict[str, int],
        *,
        physical_collections: dict[str, str],
        obsolete_collections: list[str],
        index_identity: dict,
    ) -> None:
        path = self._static_index_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = index_identity | {
            "indexed_counts": indexed_counts,
            "physical_collections": physical_collections,
            "obsolete_collections": obsolete_collections,
        }
        temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            _fsync_directory(path.parent)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _static_collections_exist(self, state: dict | None) -> bool:
        if not state:
            return False
        counts = state.get("indexed_counts")
        if not isinstance(counts, dict):
            return False
        if set(counts) != set(RAG_COLLECTIONS):
            return False
        physical_collections = _physical_collection_map(state)
        if physical_collections and set(physical_collections) != set(RAG_COLLECTIONS):
            return False
        return all(
            self.client.collection_exists(physical_collections.get(collection, collection))
            for collection in RAG_COLLECTIONS
        )

    @contextmanager
    def _static_collection_snapshot(
        self,
        collections: Sequence[str],
    ) -> Iterator[dict[str, str]]:
        with self._collection_condition:
            state = self._read_static_index_state()
            active = _physical_collection_map(state)
            snapshot = {
                collection: active.get(collection, collection) for collection in collections
            }
            for physical_name in set(snapshot.values()):
                self._collection_readers[physical_name] += 1
        try:
            yield snapshot
        finally:
            with self._collection_condition:
                for physical_name in set(snapshot.values()):
                    self._collection_readers[physical_name] -= 1
                    if self._collection_readers[physical_name] <= 0:
                        self._collection_readers.pop(physical_name, None)
                self._collection_condition.notify_all()

    def _cleanup_obsolete_collections(
        self,
        indexed_counts: dict[str, int],
        physical_collections: dict[str, str],
        index_identity: dict,
    ) -> None:
        state = self._read_static_index_state()
        obsolete = set(_obsolete_collections(state))
        deadline = time.monotonic() + _OBSOLETE_COLLECTION_WAIT_S
        with self._collection_condition:
            while any(self._collection_readers.get(name, 0) for name in obsolete):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._collection_condition.wait(timeout=remaining)
            safe_to_delete = {
                name for name in obsolete if not self._collection_readers.get(name, 0)
            }
        failed = self._delete_collections(sorted(safe_to_delete))
        remaining_obsolete = sorted((obsolete - safe_to_delete) | failed)
        try:
            self._write_static_index_state(
                indexed_counts,
                physical_collections=physical_collections,
                obsolete_collections=remaining_obsolete,
                index_identity=index_identity,
            )
        except OSError as exc:
            logger.warning("Could not persist RAG obsolete-collection cleanup state: %s", exc)

    def _delete_collections(self, collections: Sequence[str]) -> set[str]:
        failed: set[str] = set()
        for collection in collections:
            try:
                if self.client.collection_exists(collection):
                    self.client.delete_collection(collection)
            except Exception as exc:
                failed.add(collection)
                logger.warning("Could not delete obsolete RAG collection %s: %s", collection, exc)
        return failed


def _group_documents(documents: list[RagDocument]) -> dict[str, list[RagDocument]]:
    grouped: dict[str, list[RagDocument]] = defaultdict(list)
    for document in documents:
        grouped[document.collection].append(document)
    return dict(grouped)


def _embed_query(provider: EmbeddingProvider, text: str) -> list[float]:
    embed_query = getattr(provider, "embed_query", None)
    if callable(embed_query):
        return embed_query(text)
    return provider.embed(text)


def _embed_passages(
    provider: EmbeddingProvider,
    texts: Sequence[str],
) -> list[list[float]]:
    embed_passages = getattr(provider, "embed_passages", None)
    if callable(embed_passages):
        return embed_passages(texts)
    embed_many = getattr(provider, "embed_many", None)
    if callable(embed_many):
        return embed_many(texts)
    return [provider.embed(text) for text in texts]


def _batches[T](items: Sequence[T], batch_size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), batch_size):
        yield list(items[start : start + batch_size])


def _physical_collection_map(state: dict | None) -> dict[str, str]:
    if not state:
        return {}
    value = state.get("physical_collections")
    if not isinstance(value, dict):
        return {}
    return {
        str(logical): str(physical)
        for logical, physical in value.items()
        if logical in RAG_COLLECTIONS and isinstance(physical, str) and physical
    }


def _obsolete_collections(state: dict | None) -> list[str]:
    if not state:
        return []
    value = state.get("obsolete_collections")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stable_point_id(doc_id: str) -> int:
    digest = hashlib.blake2b(doc_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def _static_index_matches(current: dict | None, expected: dict) -> bool:
    if not current:
        return False
    return all(current.get(key) == value for key, value in expected.items())


def _tokenize(text: str) -> set[str]:
    return set(normalized_tokens(text))


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
