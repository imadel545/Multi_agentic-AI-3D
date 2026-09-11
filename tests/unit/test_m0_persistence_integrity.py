from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from core.agents.blueprint_composer import BlueprintComposer
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.scene_planner import ScenePlanner
from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.completion import CompletionCertificate
from core.contracts.design_blueprint import DesignBlueprint
from core.contracts.geometry_program import GeometryProgram
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.parametric import MeshQAReport
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import GeometryRequest, RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.performance import issue_requirement_analysis_receipt
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import GenerationResult
from core.services.requirement_parser import parse_requirements_text
from core.services.scene_versioning import SceneVersioningService, _verify_build_lock
from core.validation.completion_certificate import (
    build_completion_certificate,
    verify_completion_certificate,
)
from core.validation.design_blueprint import (
    evaluate_blueprint_requirement_coverage,
    evaluate_blueprint_scene_coverage,
)
from core.validation.requirement_coverage import evaluate_requirement_coverage

_CHECKS_V1 = {
    "requirements_present",
    "scene_spec_present",
    "requirement_coverage_passed",
    "pre_blender_gate_passed",
    "real_blender_generation",
    "required_artifacts_regular_files",
    "artifact_hashes_recorded",
    "qa_report_passed",
    "glb_binary_integrity_passed",
    "semantic_mesh_coverage_complete",
    "geometry_validation_passed",
    "mesh_qa_passed",
    "preview_qa_passed",
    "post_blender_gate_passed",
    "no_critical_fallback",
}


@dataclass(frozen=True)
class _CertifiedBundle:
    service: SceneVersioningService
    workflow_id: str
    version_id: str
    artifact_dir: Path
    requirements: RequirementSpec
    blueprint: DesignBlueprint
    scene: SceneSpec
    generation: GenerationResult
    certificate: CompletionCertificate


