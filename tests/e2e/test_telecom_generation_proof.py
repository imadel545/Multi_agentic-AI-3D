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
        assert isinstance(status["rag_planning_summary"], dict)
        assert status["rag_planning_summary"]["rag_used_for_extraction"] is False
        assert status["rag_planning_summary"]["rag_planning_mode"] in {
            "structured_hints_applied",
            "candidates_rejected_or_no_op",
            "context_only_no_structured_hints",
        }
        assert isinstance(status["rag_planning_summary"]["controlled_hint_fields"], list)
        assert "rag_reranker_status" in status
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
        assert [sector["azimuth_deg"] for sector in scene_plan["sectors"]] == [
            0.0,
            120.0,
            240.0,
        ]
        assert [sector["install_height_m"] for sector in scene_plan["sectors"]] == [
            24.0,
            24.0,
            24.0,
        ]
        assert all(sector["radio_asset_id"] for sector in scene_plan["sectors"])
        assert all(sector["include_cable"] is True for sector in scene_plan["sectors"])
        assert scene_plan["visual_elements"]["include_labels"] is True
        assert scene_plan["visual_elements"]["include_power_cabinet"] is True
        assert scene_plan["visual_elements"]["include_gps_antenna"] is True
        assert scene_plan["tower"]["characteristics"]["foundation_type"] == "concrete_pad"
        assert any(
            accessory["asset_type"] == "cabinet"
            for accessory in scene_plan.get("accessory_assets", [])
        )
        assert any(
            accessory["asset_type"] == "gps" for accessory in scene_plan.get("accessory_assets", [])
        )

        assembly_plan = client.get(f"/designs/{workflow_id}/artifacts/assembly_plan").json()
        components = {component["role_id"]: component for component in assembly_plan["components"]}
        assert {
            "support_structure",
            "sector_antenna",
            "antenna_mount",
            "remote_radio",
            "ground_equipment",
            "timing_antenna",
        }.issubset(components)
        assert components["support_structure"]["candidate_scores"]
        assert components["sector_antenna"]["selected_asset_id"]
        assert components["antenna_mount"]["builder_profile_id"] == "mount_bracket_v1"
        assert components["sector_cable_route"]["generation_strategy"] == "procedural_fallback"
        assert assembly_plan["units"] == "meters"

        validation_report = client.get(f"/designs/{workflow_id}/artifacts/validation_report").json()
        assert validation_report["status"] in {"passed", "failed"}
        assert validation_report["checks"]["tower_height_valid"] is True
        assert validation_report["checks"]["sector_count_valid"] is True
        assert validation_report["checks"]["antenna_height_valid"] is True
        assert validation_report["checks"]["azimuths_valid"] is True
        assert validation_report["checks"]["power_cabinet_asset_present_when_requested"] is True
        assert validation_report["checks"]["gps_asset_present_when_requested"] is True

        glb_inspection = client.get(f"/designs/{workflow_id}/artifacts/glb_inspection").json()
        assert glb_inspection["inspection_mode"] in {"glb_parse", "metadata_fallback"}
        assert glb_inspection["checks"]["has_tower"] is True
        assert glb_inspection["checks"]["has_antennas"] is True
        assert glb_inspection["checks"]["has_radios_or_rru"] is True
        assert glb_inspection["checks"]["has_cables"] is True
        assert glb_inspection["checks"]["has_azimuth_arrows"] is True
        assert glb_inspection["checks"]["has_power_cabinet"] is True
        assert glb_inspection["checks"]["has_gps_antenna"] is True
        assert glb_inspection["checks"]["has_foundation"] is True
        assert glb_inspection["checks"]["has_labels"] is True

        geometry_validation = client.get(
            f"/designs/{workflow_id}/artifacts/geometry_validation"
        ).json()
        assert geometry_validation["checks"]["antenna_count_valid"] is True
        assert geometry_validation["checks"]["rru_count_valid"] is True
        assert geometry_validation["checks"]["cable_count_valid"] is True
        assert geometry_validation["checks"]["azimuth_arrow_count_valid"] is True
        assert geometry_validation["checks"]["power_cabinet_count_valid"] is True
        assert geometry_validation["checks"]["gps_antenna_count_valid"] is True
        assert geometry_validation["checks"]["foundation_count_valid"] is True
        assert geometry_validation["checks"]["label_count_valid"] is True
        assert geometry_validation["checks"]["approx_tower_height_valid"] is True
        assert geometry_validation["checks"]["approx_antenna_height_valid"] is True
        assert geometry_validation["checks"]["azimuth_metadata_valid"] is True
        assert geometry_validation["object_counts"]["antenna"] >= 3
        assert geometry_validation["object_counts"]["rru"] >= 3
        assert geometry_validation["object_counts"]["cable"] >= 3
        assert geometry_validation["object_counts"]["foundation"] >= 1
        assert geometry_validation["object_counts"]["label"] >= 5
        assert geometry_validation["missing_objects"] == []

        qa_report = client.get(f"/designs/{workflow_id}/artifacts/qa_report").json()
        assert qa_report["checks"]["glb_structure_valid"] is True
        assert qa_report["checks"]["expected_objects_present"] is True
        assert qa_report["checks"]["geometry_validation_valid"] is True
        assert qa_report["checks"]["preview_visual_quality_valid"] is True

        rag_evidence = client.get(f"/designs/{workflow_id}/artifacts/rag_evidence").json()
        assert rag_evidence["rag_used_for_extraction"] is False
        assert rag_evidence["rag_context_count"] == status["rag_context_count"]
        assert isinstance(rag_evidence["controlled_hint_fields"], list)
        assert "rag_reranker_status" in rag_evidence
        assert "/Users/" not in json.dumps(rag_evidence, ensure_ascii=False)

        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert bundle["workflow_id"] == workflow_id
        assert bundle["scene_spec_url"].startswith(f"/designs/{workflow_id}/artifacts/scene_spec")
        assert bundle["assembly_plan_url"].startswith(
            f"/designs/{workflow_id}/artifacts/assembly_plan"
        )
        assert bundle["qa_report_url"].startswith(f"/designs/{workflow_id}/artifacts/qa_report")
        assert bundle["generation_report_url"].startswith(
            f"/designs/{workflow_id}/artifacts/generation_report"
        )
        assert bundle["rag_evidence_url"].startswith(
            f"/designs/{workflow_id}/artifacts/rag_evidence"
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
            edit = client.post(
                f"/designs/{workflow_id}/edit",
                json={"edit_prompt": "Augmente la hauteur du pylône à 32 m."},
            )
            assert edit.status_code == 200
            assert edit.json()["version_id"]
            versions = client.get(f"/designs/{workflow_id}/versions").json()
            assert len(versions) >= 2
            assert any(version["active"] for version in versions)
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
