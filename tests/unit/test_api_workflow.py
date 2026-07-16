import json
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from apps.api.telecom_studio_api.workflow import (
    WorkflowBusyError,
    WorkflowService,
    WorkflowStorageError,
)
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.contracts.validation import ValidationReport
from core.performance import requirements_hash


def test_workflow_admission_is_bounded_and_rejected_work_has_no_orphan(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingOrchestrator:
        extractor = None
        checkpoint_saver = None

        def run(self, **_kwargs):
            started.set()
            release.wait(timeout=5)
            raise RuntimeError("test release")

    service = WorkflowService(
        registry=SimpleNamespace(),  # type: ignore[arg-type]
        outputs_dir=tmp_path,
        orchestrator=BlockingOrchestrator(),  # type: ignore[arg-type]
        scene_edit_agent=SimpleNamespace(),  # type: ignore[arg-type]
        max_concurrent_workflows=1,
        max_pending_workflows=0,
    )
    try:
        accepted = service.create_design("pylône treillis 30m", "high", use_llm=False)
        assert started.wait(timeout=2)

        with pytest.raises(WorkflowBusyError, match="capacité locale"):
            service.create_design("second design", "high", use_llm=False)

        assert [path.name for path in tmp_path.glob("wf_*")] == [accepted["workflow_id"]]
        with service._workflow_operation("wf_lock_cleanup"):
            assert "wf_lock_cleanup" in service._operation_locks
        assert "wf_lock_cleanup" not in service._operation_locks
    finally:
        release.set()
        service.shutdown(wait=True)


def test_create_design_api_exposes_temporary_capacity_pressure(monkeypatch) -> None:
    def reject(*_args, **_kwargs):
        raise WorkflowBusyError("La capacité locale de génération est atteinte.")

    monkeypatch.setattr(workflow_service, "create_design", reject)
    response = TestClient(app).post(
        "/designs",
        json={"requirements_text": "Créer un pylône treillis 30m."},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "5"
    assert "capacité locale" in response.json()["detail"]


def test_create_design_api_exposes_insufficient_local_storage(monkeypatch) -> None:
    def reject(*_args, **_kwargs):
        raise WorkflowStorageError("Espace disque local insuffisant.")

    monkeypatch.setattr(workflow_service, "create_design", reject)
    response = TestClient(app).post(
        "/designs",
        json={"requirements_text": "Créer un pylône treillis 30m."},
    )

    assert response.status_code == 507
    assert response.json()["detail"] == "Espace disque local insuffisant."


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
    assert payload["requirements_hash"] == requirements_hash(
        RequirementSpec.model_validate(payload["requirements"])
    )
    assert payload["errors"][0]["code"] == "LLM_EXTRACTION_ERROR"


def test_create_design_uses_exact_confirmed_requirements(monkeypatch) -> None:
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_type="panel_5g",
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        include_power_cabinet=True,
        include_gps_antenna=True,
        detail_level="high",
    )
    captured: dict = {}

    def _capture(confirmed: RequirementSpec, **kwargs) -> dict:
        captured["requirements"] = confirmed
        captured.update(kwargs)
        return {"workflow_id": "wf_confirmed", "status": "pending"}

    monkeypatch.setattr(workflow_service, "create_design_from_requirements", _capture)
    client = TestClient(app)
    payload = {
        "requirements_text": "Créer le site confirmé.",
        "confirmed_requirements": requirements.model_dump(),
        "confirmed_requirements_hash": requirements_hash(requirements),
        "options": {"detail_level": "high"},
    }

    response = client.post("/designs", json=payload)

    assert response.status_code == 200
    assert response.json() == {"workflow_id": "wf_confirmed", "status": "pending"}
    assert captured["requirements"] == requirements
    assert captured["source_label"] == "confirmed_requirement_spec"
    assert captured["source_text"] == payload["requirements_text"]

    payload["confirmed_requirements_hash"] = "0" * 64
    rejected = client.post("/designs", json=payload)
    assert rejected.status_code == 422


def test_startup_reconciliation_terminates_only_interrupted_workflows(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    running_dir = tmp_path / "wf_interrupted"
    completed_dir = tmp_path / "wf_completed"
    running_dir.mkdir()
    completed_dir.mkdir()
    (running_dir / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": "wf_interrupted",
                "status": "running",
                "errors": [],
                "metrics": {"started_at": "2026-07-15T10:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    completed_payload = {"workflow_id": "wf_completed", "status": "completed"}
    (completed_dir / "status.json").write_text(json.dumps(completed_payload), encoding="utf-8")
    try:
        reconciled = workflow_service.reconcile_interrupted_workflows()
        interrupted_status = json.loads((running_dir / "status.json").read_text())
        events = workflow_service.get_events("wf_interrupted")
    finally:
        workflow_service.outputs_dir = original_outputs
        workflow_service._sync_output_services()  # noqa: SLF001

    assert reconciled == ["wf_interrupted"]
    assert interrupted_status["status"] == "failed"
    assert interrupted_status["metrics"]["terminal_reason"] == "process_interrupted"
    assert interrupted_status["errors"][-1]["code"] == "WORKFLOW_INTERRUPTED"
    assert [event["event_type"] for event in events][-2:] == [
        "user_issue_created",
        "workflow_failed",
    ]
    assert json.loads((completed_dir / "status.json").read_text()) == completed_payload


def test_startup_reconciliation_restores_active_version_after_interrupted_edit(
    tmp_path: Path,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_service._sync_output_services()  # noqa: SLF001
    workflow_id = "wf_interrupted_edit"
    workflow_dir = tmp_path / workflow_id
    workflow_dir.mkdir()
    scene = SceneSpec(
        scene_id=workflow_id,
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                install_height_m=24,
                azimuth_deg=0,
                beamwidth_deg=65,
            )
        ],
        visual_elements=VisualElements(),
    )
    active = workflow_service.versioning.save_version(
        workflow_id,
        scene,
        status="completed",
        artifact_dir=str(workflow_dir / "versions" / "active_artifacts"),
        activate=True,
    )
    active_dir = Path(active.artifact_dir or "")
    active_dir.mkdir(parents=True)
    (active_dir / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "status": "completed",
                "version_id": active.version_id,
                "active_version_id": active.version_id,
                "warnings": [],
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    candidate = workflow_service.versioning.save_version(
        workflow_id,
        scene,
        parent_version_id=active.version_id,
        status="generating",
        activate=False,
    )
    (workflow_dir / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "status": "running",
                "active_version_id": active.version_id,
                "active_operation": {
                    "kind": "edit",
                    "operation_id": "edit_interrupted",
                    "status": "running",
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        reconciled = workflow_service.reconcile_interrupted_workflows()
        restored = workflow_service.get_status(workflow_id)
        events = workflow_service.get_events(workflow_id)
        failed_candidate = workflow_service.versioning.get_version(
            workflow_id, candidate.version_id
        )
    finally:
        workflow_service.outputs_dir = original_outputs
        workflow_service._sync_output_services()  # noqa: SLF001

    assert reconciled == [workflow_id]
    assert restored["status"] == "completed"
    assert restored["active_operation"] is None
    assert restored["active_version_id"] == active.version_id
    assert restored["warnings"][-1]["code"] == "EDIT_INTERRUPTED_ACTIVE_VERSION_RESTORED"
    assert failed_candidate is not None
    assert failed_candidate.status == "failed"
    assert [event["event_type"] for event in events][-2:] == [
        "user_issue_created",
        "edit_patch_rejected",
    ]


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


def test_delete_active_workflow_returns_conflict(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_id = "wf_active_delete"
    (tmp_path / workflow_id).mkdir(parents=True)
    workflow_service._mark_workflow_active(workflow_id)
    client = TestClient(app)
    try:
        response = client.delete(f"/designs/{workflow_id}")
    finally:
        workflow_service._mark_workflow_inactive(workflow_id)
        workflow_service.outputs_dir = original_outputs

    assert response.status_code == 409
    assert "active workflow" in response.json()["detail"]


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


def test_event_stream_cursor_skips_old_terminal_event_for_revision(tmp_path: Path) -> None:
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
        terminal_event = workflow_service.get_events(workflow_id)[-1]
        assert terminal_event["event_type"] == "workflow_completed"

        workflow_service._mark_workflow_active(workflow_id)
        workflow_service._emit_workflow_event(
            workflow_id,
            "edit_patch_created",
            {"edit_id": "edit_cursor", "status": "running"},
        )
        workflow_service._emit_workflow_event(
            workflow_id,
            "edit_patch_applied",
            {"edit_id": "edit_cursor", "status": "completed"},
        )
        workflow_service._mark_workflow_inactive(workflow_id)

        with client.stream(
            "GET",
            f"/designs/{workflow_id}/events/stream?after_event_id={terminal_event['event_id']}",
        ) as stream:
            assert stream.status_code == 200
            body = "".join(stream.iter_text())

        assert "event: workflow_completed" not in body
        assert "event: edit_patch_created" in body
        assert "event: edit_patch_applied" in body
    finally:
        workflow_service._mark_workflow_inactive(workflow_id)
        workflow_service.outputs_dir = original_outputs


def test_download_archive_contains_only_canonical_artifact_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "wf_archive"
    output_dir.mkdir()
    (output_dir / "design.glb").write_bytes(b"glb")
    (output_dir / "status.json").write_text("{}", encoding="utf-8")
    nested_version = output_dir / "versions" / "v1"
    nested_version.mkdir(parents=True)
    (nested_version / "design.glb").write_bytes(b"duplicate")

    workflow_service._make_archive(output_dir)

    with zipfile.ZipFile(output_dir / "artifacts.zip") as archive:
        names = archive.namelist()
    assert names == ["design.glb", "status.json"]


def test_event_stream_fans_out_identical_live_events_to_two_subscribers(
    tmp_path: Path,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_id = "wf_sse_fanout"
    (tmp_path / workflow_id).mkdir(parents=True)
    workflow_service._sync_output_services()
    workflow_service._mark_workflow_active(workflow_id)
    workflow_service._emit_workflow_event(workflow_id, "design_created", {})
    received: list[list[dict]] = [[], []]

    def consume(index: int) -> None:
        received[index] = list(workflow_service.stream_events(workflow_id))

    threads = [threading.Thread(target=consume, args=(index,)) for index in range(2)]
    try:
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with workflow_service._lock:
                subscriber_count = len(workflow_service._event_subscribers.get(workflow_id, {}))
            if subscriber_count == 2:
                break
            time.sleep(0.01)
        assert subscriber_count == 2

        workflow_service._emit_workflow_event(
            workflow_id,
            "node_started",
            {"node": "generate_blender", "status": "running"},
        )
        workflow_service._emit_workflow_event(
            workflow_id,
            "workflow_completed",
            {"node": "workflow", "status": "completed"},
        )
        workflow_service._mark_workflow_inactive(workflow_id)
        for thread in threads:
            thread.join(timeout=5)

        assert all(not thread.is_alive() for thread in threads)
        event_ids = [[event["event_id"] for event in events] for events in received]
        assert event_ids[0] == event_ids[1]
        assert [event["event_type"] for event in received[0]] == [
            "design_created",
            "node_started",
            "workflow_completed",
        ]
    finally:
        workflow_service._mark_workflow_inactive(workflow_id)
        for thread in threads:
            thread.join(timeout=1)
        workflow_service.outputs_dir = original_outputs


def test_failed_terminal_event_observes_persisted_failed_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    terminal_statuses: list[str] = []
    original_emit = workflow_service._emit_workflow_event

    def fail_run(**_kwargs):
        raise RuntimeError("forced runtime failure")

    def record_emit(workflow_id: str, event_type: str, payload: dict) -> dict:
        if event_type == "workflow_failed":
            terminal_statuses.append(workflow_service.get_status(workflow_id)["status"])
        return original_emit(workflow_id, event_type, payload)

    monkeypatch.setattr(workflow_service.orchestrator, "run", fail_run)
    monkeypatch.setattr(workflow_service, "_emit_workflow_event", record_emit)
    try:
        response = workflow_service.create_design(
            requirements_text="Créer un site 5G",
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
    finally:
        workflow_service.outputs_dir = original_outputs

    assert response["status"] == "failed"
    assert terminal_statuses == ["failed"]


def test_completed_terminal_event_observes_persisted_completed_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    terminal_statuses: list[str] = []
    original_emit = workflow_service._emit_workflow_event
    result = SimpleNamespace(
        status="completed",
        total_duration_ms=7,
        generation=None,
        qa_report=None,
        report=SimpleNamespace(warnings=[], errors=[]),
    )

    def persist_result(**kwargs) -> tuple[None, None]:
        workflow_service._write_json(
            kwargs["output_dir"] / "status.json",
            {
                "workflow_id": kwargs["workflow_id"],
                "status": "completed",
                "active_version_id": None,
                "artifacts": {},
            },
        )
        return None, None

    def record_emit(workflow_id: str, event_type: str, payload: dict) -> dict:
        if event_type == "workflow_completed":
            terminal_statuses.append(workflow_service.get_status(workflow_id)["status"])
        return original_emit(workflow_id, event_type, payload)

    monkeypatch.setattr(workflow_service.orchestrator, "run", lambda **_kwargs: result)
    monkeypatch.setattr(workflow_service, "_persist_initial_result", persist_result)
    monkeypatch.setattr(workflow_service, "_emit_workflow_event", record_emit)
    try:
        response = workflow_service.create_design(
            requirements_text="Créer un site 5G",
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
    finally:
        workflow_service.outputs_dir = original_outputs

    assert response["status"] == "completed"
    assert terminal_statuses == ["completed"]


def test_failed_initial_version_is_persisted_but_never_activated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_service._sync_output_services()
    workflow_id = "wf_failed_version"
    output_dir = tmp_path / workflow_id
    output_dir.mkdir(parents=True)
    scene = SceneSpec(
        scene_id=workflow_id,
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                install_height_m=24,
                azimuth_deg=0,
                beamwidth_deg=65,
            )
        ],
        visual_elements=VisualElements(),
    )
    result = SimpleNamespace(
        scene=scene,
        status="failed",
        qa_report=None,
        generation=None,
        report=ValidationReport(
            design_id=workflow_id,
            status="failed",
            score=0.0,
            checks={},
            warnings=[],
            errors=[],
        ),
    )

    def write_status(
        workflow_id_: str,
        status: str,
        target_dir: Path,
        _result,
        version_id: str | None = None,
        active_version_id: str | None = None,
    ) -> None:
        workflow_service._write_json(
            target_dir / "status.json",
            {
                "workflow_id": workflow_id_,
                "status": status,
                "version_id": version_id,
                "active_version_id": active_version_id,
                "artifacts": {},
            },
        )

    monkeypatch.setattr(workflow_service, "_write_result_files", lambda *_args: None)
    monkeypatch.setattr(workflow_service, "_write_status", write_status)
    monkeypatch.setattr(workflow_service, "_make_archive", lambda *_args: None)
    try:
        version_id, active_version_id = workflow_service._persist_initial_result(
            workflow_id=workflow_id,
            output_dir=output_dir,
            requirements_text="failed result",
            result=result,
            edit_description="initial",
        )
        versions = workflow_service.versioning.list_versions(workflow_id)
    finally:
        workflow_service.outputs_dir = original_outputs

    assert version_id is not None
    assert active_version_id is None
    assert workflow_service.versioning.active_version_id(workflow_id) is None
    assert len(versions) == 1
    assert versions[0].status == "failed"
    assert versions[0].active is False


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
