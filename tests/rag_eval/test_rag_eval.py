from pathlib import Path

from core.rag import RagService


def test_rag_eval_5g_lattice_tower_3_sectors(tmp_path: Path) -> None:
    service = _indexed_rag(tmp_path)

    results = service.search("5G lattice tower 3 sectors", limit=12)
    rule_results = service.search("5G lattice tower 3 sectors", collection="telecom_rules", limit=3)
    found = _result_blob(results)
    rules = _result_blob(rule_results)

    assert "5g lattice tower 30m with 3 sectors" in found
    assert "tower_lattice_30m" in found
    assert "sector count must match" in rules


def test_rag_eval_microwave_dish_on_lattice_tower(tmp_path: Path) -> None:
    service = _indexed_rag(tmp_path)

    results = service.search("microwave dish on lattice tower", limit=12)
    rule_results = service.search(
        "microwave dish on lattice tower",
        collection="telecom_rules",
        limit=3,
    )
    found = _result_blob(results)
    rules = _result_blob(rule_results)

    assert "ant_microwave_dish_001" in found
    assert "compatible_networks: mw" in found
    assert "microwave dish designs do not require rru assets unless explicitly requested" in rules


def test_rag_eval_small_cell_pole(tmp_path: Path) -> None:
    service = _indexed_rag(tmp_path)

    results = service.search("small cell pole", limit=12)
    found = _result_blob(results)

    assert "small-cell pole" in found or "small-cell poles" in found
    assert "tower_small_cell_10m" in found
    assert "small_cell_pole" in found


def _indexed_rag(tmp_path: Path) -> RagService:
    service = RagService(project_root=Path.cwd(), qdrant_path=tmp_path / "qdrant")
    service.reindex()
    return service


def _result_blob(results) -> str:
    return "\n".join(
        [
            result.text.lower()
            + "\n"
            + "\n".join(f"{key}: {value}".lower() for key, value in result.payload.items())
            for result in results
        ]
    )