@pytest.mark.parametrize("mutation", ["delete", "alter"])
def test_m0_component_proof_deletion_or_alteration_invalidates_certification(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    proof_path = bundle.artifact_dir / "component_proofs.json"

    if mutation == "delete":
        proof_path.unlink()
    else:
        payload = json.loads(proof_path.read_text(encoding="utf-8"))
        payload["geometry_programs"] = []
        payload["report_sha256"] = _component_report_hash(payload)
        _write_json(proof_path, payload)

    assert not verify_completion_certificate(
        bundle.certificate,
        requirements=bundle.requirements,
        design_blueprint=bundle.blueprint,
        scene=bundle.scene,
        generation=bundle.generation,
    )
    with pytest.raises(
        ValueError,
        match="ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:component_proofs",
    ):
        bundle.service.verified_active_status_path(bundle.workflow_id)


@pytest.mark.parametrize("mutation", ["delete", "alter"])
def test_m0_geometry_program_deletion_or_alteration_invalidates_scene_certificate(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    program = bundle.scene.geometry_programs[0]
    if mutation == "delete":
        mutated_scene = bundle.scene.model_copy(update={"geometry_programs": []})
    else:
        body = program.nodes[0]
        mutated_body = body.model_copy(
            update={"size_m": body.size_m.model_copy(update={"x": body.size_m.x + 0.25})}
        )
        mutated_program = program.model_copy(update={"nodes": [mutated_body, *program.nodes[1:]]})
        mutated_scene = bundle.scene.model_copy(update={"geometry_programs": [mutated_program]})

    assert not verify_completion_certificate(
        bundle.certificate,
        requirements=bundle.requirements,
        design_blueprint=bundle.blueprint,
        scene=mutated_scene,
        generation=bundle.generation,
    )
    _write_json(
        bundle.artifact_dir / "scene_spec.json",
        mutated_scene.model_dump(mode="json"),
    )
    with pytest.raises(ValueError, match="ACTIVE_VERSION_SCENE_SPEC_HASH_MISMATCH"):
        bundle.service.verified_active_status_path(bundle.workflow_id)


@pytest.mark.parametrize(
    ("logical_name", "file_name", "mutation"),
    [
        ("glb", "design.glb", "alter"),
        ("preview", "preview.png", "delete"),
    ],
)
def test_m0_certified_artifact_deletion_or_alteration_invalidates_active_version(
    tmp_path: Path,
    logical_name: str,
    file_name: str,
    mutation: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    artifact_path = bundle.artifact_dir / file_name
    if mutation == "delete":
        artifact_path.unlink()
    else:
        artifact_path.write_bytes(b"tampered-certified-artifact")

    assert not verify_completion_certificate(
        bundle.certificate,
        requirements=bundle.requirements,
        design_blueprint=bundle.blueprint,
        scene=bundle.scene,
        generation=bundle.generation,
    )
    with pytest.raises(
        ValueError,
        match=f"ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:{logical_name}",
    ):
        bundle.service.verified_active_status_path(bundle.workflow_id)


@pytest.mark.parametrize("mutation", ["geometry_program", "digest"])
def test_m0_build_lock_trusted_input_tampering_invalidates_active_version(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    build_lock_path = bundle.artifact_dir / "build.lock.json"
    payload = json.loads(build_lock_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.2.0"
    assert payload["trusted_inputs"] == _trusted_inputs(bundle.scene)
    assert payload["trusted_inputs_sha256"] == _runtime_json_sha256(payload["trusted_inputs"])

    if mutation == "geometry_program":
        payload["trusted_inputs"]["geometry_programs"][0]["program_sha256"] = "0" * 64
        # Keep the envelope internally self-consistent. Persistence must still
        # reject it because it no longer describes the certified SceneSpec.
        payload["trusted_inputs_sha256"] = _runtime_json_sha256(payload["trusted_inputs"])
    else:
        payload["trusted_inputs_sha256"] = "0" * 64
    _write_json(build_lock_path, payload)
    _rebind_certificate_artifact(
        bundle.artifact_dir,
        logical_name="build_lock",
        file_name="build.lock.json",
    )

    with pytest.raises(
        ValueError,
        match="ACTIVE_VERSION_BUILD_LOCK_TRUSTED_INPUTS_INVALID",
    ):
        bundle.service.verified_active_status_path(bundle.workflow_id)


def test_build_lock_binds_supplementary_preview_bytes(tmp_path: Path) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    preview_path = bundle.artifact_dir / "preview_front.png"
    preview_path.write_bytes(b"real-supplementary-preview-evidence")
    build_lock_path = bundle.artifact_dir / "build.lock.json"
    payload = json.loads(build_lock_path.read_text(encoding="utf-8"))
    payload["artifacts"][preview_path.name] = {
        "size_bytes": preview_path.stat().st_size,
        "sha256": _sha256(preview_path),
    }
    _write_json(build_lock_path, payload)

    assert _verify_build_lock(bundle.artifact_dir, scene=bundle.scene) == "1.2.0"

    preview_path.write_bytes(b"tampered-supplementary-preview")
    with pytest.raises(
        ValueError,
        match="ACTIVE_VERSION_BUILD_LOCK_ARTIFACT_MISMATCH:preview_front.png",
    ):
        _verify_build_lock(bundle.artifact_dir, scene=bundle.scene)


def test_active_version_rejects_a_downloadable_input_analysis_receipt_that_diverges_from_status(
    tmp_path: Path,
) -> None:
    """The public receipt is bound to the active status even though it is not mesh input."""

    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")
    receipt = issue_requirement_analysis_receipt(
        bundle.requirements,
        requirements_text="Créer un site vérifié.",
        detail_level="high",
        provider="groq:openai/gpt-oss-120b",
        extraction_provider="groq",
        fallback_used=False,
        fallback_reason=None,
    )
    status_path = bundle.artifact_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["input_analysis_status"] = "verified"
    status["input_analysis"] = receipt.model_dump(mode="json")
    _write_json(status_path, status)

    altered_receipt = receipt.model_dump(mode="json")
    altered_receipt["provider"] = "deterministic"
    _write_json(bundle.artifact_dir / "input_analysis_receipt.json", altered_receipt)

    with pytest.raises(ValueError, match="ACTIVE_VERSION_INPUT_ANALYSIS_RECEIPT_MISMATCH"):
        bundle.service.verified_active_status_path(bundle.workflow_id)


@pytest.mark.parametrize("downgrade", ["certificate", "build_lock"])
def test_m0_persistence_rejects_component_proof_schema_downgrade(
    tmp_path: Path,
    downgrade: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema="1.2.0")

    if downgrade == "certificate":
        certificate_path = bundle.artifact_dir / "completion_certificate.json"
        payload = json.loads(certificate_path.read_text(encoding="utf-8"))
        payload["schema_version"] = "1.1.0"
        payload["checks"].pop("component_proof_verified")
        payload["artifacts"] = [
            item for item in payload["artifacts"] if item["logical_name"] != "component_proofs"
        ]
        _write_json(certificate_path, payload)
        expected_error = "ACTIVE_VERSION_COMPLETION_CERTIFICATE_SCHEMA_DOWNGRADE"
    else:
        build_lock_path = bundle.artifact_dir / "build.lock.json"
        payload = json.loads(build_lock_path.read_text(encoding="utf-8"))
        payload["schema_version"] = "1.1.0"
        payload.pop("trusted_inputs")
        payload.pop("trusted_inputs_sha256")
        _write_json(build_lock_path, payload)
        _rebind_certificate_artifact(
            bundle.artifact_dir,
            logical_name="build_lock",
            file_name="build.lock.json",
        )
        expected_error = "ACTIVE_VERSION_BUILD_LOCK_SCHEMA_DOWNGRADE"

    with pytest.raises(ValueError, match=expected_error):
        bundle.service.verified_active_status_path(bundle.workflow_id)


@pytest.mark.parametrize("certificate_schema", ["1.0.0", "1.1.0"])
def test_m0_persisted_verifier_preserves_legacy_certificate_compatibility(
    tmp_path: Path,
    certificate_schema: str,
) -> None:
    bundle = _create_certified_bundle(tmp_path, certificate_schema=certificate_schema)

    restored = bundle.service.get_verified_active_version(bundle.workflow_id)

    assert restored is not None
    assert restored.version_id == bundle.version_id
    certificate_payload = json.loads(
        (bundle.artifact_dir / "completion_certificate.json").read_text(encoding="utf-8")
    )
    assert certificate_payload["schema_version"] == certificate_schema
    manifest = bundle.service.active_design_manifest(bundle.workflow_id)
    assert manifest is not None
    assert manifest["schema_version"] == ("1.0.0" if certificate_schema == "1.0.0" else "1.1.0")


def _create_certified_bundle(
    tmp_path: Path,
    *,
    certificate_schema: str,
) -> _CertifiedBundle:
    workflow_id = "wf_aaaaaaaaaaaa"
    include_geometry_program = certificate_schema == "1.2.0"
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 1 secteur à 24m. "
        "Azimut : 0°. Ajouter une RRU."
    )
    if include_geometry_program:
        requirements = requirements.model_copy(
            update={
                "geometry_requests": [
                    GeometryRequest(
                        request_id="site_shelter",
                        semantic_role="equipment_shelter",
                        description="Outdoor telecom equipment shelter beside the tower.",
                        quantity=1,
                    )
                ]
            }
        )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset(
        "antenna",
        requirements.network_type,
        requirements.tower_type,
    )
    radio = registry.select_asset(
        "radio",
        requirements.network_type,
        requirements.tower_type,
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id,
        requirements,
        tower,
        antenna,
        radio,
    )
    if include_geometry_program:
        scene = scene.model_copy(update={"geometry_programs": [_geometry_program()]})
    blueprint = BlueprintComposer().compose(
        workflow_id=workflow_id,
        requirements=requirements,
        selected_assets=[tower, antenna, radio],
        tower_validation=TowerEngineerAgent().validate(requirements, tower),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )
    blueprint_requirement_coverage = evaluate_blueprint_requirement_coverage(
        requirements,
        blueprint,
    )
    blueprint_scene_coverage = evaluate_blueprint_scene_coverage(blueprint, scene)
    assert blueprint_requirement_coverage.passed
    assert blueprint_scene_coverage.passed

    service = SceneVersioningService(tmp_path)
    version = service.save_version(workflow_id, scene, activate=False)
    artifact_dir = service.version_artifacts_dir(workflow_id, version.version_id)
    artifact_dir.mkdir(parents=True)
    requirements_payload = requirements.model_dump(mode="json")
    scene_payload = scene.model_dump(mode="json")
    if certificate_schema == "1.0.0":
        for field_name in (
            "field_evidence",
            "conflicts",
            "assumptions",
            "requires_confirmation",
            "confirmation_fields",
        ):
            requirements_payload.pop(field_name, None)
        scene_payload.pop("schema_version", None)
    _write_json(artifact_dir / "requirements_spec.json", requirements_payload)
    _write_json(artifact_dir / "scene_spec.json", scene_payload)
    _write_json(artifact_dir / "design_blueprint.json", blueprint.model_dump(mode="json"))
    (artifact_dir / "design.glb").write_bytes(b"certified-glb-binary-evidence")
    (artifact_dir / "preview.png").write_bytes(b"certified-preview-evidence")

    component_proof = None
    if include_geometry_program:
        component_proof = _component_proof(scene)
        _write_json(artifact_dir / "component_proofs.json", component_proof)
    metadata = {
        "scene_id": scene.scene_id,
        "generation_mode": "real_blender",
    }
    if component_proof is not None:
        metadata["component_proof"] = {
            "sha256": _sha256(artifact_dir / "component_proofs.json"),
            "report_sha256": component_proof["report_sha256"],
            "passed": True,
        }
    _write_json(artifact_dir / "scene_metadata.json", metadata)
    _write_build_lock(
        artifact_dir,
        scene=scene,
        schema_version=certificate_schema,
        include_component_proof=include_geometry_program,
    )

    generation_artifacts = {
        "glb": str(artifact_dir / "design.glb"),
        "preview": str(artifact_dir / "preview.png"),
        "metadata": str(artifact_dir / "scene_metadata.json"),
        "build_lock": str(artifact_dir / "build.lock.json"),
    }
    if include_geometry_program:
        generation_artifacts["component_proofs"] = str(artifact_dir / "component_proofs.json")
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts=generation_artifacts,
    )
    requirement_coverage = evaluate_requirement_coverage(requirements, scene)
    qa_report = ValidationReport(
        design_id=scene.scene_id,
        status="passed",
        score=1.0,
        checks={"integrity": True},
    )
    glb_inspection = GlbInspectionReport(
        inspection_mode="glb_parse",
        file_exists=True,
        file_size_bytes=(artifact_dir / "design.glb").stat().st_size,
        format_valid=True,
        node_count=1,
        mesh_count=1,
        primitive_count=1,
        valid_primitive_count=1,
        position_accessor_count=1,
        buffer_count=1,
        buffer_view_count=1,
        binary_chunk_count=1,
        material_count=1,
        checks={"semantic_mesh_coverage_complete": True},
        structural_qa_passed=True,
    )
    geometry_validation = GeometryValidationReport(
        status="passed",
        checks={"integrity": True},
        mesh_qa=MeshQAReport(
            glb_parse_ok=True,
            checks=[],
            mesh_qa_passed=True,
        ),
        mesh_qa_level="mesh_level_basic",
    )
    preview_inspection = PreviewInspectionReport(
        inspection_mode="png_parse",
        file_exists=True,
        file_size_bytes=(artifact_dir / "preview.png").stat().st_size,
        width=1920,
        height=1080,
        format="png",
        minimum_resolution_valid=True,
        visual_quality_valid=True,
        preview_qa_passed=True,
    )
    pre_gate = QualityGateReport(
        stage="pre_blender",
        passed=True,
        checks={"contracts": True},
    )
    post_gate = QualityGateReport(
        stage="post_blender",
        passed=True,
        checks={"artifacts": True},
    )
    certificate = build_completion_certificate(
        workflow_id=workflow_id,
        requirements=requirements,
        design_blueprint=blueprint,
        blueprint_requirement_coverage=blueprint_requirement_coverage,
        blueprint_scene_coverage=blueprint_scene_coverage,
        scene=scene,
        requirement_coverage=requirement_coverage,
        generation=generation,
        qa_report=qa_report,
        glb_inspection=glb_inspection,
        geometry_validation=geometry_validation,
        preview_inspection=preview_inspection,
        pre_blender_gate=pre_gate,
        post_blender_gate=post_gate,
    )
    if certificate_schema == "1.0.0":
        certificate = certificate.model_copy(
            update={
                "schema_version": "1.0.0",
                "requirements_sha256": _canonical_json_sha256(
                    requirements_payload,
                    exclude={"warnings", "repair_events"},
                ),
                "design_blueprint_sha256": None,
                "scene_spec_sha256": _canonical_json_sha256(scene_payload),
                "checks": {name: True for name in _CHECKS_V1},
            }
        )
    assert certificate.schema_version == certificate_schema
    assert certificate.status == "issued"
    _write_json(
        artifact_dir / "completion_certificate.json",
        certificate.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "status.json",
        {
            "workflow_id": workflow_id,
            "version_id": version.version_id,
            "active_version_id": version.version_id,
            "status": "completed",
            "generation_mode": "real_blender",
            "completion_certificate_status": "issued",
        },
    )
    _write_json(artifact_dir / "qa_report.json", qa_report.model_dump(mode="json"))
    _write_json(
        artifact_dir / "geometry_validation.json",
        geometry_validation.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "glb_inspection.json",
        glb_inspection.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "requirement_coverage.json",
        requirement_coverage.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "blueprint_requirement_coverage.json",
        blueprint_requirement_coverage.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "blueprint_scene_coverage.json",
        blueprint_scene_coverage.model_dump(mode="json"),
    )
    _write_json(
        artifact_dir / "quality_gates.json",
        {"pre_blender": pre_gate.model_dump(), "post_blender": post_gate.model_dump()},
    )
    service.update_version(
        workflow_id,
        version.version_id,
        status="completed",
        artifact_dir=str(artifact_dir),
        generation_mode="real_blender",
    )
    service.commit_active_version(workflow_id, version.version_id)
    service.verified_active_status_path(workflow_id)
    return _CertifiedBundle(
        service=service,
        workflow_id=workflow_id,
        version_id=version.version_id,
        artifact_dir=artifact_dir,
        requirements=requirements,
        blueprint=blueprint,
        scene=scene,
        generation=generation,
        certificate=certificate,
    )


def _geometry_program() -> GeometryProgram:
    return GeometryProgram.model_validate(
        {
            "schema_version": "1.0.0",
            "program_id": "site_shelter",
            "semantic_role": "equipment_shelter",
            "requested_quantity": 1,
            "units": "meters",
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": "openai/gpt-oss-120b",
            "structured_output_mode": "strict_json_schema",
            "source_prompt_sha256": "a" * 64,
            "source_description": "Generate a bounded outdoor telecom equipment shelter.",
            "source_description_origin": "user_requirement",
            "nodes": [
                {
                    "kind": "primitive",
                    "node_id": "body",
                    "primitive": "box",
                    "size_m": {"x": 3.0, "y": 2.0, "z": 2.5},
                    "semantic_role": "equipment_shelter",
                },
                {
                    "kind": "primitive",
                    "node_id": "roof",
                    "primitive": "box",
                    "size_m": {"x": 3.2, "y": 2.2, "z": 0.2},
                },
                {
                    "kind": "primitive",
                    "node_id": "door",
                    "primitive": "box",
                    "size_m": {"x": 0.8, "y": 0.1, "z": 2.0},
                },
            ],
            "limitations": ["No structural or electrical engineering certification."],
        }
    )


def _component_proof(scene: SceneSpec) -> dict:
    program = scene.geometry_programs[0]
    program_sha256 = _canonical_json_sha256(program.model_dump(mode="json"))
    payload = {
        "schema_version": "1.0.0",
        "scene_id": scene.scene_id,
        "workflow_id": scene.scene_id,
        "assembly_plan_schema_version": None,
        "manifest_catalog_sha256": None,
        "assembly_validation": {"passed": True},
        "components": [],
        "geometry_programs": [
            {
                "component_id": f"geometry_program:{program.program_id}",
                "role_id": program.semantic_role,
                "origin": "geometry_program",
                "strategy": "procedural_generate",
                "geometry_program": {
                    "program_id": program.program_id,
                    "program_sha256": program_sha256,
                },
                "quantity": program.requested_quantity,
                "qa": {
                    "semantic_geometry_present": True,
                    "node_set_matches_program": True,
                    "passed": True,
                },
            }
        ],
        "operation_execution": {
            "declared_operation_ids": [],
            "executed_operation_ids": [],
            "missing_operation_ids": [],
            "passed": True,
        },
    }
    payload["report_sha256"] = _component_report_hash(payload)
    return payload


def _write_build_lock(
    artifact_dir: Path,
    *,
    scene: SceneSpec,
    schema_version: str,
    include_component_proof: bool,
) -> None:
    artifact_names = ["design.glb", "preview.png", "scene_metadata.json"]
    if include_component_proof:
        artifact_names.append("component_proofs.json")
    artifacts = {
        name: {
            "size_bytes": (artifact_dir / name).stat().st_size,
            "sha256": _sha256(artifact_dir / name),
        }
        for name in artifact_names
    }
    payload = {
        "schema_version": schema_version,
        "build_id": "build_m0_integrity",
        "attempt_id": "attempt_m0_integrity_1",
        "scene_id": scene.scene_id,
        "scene_spec_sha256": _sha256(artifact_dir / "scene_spec.json"),
        "worker_script_sha256": "b" * 64,
        "blender_runtime": {
            "version": "4.5.12 LTS test boundary",
            "background": True,
            "factory_startup": True,
        },
        "command_profile": {
            "background": True,
            "factory_startup": True,
            "python_exit_code": 97,
        },
        "artifacts": artifacts,
    }
    if schema_version in {"1.1.0", "1.2.0"}:
        worker_files = {"generate_scene.py": "c" * 64}
        payload["worker_bundle"] = {
            "files": worker_files,
            "sha256": hashlib.sha256(
                json.dumps(
                    worker_files,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }
    if schema_version == "1.2.0":
        trusted_inputs = _trusted_inputs(scene)
        payload["trusted_inputs"] = trusted_inputs
        payload["trusted_inputs_sha256"] = _runtime_json_sha256(trusted_inputs)
    _write_json(artifact_dir / "build.lock.json", payload)


def _trusted_inputs(scene: SceneSpec) -> dict:
    programs = [
        {
            "program_id": program.program_id,
            "program_sha256": _runtime_json_sha256(program.model_dump(mode="json")),
        }
        for program in scene.geometry_programs
    ]
    return {
        "assembly_plan_schema_version": None,
        "manifest_catalog_sha256": None,
        "builder_catalog": None,
        "manifests": [],
        "builder_profiles": [],
        "exact_assets": [],
        "assembly_operations": [],
        "geometry_programs": sorted(programs, key=lambda item: item["program_id"]),
    }


def _rebind_certificate_artifact(
    artifact_dir: Path,
    *,
    logical_name: str,
    file_name: str,
) -> None:
    certificate_path = artifact_dir / "completion_certificate.json"
    payload = json.loads(certificate_path.read_text(encoding="utf-8"))
    artifact_path = artifact_dir / file_name
    for artifact in payload["artifacts"]:
        if artifact["logical_name"] == logical_name:
            artifact["size_bytes"] = artifact_path.stat().st_size
            artifact["sha256"] = _sha256(artifact_path)
            break
    else:
        raise AssertionError(f"missing certified artifact: {logical_name}")
    _write_json(certificate_path, payload)


def _component_report_hash(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _canonical_json_sha256(payload: dict, *, exclude: set[str] | None = None) -> str:
    value = {key: item for key, item in payload.items() if key not in (exclude or set())}
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _runtime_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
