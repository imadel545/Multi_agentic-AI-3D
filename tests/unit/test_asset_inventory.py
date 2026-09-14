import json
import shutil
from pathlib import Path

from core.services.asset_evidence import ProfessionalAssetVerifier
from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry


def test_asset_inventory_reports_present_and_missing_glb_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    inventory = AssetInventoryService(Path.cwd(), registry).inspect()

    entries = inventory["entries"]
    assert inventory["asset_count"] == len(entries)
    assert inventory["status"] == "qualified_mixed_catalog"
    assert inventory["missing_file_count"] == 0
    assert inventory["real_glb_asset_count"] == sum(entry["asset_file_exists"] for entry in entries)
    assert inventory["import_ready_asset_count"] == sum(
        entry["asset_import_mode"] == "imported_glb_exact" and entry["asset_file_exists"]
        for entry in entries
    )
    assert inventory["import_qualified_glb_count"] == sum(
        entry["asset_import_mode"] == "imported_glb_exact" and entry["generation_eligible"]
        for entry in entries
    )
    assert inventory["generation_eligible_asset_count"] == sum(
        entry["generation_eligible"] for entry in entries
    )
    assert inventory["professional_evidence_asset_count"] == 0
    assert all(not entry["milestone_evidence_eligible"] for entry in entries)
    assert all(entry["milestone_evidence_failures"] for entry in entries)
    assert inventory["reference_only_asset_count"] == sum(
        entry["asset_import_mode"] == "reference_only" for entry in entries
    )
    assert inventory["qualified_integrity_failure_count"] == 0
    assert inventory["procedural_fallback_count"] == 0
    assert inventory["parametric_generation_count"] == sum(
        entry["asset_import_mode"] == "parametric_generated" for entry in entries
    )
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
    assert entries_by_id["POWER_CABINET_001"]["asset_import_mode"] == "parametric_generated"
    assert entries_by_id["CABLE_TRAY_001"]["asset_import_mode"] == "parametric_generated"
    assert entries_by_id["CABLE_TRAY_001"]["generation_eligible"] is True
    assert entries_by_id["ANT_PANEL_5G_DUALBAND_V1"]["asset_file_required"] is False
    assert "ASSET_FILE_MISSING" not in entries_by_id["ANT_PANEL_5G_DUALBAND_V1"]["warnings"]


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


def test_asset_inventory_removes_modes_from_unproved_professional_claim(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    manifests_dir = tmp_path / "catalog-override"
    asset_dir = project_root / "assets" / "antennas"
    manifests_dir.mkdir(parents=True)
    asset_dir.mkdir(parents=True)
    manifest = json.loads(
        Path("assets/manifests/ANT_PANEL_4G_001.json").read_text(encoding="utf-8")
    )
    manifest.update(
        {
            "asset_id": "UNPROVED_VENDOR_PANEL",
            "source": "vendor_supplied",
            "manufacturer": "Unverified manufacturer",
            "reference": "UNVERIFIED-001",
            "geometry_fidelity": "vendor_qualified",
        }
    )
    (manifests_dir / "UNPROVED_VENDOR_PANEL.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    shutil.copy2(Path(manifest["file"]), project_root / manifest["file"])
    verifier = ProfessionalAssetVerifier(project_root)
    registry = AssetRegistry(manifests_dir, evidence_verifier=verifier)

    inventory = AssetInventoryService(project_root, registry).inspect()

    entry = inventory["entries"][0]
    assert registry.evidence_verifier is verifier
    assert inventory["generation_eligible_asset_count"] == 0
    assert inventory["import_ready_asset_count"] == 0
    assert inventory["status"] == "qualification_error"
    assert inventory["professional_evidence_rejected_count"] == 1
    assert entry["generation_eligible"] is False
    assert entry["asset_import_mode"] == "professional_evidence_rejected"
    assert entry["effective_generation_mode"] == "quarantined_unverified"
    assert entry["allowed_generation_modes"] == []
    assert "PROFESSIONAL_ASSET_EVIDENCE_NOT_ADMITTED" in entry["warnings"]


def test_reference_manifest_without_local_quarantine_reports_missing_evidence(
    tmp_path: Path,
) -> None:
    manifests_dir = tmp_path / "assets" / "manifests"
    manifests_dir.mkdir(parents=True)
    source = Path("assets/manifests/ANT_SIERRA_6001124_REFERENCE.json")
    shutil.copy2(source, manifests_dir / source.name)

    inventory = AssetInventoryService(tmp_path, AssetRegistry(manifests_dir)).inspect()
    entry = inventory["entries"][0]

    assert inventory["reference_evidence_missing_count"] == 1
    assert entry["generation_eligible"] is False
    assert entry["reference_evidence_available"] is False
    assert entry["local_evidence_status"] == "unavailable"
    assert all(preview["available"] is False for preview in entry["preview_set"])


def test_opencellular_chassis_reference_cannot_enter_generation() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    manifest = registry.get("RADIO_OPENCELLULAR_CONNECT1_CHASSIS_REF")
    entry = AssetInventoryService(Path.cwd(), registry).inspect_asset(
        "RADIO_OPENCELLULAR_CONNECT1_CHASSIS_REF"
    )

    local_source = Path(manifest.master_representation.file)
    if local_source.is_file():
        assert entry["local_evidence_status"] == "available"
        assert entry["asset_file_exists"] is True
        assert all(preview["available"] for preview in entry["preview_set"])
    else:
        assert entry["local_evidence_status"] == "unavailable"
        assert entry["asset_file_exists"] is False
        assert all(not preview["available"] for preview in entry["preview_set"])
    assert entry["qualification_status"] == "reference_only"
    assert entry["asset_import_mode"] == "reference_only"
    assert entry["generation_eligible"] is False
    assert entry["allowed_generation_modes"] == []
    assert registry.is_generation_admitted(manifest) is False


def test_asset_inventory_does_not_publish_or_read_outside_root_paths(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "assets" / "manifests"
    manifests_dir.mkdir(parents=True)
    manifest = json.loads(
        Path("assets/manifests/ANT_PANEL_5G_DUALBAND_V1.json").read_text(encoding="utf-8")
    )
    manifest["asset_id"] = "OUTSIDE_PATH_ASSET"
    manifest["file"] = "/private/catalog/hidden.glb"
    manifest["qualification"] = {
        "status": "quarantined_unverified",
        "allowed_generation_modes": [],
    }
    (manifests_dir / "OUTSIDE_PATH_ASSET.json").write_text(json.dumps(manifest), encoding="utf-8")

    entry = AssetInventoryService(tmp_path, AssetRegistry(manifests_dir)).inspect()["entries"][0]

    assert entry["file"] == "hidden.glb"
    assert entry["asset_file_exists"] is False
