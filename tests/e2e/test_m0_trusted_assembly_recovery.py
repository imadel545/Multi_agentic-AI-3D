from __future__ import annotations

import hashlib
import json
import struct
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from core.agents.geometry_program_planner import GeometryProgramPlanner
from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.geometry_program import GeometryProgramVector3
from core.contracts.requirements import GeometryRequest
from core.llm.asset_selection import GroqAssetSelectionClient
from core.orchestration import DesignOrchestrator
from core.performance import requirements_confirmation_hash
from core.qa.assembly_constraint_inspector import _world_matrices
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text

pytestmark = pytest.mark.blender_runtime

_LOCAL_SELECTION_EXPLANATION = "compatibilité et permissions vérifiées"


def test_m0_real_trusted_assembly_geometry_adaptation_and_version(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    original_orchestrator = workflow_service.orchestrator
    original_edit_agent = workflow_service.scene_edit_agent
    registry = workflow_service.registry
    asset_transport = _StructuredAssetSelectionTransport(registry)
    geometry_groq = _StructuredGeometryGroq()
    selector = GroqAssetSelectionClient(
        api_key="bounded-test-key",
        model="openai/gpt-oss-120b",
        post=asset_transport,
    )
    orchestrator = DesignOrchestrator(
        registry=workflow_service.registry,
        extractor=original_orchestrator.extractor,
        rag_service=None,
        memory_service=None,
        blender_runner=original_orchestrator.blender_runner,
        checkpoint_saver=None,
        planning_decision_client=None,
        asset_selection_client=selector,
        geometry_program_planner=GeometryProgramPlanner(geometry_groq),  # type: ignore[arg-type]
        allow_blender_fallback=False,
    )
    workflow_service.outputs_dir = tmp_path
    workflow_service.orchestrator = orchestrator
    workflow_service.scene_edit_agent = SceneEditAgent(
        groq_client=None,
        capability_service=original_edit_agent.capability_service,
        checkpoint_saver=None,
        geometry_program_planner=orchestrator.geometry_program_planner,
    )
    client = TestClient(app)
    try:
        requirements = parse_requirements_text(
            "Créer un site 4G sur pylône treillis 30 m avec trois secteurs à 24 m, "
            "azimuts 0, 120 et 240, radios RRU, câbles, boîte alimentation, GPS et dalle béton."
        ).model_copy(
            update={
                "geometry_requests": [
                    GeometryRequest(
                        request_id="maintenance_stair",
                        semantic_role="maintenance_stair",
                        description=(
                            "Créer un escalier technique métallique compact avec plateforme "
                            "pour la maintenance au sol."
                        ),
                        quantity=1,
                        placement_context="À six mètres du pylône, posé sur le sol.",
                        maximum_dimensions_m=GeometryProgramVector3(x=4.0, y=2.0, z=3.0),
                    )
                ]
            }
        )
        requirements_text = "Site 4G confirmé avec escalier technique borné."
        response = client.post(
            "/designs",
            json={
                "requirements_text": requirements_text,
                "confirmed_requirements": requirements.model_dump(mode="json"),
                "confirmed_requirements_hash": requirements_confirmation_hash(
                    requirements,
                    requirements_text=requirements_text,
                    detail_level=requirements.detail_level,
                ),
                "options": {"detail_level": requirements.detail_level, "use_llm": False},
            },
        )
        assert response.status_code == 200, response.text
        workflow_id = response.json()["workflow_id"]
        status = _wait_for_terminal_status(client, workflow_id)
        assert status["status"] == "completed", json.dumps(status, ensure_ascii=False)
        assert status["generation_mode"] == "real_blender"
        assert status["completion_certificate_status"] == "issued"

        scene = client.get(f"/designs/{workflow_id}/artifacts/scene_spec").json()
        plan = client.get(f"/designs/{workflow_id}/artifacts/assembly_plan").json()
        components = {component["role_id"]: component for component in plan["components"]}
        assert plan["schema_version"] == "1.1.0"
        assert plan["compilation_status"] == "resolved"
        assert plan["selection_authority"] == "llm_bounded"
        assert plan["selection_provider"] == "groq"
        assert plan["selection_model"] == "openai/gpt-oss-120b"
        assert plan["selection_capability"] == "asset_selection"
        assert plan["selection_contract_version"] == "bounded_asset_selection@1.2.0"
        assert plan["llm_fallback_used"] is False
        assert plan["operations"]
        assert all(operation["instances"] for operation in plan["operations"])
        antenna_component = components["sector_antenna"]
        exact_antenna_id = antenna_component["selected_asset_id"]
        exact_antenna = registry.get(exact_antenna_id)
        assert exact_antenna.type == "antenna"
        assert "4G" in exact_antenna.compatible_networks
        assert exact_antenna.allows_generation_mode("imported_glb_exact")
        assert antenna_component["generation_strategy"] == "imported_glb_exact"
        assert antenna_component["manifest_snapshot"]["asset_id"] == exact_antenna_id
        assert _LOCAL_SELECTION_EXPLANATION in antenna_component["selection_reason"]
        assert components["timing_antenna"]["generation_strategy"] == "imported_glb_exact"
        cable_component = components["sector_cable_route"]
        cable_asset = registry.get(cable_component["selected_asset_id"])
        assert cable_asset.type == "cable"
        assert cable_asset.is_generation_eligible
        assert cable_component["manifest_snapshot"]["asset_id"] == cable_asset.asset_id
        assert _LOCAL_SELECTION_EXPLANATION in cable_component["selection_reason"]
        assert scene["geometry_programs"][0]["program_id"] == "maintenance_stair.llm_v2"
        assert scene["geometry_programs"][0]["generator_provider"] == "groq"
        assert scene["geometry_programs"][0]["generator_model"] == "openai/gpt-oss-120b"
        assert scene["geometry_programs"][0]["structured_output_mode"] == "strict_json_schema"

        proofs = client.get(f"/designs/{workflow_id}/artifacts/component_proofs").json()
        assert proofs["operation_execution"]["passed"] is True
        assert proofs["operation_execution"]["missing_operation_ids"] == []
        assert {item["role_id"] for item in proofs["components"]} == set(components)
        assert all(item["qa"]["passed"] is True for item in proofs["components"])
        antenna_proof = next(
            item for item in proofs["components"] if item["role_id"] == "sector_antenna"
        )
        assert antenna_proof["asset_id"] == exact_antenna_id
        assert antenna_proof["strategy"] == "reuse"
        assert antenna_proof["generation_strategy"] == "imported_glb_exact"
        assert all(
            instance["geometry_source"] == "imported_glb_exact"
            for instance in antenna_proof["instances"]
        )
        antenna_operation_id = "assembly:antenna-to-mount"
        assert antenna_operation_id in proofs["operation_execution"]["executed_operation_ids"]
        assert all(
            antenna_operation_id in instance["assembly_operation_ids"]
            for instance in antenna_proof["instances"]
        )
        program_proof = proofs["geometry_programs"][0]
        assert program_proof["origin"] == "geometry_program"
        assert program_proof["strategy"] == "procedural_generate"
        assert program_proof["generation_strategy"] == "typed_geometry_program_v2"
        assert program_proof["geometry_program"]["generator_provider"] == "groq"
        assert program_proof["qa"]["passed"] is True

        certificate = client.get(f"/designs/{workflow_id}/artifacts/completion_certificate").json()
        assert certificate["schema_version"] == "1.5.0"
        assert certificate["status"] == "issued"
        assert certificate["checks"]["component_proof_verified"] is True
        assert certificate["checks"]["assembly_constraint_evidence_verified"] is True
        assert certificate["checks"]["tower_access_evidence_verified"] is True
        constraint_evidence = client.get(
            f"/designs/{workflow_id}/artifacts/constraint_evidence"
        ).json()
        assert constraint_evidence["status"] == "passed"
        assert constraint_evidence["expected_measurement_count"] == 9
        assert constraint_evidence["measured_constraint_count"] == 9
        assert constraint_evidence["failed_constraint_count"] == 0
        assert all(
            frame["source"] in {"glb_fixed_anchor", "glb_resolved_anchor"}
            and frame["gltf_node_index"] is not None
            for measurement in constraint_evidence["measurements"]
            for frame in (measurement["source_frame"], measurement["target_frame"])
        )
        radio_supports = [
            measurement["target_frame"]["resolved_support"]
            for measurement in constraint_evidence["measurements"]
            if measurement["connection_id"] == "radio-to-mount"
        ]
        assert len(radio_supports) == len(scene["sectors"])
        assert all(
            support["support_anchor_id"] == "radio_adapter_base"
            and support["resolved_anchor_id"] == "radio_rail"
            and support["gltf_node_index"] is not None
            and support["gltf_mesh_index"] is not None
            for support in radio_supports
        )
        qa = client.get(f"/designs/{workflow_id}/artifacts/qa_report").json()
        assert qa["status"] == "passed"
        assert qa["checks"]["glb_structure_valid"] is True
        assert client.get(f"/designs/{workflow_id}/artifacts/glb").status_code == 200
        assert client.get(f"/designs/{workflow_id}/artifacts/preview").status_code == 200

        active = workflow_service.versioning.get_verified_active_version(workflow_id)
        assert active is not None
        initial_dir = Path(active.artifact_dir or "")
        assert initial_dir.is_dir()
        metadata = json.loads((initial_dir / "scene_metadata.json").read_text(encoding="utf-8"))
        exact_import_records = [
            item for item in metadata["asset_imports"] if item["asset_id"] == exact_antenna_id
        ]
        assert len(exact_import_records) == len(scene["sectors"])
        assert all(item["asset_import_success"] is True for item in exact_import_records)
        assert all(item["import_fallback_allowed"] is False for item in exact_import_records)
        assert all(
            item["effective_geometry_source"] == "imported_glb_exact"
            for item in exact_import_records
        )
        assert all(item["scale_factors"] == [1.0, 1.0, 1.0] for item in exact_import_records)
        assert all(
            item["asset_file"] == antenna_component["manifest_snapshot"]["asset_file"]
            for item in exact_import_records
        )
        assert all("resolved_path" not in item for item in metadata["asset_imports"])
        serialized_metadata = json.dumps(metadata, ensure_ascii=False)
        assert str(Path.cwd().resolve()) not in serialized_metadata
        assert "/Users/" not in serialized_metadata
        exact_evidence = next(
            item
            for item in proofs["assembly_validation"]["exact_imports"]
            if item["asset_id"] == exact_antenna_id
        )
        assert exact_evidence["asset_file"] == antenna_component["manifest_snapshot"]["asset_file"]
        assert (
            exact_evidence["actual_file_sha256"]
            == exact_evidence["verified_file_sha256"]
            == antenna_component["manifest_snapshot"]["verified_file_sha256"]
        )
        assert "/Users/" not in json.dumps(proofs, ensure_ascii=False)

        build_lock = json.loads((initial_dir / "build.lock.json").read_text(encoding="utf-8"))
        assert build_lock["schema_version"] == "1.3.0"
        assert build_lock["sector_preview_profile"] == {
            "required": True,
            "evidence_file": "sector_preview_evidence.json",
        }
        assert build_lock["blender_runtime"]["version"] == "4.5.12 LTS"
        assert build_lock["blender_runtime"]["version_tuple"] == [4, 5, 12]
        assert build_lock["blender_runtime"]["background"] is True
        assert build_lock["blender_runtime"]["factory_startup"] is True
        for artifact_name in (
            "design.glb",
            "preview.png",
            "component_proofs.json",
            "constraint_evidence.json",
        ):
            artifact_path = initial_dir / artifact_name
            lock_evidence = build_lock["artifacts"][artifact_name]
            assert lock_evidence["size_bytes"] == artifact_path.stat().st_size
            assert lock_evidence["sha256"] == _sha256(artifact_path)
        sector_preview_evidence = client.get(
            f"/designs/{workflow_id}/artifacts/sector_preview_evidence"
        )
        assert sector_preview_evidence.status_code == 200
        sector_preview_payload = sector_preview_evidence.json()
        assert sector_preview_payload["schema_version"] == "1.0.0"
        assert sector_preview_payload["status"] == "passed"
        assert (
            sector_preview_payload["measurement_scope"]
            == "exported_glb_semantics_and_rendered_sector_preview"
        )
        assert {preview["sector_id"] for preview in sector_preview_payload["previews"]} == {
            "S1",
            "S2",
            "S3",
        }
        for preview in sector_preview_payload["previews"]:
            assert preview["post_blender_identity_verified"] is True
            assert preview["visual_inspection"]["visual_quality_passed"] is True
            assert preview["visual_inspection"]["checks"] == {
                "file_exists": True,
                "format_valid": True,
                "minimum_resolution_valid": True,
                "subject_present": True,
                "subject_width_valid": True,
                "subject_height_valid": True,
                "subject_contrast_valid": True,
                "subject_centered": True,
                "subject_not_clipped": True,
            }
            preview_path = initial_dir / preview["file_name"]
            assert preview_path.is_file()
            assert build_lock["artifacts"][preview["file_name"]] == {
                "sha256": _sha256(preview_path),
                "size_bytes": preview_path.stat().st_size,
            }
            response = client.get(
                f"/designs/{workflow_id}/sector-previews/{preview['preview_id']}"
                f"?version_id={active.version_id}"
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert response.content == preview_path.read_bytes()
        initial_bundle = client.get(f"/designs/{workflow_id}/viewer-bundle")
        assert initial_bundle.status_code == 200
        assert initial_bundle.json()["sector_previews"] == [
            {
                "sector_id": preview["sector_id"],
                "preview_url": (
                    f"/designs/{workflow_id}/sector-previews/{preview['preview_id']}"
                    f"?version_id={active.version_id}"
                ),
                "semantic_roots": preview["semantic_roots"],
                "expected_roles": preview["expected_roles"],
                "exported_roles": preview["exported_roles"],
                "framed_roles": preview["framed_roles"],
                "post_blender_identity_verified": True,
                "visual_framing_verified": True,
                "subject_bbox_height_ratio": preview["visual_inspection"][
                    "subject_bbox_height_ratio"
                ],
                "subject_contrast_mean": preview["visual_inspection"]["subject_contrast_mean"],
                "limitations": sector_preview_payload["limitations"],
            }
            for preview in sector_preview_payload["previews"]
        ]
        trusted_inputs = build_lock["trusted_inputs"]
        assert build_lock["trusted_inputs_sha256"] == _json_sha256(trusted_inputs)
        assert trusted_inputs["manifest_catalog_sha256"] == plan["manifest_catalog_sha256"]
        assert trusted_inputs["builder_catalog"]["file"] == (
            "assets/capabilities/builder_profiles.json"
        )
        locked_manifest = next(
            item for item in trusted_inputs["manifests"] if item["role_id"] == "sector_antenna"
        )
        assert locked_manifest["asset_id"] == exact_antenna_id
        assert (
            locked_manifest["snapshot_sha256"]
            == antenna_component["manifest_snapshot"]["snapshot_sha256"]
        )
        locked_exact_asset = next(
            item for item in trusted_inputs["exact_assets"] if item["role_id"] == "sector_antenna"
        )
        assert locked_exact_asset["asset_id"] == exact_antenna_id
        assert locked_exact_asset["sha256"] == exact_evidence["actual_file_sha256"]
        assert any(
            item["operation_id"] == antenna_operation_id
            for item in trusted_inputs["assembly_operations"]
        )
        assert (
            trusted_inputs["geometry_programs"][0]["program_id"]
            == (scene["geometry_programs"][0]["program_id"])
        )
        assert "/Users/" not in json.dumps(trusted_inputs, ensure_ascii=False)

        assert asset_transport.payloads
        asset_payload = asset_transport.payloads[0]
        assert asset_payload["model"] == "openai/gpt-oss-120b"
        assert asset_payload["stream"] is False
        assert "tools" not in asset_payload
        assert asset_payload["response_format"]["type"] == "json_schema"
        assert geometry_groq.calls
        geometry_payload, geometry_policy = geometry_groq.calls[0]
        assert geometry_payload["response_format"]["type"] == "json_schema"
        assert geometry_payload["response_format"]["json_schema"]["strict"] is True
        assert geometry_policy.capability == "geometry_program_generation"

        radio_index = next(
            index
            for index, sector in enumerate(active.scene.sectors)
            if sector.radio_asset_id and sector.radio_geometry_profile is not None
        )
        sector = active.scene.sectors[radio_index]
        capability = next(
            item
            for item in workflow_service.scene_edit_agent.capability_service.resolve(
                active.scene
            ).capabilities
            if item.path == f"/sectors/{radio_index}/radio_geometry_profile/vertical_offset_m"
        )
        current_offset = sector.radio_geometry_profile.vertical_offset_m  # type: ignore[union-attr]
        requested_offset = current_offset + 0.25 if current_offset <= 2.7 else current_offset - 0.25
        workflow_service.scene_edit_agent.groq = _BoundedEditGroq(
            capability_id=capability.capability_id,
            path=capability.path,
            execution_tool=capability.execution_tool,
            value=requested_offset,
        )  # type: ignore[assignment]
        edit = client.post(
            f"/designs/{workflow_id}/edit",
            json={
                "edit_prompt": (
                    f"mets le décalage vertical du RRU du secteur {radio_index + 1} "
                    f"à {requested_offset:.2f} m"
                )
            },
        )
        assert edit.status_code == 200, edit.text
        edit_payload = edit.json()
        assert edit_payload["status"] == "applied"
        assert edit_payload["llm_decision_provenance"]["provider"] == "groq"
        assert edit_payload["llm_decision_provenance"]["fallback_used"] is False

        edited = workflow_service.versioning.get_verified_active_version(workflow_id)
        assert edited is not None
        assert edited.version_id == edit_payload["version_id"]
        assert len(edited.scene.geometry_programs) == 1
        edited_dir = Path(edited.artifact_dir or "")
        edited_proofs = json.loads((edited_dir / "component_proofs.json").read_text())
        edited_radio = next(
            item for item in edited_proofs["components"] if item["role_id"] == "remote_radio"
        )
        edited_instance = next(
            item for item in edited_radio["instances"] if item["instance_id"] == sector.sector_id
        )
        assert edited_instance["resolved_parameters"]["vertical_offset_m"] == requested_offset
        assert edited_proofs["geometry_programs"][0]["qa"]["passed"] is True
        edited_certificate = json.loads((edited_dir / "completion_certificate.json").read_text())
        edited_evidence = json.loads((edited_dir / "constraint_evidence.json").read_text())
        assert edited_certificate["status"] == "issued"
        assert edited_certificate["schema_version"] == "1.5.0"
        assert edited_certificate["checks"]["component_proof_verified"] is True
        assert edited_certificate["checks"]["assembly_constraint_evidence_verified"] is True
        assert edited_certificate["checks"]["tower_access_evidence_verified"] is True
        assert edited_evidence["status"] == "passed"
        assert edited_evidence["measured_constraint_count"] == 9
        assert edited_evidence["failed_constraint_count"] == 0
        assert all(
            measurement["target_frame"]["resolved_support"]["support_anchor_id"]
            == "radio_adapter_base"
            for measurement in edited_evidence["measurements"]
            if measurement["connection_id"] == "radio-to-mount"
        )
        versions = client.get(f"/designs/{workflow_id}/versions").json()
        assert len(versions) == 2
        assert [item["version_id"] for item in versions if item["active"]] == [edited.version_id]

        # Real Blender targeted edit; providers above are controlled transports,
        # while this selected edit deliberately exercises the explicit parser fallback.
        workflow_service.scene_edit_agent.groq = None
        before_scene = edited.scene.model_dump(mode="json")
        before_matrices = _glb_world_transforms(edited_dir / "design.glb")
        root = next(
            instance["semantic_root"]
            for component in edited_proofs["components"]
            if component["role_id"] == "sector_antenna"
            for instance in component["instances"]
            if instance["instance_id"] == "S2"
        )
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert bundle["version_id"] == edited.version_id
        targeted = client.post(
            f"/designs/{workflow_id}/edit",
            json={
                "edit_prompt": "Azimut à 80 degrés",
                "target_semantic_root": root,
                "expected_version_id": bundle["version_id"],
            },
        )
        assert targeted.status_code == 200, targeted.text
        assert targeted.json()["status"] == "applied", targeted.text
        assert targeted.json()["llm_fallback_used"] is True
        targeted_version = workflow_service.versioning.get_verified_active_version(workflow_id)
        assert targeted_version is not None
        assert targeted_version.version_id != edited.version_id
        after_scene = targeted_version.scene.model_dump(mode="json")
        assert before_scene["sectors"][1]["azimuth_deg"] == 120
        assert after_scene["sectors"][1]["azimuth_deg"] == 80
        assert after_scene["sectors"][0] == before_scene["sectors"][0]
        assert after_scene["sectors"][2] == before_scene["sectors"][2]
        assert after_scene["geometry_programs"] == before_scene["geometry_programs"]
        assert after_scene["tower"] == before_scene["tower"]
        target_dir = Path(targeted_version.artifact_dir or "")
        after_matrices = _glb_world_transforms(target_dir / "design.glb")
        for sector_id in ("S1", "S3"):
            sector_roots = [
                instance["semantic_root"]
                for component in edited_proofs["components"]
                for instance in component["instances"]
                if instance["instance_id"] == sector_id
            ]
            assert sector_roots
            for other_root in sector_roots:
                assert after_matrices[other_root] == pytest.approx(before_matrices[other_root])
        assert after_matrices[root] != pytest.approx(before_matrices[root])
        targeted_certificate = json.loads((target_dir / "completion_certificate.json").read_text())
        assert targeted_certificate["status"] == "issued"
        assert targeted_certificate["generation_mode"] == "real_blender"
        assert targeted_certificate["checks"]["component_proof_verified"] is True
        stale = client.post(
            f"/designs/{workflow_id}/edit",
            json={
                "edit_prompt": "Azimut à 90 degrés",
                "target_semantic_root": root,
                "expected_version_id": edited.version_id,
            },
        )
        assert stale.status_code == 200, stale.text
        assert stale.json()["status"] == "rejected"
        assert stale.json()["errors"][0]["code"] == "EDIT_TARGET_REJECTED"
        versions = client.get(f"/designs/{workflow_id}/versions").json()
        assert len(versions) == 3
        assert [item["version_id"] for item in versions if item["active"]] == [
            targeted_version.version_id
        ]
    finally:
        workflow_service.outputs_dir = original_outputs
        workflow_service.orchestrator = original_orchestrator
        workflow_service.scene_edit_agent = original_edit_agent


class _StructuredAssetSelectionTransport:
    def __init__(self, registry: AssetRegistry) -> None:
        self.registry = registry
        self.payloads: list[dict] = []

    def __call__(self, url, *, headers, json, timeout):
        del headers, timeout
        self.payloads.append(json)
        prompt = __import__("json").loads(json["messages"][1]["content"])
        slots = prompt["slots"]
        allowed_choices = prompt["allowed_choices"]
        selections = {}
        for slot in slots:
            candidates = slot["candidates"]
            if slot["role_id"] == "sector_antenna":
                selected_candidate = next(
                    candidate
                    for candidate in candidates
                    if self.registry.get(candidate["asset_id"]).type == "antenna"
                    and "imported_glb_exact" in candidate["allowed_generation_strategies"]
                )
            else:
                selected_candidate = candidates[0]
            selected = selected_candidate["asset_id"]
            strategy = selected_candidate["allowed_generation_strategies"][0]
            semantic_strategy = next(
                semantic
                for semantic in selected_candidate["allowed_semantic_strategies"]
                if semantic
                in {
                    "imported_glb_exact": {"reuse_component", "adapt_component"},
                    "internal_project_generated": {"compose_assets", "adapt_component"},
                }[strategy]
            )
            choice = next(
                choice
                for choice in allowed_choices
                if choice["role_id"] == slot["role_id"]
                and choice["asset_id"] == selected
                and choice["generation_strategy"] == strategy
                and choice["semantic_strategy"] == semantic_strategy
            )
            selections[slot["role_id"]] = choice["choice_id"]
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": __import__("json").dumps({"selections": selections})}}
                ]
            },
        )


