import json
import shutil
from pathlib import Path

from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry


def test_asset_inventory_reports_present_and_missing_glb_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    inventory = AssetInventoryService(Path.cwd(), registry).inspect()

    assert inventory["asset_count"] == 12
    assert inventory["status"] == "qualified_mixed_catalog"
    assert inventory["missing_file_count"] == 0
    assert inventory["real_glb_asset_count"] == 12
    assert inventory["import_ready_asset_count"] == 4
    assert inventory["import_qualified_glb_count"] == 4
    assert inventory["generation_eligible_asset_count"] == 10
    assert inventory["reference_only_asset_count"] == 2
    assert inventory["qualified_integrity_failure_count"] == 0
    assert inventory["procedural_fallback_count"] == 0
    assert inventory["parametric_generation_count"] == 6
    assert inventory["procedural_generation_required"] is True
    entries_by_id = {entry["asset_id"]: entry for entry in inventory["entries"]}
    assert entries_by_id["TOWER_LATTICE_30M"]["asset_file_exists"] is True
    assert entries_by_id["TOWER_LATTICE_30M"]["asset_import_mode"] == "parametric_generated"
    assert entries_by_id["TOWER_LATTICE_30M"]["generation_eligible"] is True
    assert entries_by_id["TOWER_LATTICE_30M"]["source"] == "cc_by"
    assert entries_by_id["TOWER_LATTICE_30M"]["attribution_required"] is True
    assert "ATTRIBUTION_REQUIRED" in entries_by_id["TOWER_LATTICE_30M"]["warnings"]
    assert "CC_BY_ASSET_NOT_VENDOR_GRADE" in entries_by_id["TOWER_LATTICE_30M"]["warnings"]
    assert entries_by_id["ANT_PANEL_4G_001"]["asset_file_exists"] is True
    assert entries_by_id["ANT_PANEL_4G_001"]["source"] == "internal_cleaned"
    assert (
        "INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE" in entries_by_id["ANT_PANEL_4G_001"]["warnings"]
    )
    assert entries_by_id["POWER_CABINET_001"]["asset_file_exists"] is True
    assert entries_by_id["GPS_ANTENNA_001"]["asset_file_exists"] is True
    assert entries_by_id["ANT_PANEL_5G_001"]["asset_file_exists"] is True
    assert entries_by_id["ANT_PANEL_5G_001"]["asset_import_mode"] == "parametric_generated"
    assert entries_by_id["ANT_PANEL_5G_001"]["source"] == "internal_test_minimal"
    assert (
        "INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE"
        in entries_by_id["ANT_PANEL_5G_001"]["warnings"]
    )
    assert entries_by_id["RRU_SMALL_001"]["asset_file_exists"] is True
    assert entries_by_id["TOWER_MONOPOLE_30M"]["asset_file_exists"] is True
    assert entries_by_id["TOWER_MONOPOLE_30M"]["asset_import_mode"] == "parametric_generated"
    assert entries_by_id["TOWER_MONOPOLE_30M"]["effective_generation_mode"] == (
        "parametric_generated"
    )
    assert entries_by_id["TOWER_MONOPOLE_30M"]["source"] == "internal_project_generated"
    assert (
        "INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE"
        in entries_by_id["TOWER_MONOPOLE_30M"]["warnings"]
    )
    assert entries_by_id["TOWER_ROOFTOP_12M"]["asset_file_exists"] is True
    assert entries_by_id["TOWER_SMALL_CELL_10M"]["asset_file_exists"] is True
    assert entries_by_id["ANT_PANEL_4G_001"]["asset_import_mode"] == "imported_glb_exact"
    assert entries_by_id["ANT_PANEL_4G_001"]["qualified_file_hash_matches"] is True
    assert entries_by_id["GPS_ANTENNA_001"]["asset_import_mode"] == "imported_glb_exact"
    assert entries_by_id["POWER_CABINET_001"]["asset_import_mode"] == "imported_glb_exact"
    assert entries_by_id["CABLE_TRAY_001"]["asset_import_mode"] == "reference_only"
    assert entries_by_id["CABLE_TRAY_001"]["generation_eligible"] is False


def test_asset_inventory_rejects_a_changed_qualified_glb(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "assets" / "manifests"
    asset_dir = tmp_path / "assets" / "antennas"
    manifests_dir.mkdir(parents=True)
    asset_dir.mkdir(parents=True)
    source_manifest = Path("assets/manifests/ANT_PANEL_4G_001.json")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    target_asset = asset_dir / "ant_panel_4g_001.glb"
    shutil.copy2(Path(manifest["file"]), target_asset)
    with target_asset.open("ab") as stream:
        stream.write(b"changed-after-qualification")
    (manifests_dir / source_manifest.name).write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    inventory = AssetInventoryService(tmp_path, AssetRegistry(manifests_dir)).inspect()

    entry = inventory["entries"][0]
    assert inventory["status"] == "qualification_error"
    assert inventory["qualified_integrity_failure_count"] == 1
    assert entry["asset_import_mode"] == "qualified_file_rejected"
    assert entry["generation_eligible"] is False
    assert entry["qualified_file_hash_matches"] is False
    assert "QUALIFIED_ASSET_HASH_MISMATCH" in entry["warnings"]
