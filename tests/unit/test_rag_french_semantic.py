"""Deterministic unit tests for French telecom RAG and NVIDIA provider metadata."""

from pathlib import Path

from core.rag import RagService
from core.rag.embeddings import DEFAULT_MODEL, HashEmbeddingProvider, NvidiaEmbeddingProvider


def test_french_query_finds_lattice_tower_assets_without_network(tmp_path: Path) -> None:
    provider = HashEmbeddingProvider()
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=provider,
    )
    service.reindex()

    results = service.search("pylône treillis pour antennes 5G", limit=5)

    assert results
    # Project documents/manifests carry enough French telecom vocabulary for a
    # deterministic unit test. BGE-M3 quality belongs to an explicit live test.
    assert any(
        "treillis" in result.text.lower()
        or result.payload.get("asset_id") == "TOWER_LATTICE_30M"
        or "lattice" in result.text.lower()
        for result in results
    )


def test_embedding_provider_is_nvidia_bge_m3_without_network() -> None:
    provider = NvidiaEmbeddingProvider(DEFAULT_MODEL, api_key="unit-test-key")

    assert "nvidia" in provider.name
    assert "bge-m3" in provider.name
    assert provider.dimensions == 1024
