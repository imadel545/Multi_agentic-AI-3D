from pathlib import Path

from core.rag import RagService


def test_rag_reindex_and_search_returns_context(tmp_path: Path) -> None:
    service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
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
