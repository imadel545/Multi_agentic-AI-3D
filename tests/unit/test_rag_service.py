import json
import shutil
from pathlib import Path

import httpx
import pytest

from core.rag import RagService
from core.rag.documents import load_rag_documents
from core.rag.embeddings import HashEmbeddingProvider, build_embedding_provider
from core.rag.models import RagSearchResult
from core.rag.reranker import NvidiaReranker, PassthroughReranker, build_reranker
from core.rag.text import normalized_tokens


def test_static_rag_excludes_reference_only_assets_from_planning_context() -> None:
    documents = load_rag_documents(Path.cwd())
    asset_ids = {
        document.payload.get("asset_id")
        for document in documents
        if document.payload.get("doc_type") == "asset_manifest"
    }

    assert "ANT_SIERRA_6001124_REFERENCE" not in asset_ids
    assert "ANT_PANEL_4G_001" in asset_ids
    panel = next(
        document
        for document in documents
        if document.payload.get("asset_id") == "ANT_PANEL_4G_001"
    )
    assert "qualification_status: qualified_for_generation" in panel.text
    assert panel.payload["generation_eligible"] is True


def test_static_rag_excludes_an_exact_asset_when_its_runtime_file_is_missing(
    tmp_path: Path,
) -> None:
    manifests = tmp_path / "assets" / "manifests"
    manifests.mkdir(parents=True)
    source = Path("assets/manifests/ANT_PANEL_4G_001.json")
    shutil.copy2(source, manifests / source.name)

    documents = load_rag_documents(tmp_path)

    assert not any(
        document.payload.get("asset_id") == "ANT_PANEL_4G_001"
        for document in documents
    )


def test_rag_reindex_and_search_returns_context(tmp_path: Path) -> None:
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
        reranker=PassthroughReranker(),
    )

    report = service.reindex()
    results = service.search("5G lattice tower 3 sectors", limit=5)

    assert report.status == "indexed"
    assert report.collections["telecom_rules"] >= 1
    assert report.collections["asset_manifests"] >= 8
    assert report.total_documents >= 10
    assert results
    assert any(
        "lattice" in result.text.lower() or result.payload.get("asset_id") == "TOWER_LATTICE_30M"
        for result in results
    )


def test_static_reindex_embeds_the_cross_collection_corpus_in_one_batch(tmp_path: Path) -> None:
    class CountingEmbeddingProvider(HashEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(dimensions=32)
            self.passage_calls = 0

        def embed_passages(self, texts) -> list[list[float]]:
            self.passage_calls += 1
            return super().embed_passages(texts)

    provider = CountingEmbeddingProvider()
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
        reranker=PassthroughReranker(),
    )

    report = service.reindex()

    assert report.total_documents > 0
    assert provider.passage_calls == 1


def test_static_rag_uses_visible_local_lexical_fallback_when_embeddings_fail(
    tmp_path: Path,
) -> None:
    class TimedOutEmbeddingProvider:
        name = "nvidia:test-timeout"
        dimensions = 8

        def embed(self, text: str) -> list[float]:
            raise TimeoutError("remote embedding timed out")

        def embed_many(self, texts) -> list[list[float]]:
            raise TimeoutError("remote embedding timed out")

        def embed_query(self, text: str) -> list[float]:
            raise TimeoutError("remote embedding timed out")

        def embed_passages(self, texts) -> list[list[float]]:
            raise TimeoutError("remote embedding timed out")

    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=TimedOutEmbeddingProvider(),
        reranker=PassthroughReranker(),
    )

    results = service.search("site 5G pylone trois secteurs RRU", limit=5)

    assert results
    assert all(result.payload["retrieval_mode"] == "degraded_local_lexical" for result in results)
    assert all(result.payload["retrieval_degraded_reason"] == "index_timeout" for result in results)
    assert all(result.payload["reranker_status"] == "not_recorded" for result in results)
    assert service.last_retrieval_diagnostics is not None
    assert service.last_retrieval_diagnostics.status == "degraded_local_lexical"
    assert service.last_retrieval_diagnostics.degraded_reason == "index_timeout"
    assert service.health_snapshot()["status"] == "failed"


def test_rag_search_reindexes_when_docs_change(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "docs").mkdir(parents=True)
    (project_root / "data" / "knowledge").mkdir(parents=True)
    (project_root / "assets" / "manifests").mkdir(parents=True)
    old_doc = project_root / "data" / "knowledge" / "design_patterns.md"
    old_doc.write_text("# Old\n\nobsolete deleted context for lattice demo", encoding="utf-8")
    service = RagService(
        project_root=project_root,
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
        reranker=PassthroughReranker(),
    )
    service.reindex()

    old_doc.unlink()
    (project_root / "data" / "knowledge" / "design_patterns.md").write_text(
        "# Current\n\nfresh active context for rooftop planning",
        encoding="utf-8",
    )

    results = service.search("fresh active rooftop planning", limit=5)

    assert results
    assert all("obsolete deleted context" not in result.text for result in results)
    assert any("fresh active context" in result.text for result in results)


def test_rag_filtered_search_by_network_and_tower(tmp_path: Path) -> None:
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
        reranker=PassthroughReranker(),
    )
    service.reindex()

    results = service.search(
        "microwave dish lattice",
        limit=5,
        collection="asset_manifests",
        filters={"network_type": "MW", "tower_type": "lattice_tower", "doc_type": "asset_manifest"},
    )

    assert results
    assert all("MW" in result.payload.get("compatible_networks", []) for result in results)


