import json
from pathlib import Path

import httpx
import pytest

from core.rag import RagService
from core.rag.documents import load_rag_documents
from core.rag.embeddings import HashEmbeddingProvider, build_embedding_provider
from core.rag.models import RagSearchResult
from core.rag.reranker import NvidiaReranker, PassthroughReranker, build_reranker
from core.rag.text import normalized_tokens


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
        build_embedding_provider("nvidia", "baai/bge-m3")


def test_nvidia_embedding_provider_never_deletes_user_model_cache(
    tmp_path: Path, monkeypatch
) -> None:
    cache_dir = tmp_path / "hub" / "models--BAAI--bge-m3"
    cache_dir.mkdir(parents=True)
    marker = cache_dir / "user-owned-cache"
    marker.write_text("keep", encoding="utf-8")

    class StubNvidiaProvider:
        name = "nvidia:baai/bge-m3"
        dimensions = 1024

        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", StubNvidiaProvider)

    provider = build_embedding_provider("nvidia", "baai/bge-m3", api_key="test")

    assert provider.name == "nvidia:baai/bge-m3"
    assert marker.read_text(encoding="utf-8") == "keep"


def test_auto_embedding_provider_can_bootstrap_with_hash(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("nvidia unavailable")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    provider = build_embedding_provider("auto", "baai/bge-m3")

    assert isinstance(provider, HashEmbeddingProvider)


def test_auto_embedding_provider_honors_explicit_strict_quality(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("nvidia unavailable")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    with pytest.raises(RuntimeError, match="nvidia unavailable"):
        build_embedding_provider(
            "auto",
            "baai/bge-m3",
            strict_quality=True,
        )


def test_reranker_defaults_to_passthrough() -> None:
    assert isinstance(build_reranker(), PassthroughReranker)


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


def test_nvidia_reranker_missing_key_is_visible_passthrough() -> None:
    reranker = build_reranker(provider_name="nvidia", api_key=None)
    results = [RagSearchResult(collection="c", doc_id="a", score=0.1, text="A", payload={})]

    assert reranker.rerank("query", results, top_k=1) == results
    assert reranker.status == "degraded_passthrough"
    assert reranker.degraded_reason == "missing_nvidia_api_key"
