from pathlib import Path

from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry


def test_asset_inventory_reports_present_and_missing_glb_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    inventory = AssetInventoryService(Path.cwd(), registry).inspect()

    assert inventory["asset_count"] == 8
    assert inventory["status"] == "partial_import_ready"
    assert inventory["missing_file_count"] == 6
    assert inventory["real_glb_asset_count"] == 2
    assert inventory["import_ready_asset_count"] == 2
    assert inventory["procedural_fallback_count"] == 6
    assert inventory["procedural_generation_required"] is True
    entries_by_id = {entry["asset_id"]: entry for entry in inventory["entries"]}
    assert entries_by_id["ANT_PANEL_5G_001"]["asset_file_exists"] is True
    assert entries_by_id["ANT_PANEL_5G_001"]["asset_import_mode"] == "imported_glb"
    assert entries_by_id["ANT_PANEL_5G_001"]["source"] == "internal_test_minimal"
    assert (
        "INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE"
        in entries_by_id["ANT_PANEL_5G_001"]["warnings"]
    )
    assert entries_by_id["RRU_SMALL_001"]["asset_file_exists"] is True
    assert entries_by_id["TOWER_LATTICE_30M"]["asset_file_exists"] is False
    assert entries_by_id["TOWER_LATTICE_30M"]["effective_generation_mode"] == (
        "procedural_fallback"
    )
