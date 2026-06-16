from pathlib import Path

import pytest

from core.rag import RagService
from core.rag.documents import load_rag_documents
from core.rag.embeddings import HashEmbeddingProvider, build_embedding_provider
from core.rag.reranker import PassthroughReranker, build_reranker


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


def test_nvidia_embedding_provider_is_strict_when_configured(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("missing nvidia key")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    with pytest.raises(RuntimeError, match="NVIDIA API embedding provider is required"):
        build_embedding_provider("nvidia", "baai/bge-m3")


def test_auto_embedding_provider_can_bootstrap_with_hash(monkeypatch) -> None:
    class FailingNvidiaProvider:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("nvidia unavailable")

    monkeypatch.setattr("core.rag.embeddings.NvidiaEmbeddingProvider", FailingNvidiaProvider)

    provider = build_embedding_provider("auto", "baai/bge-m3")

    assert isinstance(provider, HashEmbeddingProvider)


def test_reranker_defaults_to_passthrough() -> None:
    assert isinstance(build_reranker(), PassthroughReranker)
