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
        assert payload["version_id"] is not None
        assert payload["artifacts"]
        assert payload["generation_mode"] in {"real_blender", "fallback_no_blender"}
        assert payload["qa_score"] == 1.0
        assert payload["patch"]["edit_llm_provider"] in {"groq", "deterministic_fallback"}
        version_id = payload["version_id"]
        version_artifacts = payload["artifacts"]
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
            assert Path(version_artifacts[key]).exists()
        assert Path(version_artifacts["scene_spec"]).parent.name == f"{version_id}_artifacts"
        assert Path(version_artifacts["scene_spec"]).parent != tmp_path / workflow_id
        assert (Path(version_artifacts["scene_spec"]).parent / "scene_patch.json").exists()
        assert (Path(version_artifacts["scene_spec"]).parent / "scene_diff.json").exists()
        scene_payload = json.loads(Path(version_artifacts["scene_spec"]).read_text())
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
        assert Path(edited_version["artifacts"]["qa_report"]).exists()

        status = client.get(f"/designs/{workflow_id}").json()
        assert status["active_version_id"] == version_id
        assert status["artifacts"]["scene_spec"] == version_artifacts["scene_spec"]

        # Rollback
        first_version = versions[0]["version_id"]
        rollback_resp = client.post(f"/designs/{workflow_id}/versions/{first_version}/rollback")
        assert rollback_resp.status_code == 200
        assert rollback_resp.json()["rolled_back"] is True
        rolled_status = client.get(f"/designs/{workflow_id}").json()
        assert rolled_status["active_version_id"] == first_version

        # Events
        events_resp = client.get(f"/designs/{workflow_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert any(e["event_type"] == "edit_patch_applied" for e in events)
        assert any(e["payload"].get("version_id") == version_id for e in events)
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
    finally:
        workflow_service.outputs_dir = original_outputs
