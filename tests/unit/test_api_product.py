"""Tests for product-oriented API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service


def test_studio_summary_returns_design_counts(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        assert response["status"] == "completed"

        summary = client.get("/studio/summary").json()
        assert summary["total_designs"] >= 1
        assert summary["completed_designs"] >= 1
        assert "asset_inventory_status" in summary
        assert "blender_available" in summary
        assert isinstance(summary["warnings"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_user_summary_returns_human_readable_issues(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        summary = client.get(f"/designs/{workflow_id}/user-summary").json()

        assert summary["workflow_id"] == workflow_id
        assert summary["status"] == "completed"
        assert summary["current_operation"]
        assert summary["next_recommended_action"]
        assert summary["qa_summary"]
        assert isinstance(summary["human_readable_issues"], list)
        assert isinstance(summary["limitations"], list)
        for issue in summary["human_readable_issues"]:
            assert "title" in issue
            assert "severity" in issue
            assert "impact" in issue
            assert "recommended_action" in issue
    finally:
        workflow_service.outputs_dir = original_outputs


def test_current_operation_for_completed_workflow(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()

        assert operation["workflow_id"] == workflow_id
        assert operation["status"] == "completed"
        assert operation["current_operation"]
        assert operation["next_recommended_action"]
        assert operation["progress_indicator"] == "done"
    finally:
        workflow_service.outputs_dir = original_outputs


def test_viewer_bundle_returns_artifact_urls(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()

        assert bundle["workflow_id"] == workflow_id
        assert bundle["status"] == "completed"
        assert isinstance(bundle["viewer_artifacts"], list)
        names = {a["name"] for a in bundle["viewer_artifacts"]}
        assert "design.glb" in names
        assert "preview.png" in names
        for artifact in bundle["viewer_artifacts"]:
            assert artifact["url"].startswith(f"/designs/{workflow_id}/artifacts/")
            assert isinstance(artifact["available"], bool)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_timeline_summary_returns_readable_steps(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        timeline = client.get(f"/designs/{workflow_id}/timeline-summary").json()

        assert timeline["workflow_id"] == workflow_id
        assert isinstance(timeline["timeline_steps"], list)
        assert len(timeline["timeline_steps"]) > 0
        for step in timeline["timeline_steps"]:
            assert "step" in step
            assert "status" in step
            assert "human_readable" in step
    finally:
        workflow_service.outputs_dir = original_outputs


def test_user_issues_endpoint_returns_issues(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        issues_payload = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert issues_payload["workflow_id"] == workflow_id
        assert isinstance(issues_payload["human_readable_issues"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_product_endpoints_return_404_for_unknown_workflow() -> None:
    client = TestClient(app)
    endpoints = [
        "/designs/wf_unknown/user-summary",
        "/designs/wf_unknown/current-operation",
        "/designs/wf_unknown/user-issues",
        "/designs/wf_unknown/viewer-bundle",
        "/designs/wf_unknown/timeline-summary",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 404, endpoint


def test_frontend_does_not_need_raw_json_for_primary_ui(tmp_path: Path) -> None:
    """User-summary must expose enough structured data to render UI without status.json."""
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        summary = client.get(f"/designs/{workflow_id}/user-summary").json()
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()
        issues = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert summary["qa_summary"]
        assert summary["asset_quality_summary"]
        assert bundle["viewer_artifacts"]
        assert operation["current_operation"]
        assert isinstance(issues["human_readable_issues"], list)
    finally:
        workflow_service.outputs_dir = original_outputs
