from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from core.agents.scene_edit_agent import SceneEditAgent
from core.orchestration import DesignOrchestrator
from core.services.checkpoint_saver import SqliteCheckpointSaver

pytestmark = pytest.mark.blender_runtime


def test_chat_cabinet_removal_restore_and_failed_revision_are_version_safe(
    tmp_path: Path,
) -> None:
    original_outputs = workflow_service.outputs_dir
    original_orchestrator = workflow_service.orchestrator
    original_edit_agent = workflow_service.scene_edit_agent
    checkpoint_saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    workflow_service.orchestrator = DesignOrchestrator(
        registry=workflow_service.registry,
        extractor=original_orchestrator.extractor,
        rag_service=None,
        memory_service=None,
        blender_runner=original_orchestrator.blender_runner,
        checkpoint_saver=checkpoint_saver,
        planning_decision_client=None,
        asset_selection_client=None,
        blueprint_composer=original_orchestrator.blueprint_composer,
        geometry_program_planner=original_orchestrator.geometry_program_planner,
        design_domain_router=None,
        cognitive_design_planner=None,
        cognitive_scene_compiler=original_orchestrator.cognitive_scene_compiler,
        allow_blender_fallback=False,
    )
    workflow_service.scene_edit_agent = SceneEditAgent(
        groq_client=None,
        capability_service=original_edit_agent.capability_service,
        checkpoint_saver=checkpoint_saver,
        geometry_program_planner=original_orchestrator.geometry_program_planner,
    )
    workflow_service.outputs_dir = tmp_path
    workflow_service._sync_output_services()
    client = TestClient(app)

    try:
        created = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30 m avec un secteur à 24 m, "
                "azimut 0°. Ajouter boîte alimentation et GPS."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = created["workflow_id"]
        assert created["status"] == "completed", _status_diagnostic(workflow_id)

        initial = _verified_active_version(workflow_id)
        assert initial.generation_mode == "real_blender"
        initial_dir = Path(initial.artifact_dir or "")
        _assert_accessory_artifacts(
            initial_dir,
            expect_cabinet=True,
            expect_gps=True,
        )

        removed_response = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "supprime boite alimentation"},
        )
        assert removed_response.status_code == 200, removed_response.text
        removed_payload = removed_response.json()
        assert removed_payload["status"] == "applied", removed_payload
        assert removed_payload["edit_status"] == "applied"
        assert removed_payload["generation_mode"] == "real_blender"
        assert removed_payload["patch"]["edit_llm_provider"] == "deterministic_fallback"
        assert removed_payload["patch"]["edit_llm_fallback_used"] is True
        assert any(
            operation["path"] == "/visual_elements/include_power_cabinet"
            and operation["value"] is False
            for operation in removed_payload["patch"]["operations"]
        )

        removed = _verified_active_version(workflow_id)
        assert removed.version_id == removed_payload["version_id"]
        assert removed.version_id != initial.version_id
        assert removed.parent_version_id == initial.version_id
        assert removed.scene.visual_elements.include_power_cabinet is False
        assert removed.scene.visual_elements.include_gps_antenna is True
        assert not any(
            accessory.asset_type == "cabinet" for accessory in removed.scene.accessory_assets
        )
        assert any(accessory.asset_type == "gps" for accessory in removed.scene.accessory_assets)
        removed_dir = Path(removed.artifact_dir or "")
        _assert_accessory_artifacts(
            removed_dir,
            expect_cabinet=False,
            expect_gps=True,
        )
        _assert_only_active_version(workflow_id, removed.version_id)

        restored_response = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "ajoute boite alimentation"},
        )
        assert restored_response.status_code == 200, restored_response.text
        restored_payload = restored_response.json()
        assert restored_payload["status"] == "applied", restored_payload
        assert restored_payload["edit_status"] == "applied"
        assert restored_payload["generation_mode"] == "real_blender"
        assert restored_payload["patch"]["edit_llm_provider"] == "deterministic_fallback"
        assert restored_payload["patch"]["edit_llm_fallback_used"] is True
        assert any(
            operation["path"] == "/visual_elements/include_power_cabinet"
            and operation["value"] is True
            for operation in restored_payload["patch"]["operations"]
        )

        restored = _verified_active_version(workflow_id)
        assert restored.version_id == restored_payload["version_id"]
        assert restored.version_id != removed.version_id
        assert restored.parent_version_id == removed.version_id
        assert restored.scene.visual_elements.include_power_cabinet is True
        assert restored.scene.visual_elements.include_gps_antenna is True
        assert any(
            accessory.asset_type == "cabinet" for accessory in restored.scene.accessory_assets
        )
        assert any(accessory.asset_type == "gps" for accessory in restored.scene.accessory_assets)
        restored_dir = Path(restored.artifact_dir or "")
        _assert_accessory_artifacts(
            restored_dir,
            expect_cabinet=True,
            expect_gps=True,
        )
        _assert_only_active_version(workflow_id, restored.version_id)

        restored_glb_hash = _sha256(restored_dir / "design.glb")
        rejected_response = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "mets la hauteur du pylône à 0 m"},
        )
        assert rejected_response.status_code == 200, rejected_response.text
        rejected_payload = rejected_response.json()
        assert rejected_payload["status"] in {"failed", "rejected"}, rejected_payload
        assert rejected_payload["edit_status"] in {"failed", "rejected"}
        assert rejected_payload["version_id"] is None
        assert rejected_payload["errors"]

        still_active = _verified_active_version(workflow_id)
        assert still_active.version_id == restored.version_id
        assert Path(still_active.artifact_dir or "") == restored_dir
        assert _sha256(restored_dir / "design.glb") == restored_glb_hash
        _assert_accessory_artifacts(
            restored_dir,
            expect_cabinet=True,
            expect_gps=True,
        )
        _assert_only_active_version(workflow_id, restored.version_id)
    finally:
        workflow_service.scene_edit_agent = original_edit_agent
        workflow_service.orchestrator = original_orchestrator
        workflow_service.outputs_dir = original_outputs
        workflow_service._sync_output_services()