class _StructuredGeometryGroq:
    model = "openai/gpt-oss-120b"

    def __init__(self) -> None:
        self.calls: list[tuple[dict, object]] = []

    def request_json(self, payload, *, policy):
        self.calls.append((payload, policy))
        return {
            "schema_version": "1.0.0",
            "program_id": "untrusted_model_id",
            "semantic_role": "maintenance_stair",
            "requested_quantity": 1,
            "units": "meters",
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": self.model,
            "structured_output_mode": "strict_json_schema",
            "source_prompt_sha256": "0" * 64,
            "materials": [],
            "nodes": [
                {
                    "kind": "primitive",
                    "node_id": "stair_body",
                    "primitive": "box",
                    "size_m": {"x": 2.4, "y": 1.2, "z": 0.18},
                    "semantic_role": "maintenance_stair",
                    "transform": {"translation_m": {"x": 6.0, "y": 0.0, "z": 0.09}},
                    "bevel_m": 0.02,
                },
                {
                    "kind": "primitive",
                    "node_id": "stair_step",
                    "primitive": "box",
                    "size_m": {"x": 0.5, "y": 1.2, "z": 0.16},
                    "transform": {"translation_m": {"x": 5.0, "y": 0.0, "z": 0.28}},
                    "bevel_m": 0.01,
                },
                {
                    "kind": "curve",
                    "node_id": "stair_guardrail",
                    "points_m": [
                        {"x": 4.8, "y": -0.6, "z": 0.35},
                        {"x": 7.2, "y": -0.6, "z": 1.1},
                    ],
                    "bevel_depth_m": 0.03,
                },
            ],
            "assumptions": ["Generic galvanized-steel maintenance component."],
            "limitations": ["Not a structural engineering certification."],
            "deterministic_adjustments": [],
        }


