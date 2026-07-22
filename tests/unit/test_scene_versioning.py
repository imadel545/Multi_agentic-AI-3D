import hashlib
import json
from pathlib import Path

import pytest

from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.services.event_log import EventLogService
from core.services.scene_versioning import SceneVersioningService, _atomic_write_text


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


def test_atomic_version_write_never_leaves_temporary_files(tmp_outputs):
    target = tmp_outputs / "active_version.json"

    _atomic_write_text(target, '{"version_id":"v1"}')
    _atomic_write_text(target, '{"version_id":"v2"}')

    assert target.read_text(encoding="utf-8") == '{"version_id":"v2"}'
    assert list(tmp_outputs.glob(".active_version.json.*.tmp")) == []


def test_completed_version_commit_is_hash_bound_and_canonical(tmp_outputs, sample_scene):
    svc = SceneVersioningService(tmp_outputs)
    version = svc.save_version("wf_1", sample_scene, edit_description="verified", activate=False)
    artifact_dir = svc.version_artifacts_dir("wf_1", version.version_id)
    artifact_dir.mkdir(parents=True)
    artifacts = []
    for logical_name, file_name, content in (
        ("glb", "design.glb", b"verified-glb"),
        ("preview", "preview.png", b"verified-preview"),
        ("metadata", "scene_metadata.json", b"verified-metadata"),
        ("build_lock", "build.lock.json", b"verified-build-lock"),
    ):
        path = artifact_dir / file_name
        path.write_bytes(content)
        artifacts.append(
            {
                "logical_name": logical_name,
                "file_name": file_name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    (artifact_dir / "completion_certificate.json").write_text(
        json.dumps({"status": "issued", "artifacts": artifacts}), encoding="utf-8"
    )
    (artifact_dir / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": "wf_1",
                "version_id": version.version_id,
                "active_version_id": version.version_id,
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    svc.update_version(
        "wf_1",
        version.version_id,
        status="completed",
        artifact_dir=str(artifact_dir),
    )

    committed = svc.commit_active_version("wf_1", version.version_id)

    assert committed.version_id == version.version_id
    assert svc.active_version_id("wf_1") == version.version_id
    manifest = svc.active_design_manifest("wf_1")
    assert manifest is not None
    assert manifest["version_id"] == version.version_id
    assert {item["logical_name"] for item in manifest["certified_artifacts"]} == {
        "glb",
        "preview",
        "metadata",
        "build_lock",
    }

    (artifact_dir / "design.glb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH"):
        svc.commit_active_version("wf_1", version.version_id)