def _verified_active_version(workflow_id: str):
    version = workflow_service.versioning.get_verified_active_version(workflow_id)
    assert version is not None
    status = workflow_service.get_status(workflow_id)
    assert status["status"] == "completed", status
    assert status["active_version_id"] == version.version_id
    assert status["generation_mode"] == "real_blender"
    assert status["completion_certificate_status"] == "issued"
    return version


def _assert_only_active_version(workflow_id: str, expected_version_id: str) -> None:
    versions = workflow_service.list_versions_public(workflow_id)
    assert [item["version_id"] for item in versions if item["active"]] == [expected_version_id]


def _assert_accessory_artifacts(
    artifact_dir: Path,
    *,
    expect_cabinet: bool,
    expect_gps: bool,
) -> None:
    glb_path = artifact_dir / "design.glb"
    inspection = _read_json(artifact_dir / "glb_inspection.json")
    geometry = _read_json(artifact_dir / "geometry_validation.json")
    proofs = _read_json(artifact_dir / "component_proofs.json")
    certificate = _read_json(artifact_dir / "completion_certificate.json")
    nodes = _glb_nodes(glb_path)

    assert inspection["inspection_mode"] == "glb_parse"
    # These booleans express whether the scene's expectation was satisfied.  For an
    # intentionally absent option, the semantic count and raw GLB nodes below are
    # the evidence that no geometry leaked into the export.
    if expect_cabinet:
        assert inspection["checks"]["has_power_cabinet"] is True
    if expect_gps:
        assert inspection["checks"]["has_gps_antenna"] is True
    assert inspection["semantic_object_counts"].get("power_cabinet", 0) == int(expect_cabinet)
    assert inspection["semantic_object_counts"].get("gps", 0) == int(expect_gps)
    assert geometry["object_counts"].get("power_cabinet", 0) == int(expect_cabinet)
    assert geometry["object_counts"].get("gps", 0) == int(expect_gps)
    assert geometry["checks"]["power_cabinet_count_valid"] is True
    assert geometry["checks"]["gps_antenna_count_valid"] is True

    proof_roles = {component["role_id"] for component in proofs["components"]}
    assert ("ground_equipment" in proof_roles) is expect_cabinet
    assert ("timing_antenna" in proof_roles) is expect_gps
    assert proofs["operation_execution"]["passed"] is True

    cabinet_mesh_nodes = [
        node
        for node in nodes
        if isinstance(node.get("mesh"), int)
        and (
            "power_cabinet" in str(node.get("name", "")).lower()
            or (node.get("extras") or {}).get("semantic_role") == "cabinet"
        )
    ]
    gps_nodes = [
        node
        for node in nodes
        if "gps" in str(node.get("name", "")).lower()
        or (node.get("extras") or {}).get("semantic_role") == "gps"
    ]
    assert bool(cabinet_mesh_nodes) is expect_cabinet
    assert bool(gps_nodes) is expect_gps
    assert certificate["status"] == "issued"
    assert certificate["checks"]["component_proof_verified"] is True


def _glb_nodes(path: Path) -> list[dict]:
    raw = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    assert magic == b"glTF"
    assert version == 2
    assert declared_length == len(raw)
    chunk_length, chunk_type = struct.unpack_from("<II", raw, 12)
    assert chunk_type == 0x4E4F534A
    payload = json.loads(raw[20 : 20 + chunk_length].decode("utf-8"))
    return payload.get("nodes", [])


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status_diagnostic(workflow_id: str) -> str:
    return json.dumps(workflow_service.get_status(workflow_id), ensure_ascii=False, indent=2)
