import pytest

from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.tower import TowerAccessGeometryProfile, TowerCharacteristics
from core.services.dependent_constraints import with_dependent_operations
from core.services.patch_applier import PatchApplier
from core.services.platform_edit_resolution import resolve_platform_edit

PRESENCE_PATH = "/tower/characteristics/has_platform"
COUNT_PATH = "/tower/characteristics/platform_count"
LADDER_PATH = "/tower/characteristics/has_ladder"


def _scene(
    *,
    levels: list[float] | None = None,
    count: int | None = None,
    has_platform: bool | None = None,
    profile: bool = True,
) -> SceneSpec:
    explicit_levels = [21.5] if levels is None else levels
    platform_count = len(explicit_levels) if count is None else count
    platform_presence = platform_count > 0 if has_platform is None else has_platform
    return SceneSpec(
        scene_id="platform_edit",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower_01",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=24,
            characteristics=TowerCharacteristics(
                structure="lattice",
                leg_count=4,
                base_width_m=4,
                top_width_m=1,
                foundation_type="concrete_pad",
                has_platform=platform_presence,
                platform_count=platform_count,
                platform_levels_m=explicit_levels,
            ),
            tower_access_geometry_profile=TowerAccessGeometryProfile() if profile else None,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ant_01",
                install_height_m=20,
                azimuth_deg=0,
                mechanical_tilt_deg=3,
                beamwidth_deg=65,
            )
        ],
    )


def _patch(*operations: PatchOperation) -> ScenePatch:
    return ScenePatch(edit_description="platform edit", operations=list(operations))


def test_count_increase_preserves_explicit_level_and_derives_only_missing_level() -> None:
    scene = _scene()
    patch = _patch(
        PatchOperation(path=COUNT_PATH, value=2),
        PatchOperation(path=LADDER_PATH, value=True),
    )
    patch = with_dependent_operations(
        scene,
        patch,
        allowed_paths={COUNT_PATH, LADDER_PATH},
    )

    # The internal level reconciliation does not add an undeclared patch path.
    assert [operation.path for operation in patch.operations] == [COUNT_PATH, LADDER_PATH]
    assert patch.derived_assumptions
    assert "21.5 m" in patch.derived_assumptions[0]
    assert "13.2 m" in patch.derived_assumptions[0]
    assert "lattice_tower_access_v1" not in patch.derived_assumptions[0]

    patched, report = PatchApplier().apply(
        scene,
        patch,
        allowed_paths={COUNT_PATH, LADDER_PATH},
    )
    assert report.status == "passed"
    assert patched.tower is not None
    assert patched.tower.characteristics.has_platform is True
    assert patched.tower.characteristics.platform_count == 2
    assert patched.tower.characteristics.platform_levels_m == [13.2, 21.5]
    assert patched.tower.characteristics.has_ladder is True


def test_count_decrease_keeps_the_highest_existing_platform_levels() -> None:
    scene = _scene(levels=[13.2, 17.4, 21.5])
    patch = with_dependent_operations(
        scene,
        _patch(PatchOperation(path=COUNT_PATH, value=1)),
        allowed_paths={COUNT_PATH},
    )
    patched, report = PatchApplier().apply(scene, patch, allowed_paths={COUNT_PATH})

    assert report.status == "passed"
    assert patched.tower is not None
    assert patched.tower.characteristics.platform_count == 1
    assert patched.tower.characteristics.platform_levels_m == [21.5]
    assert "21.5 m" in patch.derived_assumptions[0]


@pytest.mark.parametrize(
    "operation",
    [
        PatchOperation(path=PRESENCE_PATH, value=False),
        PatchOperation(path=COUNT_PATH, value=0),
    ],
)
def test_disable_or_zero_count_clears_all_platform_state(operation: PatchOperation) -> None:
    scene = _scene()
    patch = with_dependent_operations(
        scene,
        _patch(operation),
        allowed_paths={operation.path},
    )
    patched, report = PatchApplier().apply(scene, patch, allowed_paths={operation.path})

    assert report.status == "passed"
    assert patched.tower is not None
    characteristics = patched.tower.characteristics
    assert characteristics.has_platform is False
    assert characteristics.platform_count == 0
    assert characteristics.platform_levels_m == []


def test_enable_platform_uses_declared_profile_for_first_level() -> None:
    scene = _scene(levels=[], count=0, has_platform=False)
    patch = with_dependent_operations(
        scene,
        _patch(PatchOperation(path=PRESENCE_PATH, value=True)),
        allowed_paths={PRESENCE_PATH},
    )
    patched, report = PatchApplier().apply(scene, patch, allowed_paths={PRESENCE_PATH})

    assert report.status == "passed"
    assert patched.tower is not None
    assert patched.tower.characteristics.platform_count == 1
    assert patched.tower.characteristics.platform_levels_m == [13.2]


def test_count_increase_without_profile_returns_original_scene() -> None:
    scene = _scene(profile=False)
    patch = _patch(PatchOperation(path=COUNT_PATH, value=2))

    patched, report = PatchApplier().apply(scene, patch, allowed_paths={COUNT_PATH})

    assert report.status == "failed"
    assert patched == scene
    assert "declared tower access geometry profile" in report.errors[0].message


def test_contradictory_presence_and_count_return_original_scene() -> None:
    scene = _scene()
    patch = _patch(
        PatchOperation(path=PRESENCE_PATH, value=False),
        PatchOperation(path=COUNT_PATH, value=2),
    )

    patched, report = PatchApplier().apply(
        scene,
        patch,
        allowed_paths={PRESENCE_PATH, COUNT_PATH},
    )

    assert report.status == "failed"
    assert patched == scene
    assert "contradicts" in report.errors[0].message


def test_unrelated_edit_never_rewrites_explicit_platform_levels() -> None:
    scene = _scene()
    patch = _patch(PatchOperation(path="/tower/height_m", value=25))

    assert resolve_platform_edit(scene, patch) is None
    patched, report = PatchApplier().apply(scene, patch, allowed_paths={"/tower/height_m"})
    assert report.status == "passed"
    assert patched.tower is not None
    assert patched.tower.characteristics.platform_levels_m == [21.5]
