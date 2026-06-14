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
        assert summary["asset_inventory_status"] == "partial_import_ready"
        assert summary["asset_count"] == 12
        assert summary["real_glb_asset_count"] == 9
        assert summary["missing_file_count"] == 3
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
        assert operation["current_phase"] in {
            "requirements",
            "rag",
            "memory",
            "assets",
            "scene",
            "quality_gate",
            "blender",
            "qa",
            "workflow",
        }
        assert operation["current_node"]
        assert operation["event_source"] == "runtime_events"
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
        assert bundle["generation_mode"]
        assert isinstance(bundle["human_warnings_count"], int)
        assert isinstance(bundle["human_errors_count"], int)
        assert isinstance(bundle["viewer_artifacts"], list)
        names = {a["name"] for a in bundle["viewer_artifacts"]}
        assert "design.glb" in names
        assert "preview.png" in names
        for artifact in bundle["viewer_artifacts"]:
            assert artifact["url"].startswith(f"/designs/{workflow_id}/artifacts/")
            assert "/Users/" not in artifact["url"]
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
        step_names = {step["step"] for step in timeline["timeline_steps"]}
        assert "design_created" in step_names
        assert "retrieve_rag_context" in step_names
        assert "memory_recall" in step_names
        assert "select_assets" in step_names
        assert "plan_scene" in step_names
        assert "generate_blender" in step_names
        assert "qa_generation" in step_names
        assert timeline["timeline_steps"][-1]["step"] == "workflow_completed"
        for step in timeline["timeline_steps"]:
            assert "step" in step
            assert "status" in step
            assert "human_readable" in step
    finally:
        workflow_service.outputs_dir = original_outputs


def test_workflow_events_expose_runtime_nodes_without_premature_blender_event(
    tmp_path: Path,
) -> None:
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
        events = client.get(f"/designs/{workflow_id}/events").json()

        event_types = [event["event_type"] for event in events]
        assert event_types[0] == "design_created"
        assert "blender_started" not in event_types
        node_events = [
            event
            for event in events
            if event["event_type"] in {"node_completed", "node_failed", "node_skipped"}
        ]
        assert node_events
        nodes = [event["payload"]["node"] for event in node_events]
        assert "extract_requirements" in nodes
        assert "retrieve_rag_context" in nodes
        assert "select_assets" in nodes
        assert "plan_scene" in nodes
        assert "generate_blender" in nodes
        assert "qa_generation" in nodes
        assert all(event["payload"].get("phase") for event in node_events)
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


def test_cors_allows_local_frontend_and_rejects_unknown_origin() -> None:
    client = TestClient(app)
    allowed = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    rejected = client.get("/health", headers={"Origin": "https://example.invalid"})
    assert rejected.status_code == 200
    assert "access-control-allow-origin" not in rejected.headers


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


def test_product_issues_humanize_real_asset_warning_codes() -> None:
    status = {
        "status": "completed",
        "warnings": [
            {
                "code": "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
                "message": "ANT_PANEL_5G_001: INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
                "severity": "warning",
            },
            {
                "code": "ASSET_IMPORT_PROCEDURAL_FALLBACK",
                "message": (
                    "TOWER_MONOPOLE_30M used procedural fallback instead of a real GLB import."
                ),
                "severity": "warning",
            },
        ],
        "errors": [],
        "asset_import_summary": {"procedural_fallback_count": 1},
    }

    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(status)
    titles = {issue["title"] for issue in issues}
    assert "Asset interne minimal" in titles
    assert "Fallback procédural d'asset" in titles


def test_product_issues_include_failed_runtime_nodes() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    status = {"status": "completed", "warnings": [], "errors": []}
    events = [
        {
            "event_type": "node_failed",
            "payload": {
                "node": "retrieve_rag_context",
                "phase": "rag",
                "status": "failed",
                "detail": "failed: RuntimeError",
                "errors": ["Qdrant local storage is locked."],
            },
        }
    ]

    issues = _collect_user_issues(status, events)

    assert issues == [
        {
            "title": "Recherche RAG en mode dégradé",
            "severity": "warning",
            "impact": "Qdrant local storage is locked.",
            "recommended_action": (
                "Vérifiez Qdrant ou utilisez un serveur Qdrant externe si plusieurs processus "
                "accèdent au stockage local."
            ),
            "technical_code": "RUNTIME_NODE_FAILED:retrieve_rag_context",
        }
    ]
