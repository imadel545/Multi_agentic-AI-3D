import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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
        assert payload["patch"]["edit_llm_provider"] in {"groq", "deterministic_fallback"}
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
        assert "artifact_dir" not in edited_version
        assert edited_version["artifacts"]["qa_report"].startswith(
            f"/designs/{workflow_id}/artifacts/qa_report?version_id={version_id}"
        )
        assert "/Users/" not in edited_version["artifacts"]["qa_report"]

        status = client.get(f"/designs/{workflow_id}").json()
        assert status["active_version_id"] == version_id
        assert status["artifacts"]["scene_spec"] == f"/designs/{workflow_id}/artifacts/scene_spec"
        assert status["active_version_artifacts"]["scene_spec"] == version_artifacts["scene_spec"]

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

        # Events
        events_resp = client.get(f"/designs/{workflow_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert any(e["event_type"] == "edit_patch_applied" for e in events)
        assert any(e["payload"].get("version_id") == version_id for e in events)
        rollback_event = next(e for e in events if e["event_type"] == "version_rolled_back")
        assert rollback_event["payload"]["version_id"] == first_version
        assert rollback_event["payload"]["human_label"] == "Version restaurée"
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
    finally:
        workflow_service.outputs_dir = original_outputs
