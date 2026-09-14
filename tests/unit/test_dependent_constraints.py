from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.services.dependent_constraints import (
    derive_dependent_operations,
    edit_failure_user_text,
    with_dependent_operations,
)
from core.services.patch_applier import PatchApplier


def _scene() -> SceneSpec:
    return SceneSpec(
        scene_id="wf_test",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower_01",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=42,
        ),
        sectors=[
            SectorSpec(
                sector_id=f"S{index + 1}",
                antenna_asset_id="ant_01",
                install_height_m=height,
                azimuth_deg=azimuth,
                mechanical_tilt_deg=3,
                beamwidth_deg=65,
            )
            for index, (height, azimuth) in enumerate([(38, 0), (38, 120), (12, 240)])
        ],
        visual_elements=VisualElements(),
    )


def _lower_tower(scene: SceneSpec, height: float) -> ScenePatch:
    return ScenePatch(
        edit_description="lower the tower",
        operations=[PatchOperation(path="/tower/height_m", value=height)],
    )


def test_lowering_the_tower_carries_mounted_sectors_with_it() -> None:
    scene = _scene()
    assert scene.tower is not None and scene.sectors
    original_height = scene.tower.height_m
    highest = max(sector.install_height_m for sector in scene.sectors)
    new_height = round(highest / 2, 1)
    derived = derive_dependent_operations(scene, _lower_tower(scene, new_height))
    affected = [s for s in scene.sectors if s.install_height_m > new_height]
    assert len(derived.operations) == len(affected)
    assert derived.assumptions and all("sous le sommet" in a for a in derived.assumptions)
    for op, sector in zip(derived.operations, affected, strict=True):
        assert op.value <= new_height
        expected_offset = original_height - sector.install_height_m
        assert abs((new_height - op.value) - expected_offset) < 1e-6 or op.value == 1.0
    patched, report = PatchApplier().apply(
        scene, with_dependent_operations(scene, _lower_tower(scene, new_height))
    )
    assert report.status != "failed"
    assert patched is not None and patched.tower is not None
    assert patched.tower.height_m == new_height
    assert all(s.install_height_m <= new_height for s in patched.sectors)


def test_raising_the_tower_derives_nothing() -> None:
    scene = _scene()
    assert scene.tower is not None
    derived = derive_dependent_operations(scene, _lower_tower(scene, scene.tower.height_m + 5))
    assert derived.operations == [] and derived.assumptions == []


def test_explicit_sector_height_is_not_overridden() -> None:
    scene = _scene()
    assert scene.tower is not None and scene.sectors
    new_height = round(scene.tower.height_m / 3, 1)
    patch = ScenePatch(
        edit_description="lower everything",
        operations=[
            PatchOperation(path="/tower/height_m", value=new_height),
            PatchOperation(path="/sectors/0/install_height_m", value=max(new_height - 1, 1.0)),
        ],
    )
    derived = derive_dependent_operations(scene, patch)
    assert all(op.path != "/sectors/0/install_height_m" for op in derived.operations)


def test_undeclared_dependent_capability_fails_with_actionable_reason() -> None:
    scene = _scene()
    assert scene.tower is not None
    new_height = round(scene.tower.height_m / 3, 1)
    try:
        derive_dependent_operations(
            scene, _lower_tower(scene, new_height), allowed_paths={"/tower/height_m"}
        )
    except ValueError as exc:
        text = edit_failure_user_text(str(exc))
        assert "au-dessus de la hauteur de pylône" in text
    else:
        raise AssertionError("expected a dependency failure")


def test_edit_failure_text_strips_pydantic_noise() -> None:
    raw = (
        "Adaptation plan failed SceneSpec validation: Patched scene failed validation: "
        "1 validation error for SceneSpec\n  Value error, S1 install_height_m exceeds tower "
        "height (38.0 > 20.0) [type=value_error, input_value={'schema_version': '1.0.0'}]"
    )
    text = edit_failure_user_text(raw)
    assert "38 m" in text and "20 m" in text and "pydantic" not in text.lower()
    assert "[type=" not in text
    assert "valeur à appliquer" in edit_failure_user_text(
        "Patch numeric value is not grounded in the prompt: /tower/height_m"
    )