def test_rag_documents_expose_structured_hints_without_absolute_paths() -> None:
    documents = load_rag_documents(Path.cwd())

    template = next(
        document
        for document in documents
        if document.collection == "scene_templates"
        and document.payload.get("filename") == "scene_templates.md"
        and document.payload.get("planning_hints")
    )

    assert template.payload["planning_hints"]["antenna_install_height_m"] == 24.0
    assert template.payload["planning_hints"]["include_sector_beams"] is True
    assert not str(template.payload["source_path"]).startswith("/")


def test_rag_documents_exclude_developer_architecture_docs() -> None:
    documents = load_rag_documents(Path.cwd())

    assert documents
    assert all(document.payload.get("doc_type") != "project_doc" for document in documents)
    assert all(
        not str(document.payload.get("source_path", "")).startswith("docs/")
        for document in documents
    )


def test_rag_indexes_only_validated_generation_eligible_library_assets(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    catalog = project_root / "assets" / "library" / "index" / "catalog.jsonl"
    catalog.parent.mkdir(parents=True)
    entries = [
        {
            "file_id": "lib_validated",
            "relative_path": "3D/Pylone/tower.glb",
            "category": "Pylone",
            "claimed_dimension": "3d",
            "extension": "glb",
            "qualification_status": "validated",
            "generation_eligible": True,
        },
        {
            "file_id": "lib_quarantined",
            "relative_path": "3D/Pylone/raw.dwg",
            "category": "Pylone",
            "claimed_dimension": "3d",
            "extension": "dwg",
            "qualification_status": "quarantined_unverified",
            "generation_eligible": False,
        },
    ]
    catalog.write_text("\n".join(json.dumps(item) for item in entries) + "\n", encoding="utf-8")

    documents = load_rag_documents(project_root)

    library_docs = [
        doc for doc in documents if doc.payload.get("doc_type") == "asset_library_entry"
    ]
    assert [doc.payload["file_id"] for doc in library_docs] == ["lib_validated"]
    assert library_docs[0].payload["planning_hints"] == {}


def test_french_token_normalization_is_accent_insensitive() -> None:
    assert normalized_tokens("Pylône câblé à 30 m") == ["pylone", "cable", "a", "30", "m"]


def test_nvidia_embedding_provider_is_strict_when_configured(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("missing nvidia key")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    with pytest.raises(RuntimeError, match="NVIDIA API embedding provider is required"):
        build_embedding_provider("nvidia", "nvidia/llama-nemotron-embed-1b-v2")


def test_nvidia_embedding_provider_never_deletes_user_model_cache(
    tmp_path: Path, monkeypatch
) -> None:
    cache_dir = tmp_path / "hub" / "user-owned-model-cache"
    cache_dir.mkdir(parents=True)
    marker = cache_dir / "user-owned-cache"
    marker.write_text("keep", encoding="utf-8")

    class StubNvidiaProvider:
        name = "nvidia:nvidia/llama-nemotron-embed-1b-v2"
        dimensions = 1024

        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", StubNvidiaProvider)

    provider = build_embedding_provider(
        "nvidia", "nvidia/llama-nemotron-embed-1b-v2", api_key="test"
    )

    assert provider.name == "nvidia:nvidia/llama-nemotron-embed-1b-v2"
    assert marker.read_text(encoding="utf-8") == "keep"


def test_auto_embedding_provider_can_bootstrap_with_hash(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("nvidia unavailable")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    provider = build_embedding_provider("auto", "nvidia/llama-nemotron-embed-1b-v2")

    assert isinstance(provider, HashEmbeddingProvider)


def test_auto_embedding_provider_honors_explicit_strict_quality(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("nvidia unavailable")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    with pytest.raises(RuntimeError, match="nvidia unavailable"):
        build_embedding_provider(
            "auto",
            "nvidia/llama-nemotron-embed-1b-v2",
            strict_quality=True,
        )


def test_local_neural_embedding_provider_is_not_supported() -> None:
    with pytest.raises(RuntimeError, match="Use nvidia, auto, or deterministic"):
        build_embedding_provider(
            "sentence-transformers",
            "unqualified-local-model",
        )


def test_reranker_defaults_to_passthrough() -> None:
    assert isinstance(build_reranker(), PassthroughReranker)


def test_local_neural_reranker_is_not_supported() -> None:
    with pytest.raises(RuntimeError, match="Use nvidia or passthrough"):
        build_reranker("unqualified-local-reranker", provider_name="local")


def test_nvidia_reranker_uses_remote_scores_without_real_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer nvidia-test-token"
        assert "passages" in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"rankings": [{"index": 1, "score": 0.91}, {"index": 0, "score": 0.12}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = NvidiaReranker(api_key="nvidia-test-token", http_client=client)
    results = [
        RagSearchResult(collection="c", doc_id="a", score=0.1, text="A", payload={}),
        RagSearchResult(collection="c", doc_id="b", score=0.2, text="B", payload={}),
    ]

    reranked = reranker.rerank("query", results, top_k=2)

    assert [result.doc_id for result in reranked] == ["b", "a"]
    assert reranker.status == "primary_nvidia_reranker"
    assert reranker.degraded_reason is None
    client.close()


def test_nvidia_reranker_is_unverified_before_first_provider_response() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    reranker = NvidiaReranker(api_key="nvidia-test-token", http_client=client)

    assert reranker.status == "configured_unverified"
    assert reranker.degraded_reason is None
    client.close()


def test_nvidia_reranker_missing_key_is_visible_passthrough() -> None:
    reranker = build_reranker(provider_name="nvidia", api_key=None)
    results = [RagSearchResult(collection="c", doc_id="a", score=0.1, text="A", payload={})]

    assert reranker.rerank("query", results, top_k=1) == results
    assert reranker.status == "degraded_passthrough"
    assert reranker.degraded_reason == "missing_nvidia_api_key"
