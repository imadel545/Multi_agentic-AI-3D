import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.contracts.assets import AssetManifest, AssetQualification
from core.services.asset_registry import AssetRegistry, _candidate_score


def test_registry_loads_and_selects_5g_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    tower = registry.select_tower("lattice_tower", "5G", 30)
    antenna = registry.select_asset("antenna", "5G", "lattice_tower")
    radio = registry.select_asset("radio", "5G", "lattice_tower")

    assert tower.asset_id == "TOWER_LATTICE_30M"
    assert antenna.asset_id == "ANT_PANEL_5G_001"
    assert radio.asset_id == "RRU_SMALL_001"
    assert antenna.geometry_fidelity == "technical_generic"
    assert radio.geometry_fidelity == "technical_generic"


def test_asset_manifest_defaults_to_schematic_geometry_fidelity() -> None:
    manifest = AssetManifest(
        asset_id="TEST_SCHEMATIC",
        type="radio",
        file="assets/test.glb",
        compatible_networks=["5G"],
    )

    assert manifest.geometry_fidelity == "schematic"


def test_asset_manifest_rejects_unknown_geometry_fidelity() -> None:
    with pytest.raises(ValidationError):
        AssetManifest(
            asset_id="TEST_UNKNOWN_FIDELITY",
            type="radio",
            file="assets/test.glb",
            compatible_networks=["5G"],
            geometry_fidelity="marketing_grade",
        )


def test_exact_import_qualification_requires_all_geometry_proofs() -> None:
    with pytest.raises(ValidationError, match="all geometry checks"):
        AssetQualification(
            status="qualified_for_generation",
            allowed_generation_modes=["imported_glb_exact"],
            verified_file_sha256="a" * 64,
            mesh_integrity_verified=True,
            dimensions_verified=True,
            pivot_verified=False,
            orientation_verified=True,
        )


def test_registry_exposes_only_qualified_generation_candidates() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    selected = registry.select_asset("antenna", "4G", "lattice_tower")
    bracket = registry.get("MOUNTING_BRACKET_001")

    assert selected.asset_id == "ANT_PANEL_4G_001"
    assert selected.allows_generation_mode("imported_glb_exact") is True
    assert bracket.is_generation_eligible is True
    assert bracket.builder_profile_id == "mount_bracket_v1"


def test_registry_refuses_unverified_vendor_claim_from_selection_and_snapshot(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifests_dir = project_root / "assets" / "manifests"
    asset_dir = project_root / "assets" / "antennas"
    manifests_dir.mkdir(parents=True)
    asset_dir.mkdir(parents=True)
    payload = json.loads(
        Path("assets/manifests/ANT_PANEL_4G_001.json").read_text(encoding="utf-8")
    )
    payload.update(
        {
            "asset_id": "UNVERIFIED_VENDOR_PANEL",
            "source": "vendor_supplied",
            "manufacturer": "Unverified manufacturer",
            "reference": "UNVERIFIED-001",
            "geometry_fidelity": "vendor_qualified",
        }
    )
    (manifests_dir / "UNVERIFIED_VENDOR_PANEL.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    shutil.copy2(Path(payload["file"]), project_root / payload["file"])
    registry = AssetRegistry(manifests_dir)
    manifest = registry.get("UNVERIFIED_VENDOR_PANEL")

    assert manifest.is_generation_eligible is True
    assert registry.is_generation_admitted(manifest) is False
    with pytest.raises(LookupError, match="no validated antenna asset"):
        registry.select_asset("antenna", "4G", "lattice_tower")
    with pytest.raises(ValueError, match="ASSET_GENERATION_NOT_ADMITTED"):
        registry.manifest_snapshot(
            manifest.asset_id,
            generation_mode="imported_glb_exact",
        )


def test_candidate_scoring_prioritizes_declared_vendor_fidelity() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    base = registry.get("ANT_PANEL_4G_001")
    schematic = base.model_copy(
        update={"asset_id": "ANT_SCHEMATIC", "geometry_fidelity": "schematic"}
    )
    vendor = base.model_copy(
        update={"asset_id": "ANT_VENDOR", "geometry_fidelity": "vendor_qualified"}
    )

    schematic_score = _candidate_score(
        schematic,
        network_type="4G",
        tower_type="lattice_tower",
        min_height_m=None,
    )
    vendor_score = _candidate_score(
        vendor,
        network_type="4G",
        tower_type="lattice_tower",
        min_height_m=None,
    )

    assert vendor_score.total_score > schematic_score.total_score
    assert vendor_score.fidelity_score == 100.0
    assert schematic_score.fidelity_score == 35.0
    assert "géométrie fournisseur qualifiée" in vendor_score.reasons
