import hashlib
import json
from pathlib import Path

import pytest

from core.contracts.completion import CompletionCertificate
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.services.event_log import EventLogService
from core.services.requirement_parser import parse_requirements_text
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
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 1 secteur à 24m. Azimut : 0°."
    )
    requirements_path = artifact_dir / "requirements_spec.json"
    scene_path = artifact_dir / "scene_spec.json"
    requirements_payload = requirements.model_dump()
    for field_name in (
        "field_evidence",
        "conflicts",
        "assumptions",
        "requires_confirmation",
        "confirmation_fields",
    ):
        requirements_payload.pop(field_name)
    scene_payload = sample_scene.model_dump()
    scene_payload.pop("schema_version")
    requirements_path.write_text(json.dumps(requirements_payload), encoding="utf-8")
    scene_path.write_text(json.dumps(scene_payload), encoding="utf-8")
    (artifact_dir / "design.glb").write_bytes(b"verified-glb")
    (artifact_dir / "preview.png").write_bytes(b"verified-preview")
    (artifact_dir / "scene_metadata.json").write_bytes(b"verified-metadata")
    artifact_hashes = {
        name: {
            "size_bytes": (artifact_dir / name).stat().st_size,
            "sha256": hashlib.sha256((artifact_dir / name).read_bytes()).hexdigest(),
        }
        for name in ("design.glb", "preview.png", "scene_metadata.json")
    }
    (artifact_dir / "build.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "build_id": "build_verified",
                "attempt_id": "build_verified_attempt_1",
                "scene_id": sample_scene.scene_id,
                "scene_spec_sha256": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
                "worker_script_sha256": "a" * 64,
                "blender_runtime": {
                    "version": "test",
                    "background": True,
                    "factory_startup": True,
                },
                "command_profile": {
                    "background": True,
                    "factory_startup": True,
                    "python_exit_code": 97,
                },
                "artifacts": artifact_hashes,
            }
        ),
        encoding="utf-8",
    )
    artifacts = []
    for logical_name, file_name in (
        ("glb", "design.glb"),
        ("preview", "preview.png"),
        ("metadata", "scene_metadata.json"),
        ("build_lock", "build.lock.json"),
    ):
        path = artifact_dir / file_name
        artifacts.append(
            {
                "logical_name": logical_name,
                "file_name": file_name,
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    checks = {
        "requirements_present": True,
        "scene_spec_present": True,
        "requirement_coverage_passed": True,
        "pre_blender_gate_passed": True,
        "real_blender_generation": True,
        "required_artifacts_regular_files": True,
        "artifact_hashes_recorded": True,
        "qa_report_passed": True,
        "glb_binary_integrity_passed": True,
        "semantic_mesh_coverage_complete": True,
        "geometry_validation_passed": True,
        "mesh_qa_passed": True,
        "preview_qa_passed": True,
        "post_blender_gate_passed": True,
        "no_critical_fallback": True,
    }
    certificate = CompletionCertificate(
        workflow_id="wf_1",
        status="issued",
        evaluated_at="2026-07-29T00:00:00Z",
        requirements_sha256=_canonical_json_hash(
            requirements_payload,
            exclude={"warnings", "repair_events"},
        ),
        scene_spec_sha256=_canonical_json_hash(scene_payload),
        generation_mode="real_blender",
        artifacts=artifacts,
        checks=checks,
        blockers=[],
    )
    (artifact_dir / "completion_certificate.json").write_text(
        certificate.model_dump_json(), encoding="utf-8"
    )
    (artifact_dir / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": "wf_1",
                "version_id": version.version_id,
                "active_version_id": version.version_id,
                "status": "completed",
                "generation_mode": "real_blender",
                "completion_certificate_status": "issued",
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

    divergent_scene = sample_scene.model_copy(
        update={
            "tower": sample_scene.tower.model_copy(update={"height_m": 37.0}),
        }
    )
    svc.update_version("wf_1", version.version_id, scene=divergent_scene)
    with pytest.raises(ValueError, match="ACTIVE_VERSION_SCENE_VERSION_MISMATCH"):
        svc.verified_active_status_path("wf_1")
    with pytest.raises(ValueError, match="ACTIVE_VERSION_SCENE_VERSION_MISMATCH"):
        svc.commit_active_version("wf_1", version.version_id)
    svc.update_version("wf_1", version.version_id, scene=sample_scene)

    (artifact_dir / "design.glb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH"):
        svc.verified_active_status_path("wf_1")


def _canonical_json_hash(payload: dict, *, exclude: set[str] | None = None) -> str:
    canonical_payload = {
        key: value for key, value in payload.items() if key not in (exclude or set())
    }
    encoded = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_completed_version_rejects_minimal_certificate(tmp_outputs, sample_scene):
    svc = SceneVersioningService(tmp_outputs)
    version = svc.save_version("wf_1", sample_scene, activate=False)
    artifact_dir = svc.version_artifacts_dir("wf_1", version.version_id)
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "completion_certificate.json").write_text(
        json.dumps({"status": "issued", "artifacts": []}),
        encoding="utf-8",
    )
    svc.update_version(
        "wf_1",
        version.version_id,
        status="completed",
        artifact_dir=str(artifact_dir),
    )

    with pytest.raises(ValueError, match="ACTIVE_VERSION_COMPLETION_CERTIFICATE_INVALID"):
        svc.commit_active_version("wf_1", version.version_id)
