import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from core.contracts.requirements import RequirementSpec


def test_create_design_api_generates_artifacts(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°. Ajouter câbles, faisceaux et labels."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        assert response["status"] == "completed"

        status = client.get(f"/designs/{response['workflow_id']}").json()
        internal_status = workflow_service.get_status(response["workflow_id"])
        assert status["status"] == "completed"
        assert status["created_at"].endswith("Z")
        assert status["extraction_provider"] == "deterministic"
        assert status["llm_provider"] == "deterministic"
        assert isinstance(status["llm_available"], bool)
        assert status["llm_fallback_used"] is True
        assert status["llm_fallback_reason"] == "deterministic_extraction_requested"
        assert status["rag_context_count"] is not None
        assert status["memory_hits"] is not None
        assert status["memory_context_count"] is not None
        assert status["generation_mode"] in {"real_blender", "fallback_no_blender"}
        assert status["blender_available"] in {True, False}
        assert status["qa_score"] == 1.0
        assert status["tower_characteristics_summary"]["structure"] == "lattice"
        assert status["tower_characteristics_summary"]["base_width_m"] == 4.0
        assert status["structural_qa_passed"] is True
        assert status["expected_objects_present"] is True
        assert status["glb_inspection_summary"]["structural_qa_passed"] is True
        assert status["geometry_validation_summary"]["status"] == "passed"
        assert status["preview_inspection_summary"]["minimum_resolution_valid"] is True
        assert status["asset_import_summary"]["asset_count"] >= 4
        assert status["asset_import_summary"]["asset_file_exists_count"] >= 1
        assert status["asset_imports"]
        assert any(
            record["asset_id"] == "ANT_PANEL_5G_001" and record["asset_file_exists"] is True
            for record in status["asset_imports"]
        )
        assert all(
            record["import_mode"]
            in {
                "imported_glb",
                "procedural_fallback",
                "missing_file",
                "parametric_generated",
                "internal_project_generated",
            }
            for record in status["asset_imports"]
        )
        assert status["total_duration_ms"] >= 0
        assert status["total_workflow_duration_ms"] >= 0
        assert status["metrics"]["trace_steps"] >= 8
        assert len(status["quality_gates"]) == 2
        assert all(gate["passed"] for gate in status["quality_gates"])
        for key in [
            "total_workflow_duration_ms",
            "rag_duration_ms",
            "planning_duration_ms",
            "blender_duration_ms",
            "qa_duration_ms",
            "memory_duration_ms",
            "memory_hits",
            "artifact_size_bytes",
            "requirements_hash",
            "scene_spec_hash",
            "asset_manifest_hash",
            "knowledge_index_hash",
            "geometry_validation_passed",
            "cache_hits",
            "cache_misses",
        ]:
            assert key in status["metrics"]
        assert status["download_url"] == f"/designs/{response['workflow_id']}/download"
        assert status["trace_path"] is None
        assert status["trace_url"] == f"/designs/{response['workflow_id']}/artifacts/trace"
        assert status["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert status["runtime_capabilities"]["websocket_runtime"] is False
        assert any(action["action"] == "human_in_loop" for action in status["unsupported_actions"])
        designs = client.get("/designs").json()
        assert designs[0]["workflow_id"] == response["workflow_id"]
        assert designs[0]["created_at"].endswith("Z")
        for artifact_url in status["artifacts"].values():
            assert artifact_url.startswith(f"/designs/{response['workflow_id']}/")
            assert "/Users/" not in artifact_url
        assert status["asset_imports"]
        assert all("resolved_path" not in record for record in status["asset_imports"])
        assert "/Users/" not in str(status["asset_imports"])
        assert Path(internal_status["trace_path"]).exists()
        assert Path(internal_status["artifacts"]["scene_spec"]).exists()
        assert Path(internal_status["artifacts"]["extraction_report"]).exists()
        assert Path(internal_status["artifacts"]["validation_report"]).exists()
        assert Path(internal_status["artifacts"]["quality_gates"]).exists()
        assert Path(internal_status["artifacts"]["qa_report"]).exists()
        assert Path(internal_status["artifacts"]["generation_report"]).exists()
        assert Path(internal_status["artifacts"]["rag_evidence"]).exists()
        assert Path(internal_status["artifacts"]["glb_inspection"]).exists()
        assert Path(internal_status["artifacts"]["geometry_validation"]).exists()
        assert Path(internal_status["artifacts"]["preview_inspection"]).exists()
        assert Path(internal_status["artifacts"]["memory_recall"]).exists()
        assert Path(internal_status["artifacts"]["metadata"]).exists()
        assert Path(internal_status["artifacts"]["glb"]).exists()
        assert Path(internal_status["artifacts"]["preview"]).exists()
        assert Path(internal_status["artifacts"]["download"]).exists()
        rag_evidence = json.loads(
            Path(internal_status["artifacts"]["rag_evidence"]).read_text(encoding="utf-8")
        )
        assert rag_evidence["rag_used_for_extraction"] is False
        assert isinstance(rag_evidence["controlled_hint_fields"], list)
        assert "rag_reranker_status" in rag_evidence
        scene_status = json.loads(
            Path(internal_status["artifacts"]["scene_spec"]).read_text(encoding="utf-8")
        )
        assert scene_status["visual_elements"]["include_power_cabinet"] is False
        assert scene_status["visual_elements"]["include_gps_antenna"] is False
        trace = json.loads(Path(internal_status["trace_path"]).read_text(encoding="utf-8"))
        assert trace["workflow_id"] == response["workflow_id"]
        assert trace["metrics"]["memory_hits"] == status["memory_hits"]
        assert trace["metrics"]["memory_context_count"] == status["memory_context_count"]
        assert (
            trace["metrics"]["total_workflow_duration_ms"] == status["total_workflow_duration_ms"]
        )
        assert len(trace["quality_gates"]) == 2
        assert trace["glb_inspection"]["structural_qa_passed"] is True
        assert trace["geometry_validation"]["status"] == "passed"
        assert trace["preview_inspection"]["preview_qa_passed"] is True
        assert any(step["node"] == "memory_writeback" for step in trace["steps"])
    finally:
        workflow_service.outputs_dir = original_outputs


def test_api_status_exposes_structural_qa(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        status = client.get(f"/designs/{workflow_id}").json()

        assert status["structural_qa_passed"] is True
        assert status["expected_objects_present"] is True
        assert status["glb_inspection_summary"]["inspection_mode"] in {
            "glb_parse",
            "metadata_fallback",
        }
        assert status["preview_inspection_summary"]["format"] == "png"
    finally:
        workflow_service.outputs_dir = original_outputs


def test_create_design_async_status_is_available_immediately(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = client.post(
            "/designs",
            json={
                "requirements_text": (
                    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                    "Azimuts : 0°, 120°, 240°."
                ),
                "options": {"detail_level": "high", "use_llm": False},
            },
        )
        assert response.status_code == 200
        workflow_id = response.json()["workflow_id"]

        status_response = client.get(f"/designs/{workflow_id}")

        assert status_response.status_code == 200
        assert status_response.json()["status"] in {"pending", "running", "completed"}
        for _ in range(60):
            status = client.get(f"/designs/{workflow_id}").json()["status"]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.1)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_geometry_validation_report_written(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        internal_status = workflow_service.get_status(workflow_id)
        geometry_path = Path(internal_status["artifacts"]["geometry_validation"])

        assert geometry_path.exists()
        payload = json.loads(geometry_path.read_text(encoding="utf-8"))
        assert payload["status"] == "passed"
        assert payload["checks"]["antenna_count_valid"] is True
    finally:
        workflow_service.outputs_dir = original_outputs


def test_api_design_uses_configured_llm_provider_when_enabled(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    extractor = workflow_service.orchestrator.extractor
    original_provider = extractor.provider
    original_provider_name = extractor.provider_name
    original_enabled = extractor.enabled
    provider = RecordingRequirementProvider()
    workflow_service.outputs_dir = tmp_path
    extractor.provider = provider
    extractor.provider_name = "groq:test-provider"
    extractor.enabled = True
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°. Ajouter boîte alimentation et GPS."
            ),
            detail_level="high",
            use_llm=True,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        status = client.get(f"/designs/{workflow_id}").json()

        assert provider.calls == 1
        assert status["llm_provider"] == "groq:test-provider"
        assert status["extraction_provider"] == "groq"
        assert status["llm_available"] is True
        assert status["llm_fallback_used"] is False
        assert status["llm_fallback_reason"] is None
        requirements = client.get(f"/designs/{workflow_id}/artifacts/requirements_spec").json()
        scene = client.get(f"/designs/{workflow_id}/artifacts/scene_spec").json()
        extraction_report = client.get(f"/designs/{workflow_id}/artifacts/extraction_report").json()
        assert requirements["include_power_cabinet"] is True
        assert requirements["include_gps_antenna"] is True
        assert scene["visual_elements"]["include_power_cabinet"] is True
        assert scene["visual_elements"]["include_gps_antenna"] is True
        assert extraction_report["mode"] == "structured_llm"
        assert extraction_report["provider"] == "groq:test-provider"
        assert extraction_report["model_name"] == "test-provider"
        assert extraction_report["validated_schema"] is True
        assert extraction_report["schema_name"] == "RequirementSpec"
        assert extraction_report["rag_used_for_extraction"] is False
        assert extraction_report["rag_context_count"] == status["rag_context_count"]
        assert extraction_report["critical_fields"]["include_power_cabinet"] is True
        assert extraction_report["critical_fields"]["include_gps_antenna"] is True
    finally:
        workflow_service.outputs_dir = original_outputs
        extractor.provider = original_provider
        extractor.provider_name = original_provider_name
        extractor.enabled = original_enabled


def test_api_design_with_use_llm_false_does_not_call_configured_provider(
    tmp_path: Path,
) -> None:
    original_outputs = workflow_service.outputs_dir
    extractor = workflow_service.orchestrator.extractor
    original_provider = extractor.provider
    original_provider_name = extractor.provider_name
    original_enabled = extractor.enabled
    provider = RecordingRequirementProvider()
    workflow_service.outputs_dir = tmp_path
    extractor.provider = provider
    extractor.provider_name = "groq:test-provider"
    extractor.enabled = True
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
        status = client.get(f"/designs/{workflow_id}").json()

        assert provider.calls == 0
        assert status["llm_provider"] == "deterministic"
        assert status["extraction_provider"] == "deterministic"
        assert status["llm_available"] is True
        assert status["llm_fallback_used"] is True
        assert status["llm_fallback_reason"] == "deterministic_extraction_requested"
    finally:
        workflow_service.outputs_dir = original_outputs
        extractor.provider = original_provider
        extractor.provider_name = original_provider_name
        extractor.enabled = original_enabled


def test_parse_requirements_api_returns_provider_and_fallback_error() -> None:
    extractor = workflow_service.orchestrator.extractor
    original_provider = extractor.provider
    original_provider_name = extractor.provider_name
    original_enabled = extractor.enabled
    extractor.provider = FailingRequirementProvider()
    extractor.provider_name = "groq:test-provider"
    extractor.enabled = True
    client = TestClient(app)
    try:
        response = client.post(
            "/requirements/parse",
            json={
                "requirements_text": (
                    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                    "Azimuts : 0, 120, 240."
                ),
                "detail_level": "high",
                "use_llm": True,
            },
        )
    finally:
        extractor.provider = original_provider
        extractor.provider_name = original_provider_name
        extractor.enabled = original_enabled

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["extraction_provider"] == "fallback"
    assert payload["fallback_used"] is True
    assert payload["llm_fallback_reason"] == "RuntimeError: forced provider failure"
    assert payload["requirements"]["tower_type"] == "lattice_tower"
    assert payload["errors"][0]["code"] == "LLM_EXTRACTION_ERROR"


def test_assets_inventory_route_is_not_shadowed() -> None:
    client = TestClient(app)

    response = client.get("/assets/inventory")

    assert response.status_code == 200
    payload = response.json()
    assert "asset_count" in payload
    assert "procedural_generation_required" in payload
    assert payload["status"] == "ready_for_import"
    assert payload["real_glb_asset_count"] == 12
    assert all(entry["asset_import_mode"] == "imported_glb" for entry in payload["entries"])
    assert any(entry["asset_import_mode"] == "imported_glb" for entry in payload["entries"])


def test_design_artifact_endpoint_serves_active_and_version_files(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        status = client.get(f"/designs/{workflow_id}").json()
        version_id = status["active_version_id"]

        scene_response = client.get(f"/designs/{workflow_id}/artifacts/scene_spec")
        version_scene_response = client.get(
            f"/designs/{workflow_id}/artifacts/scene_spec?version_id={version_id}"
        )
        traversal_response = client.get(f"/designs/{workflow_id}/artifacts/../../pyproject")

        assert scene_response.status_code == 200
        assert scene_response.json()["network_type"] == "5G"
        assert version_scene_response.status_code == 200
        assert version_scene_response.json()["network_type"] == "5G"
        assert traversal_response.status_code == 404
    finally:
        workflow_service.outputs_dir = original_outputs


def test_global_exception_handler_returns_json_500(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    original_get_status = workflow_service.get_status
    workflow_service.outputs_dir = tmp_path

    def explode(_workflow_id: str) -> dict:
        raise RuntimeError("forced test failure")

    workflow_service.get_status = explode  # type: ignore[method-assign]
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.get("/designs/wf_000000000000")
    finally:
        workflow_service.get_status = original_get_status  # type: ignore[method-assign]
        workflow_service.outputs_dir = original_outputs

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "Internal server error"
    assert payload["type"] == "RuntimeError"
    assert response.headers["x-request-id"]


def test_event_stream_unknown_workflow_returns_404(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = client.get("/designs/wf_000000000000/events/stream")
    finally:
        workflow_service.outputs_dir = original_outputs

    assert response.status_code == 404


def test_event_stream_replays_complete_push_sse_events(tmp_path: Path) -> None:
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

        with client.stream("GET", f"/designs/{workflow_id}/events/stream") as stream:
            assert stream.status_code == 200
            body = "".join(stream.iter_text())

        assert "event: node_started" in body
        assert "event: workflow_completed" in body
        events = [
            json.loads(line.removeprefix("data: "))
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        assert events
        assert all(event["workflow_id"] == workflow_id for event in events)
        assert all(event["timestamp"] for event in events)
        assert all(event["event_id"] for event in events)
        assert all(event["event_source"] == "push_sse" for event in events)
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
        assert any(event["event_type"] == "artifact_ready" for event in events)
    finally:
        workflow_service.outputs_dir = original_outputs


class RecordingRequirementProvider:
    def __init__(self) -> None:
        self.calls = 0

    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        self.calls += 1
        return RequirementSpec(
            network_type="5G",
            site_type="telecom_site",
            tower_type="lattice_tower",
            tower_height_m=30,
            sector_count=3,
            antenna_type="panel_5g",
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
            mechanical_tilt_deg=3,
            electrical_tilt_deg=0,
            beamwidth_deg=65,
            include_rru=True,
            include_cables=True,
            include_beams=True,
            include_labels=True,
            include_power_cabinet=True,
            include_gps_antenna=True,
            detail_level=detail_level,
            warnings=[],
        )


class FailingRequirementProvider:
    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        raise RuntimeError("forced provider failure")
