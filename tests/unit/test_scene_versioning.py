from pathlib import Path

import pytest

from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.services.event_log import EventLogService
from core.services.scene_versioning import SceneVersioningService


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
            )
        ],
        visual_elements=VisualElements(),
    )


@pytest.fixture
def tmp_outputs(tmp_path: Path) -> Path:
    return tmp_path


def test_versioning_save_and_get_active(tmp_outputs, sample_scene):
    svc = SceneVersioningService(tmp_outputs)
    v = svc.save_version("wf_1", sample_scene, edit_description="initial")
    assert v.version_id.startswith("v")
    active = svc.get_active_version("wf_1")
    assert active is not None
    assert active.scene.tower.height_m == 30


def test_versioning_list_versions(tmp_outputs, sample_scene):
    svc = SceneVersioningService(tmp_outputs)
    v1 = svc.save_version("wf_1", sample_scene, edit_description="v1")
    svc.save_version("wf_1", sample_scene, parent_version_id=v1.version_id, edit_description="v2")
    versions = svc.list_versions("wf_1")
    assert len(versions) == 2


def test_versioning_rollback(tmp_outputs, sample_scene):
    svc = SceneVersioningService(tmp_outputs)
    v1 = svc.save_version("wf_1", sample_scene, edit_description="v1")
    svc.save_version("wf_1", sample_scene, edit_description="v2")
    rolled = svc.rollback("wf_1", v1.version_id)
    assert rolled is not None
    assert rolled.version_id == v1.version_id
    active = svc.get_active_version("wf_1")
    assert active.version_id == v1.version_id


def test_event_log_emit_and_list(tmp_outputs):
    svc = EventLogService(tmp_outputs)
    svc.emit("wf_1", "design_created", {"detail_level": "high"})
    svc.emit("wf_1", "blender_started")
    events = svc.list_events("wf_1")
    assert len(events) == 2
    assert events[0].event_type == "design_created"
    assert events[1].event_type == "blender_started"
