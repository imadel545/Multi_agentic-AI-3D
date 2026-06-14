"""Semantic RAG tests for French telecom queries using NVIDIA BAAI/bge-m3."""

from pathlib import Path

from core.rag import RagService
from core.rag.embeddings import EmbeddingProvider


def test_french_query_finds_lattice_tower_assets(
    nvidia_embedding_provider: EmbeddingProvider, tmp_path: Path
) -> None:
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider=nvidia_embedding_provider,
    )
    service.reindex()

    results = service.search("pylône treillis pour antennes 5G", limit=5)

    assert results
    # bge-m3 should understand the French paraphrase and rank the lattice tower high.
    assert any(
        "treillis" in result.text.lower()
        or result.payload.get("asset_id") == "TOWER_LATTICE_30M"
        or "lattice" in result.text.lower()
        for result in results
    )


def test_embedding_provider_is_nvidia_bge_m3(nvidia_embedding_provider: EmbeddingProvider) -> None:
    assert "nvidia" in nvidia_embedding_provider.name
    assert "bge-m3" in nvidia_embedding_provider.name
    assert nvidia_embedding_provider.dimensions == 1024
