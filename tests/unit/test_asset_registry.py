from pathlib import Path

import pytest
from pydantic import ValidationError

from core.contracts.assets import AssetManifest, AssetQualification
from core.services.asset_registry import AssetRegistry


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
    reference_only = registry.get("MOUNTING_BRACKET_001")

    assert selected.asset_id == "ANT_PANEL_4G_001"
    assert selected.allows_generation_mode("imported_glb_exact") is True
    assert reference_only.is_generation_eligible is False
