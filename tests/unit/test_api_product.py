"""Tests for product-oriented API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from apps.api.telecom_studio_api.product import _studio_warnings
from apps.api.telecom_studio_api.runtime_contract import memory_status


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
        assert summary["asset_inventory_status"] == "qualified_mixed_catalog"
        assert summary["generation_eligible_asset_count"] == 10
        assert summary["reference_only_asset_count"] == 2
        assert summary["asset_count"] == 12
        assert summary["real_glb_asset_count"] == 12
        assert summary["missing_file_count"] == 0
        assert not any(
            warning.get("technical_code") == "STUDIO_NO_QUALIFIED_ASSETS"
            for warning in summary["warnings"]
        )
        assert "blender_available" in summary
        assert isinstance(summary["llm_available"], bool)
        assert summary["rag_embedding_provider"]
        assert summary["rag_status"] in {
            "primary_nvidia_embedding",
            "configured_unverified",
            "configured_but_last_operation_failed",
            "local_sentence_transformers_explicit",
            "deterministic_hash_fallback",
            "custom_provider",
        }
        assert isinstance(summary["rag_degraded"], bool)
        assert summary["rag_reranker_status"] in {
            "passthrough_no_rerank",
            "explicit_local_reranker",
            "primary_nvidia_reranker",
            "degraded_passthrough",
            "not_loaded",
            "custom",
        }
        assert summary["rag_reranker_provider"] in {
            "nvidia",
            "local",
            "passthrough",
            "disabled",
            None,
        }
        assert "rag_reranker_model" in summary
        assert "rag_reranker_degraded_reason" in summary
        assert summary["rag_operational_status"] in {
            "unverified",
            "operational",
            "failed",
        }
        assert "rag_last_operation" in summary
        assert summary["rag_reindex_url"] == "/rag/reindex"
        assert summary["memory_status"] in {"available", "disabled"} or summary[
            "memory_status"
        ].startswith("degraded:")
        assert isinstance(summary["workflow_memory_count"], int)
        assert "memory_vector_status" in summary
        assert isinstance(summary["memory_vector_errors"], list)
        assert summary["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert summary["runtime_capabilities"]["websocket_runtime"] is False
        assert any(action["action"] == "cancel" for action in summary["unsupported_actions"])
        assert isinstance(summary["warnings"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


class _MemoryStatusProbe:
    def __init__(self, latest: dict, compatibility: dict) -> None:
        self.latest = latest
        self.compatibility = compatibility

    def stats(self) -> dict:
        return {}

    def index_health(self) -> dict:
        return {
            "latest_index_result": self.latest,
            "vector_compatibility": self.compatibility,
        }


def test_memory_status_distinguishes_migration_from_index_failure() -> None:
    migration = memory_status(
        _MemoryStatusProbe(
            {"status": "not_indexed", "errors": []},
            {"status": "migration_pending", "degraded": True},
        )
    )
    assert migration["memory_status"] == "degraded:vector_migration_pending"
    assert migration["memory_vector_status"] == "migration_pending"
    assert migration["memory_vector_errors"] == []

    failure = memory_status(
        _MemoryStatusProbe(
            {"status": "failed", "errors": ["provider_failure"]},
            {"status": "compatible", "degraded": False},
        )
    )
    assert failure["memory_status"] == "degraded:vector_index"
    assert failure["memory_vector_status"] == "failed"
    assert failure["memory_vector_errors"] == ["vector_index_write_failed"]


def test_studio_warnings_distinguish_unverified_and_failed_rag() -> None:
    inventory = {"entries": [], "missing_file_count": 0}
    unverified = _studio_warnings(
        inventory,
        {
            "degraded": True,
            "status": "configured_unverified",
            "reranker_degraded_reason": None,
        },
    )
    assert unverified[0]["title"] == "RAG configuré mais non vérifié"
    assert "recherche de contrôle" in unverified[0]["recommended_action"]

    failed = _studio_warnings(
        inventory,
        {
            "degraded": True,
            "status": "configured_but_last_operation_failed",
            "reranker_degraded_reason": None,
        },
    )
    assert failed[0]["title"] == "RAG indisponible lors du dernier appel"
    assert "Configurer NVIDIA_API_KEY" not in failed[0]["recommended_action"]


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
        assert summary["runtime_capabilities"]["workflow_id_source"] == "workflow_id"
        assert any(
            action["action"] == "websocket_runtime" for action in summary["unsupported_actions"]
        )
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
        workflow_service._emit_workflow_event(
            workflow_id,
            "workflow_failed",
            {
                "phase": "runtime",
                "node": "stale_recovery_event",
                "status": "failed",
                "error": "STALE_EVENT_FOR_PROJECTION_TEST",
            },
        )
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()

        assert operation["workflow_id"] == workflow_id
        assert operation["status"] == "completed"
        assert operation["current_operation"]
        assert operation["next_recommended_action"]
        assert operation["progress_indicator"] == "done"
        assert operation["phase"] == "workflow"
        assert operation["human_label"] == "Workflow terminé"
        assert operation["progress_message"]
        assert operation["progress_label"] == "Terminé"
        assert operation["is_running"] is False
        assert operation["is_terminal"] is True
        assert operation["last_event_at"]
        assert "open_viewer" in operation["available_actions"]
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
        assert operation["event_source"] == "push_sse"
        assert operation["state_source"] == "status"
        assert operation["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert operation["runtime_capabilities"]["can_cancel"] is False
        assert any(action["action"] == "pause" for action in operation["unsupported_actions"])
    finally:
        workflow_service.outputs_dir = original_outputs


def test_current_operation_prefers_persisted_edit_over_old_terminal_event(
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
        previous = workflow_service._begin_active_operation(
            workflow_id,
            operation_id="edit_test",
            kind="edit",
            human_label="Révision du design",
        )

        status = client.get(f"/designs/{workflow_id}").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()

        assert status["status"] == "running"
        assert status["active_operation"]["operation_id"] == "edit_test"
        assert operation["human_label"] == "Révision du design"
        assert operation["state_source"] == "persisted_active_operation"
        assert operation["is_running"] is True
        assert operation["is_terminal"] is False
        workflow_service._restore_status_after_operation(
            workflow_id, previous, operation_id="edit_test"
        )
        assert client.get(f"/designs/{workflow_id}").json()["status"] == "completed"
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
        assert bundle["primary_glb_url"]
        assert bundle["preview_url"]
        assert bundle["report_url"]
        assert bundle["metadata_url"]
        assert bundle["requirements_spec_url"]
        assert bundle["extraction_report_url"]
        assert bundle["scene_spec_url"]
        assert bundle["qa_report_url"]
        assert bundle["generation_report_url"]
        assert bundle["geometry_validation_url"]
        assert bundle["requirement_coverage_url"]
        assert bundle["completion_certificate_url"]
        assert bundle["requirement_coverage_passed"] is True
        assert bundle["requirement_coverage_ratio"] == 1.0
        assert bundle["completion_certificate_status"] == "issued"
        assert bundle["rag_evidence_url"]
        assert bundle["llm_provider"] == "deterministic"
        assert bundle["extraction_provider"] == "deterministic"
        assert isinstance(bundle["llm_available"], bool)
        assert bundle["llm_fallback_used"] is True
        assert bundle["llm_fallback_reason"] == "deterministic_extraction_requested"
        assert bundle["rag_context_count"] == 0 or isinstance(bundle["rag_context_count"], int)
        assert isinstance(bundle["rag_planning_summary"], dict)
        assert bundle["rag_planning_summary"]["rag_used_for_extraction"] is False
        assert "rag_planning_mode" in bundle["rag_planning_summary"]
        assert isinstance(bundle["rag_planning_summary"]["controlled_hint_fields"], list)
        assert "rag_reranker_status" in bundle
        assert "rag_reranker_provider" in bundle
        assert "rag_reranker_model" in bundle
        assert "rag_reranker_degraded_reason" in bundle
        assert bundle["memory_context_count"] == 0 or isinstance(
            bundle["memory_context_count"], int
        )
        assert bundle["qa_summary"]["mesh_qa_level"]
        assert isinstance(bundle["qa_summary"]["checks_passed"], list)
        assert isinstance(bundle["qa_summary"]["checks_failed"], list)
        assert bundle["primary_glb_url"].startswith(f"/designs/{workflow_id}/artifacts/glb")
        assert "/Users/" not in bundle["primary_glb_url"]
        assert bundle["runtime_capabilities"]["workflow_id_source"] == "workflow_id"
        assert bundle["runtime_capabilities"]["websocket_runtime"] is False
        assert any(action["action"] == "retry" for action in bundle["unsupported_actions"])
        if bundle["mesh_qa_level"] == "mesh_level_basic":
            assert any("mesh_level_basic" in item for item in bundle["limitations"])
        assert "open_viewer" in bundle["available_actions"]
        assert isinstance(bundle["human_warnings_count"], int)
        assert isinstance(bundle["human_errors_count"], int)
        assert isinstance(bundle["viewer_artifacts"], list)
        names = {a["name"] for a in bundle["viewer_artifacts"]}
        assert "design.glb" in names
        assert "preview.png" in names
        assert "scene_metadata.json" in names
        assert "requirements_spec.json" in names
        assert "extraction_report.json" in names
        assert "qa_report.json" in names
        assert "geometry_validation.json" in names
        assert "rag_evidence.json" in names
        for artifact in bundle["viewer_artifacts"]:
            assert artifact["url"].startswith(f"/designs/{workflow_id}/artifacts/")
            assert "/Users/" not in artifact["url"]
            assert isinstance(artifact["available"], bool)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_failed_blender_workflow_does_not_advertise_viewer_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    monkeypatch.setattr(
        workflow_service.orchestrator.blender_runner,
        "_resolve_blender_binary",
        lambda: None,
    )
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

        assert response["status"] == "failed"
        status = client.get(f"/designs/{workflow_id}").json()
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        events = client.get(f"/designs/{workflow_id}/events").json()

        assert "glb" not in status["artifacts"]
        assert "preview" not in status["artifacts"]
        assert bundle["primary_glb_url"] is None
        assert bundle["preview_url"] is None
        assert not any(event["event_type"] == "artifact_ready" for event in events)
        availability = {
            artifact["name"]: artifact["available"] for artifact in bundle["viewer_artifacts"]
        }
        assert availability["design.glb"] is False
        assert availability["preview.png"] is False
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
        assert timeline["event_source"] == "push_sse"
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
            assert "node" in step
            assert "label" in step
            assert "human_label" in step
            assert "progress_message" in step
            assert "phase" in step
            assert "status" in step
            assert "started_at" in step
            assert "completed_at" in step
            assert "duration_ms" in step
            assert "warnings_count" in step
            assert "errors_count" in step
            assert "artifact_refs" in step
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
            if event["event_type"]
            in {"node_started", "node_completed", "node_failed", "node_skipped"}
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
        assert all(event.get("workflow_id") == workflow_id for event in events)
        assert all(event.get("timestamp") for event in events)
        assert all(event.get("event_id") for event in events)
        assert all(event.get("event_source") == "workflow_events_jsonl" for event in events)
        required_payload_fields = {
            "phase",
            "node",
            "human_label",
            "progress_message",
            "status",
            "duration_ms",
            "warnings",
            "errors",
            "artifact_refs",
        }
        assert all(required_payload_fields.issubset(event["payload"]) for event in events)
        assert "node_started" in event_types
        assert "artifact_ready" in event_types
        assert "qa_completed" in event_types
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


def test_invalid_design_has_frontend_readable_failure_contract(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text="Créer un pylône 300m avec 20 secteurs",
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        assert response["status"] == "failed"

        status = client.get(f"/designs/{workflow_id}").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()
        timeline = client.get(f"/designs/{workflow_id}/timeline-summary").json()
        issues = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert status["status"] == "failed"
        assert any(error["code"] == "INVALID_REQUIREMENTS" for error in status["errors"])
        assert operation["is_terminal"] is True
        assert operation["progress_label"] == "Échec"
        assert "retry_with_changes" in operation["available_actions"]
        assert operation["runtime_capabilities"]["can_retry_same_workflow"] is False
        assert any(action["action"] == "retry" for action in operation["unsupported_actions"])
        assert timeline["timeline_steps"][-1]["status"] == "failed"
        assert issues["human_readable_issues"]
        assert any(
            issue["technical_code"] == "INVALID_REQUIREMENTS"
            for issue in issues["human_readable_issues"]
        )
    finally:
        workflow_service.outputs_dir = original_outputs


def test_document_pack_capabilities_expose_limited_frontend_contract() -> None:
    client = TestClient(app)

    payload = client.get("/document-packs/capabilities").json()

    assert payload["document_pack_status"] == "limited"
    assert payload["supported_upload_format"] == "zip_or_multiple_files"
    assert payload["supported_inputs"]["upload"] == "zip_or_multiple_files"
    assert ".pdf" in payload["supported_extensions"]
    assert payload["limits"]["max_zip_size_mb"] == 80
    assert payload["max_size"]["zip_mb"] == 80
    assert "available_tools" in payload
    assert "disabled_tools" in payload
    assert isinstance(payload["limitations"], list)
    assert payload["next_action"]
    assert payload["truth"]["advanced_ingestion"] is False
    assert payload["truth"]["docling_default_enabled"] is False
    assert "pdf_text_extraction" in payload["capabilities"]
    # Backwards-compatible flat keys are still present.
    assert "pdf_text_extraction" in payload


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


def test_frontend_v1_openapi_contract_has_typed_public_surfaces() -> None:
    schema = app.openapi()

    assert (
        schema["paths"]["/designs"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["items"]["$ref"]
        == "#/components/schemas/DesignListSummary"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/events"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["items"]["$ref"]
        == "#/components/schemas/WorkflowEventView"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/versions"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["items"]["$ref"]
        == "#/components/schemas/PublicVersionInfo"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/versions/{version_id}/rollback"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RollbackVersionResponse"
    )
    assert (
        schema["paths"]["/document-packs/capabilities"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/DocumentPackCapabilitiesView"
    )
    assert (
        schema["paths"]["/assets/inventory"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/AssetInventoryResponse"
    )
    assert "RuntimeCapabilities" in schema["components"]["schemas"]
    assert "UnsupportedAction" in schema["components"]["schemas"]
    assert (
        schema["paths"]["/document-packs/{pack_id}/generate-design"]["post"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DocumentPackGenerateDesignResponse"
    )


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


def test_product_issues_humanize_ai_rf_and_tower_warning_codes() -> None:
    status = {
        "status": "completed",
        "warnings": [
            {
                "code": "LLM_FIELD_REPAIRED",
                "message": "include_gps_antenna restored from deterministic baseline.",
                "severity": "warning",
            },
            {
                "code": "RF_BEAMWIDTH_NARROW",
                "message": "Beamwidth 65.0° may be too narrow for 3 sectors.",
                "severity": "warning",
            },
            {
                "code": "TOWER_PLATFORM_RECOMMENDED",
                "message": "Tower platform recommended for equipment access.",
                "severity": "warning",
            },
            {
                "code": "TOWER_AVIATION_MARKING_REVIEW_REQUIRED",
                "message": "Applicable aviation rules require review.",
                "severity": "warning",
            },
        ],
        "errors": [],
    }

    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(status)
    titles = {issue["title"] for issue in issues}
    assert "Champ IA réparé par le backend" in titles
    assert "Beamwidth à vérifier" in titles
    assert "Plateforme pylône recommandée" in titles
    assert "Balisage aviation à vérifier" in titles


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


def test_product_issues_expose_bounded_planning_fallback_without_degrading_3d() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(
        {
            "status": "completed",
            "generation_mode": "real_blender",
            "warnings": [],
            "errors": [],
            "rag_planning_summary": {
                "decision_fallback_used": True,
                "decision_fallback_reason": "provider_timeout",
            },
        }
    )

    planning_issue = next(
        issue
        for issue in issues
        if issue["technical_code"] == "PLANNING_DECISION_FALLBACK_INFERRED"
    )
    assert planning_issue["severity"] == "info"
    assert "valeurs déjà validées" in planning_issue["impact"]
