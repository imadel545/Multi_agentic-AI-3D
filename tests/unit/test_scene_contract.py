import pytest
from pydantic import ValidationError

from apps.blender_worker.generate_scene import _camera_view_direction
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec
from core.contracts.tower import TowerAccessGeometryProfile, TowerCharacteristics


def _scene_payload() -> dict:
    return SceneSpec(
        scene_id="wf_contract",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="antenna",
                install_height_m=24,
                azimuth_deg=0,
                beamwidth_deg=65,
            )
        ],
    ).model_dump()


@pytest.mark.parametrize("field,value", [("position", [1, 0, 0]), ("rotation_deg", [0, 0, 5])])
def test_scene_rejects_silently_ignored_tower_transforms(field: str, value: list[int]) -> None:
    payload = _scene_payload()
    payload["tower"][field] = value

    with pytest.raises(ValidationError, match=f"tower.{field}"):
        SceneSpec.model_validate(payload)


def test_scene_rejects_unimplemented_gltf_export() -> None:
    payload = _scene_payload()
    payload["export"]["formats"] = ["gltf", "png", "json_report"]

    with pytest.raises(ValidationError, match="gltf export is not operational"):
        SceneSpec.model_validate(payload)


def test_scene_rejects_unknown_schema_and_non_finite_geometry() -> None:
    payload = _scene_payload()
    payload["schema_version"] = "3.0.0"
    with pytest.raises(ValidationError, match="1.0.0|2.0.0"):
        SceneSpec.model_validate(payload)

    payload = _scene_payload()
    payload["sectors"][0]["beam_radius_m"] = float("inf")
    with pytest.raises(ValidationError, match="finite number"):
        SceneSpec.model_validate(payload)


def test_legacy_scene_without_detail_level_defaults_to_high() -> None:
    payload = _scene_payload()
    payload.pop("detail_level")

    scene = SceneSpec.model_validate(payload)

    assert scene.detail_level == "high"


def test_tower_access_levels_derive_legacy_count_without_changing_legacy_scene_shape() -> None:
    characteristics = TowerCharacteristics(
        structure="lattice",
        platform_levels_m=[12.0, 24.0],
    )

    assert characteristics.has_platform is True
    assert characteristics.platform_count == 2
    assert characteristics.platform_levels_m == [12.0, 24.0]

    legacy_payload = _scene_payload()
    assert "platform_levels_m" not in legacy_payload["tower"]["characteristics"]
    assert "tower_access_geometry_profile" not in legacy_payload["tower"]


def test_tower_access_contract_rejects_conflicting_levels_and_out_of_bounds_scene_level() -> None:
    with pytest.raises(ValidationError, match="platform_levels_m must be empty"):
        TowerCharacteristics(
            structure="lattice",
            has_platform=False,
            platform_levels_m=[12.0],
        )

    with pytest.raises(ValidationError, match="platform_count must match"):
        TowerCharacteristics(
            structure="lattice",
            has_platform=True,
            platform_count=1,
            platform_levels_m=[12.0, 24.0],
        )

    with pytest.raises(ValidationError, match="below tower height_m"):
        SceneAssetPlacement(
            asset_id="tower",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
            characteristics=TowerCharacteristics(
                structure="lattice",
                platform_levels_m=[30.0],
            ),
        )


def test_scene_tower_carries_only_a_lattice_access_profile() -> None:
    profile = TowerAccessGeometryProfile()
    placement = SceneAssetPlacement(
        asset_id="tower",
        position=[0, 0, 0],
        rotation_deg=[0, 0, 0],
        height_m=30,
        characteristics=TowerCharacteristics(structure="lattice"),
        tower_access_geometry_profile=profile,
    )

    assert placement.tower_access_geometry_profile == profile

    with pytest.raises(ValidationError, match="requires a lattice tower"):
        SceneAssetPlacement(
            asset_id="tower",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
            characteristics=TowerCharacteristics(structure="monopole", leg_count=1),
            tower_access_geometry_profile=profile,
        )


def test_scene_rejects_duplicate_sector_ids() -> None:
    payload = _scene_payload()
    payload["sectors"].append({**payload["sectors"][0], "azimuth_deg": 120})

    with pytest.raises(ValidationError, match="sector_id values must be unique"):
        SceneSpec.model_validate(payload)


def test_preview_camera_modes_have_distinct_operational_directions() -> None:
    directions = {mode: _camera_view_direction(mode) for mode in ("isometric", "front", "top")}

    assert len(set(directions.values())) == 3
    assert directions["top"] == (0.0, 0.0, 1.0)
