from pathlib import Path

from core.contracts.assets import DimensionsM
from core.contracts.scene import SceneAccessoryPlacement, SceneAssetPlacement, SectorSpec
from core.parametric.resolver import ParametricModelResolver
from core.services.asset_registry import AssetRegistry


def _resolver() -> ParametricModelResolver:
    return ParametricModelResolver(AssetRegistry(Path("assets/manifests")))


def test_resolver_never_imports_unqualified_companion_tower_glb() -> None:
    strategy, source, reason, warnings = _resolver().resolve_tower(
        SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            dimensions_m=DimensionsM(width=4.0, depth=4.0, height=30.0),
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=30.0,
        )
    )

    assert strategy == "parametric_generated"
    assert source == "parametric_generated"
    assert "qualified parametric tower profile" in reason
    assert warnings == []


def test_resolver_uses_only_manifest_authorized_component_modes() -> None:
    resolver = _resolver()
    qualified_import = SectorSpec(
        sector_id="S1",
        antenna_asset_id="ANT_PANEL_4G_001",
        antenna_dimensions_m=DimensionsM(width=0.42, depth=0.169, height=1.4),
        install_height_m=24.0,
        azimuth_deg=0.0,
        beamwidth_deg=65.0,
    )
    qualified_parametric = qualified_import.model_copy(
        update={
            "antenna_asset_id": "ANT_PANEL_5G_001",
            "antenna_dimensions_m": DimensionsM(width=0.45, depth=0.18, height=1.6),
        }
    )

    imported = resolver.resolve_sector_component(qualified_import, "antenna")
    generated = resolver.resolve_sector_component(qualified_parametric, "antenna")

    assert imported[:2] == ("imported_glb_exact", "imported_glb_exact")
    assert generated[:2] == (
        "internal_project_generated",
        "internal_project_generated",
    )


def test_resolver_quarantines_reference_only_accessory_from_generation() -> None:
    strategy, source, reason, warnings = _resolver().resolve_accessory(
        SceneAccessoryPlacement(
            asset_id="MOUNTING_BRACKET_001",
            asset_type="bracket",
            dimensions_m=DimensionsM(width=0.8, depth=0.18, height=0.18),
            position=[1.0, 0.0, 3.0],
            rotation_deg=[0.0, 0.0, 0.0],
        )
    )

    assert strategy == "procedural_fallback"
    assert source == "degraded"
    assert "not qualified" in reason
    assert warnings == ["ACCESSORY_ASSET_NOT_GENERATION_QUALIFIED:MOUNTING_BRACKET_001"]
