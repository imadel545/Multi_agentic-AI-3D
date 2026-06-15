import pytest
from pydantic import ValidationError

from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.services.diff_engine import DiffEngine
from core.services.patch_applier import PatchApplier


@pytest.fixture
def sample_scene() -> SceneSpec:
    return SceneSpec(
        scene_id="wf_test",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower_01",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ant_01",
                install_height_m=24,
                azimuth_deg=0,
                mechanical_tilt_deg=3,
                beamwidth_deg=65,
            ),
            SectorSpec(
                sector_id="S2",
                antenna_asset_id="ant_01",
                install_height_m=24,
                azimuth_deg=120,
                mechanical_tilt_deg=3,
                beamwidth_deg=65,
            ),
        ],
        visual_elements=VisualElements(),
    )


def test_patch_applier_replace_height(sample_scene):
    applier = PatchApplier()
    patch = ScenePatch(
        edit_description="raise tower",
        operations=[PatchOperation(op="replace", path="/tower/height_m", value=35)],
    )
    patched, report = applier.apply(sample_scene, patch)
    assert report.status == "passed"
    assert patched.tower.height_m == 35


def test_patch_applier_rejects_unknown_path(sample_scene):
    with pytest.raises(ValidationError):
        PatchOperation(op="replace", path="/unknown/path", value=1)


def test_patch_applier_replace_sector_azimuth(sample_scene):
    applier = PatchApplier()
    patch = ScenePatch(
        edit_description="rotate sector",
        operations=[PatchOperation(op="replace", path="/sectors/0/azimuth_deg", value=45)],
    )
    patched, report = applier.apply(sample_scene, patch)
    assert report.status == "passed"
    assert patched.sectors[0].azimuth_deg == 45


def test_patch_applier_replace_all_sector_heights_with_wildcard(sample_scene):
    applier = PatchApplier()
    patch = ScenePatch(
        edit_description="raise all antennas",
        operations=[PatchOperation(op="replace", path="/sectors/*/install_height_m", value=26)],
    )
    patched, report = applier.apply(sample_scene, patch)

    assert report.status == "passed"
    assert [sector.install_height_m for sector in patched.sectors] == [26, 26]


def test_diff_engine_detects_changes(sample_scene):
    applier = PatchApplier()
    patch = ScenePatch(
        edit_description="add gps",
        operations=[
            PatchOperation(op="replace", path="/visual_elements/include_gps_antenna", value=True)
        ],
    )
    patched, _ = applier.apply(sample_scene, patch)
    diff = DiffEngine.diff_scenes(sample_scene, patched)
    assert diff["visual_elements_changed"] is True
    assert diff["visual_changes"]["include_gps_antenna"]["new"] is True


def test_scene_edit_agent_fallback_height(sample_scene):
    agent = SceneEditAgent(groq_client=None)
    patch = agent.create_patch("wf_test", sample_scene, "mets la tour à 40m")
    assert patch.edit_llm_fallback_used is True
    assert any(op.path == "/tower/height_m" and op.value == 40 for op in patch.operations)


def test_scene_edit_agent_fallback_gps(sample_scene):
    agent = SceneEditAgent(groq_client=None)
    patch = agent.create_patch("wf_test", sample_scene, "ajoute GPS")
    assert any(op.path == "/visual_elements/include_gps_antenna" for op in patch.operations)


def test_scene_edit_agent_fallback_cable_removal(sample_scene):
    agent = SceneEditAgent(groq_client=None)
    patch = agent.create_patch("wf_test", sample_scene, "supprime les câbles")
    assert all(op.value is False for op in patch.operations if "include_cable" in op.path)
