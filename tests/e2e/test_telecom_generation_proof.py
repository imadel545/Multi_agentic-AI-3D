import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service

E2E_PROMPT = (
    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
    "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, boîte alimentation, "
    "dalle béton, GPS, labels, couleurs professionnelles et export GLB."
)


def test_designs_contract_proves_product_e2e_generation(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        create_response = client.post(
            "/designs",
            json={
                "requirements_text": E2E_PROMPT,
                "options": {"detail_level": "high", "use_llm": False},
            },
        )
        assert create_response.status_code == 200
        workflow_id = create_response.json()["workflow_id"]
        assert workflow_id.startswith("wf_")

        status = _wait_for_terminal_status(client, workflow_id)
        assert status["status"] in {"completed", "failed"}
        assert status["trace_path"] is None
        assert status["extraction_provider"] == "deterministic"
        assert status["llm_provider"] == "deterministic"
        assert isinstance(status["llm_available"], bool)
        assert status["llm_fallback_used"] is True
        assert status["llm_fallback_reason"] == "deterministic_extraction_requested"
        assert status["rag_context_count"] is not None
        assert status["memory_context_count"] is not None
        assert status["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert any(action["action"] == "cancel" for action in status["unsupported_actions"])
        assert status["generation_mode"] in {
            "real_blender",
            "fallback_no_blender",
            "fallback_blender_timeout",
            "fallback_blender_error",
            "fallback_blender_missing_artifacts",
        }

        requirements = client.get(f"/designs/{workflow_id}/artifacts/requirements_spec").json()
        assert requirements["network_type"] == "5G"
        assert requirements["tower_type"] == "lattice_tower"
        assert requirements["tower_height_m"] == 30
        assert requirements["sector_count"] == 3
        assert requirements["antenna_install_height_m"] == 24
        assert requirements["azimuths_deg"] == [0.0, 120.0, 240.0]
        assert requirements["include_rru"] is True
        assert requirements["include_cables"] is True
        assert requirements["include_labels"] is True
        assert requirements["include_power_cabinet"] is True
        assert requirements["include_gps_antenna"] is True
        assert requirements["tower_characteristics"]["foundation_type"] == "concrete_pad"

        scene_plan = client.get(f"/designs/{workflow_id}/artifacts/scene_spec").json()
        assert scene_plan["network_type"] == "5G"
        assert scene_plan["tower"]["height_m"] == 30
        assert len(scene_plan["sectors"]) == 3
        assert scene_plan["visual_elements"]["include_power_cabinet"] is True
        assert scene_plan["visual_elements"]["include_gps_antenna"] is True
        assert any(
            accessory["asset_type"] == "cabinet"
            for accessory in scene_plan.get("accessory_assets", [])
        )
        assert any(
            accessory["asset_type"] == "gps" for accessory in scene_plan.get("accessory_assets", [])
        )

        validation_report = client.get(f"/designs/{workflow_id}/artifacts/validation_report").json()
        assert validation_report["status"] in {"passed", "failed"}
        assert validation_report["checks"]["tower_height_valid"] is True
        assert validation_report["checks"]["sector_count_valid"] is True
        assert validation_report["checks"]["antenna_height_valid"] is True
        assert validation_report["checks"]["azimuths_valid"] is True
        assert validation_report["checks"]["power_cabinet_asset_present_when_requested"] is True

        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert bundle["workflow_id"] == workflow_id
        assert bundle["scene_spec_url"].startswith(f"/designs/{workflow_id}/artifacts/scene_spec")
        assert bundle["qa_report_url"].startswith(f"/designs/{workflow_id}/artifacts/qa_report")
        assert bundle["generation_report_url"].startswith(
            f"/designs/{workflow_id}/artifacts/generation_report"
        )
        assert bundle["geometry_validation_url"].startswith(
            f"/designs/{workflow_id}/artifacts/geometry_validation"
        )
        assert bundle["extraction_provider"] == status["extraction_provider"]
        assert bundle["llm_fallback_reason"] == status["llm_fallback_reason"]
        assert bundle["runtime_capabilities"]["workflow_id_source"] == "workflow_id"
        assert bundle["runtime_capabilities"]["websocket_runtime"] is False
        assert any(
            action["action"] == "websocket_runtime" for action in bundle["unsupported_actions"]
        )
        if bundle["mesh_qa_level"] == "mesh_level_basic":
            assert any("mesh_level_basic" in item for item in bundle["limitations"])
        assert "/Users/" not in json.dumps(bundle, ensure_ascii=False)

        timeline = client.get(f"/designs/{workflow_id}/timeline-summary").json()
        nodes = {step["node"] for step in timeline["timeline_steps"]}
        assert "extract_requirements" in nodes
        assert "retrieve_rag_context" in nodes
        assert "select_assets" in nodes
        assert "plan_scene" in nodes
        assert "generate_blender" in nodes
        assert "qa_generation" in nodes

        events = client.get(f"/designs/{workflow_id}/events").json()
        assert events
        assert all(event["workflow_id"] == workflow_id for event in events)
        assert all(event["event_id"] for event in events)
        assert all(event["timestamp"] for event in events)
        assert any(event["event_type"] == "artifact_ready" for event in events)
        assert any(event["payload"]["node"] == "retrieve_rag_context" for event in events)
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

        with client.stream("GET", f"/designs/{workflow_id}/events/stream") as stream:
            assert stream.status_code == 200
            stream_body = "".join(stream.iter_text())
        assert "event: workflow_completed" in stream_body or "event: workflow_failed" in stream_body

        preview_response = client.get(f"/designs/{workflow_id}/artifacts/preview")
        assert preview_response.status_code == 200
        assert preview_response.headers["content-type"].startswith("image/png")

        glb_response = client.get(f"/designs/{workflow_id}/artifacts/glb")
        assert glb_response.status_code == 200
        assert len(glb_response.content) > 32

        if status["blender_available"] is True:
            assert status["status"] == "completed"
            assert status["generation_mode"] == "real_blender"
            assert bundle["mesh_qa_passed"] is True
        else:
            assert status["generation_mode"].startswith("fallback_")
            issues = client.get(f"/designs/{workflow_id}/user-issues").json()
            assert issues["human_readable_issues"]
            assert any(
                "Blender" in issue["title"] or "fallback" in issue["impact"].lower()
                for issue in issues["human_readable_issues"]
            )
    finally:
        workflow_service.outputs_dir = original_outputs


def _wait_for_terminal_status(client: TestClient, workflow_id: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        response = client.get(f"/designs/{workflow_id}")
        assert response.status_code == 200
        status = response.json()
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.25)
    raise AssertionError(f"workflow did not finish: {workflow_id}")
