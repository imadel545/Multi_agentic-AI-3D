import pytest

from core.contracts.adaptation import ResolvedAdaptationCapability, SceneAdaptationCapabilities
from core.services.exact_asset_edit import fallback_rigid_patch


def _capabilities(*asset_ids: str) -> SceneAdaptationCapabilities:
    capabilities = []
    for index, asset_id in enumerate(asset_ids):
        program_index = index
        for field, axes, maximum in (
            ("translation_m", "xyz", 100.0),
            ("rotation_deg", "xz", 360.0),
        ):
            for axis in axes:
                capabilities.append(
                    ResolvedAdaptationCapability(
                        capability_id=f"geometry_program_{program_index + 1}:{field}_{axis}",
                        asset_id=asset_id,
                        profile_id="catalog_rigid_placement_v1",
                        label=(
                            f"{'Position' if field == 'translation_m' else 'Rotation'} "
                            f"{axis.upper()} de {asset_id}"
                        ),
                        path=(
                            f"/geometry_programs/{program_index}/nodes/0/transform/"
                            f"{field}/{axis}"
                        ),
                        value_type="number",
                        execution_tool="asset_transform",
                        effect="placement",
                        description="bounded exact asset pose",
                        unit="m" if field == "translation_m" else "deg",
                        minimum=-maximum,
                        maximum=maximum,
                    )
                )
    return SceneAdaptationCapabilities(
        scene_id="test",
        catalog_version="1.0.0",
        catalog_hash="catalog",
        capabilities=capabilities,
    )


def test_exact_asset_fallback_parses_axis_pairs_and_keeps_source_immutable() -> None:
    patch = fallback_rigid_patch(
        "Déplace le panneau à x=1,2 m, y=-0,4 m et tourne z à 15 degrés",
        _capabilities("ANT_PANEL_4G_001"),
        "groq unavailable",
    )

    assert patch is not None
    assert patch.adaptation_tools == ["asset_transform"]
    assert [(operation.path, operation.value) for operation in patch.operations] == [
        (
            "/geometry_programs/0/nodes/0/transform/translation_m/x",
            1.2,
        ),
        (
            "/geometry_programs/0/nodes/0/transform/translation_m/y",
            -0.4,
        ),
        (
            "/geometry_programs/0/nodes/0/transform/rotation_deg/z",
            15.0,
        ),
    ]


def test_exact_asset_fallback_rejects_unauthorized_axis() -> None:
    with pytest.raises(ValueError, match="axe Y"):
        fallback_rigid_patch(
            "tourne le panneau sur y à 15 degrés",
            _capabilities("ANT_PANEL_4G_001"),
            "groq unavailable",
        )


def test_exact_asset_fallback_accepts_value_before_axis() -> None:
    patch = fallback_rigid_patch(
        "positionne le panneau 1,2 m sur x et -0,4 m sur y",
        _capabilities("ANT_PANEL_4G_001"),
        "groq unavailable",
    )

    assert patch is not None
    assert [(operation.path, operation.value) for operation in patch.operations] == [
        (
            "/geometry_programs/0/nodes/0/transform/translation_m/x",
            1.2,
        ),
        (
            "/geometry_programs/0/nodes/0/transform/translation_m/y",
            -0.4,
        ),
    ]


def test_exact_asset_fallback_keeps_vector_units_on_their_declared_field() -> None:
    patch = fallback_rigid_patch(
        "déplace le panneau [1,2,3] m et tourne z à 6 degrés",
        _capabilities("ANT_PANEL_4G_001"),
        "groq unavailable",
    )

    assert patch is not None
    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/geometry_programs/0/nodes/0/transform/translation_m/x", 1.0),
        ("/geometry_programs/0/nodes/0/transform/translation_m/y", 2.0),
        ("/geometry_programs/0/nodes/0/transform/translation_m/z", 3.0),
        ("/geometry_programs/0/nodes/0/transform/rotation_deg/z", 6.0),
    ]


def test_exact_asset_fallback_refuses_mixed_unitless_pose_request() -> None:
    assert (
        fallback_rigid_patch(
            "déplace le panneau à x=1 et tourne z=15",
            _capabilities("ANT_PANEL_4G_001"),
            "groq unavailable",
        )
        is None
    )


def test_exact_asset_fallback_refuses_ambiguous_component() -> None:
    assert (
        fallback_rigid_patch(
            "déplace le composant à x=1 m",
            _capabilities("ANT_PANEL_4G_001", "ANT_PANEL_5G_001"),
            "groq unavailable",
        )
        is None
    )