class _BoundedEditGroq:
    model = "openai/gpt-oss-120b"

    def __init__(
        self,
        *,
        capability_id: str,
        path: str,
        execution_tool: str,
        value: float,
    ) -> None:
        self.capability_id = capability_id
        self.path = path
        self.execution_tool = execution_tool
        self.value = value

    @staticmethod
    def request_json(_payload, policy=None):
        del policy
        return {
            "action": "standard_adaptation",
            "program_id": None,
            "reason": "La demande cible un paramètre RRU déclaré.",
        }

    def _post_raw(self, _payload):
        return {
            "edit_description": "Adapter le décalage vertical du RRU",
            "operations": [
                {
                    "op": "replace",
                    "capability_id": self.capability_id,
                    "path": self.path,
                    "value_json": json.dumps(self.value),
                    "execution_tool": self.execution_tool,
                    "rationale": "Secteur, paramètre et valeur sont explicites.",
                }
            ],
            "unsupported_requests": [],
            "assumptions": [],
        }


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _glb_world_transforms(path: Path) -> dict[str, list[float]]:
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", raw)
    assert magic == b"glTF" and version == 2 and total == len(raw)
    json_size, chunk_type = struct.unpack_from("<II", raw, 12)
    assert chunk_type == 0x4E4F534A
    payload = json.loads(raw[20 : 20 + json_size])
    matrices, _ = _world_matrices(payload)
    return {
        node["name"]: [value for row in matrices[index] for value in row]
        for index, node in enumerate(payload["nodes"])
        if "name" in node
    }
