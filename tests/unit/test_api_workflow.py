import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service


def test_create_design_api_generates_artifacts(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = client.post(
            "/designs",
            json={
                "requirements_text": (
                    "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
                    "Azimuts : 0°, 120°, 240°. Ajouter câbles, faisceaux et labels."
                ),
                "options": {"detail_level": "high", "generate_variants": False, "use_llm": False},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"

        status_response = client.get(f"/designs/{payload['workflow_id']}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["status"] == "completed"
        assert status["llm_provider"] == "deterministic"
        assert status["llm_fallback_used"] is True
        assert status["rag_context_count"] is not None
        assert status["memory_hits"] is not None
        assert status["memory_context_count"] is not None
        assert status["generation_mode"] in {"real_blender", "fallback_no_blender"}
        assert status["blender_available"] in {True, False}
        assert status["qa_score"] == 1.0
        assert status["structural_qa_passed"] is True
        assert status["expected_objects_present"] is True
        assert status["glb_inspection_summary"]["structural_qa_passed"] is True
        assert status["preview_inspection_summary"]["minimum_resolution_valid"] is True
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
            "cache_hits",
            "cache_misses",
        ]:
            assert key in status["metrics"]
        assert status["download_url"] == f"/designs/{payload['workflow_id']}/download"
        assert Path(status["trace_path"]).exists()
        assert Path(status["artifacts"]["scene_spec"]).exists()
        assert Path(status["artifacts"]["extraction_report"]).exists()
        assert Path(status["artifacts"]["validation_report"]).exists()
        assert Path(status["artifacts"]["quality_gates"]).exists()
        assert Path(status["artifacts"]["qa_report"]).exists()
        assert Path(status["artifacts"]["generation_report"]).exists()
        assert Path(status["artifacts"]["glb_inspection"]).exists()
        assert Path(status["artifacts"]["preview_inspection"]).exists()
        assert Path(status["artifacts"]["memory_recall"]).exists()
        assert Path(status["artifacts"]["metadata"]).exists()
        assert Path(status["artifacts"]["glb"]).exists()
        assert Path(status["artifacts"]["preview"]).exists()
        assert Path(status["artifacts"]["download"]).exists()
        trace = json.loads(Path(status["trace_path"]).read_text(encoding="utf-8"))
        assert trace["workflow_id"] == payload["workflow_id"]
        assert trace["metrics"]["memory_hits"] == status["memory_hits"]
        assert trace["metrics"]["memory_context_count"] == status["memory_context_count"]
        assert (
            trace["metrics"]["total_workflow_duration_ms"]
            == status["total_workflow_duration_ms"]
        )
        assert len(trace["quality_gates"]) == 2
        assert trace["glb_inspection"]["structural_qa_passed"] is True
        assert trace["preview_inspection"]["preview_qa_passed"] is True
        assert any(step["node"] == "memory_writeback" for step in trace["steps"])
    finally:
        workflow_service.outputs_dir = original_outputs


def test_api_status_exposes_structural_qa(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = client.post(
            "/designs",
            json={
                "requirements_text": (
                    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                    "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
                ),
                "options": {"detail_level": "high", "generate_variants": False, "use_llm": False},
            },
        )
        workflow_id = response.json()["workflow_id"]
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
