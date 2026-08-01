import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_unit_tests_from_groq():
    original = workflow_service.scene_edit_agent.groq
    workflow_service.scene_edit_agent.groq = None
    try:
        yield
    finally:
        workflow_service.scene_edit_agent.groq = original


def test_edit_unknown_workflow_returns_404(client, tmp_path):
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    try:
        response = client.post(
            "/designs/wf_000000000000/edit",
            json={"edit_prompt": "augmente la hauteur à 35 m"},
        )
    finally:
        workflow_service.outputs_dir = original_outputs

    assert response.status_code == 404
    assert response.json()["detail"] == "workflow not found"


def test_edit_design_creates_version(client, tmp_path):
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    try:
        # Create a design synchronously
        create_resp = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m. 3 secteurs à 24m. Azimuts 0, 120, 240."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = create_resp["workflow_id"]

        # Edit the design
        resp = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "mets les antennes à 26m"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "applied"
        assert payload["edit_status"] == "applied"
        assert payload["message"]
        assert payload["version_id"] is not None
        assert payload["artifacts"]
        assert payload["generation_mode"] in {"real_blender", "fallback_no_blender"}
        assert payload["qa_score"] == 1.0
        assert payload["patch"]["edit_llm_provider"] == "deterministic_fallback"
        provenance = payload["llm_decision_provenance"]
        assert provenance["provider"] == "deterministic_fallback"
        assert provenance["model"] is None
        assert provenance["capability_called"] == "scene_adaptation"
        assert provenance["fallback_used"] is True
        assert provenance["structured_decision"]["operations"]
        assert provenance["candidates_considered"]
        assert provenance["strategy_selected"] == ["sector_layout"]
        assert provenance["rationale"]
        assert provenance["version_id"] == payload["version_id"]
        if payload["llm_fallback_used"]:
            assert payload["llm_fallback_reason"]
        version_id = payload["version_id"]
        version_artifacts = payload["artifacts"]
        assert payload["viewer_bundle_url"] == f"/designs/{workflow_id}/viewer-bundle"
        assert payload["timeline_url"] == f"/designs/{workflow_id}/timeline-summary"
        assert payload["user_issues_url"] == f"/designs/{workflow_id}/user-issues"
        assert payload["current_operation_url"] == f"/designs/{workflow_id}/current-operation"
        assert "open_viewer" in payload["available_actions"]
        for key in [
            "scene_spec",
            "validation_report",
            "quality_gates",
            "qa_report",
            "generation_report",
            "glb_inspection",
            "geometry_validation",
            "preview_inspection",
            "glb",
            "preview",
            "metadata",
            "download",
        ]:
            assert version_artifacts[key].startswith(
                f"/designs/{workflow_id}/artifacts/{key}"
            ) or version_artifacts[key].startswith(f"/designs/{workflow_id}/download")
            assert "/Users/" not in version_artifacts[key]
            if key != "download":
                assert f"version_id={version_id}" in version_artifacts[key]
        raw_versions = workflow_service.list_versions(workflow_id)
        raw_edited_version = next(
            version for version in raw_versions if version["version_id"] == version_id
        )
        raw_artifacts = raw_edited_version["artifacts"]
        assert Path(raw_artifacts["scene_spec"]).parent.name == f"{version_id}_artifacts"
        assert Path(raw_artifacts["scene_spec"]).parent != tmp_path / workflow_id
        assert (Path(raw_artifacts["scene_spec"]).parent / "scene_patch.json").exists()
        assert (Path(raw_artifacts["scene_spec"]).parent / "scene_diff.json").exists()
        assert (Path(raw_artifacts["scene_spec"]).parent / "adaptation_plan.json").exists()
        assert (Path(raw_artifacts["scene_spec"]).parent / "adaptation_capabilities.json").exists()
        provenance_path = Path(raw_artifacts["llm_decision_provenance"])
        assert provenance_path.exists()
        assert json.loads(provenance_path.read_text())["version_id"] == version_id
        scene_payload = json.loads(Path(raw_artifacts["scene_spec"]).read_text())
        assert [sector["install_height_m"] for sector in scene_payload["sectors"]] == [
            26.0,
            26.0,
            26.0,
        ]

        # List versions
        versions_resp = client.get(f"/designs/{workflow_id}/versions")
        assert versions_resp.status_code == 200
        versions = versions_resp.json()
        assert len(versions) >= 2  # initial + edit
        edited_version = next(
            version for version in versions if version["version_id"] == version_id
        )
        assert edited_version["active"] is True
        assert edited_version["status"] == "completed"
        assert edited_version["llm_decision_provenance"]["provider"] == ("deterministic_fallback")
        assert "artifact_dir" not in edited_version
        assert edited_version["artifacts"]["qa_report"].startswith(
            f"/designs/{workflow_id}/artifacts/qa_report?version_id={version_id}"
        )
        assert "/Users/" not in edited_version["artifacts"]["qa_report"]

        status = client.get(f"/designs/{workflow_id}").json()
        assert status["active_version_id"] == version_id
        assert status["artifacts"]["scene_spec"] == f"/designs/{workflow_id}/artifacts/scene_spec"
        assert status["active_version_artifacts"]["scene_spec"] == version_artifacts["scene_spec"]
        assert status["llm_provider"] == "deterministic_fallback"
        assert status["llm_decision_provenance"]["version_id"] == version_id
        viewer_bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert viewer_bundle["llm_decision_provenance"]["version_id"] == version_id
        assert viewer_bundle["llm_decision_provenance_url"].endswith(
            f"llm_decision_provenance?version_id={version_id}"
        )

        # Rollback
        first_version = versions[0]["version_id"]
        rollback_resp = client.post(f"/designs/{workflow_id}/versions/{first_version}/rollback")
        assert rollback_resp.status_code == 200
        rollback_payload = rollback_resp.json()
        assert rollback_payload["rolled_back"] is True
        assert rollback_payload["status"] == "rolled_back"
        assert rollback_payload["active_version_id"] == first_version
        assert rollback_payload["viewer_bundle_url"] == f"/designs/{workflow_id}/viewer-bundle"
        assert rollback_payload["timeline_url"] == f"/designs/{workflow_id}/timeline-summary"
        assert rollback_payload["user_issues_url"] == f"/designs/{workflow_id}/user-issues"
        assert rollback_payload["current_operation_url"] == (
            f"/designs/{workflow_id}/current-operation"
        )
        assert "open_viewer" in rollback_payload["available_actions"]
        rolled_status = client.get(f"/designs/{workflow_id}").json()
        assert rolled_status["active_version_id"] == first_version

        active_version = workflow_service.versioning.get_active_version(workflow_id)
        assert active_version is not None
        divergent_scene = active_version.scene.model_copy(
            update={
                "tower": active_version.scene.tower.model_copy(update={"height_m": 37.0}),
            }
        )
        workflow_service.versioning.update_version(
            workflow_id,
            active_version.version_id,
            scene=divergent_scene,
        )
        blocked_edit = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "mets les antennes à 25m"},
        )
        assert blocked_edit.status_code == 200
        assert blocked_edit.json()["status"] == "failed"
        assert blocked_edit.json()["errors"][0]["code"] == "ACTIVE_VERSION_INTEGRITY_FAILED"
        assert (
            client.post(
                f"/designs/{workflow_id}/versions/{active_version.version_id}/rollback"
            ).status_code
            == 404
        )
        workflow_service.versioning.update_version(
            workflow_id,
            active_version.version_id,
            scene=active_version.scene,
        )
        failed_version = workflow_service.versioning.save_version(
            workflow_id,
            active_version.scene,
            parent_version_id=first_version,
            edit_description="failed revision",
            status="failed",
            artifact_dir=str(tmp_path / workflow_id / "failed_artifacts"),
            activate=False,
        )
        failed_rollback = client.post(
            f"/designs/{workflow_id}/versions/{failed_version.version_id}/rollback"
        )
        assert failed_rollback.status_code == 404
        assert workflow_service.versioning.active_version_id(workflow_id) == first_version

        # Events
        events_resp = client.get(f"/designs/{workflow_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert any(e["event_type"] == "edit_patch_applied" for e in events)
        interpreted = next(e for e in events if e["event_type"] == "edit_patch_interpreted")
        assert interpreted["payload"]["llm_provider"] == "deterministic_fallback"
        assert interpreted["payload"]["operation_count"] >= 1
        adaptation_nodes = [
            event["payload"]["node"]
            for event in events
            if event["event_type"] == "edit_adaptation_node_completed"
        ]
        assert adaptation_nodes == [
            "discover_capabilities",
            "plan_adaptation",
            "validate_adaptation",
            "execute_adaptation",
        ]
        assert any(e["payload"].get("version_id") == version_id for e in events)
        rollback_event = next(e for e in events if e["event_type"] == "version_rolled_back")
        assert rollback_event["payload"]["version_id"] == first_version
        assert rollback_event["payload"]["human_label"] == "Version restaurée"
    finally:
        workflow_service.outputs_dir = original_outputs


def test_rru_edit_runs_real_blender_and_preserves_groq_provenance_on_rollback(client, tmp_path):
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    try:
        create_result = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30 m, avec trois secteurs à 24 m, "
                "azimuts 0, 120 et 240, radios RRU et équipement au sol."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = create_result["workflow_id"]
        initial_version = workflow_service.versioning.get_verified_active_version(workflow_id)
        assert initial_version is not None
        radio_index = next(
            index
            for index, sector in enumerate(initial_version.scene.sectors)
            if sector.radio_asset_id is not None and sector.radio_geometry_profile is not None
        )
        initial_sector = initial_version.scene.sectors[radio_index]
        initial_radio_id = initial_sector.radio_asset_id
        assert initial_radio_id
        assert initial_sector.radio_geometry_profile is not None

        capabilities = workflow_service.scene_edit_agent.capability_service.resolve(
            initial_version.scene
        )
        capability = next(
            item
            for item in capabilities.capabilities
            if item.path == f"/sectors/{radio_index}/radio_geometry_profile/vertical_offset_m"
        )
        current_offset = initial_sector.radio_geometry_profile.vertical_offset_m
        requested_offset = round(
            current_offset + 0.3 if current_offset <= 2.7 else current_offset - 0.3,
            2,
        )

        class BoundedGroq:
            model = "openai/gpt-oss-120b"

            @staticmethod
            def request_json(_payload, policy=None):
                return {
                    "action": "standard_adaptation",
                    "program_id": None,
                    "reason": "La demande cible le profil RRU actif.",
                }

            @staticmethod
            def _post_raw(_payload):
                return {
                    "edit_description": "Adapter le décalage vertical du RRU actif",
                    "operations": [
                        {
                            "op": "replace",
                            "capability_id": capability.capability_id,
                            "path": capability.path,
                            "value_json": json.dumps(requested_offset),
                            "execution_tool": capability.execution_tool,
                            "rationale": "La valeur et le secteur sont explicites.",
                        }
                    ],
                    "unsupported_requests": [],
                    "assumptions": [],
                }

        workflow_service.scene_edit_agent.groq = BoundedGroq()  # type: ignore[assignment]
        initial_glb = Path(initial_version.artifact_dir or "") / "design.glb"
        initial_glb_hash = hashlib.sha256(initial_glb.read_bytes()).hexdigest()
        prompt_value = str(requested_offset).replace(".", ",")
        response = client.post(
            f"/designs/{workflow_id}/edit",
            json={
                "edit_prompt": (
                    f"mets le décalage vertical du RRU du secteur {radio_index + 1} "
                    f"à {prompt_value} m"
                )
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "applied"
        assert payload["diff_summary"]["sectors_changed"] is True
        changed_sector = payload["diff_summary"]["sector_changes"][0]
        assert changed_sector["sector_id"] == initial_sector.sector_id
        assert "radio_geometry_profile" in changed_sector["fields"]
        edited_version_id = payload["version_id"]
        provenance = payload["llm_decision_provenance"]
        assert provenance["provider"] == "groq"
        assert provenance["model"] == "openai/gpt-oss-120b"
        assert provenance["fallback_used"] is False
        assert provenance["strategy_selected"] == ["sector_layout"]
        assert provenance["structured_decision"]["operations"][0]["path"] == capability.path
        assert any(
            candidate["asset_id"] == initial_radio_id
            and candidate["capability_id"] == capability.capability_id
            for candidate in provenance["candidates_considered"]
        )

        edited_version = workflow_service.versioning.get_verified_active_version(workflow_id)
        assert edited_version is not None
        assert edited_version.version_id == edited_version_id
        edited_sector = edited_version.scene.sectors[radio_index]
        assert edited_sector.radio_asset_id == initial_radio_id
        assert edited_sector.radio_geometry_profile is not None
        assert edited_sector.radio_geometry_profile.vertical_offset_m == requested_offset
        edited_artifact_dir = Path(edited_version.artifact_dir or "")
        assert hashlib.sha256((edited_artifact_dir / "design.glb").read_bytes()).hexdigest() != (
            initial_glb_hash
        )
        inspection = json.loads((edited_artifact_dir / "glb_inspection.json").read_text())
        assert inspection["structural_qa_passed"] is True
        assert inspection["semantic_object_counts"]["rru"] >= 1
        component_proofs = json.loads((edited_artifact_dir / "component_proofs.json").read_text())
        radio_proof = next(
            component
            for component in component_proofs["components"]
            if component["role_id"] == "remote_radio"
        )
        edited_radio_instance = next(
            instance
            for instance in radio_proof["instances"]
            if instance["instance_id"] == initial_sector.sector_id
        )
        assert edited_radio_instance["resolved_parameters"]["vertical_offset_m"] == (
            requested_offset
        )
        assert edited_radio_instance["qa"]["passed"] is True
        assert f"S{radio_index + 1}" in inspection["semantic_sector_ids"]["rru"]
        certificate = json.loads((edited_artifact_dir / "completion_certificate.json").read_text())
        assert certificate["status"] == "issued"

        # Re-read from durable JSON, roll away, then restore the edited version.
        reloaded = workflow_service.versioning.get_version(workflow_id, edited_version_id)
        assert reloaded is not None
        assert reloaded.llm_decision_provenance is not None
        assert reloaded.llm_decision_provenance.model == "openai/gpt-oss-120b"
        assert (
            client.post(
                f"/designs/{workflow_id}/versions/{initial_version.version_id}/rollback"
            ).status_code
            == 200
        )
        assert (
            client.post(f"/designs/{workflow_id}/versions/{edited_version_id}/rollback").status_code
            == 200
        )
        restored = client.get(f"/designs/{workflow_id}").json()
        assert restored["active_version_id"] == edited_version_id
        assert restored["llm_provider"] == "groq:openai/gpt-oss-120b"
        assert restored["llm_decision_provenance"]["version_id"] == edited_version_id
    finally:
        workflow_service.outputs_dir = original_outputs


def test_edit_design_rejected_on_bad_prompt(client, tmp_path):
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    try:
        create_resp = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m. 3 secteurs à 24m. Azimuts 0, 120, 240."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = create_resp["workflow_id"]

        resp = client.post(
            f"/designs/{workflow_id}/edit",
            json={"edit_prompt": "abc xyz 12345 nonexistent command"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "failed"
        assert payload["edit_status"] == "failed"
        assert payload["message"]
        assert "edit_prompt_again" in payload["available_actions"]
        restored_status = client.get(f"/designs/{workflow_id}").json()
        assert restored_status["status"] == "completed"
        assert restored_status.get("active_operation") is None
    finally:
        workflow_service.outputs_dir = original_outputs
