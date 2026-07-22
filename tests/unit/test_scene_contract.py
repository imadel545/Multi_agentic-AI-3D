import pytest
from pydantic import ValidationError

from apps.blender_worker.generate_scene import _camera_view_direction
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec


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


def test_preview_camera_modes_have_distinct_operational_directions() -> None:
    directions = {mode: _camera_view_direction(mode) for mode in ("isometric", "front", "top")}

    assert len(set(directions.values())) == 3
    assert directions["top"] == (0.0, 0.0, 1.0)
