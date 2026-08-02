from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from core.agents.blueprint_composer import design_blueprint_hash
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.contracts.completion import (
    CertifiedArtifact,
    CompletionCertificate,
    RequirementCoverageReport,
)
from core.contracts.design_blueprint import BlueprintCoverageReport, DesignBlueprint
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.performance import requirements_hash, scene_spec_hash
from core.services.blender_runner import GenerationResult
from core.services.cognitive_scene_compiler import cognitive_plan_hash

_BASE_CERTIFIED_ARTIFACTS = ("glb", "preview", "metadata", "build_lock")
_M0_CERTIFIED_ARTIFACTS = (
    "glb",
    "preview",
    "metadata",
    "component_proofs",
    "build_lock",
)


def build_completion_certificate(
    *,
    workflow_id: str,
    requirements: RequirementSpec | None,
    design_blueprint: DesignBlueprint | None,
    blueprint_requirement_coverage: BlueprintCoverageReport | None,
    blueprint_scene_coverage: BlueprintCoverageReport | None,
    scene: SceneSpec | None,
    requirement_coverage: RequirementCoverageReport | None,
    generation: GenerationResult | None,
    qa_report: ValidationReport | None,
    glb_inspection: GlbInspectionReport | None,
    geometry_validation: GeometryValidationReport | None,
    preview_inspection: PreviewInspectionReport | None,
    pre_blender_gate: QualityGateReport | None,
    post_blender_gate: QualityGateReport | None,
    cognitive_plan: CognitiveDesignPlan | None = None,
) -> CompletionCertificate:
    if cognitive_plan is not None:
        return _build_cognitive_completion_certificate(
            workflow_id=workflow_id,
            cognitive_plan=cognitive_plan,
            scene=scene,
            requirement_coverage=requirement_coverage,
            generation=generation,
            qa_report=qa_report,
            glb_inspection=glb_inspection,
            geometry_validation=geometry_validation,
            preview_inspection=preview_inspection,
            pre_blender_gate=pre_blender_gate,
            post_blender_gate=post_blender_gate,
        )
    component_proof_required = bool(
        scene
        and (
            scene.geometry_programs
            or (scene.assembly_plan is not None and scene.assembly_plan.schema_version == "1.1.0")
        )
    )
    certified_artifact_names = (
        _M0_CERTIFIED_ARTIFACTS if component_proof_required else _BASE_CERTIFIED_ARTIFACTS
    )
    artifacts = _artifact_evidence(generation, certified_artifact_names)
    requirements_sha256 = requirements_hash(requirements) if requirements else "0" * 64
    blueprint_sha256 = (
        design_blueprint_hash(design_blueprint) if design_blueprint is not None else None
    )
    scene_sha256 = scene_spec_hash(scene) if scene else "0" * 64
    mesh_qa = geometry_validation.mesh_qa if geometry_validation else None
    checks = {
        "requirements_present": requirements is not None,
        "design_blueprint_present": design_blueprint is not None,
        "blueprint_requirement_coverage_passed": bool(
            blueprint_requirement_coverage and blueprint_requirement_coverage.passed
        ),
        "blueprint_scene_coverage_passed": bool(
            blueprint_scene_coverage and blueprint_scene_coverage.passed
        ),
        "scene_spec_present": scene is not None,
        "requirement_coverage_passed": bool(requirement_coverage and requirement_coverage.passed),
        "pre_blender_gate_passed": bool(pre_blender_gate and pre_blender_gate.passed),
        "real_blender_generation": bool(
            generation and generation.status == "generated" and generation.mode == "real_blender"
        ),
        "required_artifacts_regular_files": len(artifacts) == len(certified_artifact_names),
        "artifact_hashes_recorded": len(artifacts) == len(certified_artifact_names)
        and all(artifact.size_bytes > 0 and bool(artifact.sha256) for artifact in artifacts),
        "qa_report_passed": bool(qa_report and qa_report.status == "passed"),
        "glb_binary_integrity_passed": bool(
            glb_inspection
            and glb_inspection.structural_qa_passed
            and glb_inspection.binary_chunk_count > 0
            and glb_inspection.valid_primitive_count == glb_inspection.primitive_count
            and glb_inspection.primitive_count > 0
        ),
        "semantic_mesh_coverage_complete": bool(
            glb_inspection and glb_inspection.checks.get("semantic_mesh_coverage_complete") is True
        ),
        "geometry_validation_passed": bool(
            geometry_validation and geometry_validation.status == "passed"
        ),
        "mesh_qa_passed": bool(mesh_qa and mesh_qa.mesh_qa_passed),
        "preview_qa_passed": bool(preview_inspection and preview_inspection.preview_qa_passed),
        "post_blender_gate_passed": bool(post_blender_gate and post_blender_gate.passed),
        "no_critical_fallback": bool(
            generation and generation.mode == "real_blender" and generation.status == "generated"
        ),
    }
    if component_proof_required:
        checks["component_proof_verified"] = _component_proof_verified(
            generation,
            scene,
        )
    blockers = [name for name, passed in checks.items() if not passed]
    return CompletionCertificate(
        schema_version="1.2.0" if component_proof_required else "1.1.0",
        workflow_id=workflow_id,
        status="issued" if not blockers else "rejected",
        evaluated_at=datetime.now(UTC),
        requirements_sha256=requirements_sha256,
        design_blueprint_sha256=blueprint_sha256,
        scene_spec_sha256=scene_sha256,
        generation_mode=generation.mode if generation else None,
        artifacts=artifacts,
        checks=checks,
        blockers=blockers,
    )


def verify_completion_certificate(
    certificate: CompletionCertificate | None,
    *,
    requirements: RequirementSpec | None,
    design_blueprint: DesignBlueprint | None,
    scene: SceneSpec | None,
    generation: GenerationResult | None,
    cognitive_plan: CognitiveDesignPlan | None = None,
) -> bool:
    if certificate is not None and certificate.schema_version == "1.3.0":
        return _verify_cognitive_completion_certificate(
            certificate,
            cognitive_plan=cognitive_plan,
            scene=scene,
            generation=generation,
        )
    if (
        certificate is None
        or certificate.status != "issued"
        or not certificate.checks
        or not all(certificate.checks.values())
        or requirements is None
        or design_blueprint is None
        or scene is None
        or generation is None
        or certificate.requirements_sha256 != requirements_hash(requirements)
        or certificate.design_blueprint_sha256 != design_blueprint_hash(design_blueprint)
        or certificate.scene_spec_sha256 != scene_spec_hash(scene)
    ):
        return False
    certified_artifact_names = (
        _M0_CERTIFIED_ARTIFACTS
        if certificate.schema_version == "1.2.0"
        else _BASE_CERTIFIED_ARTIFACTS
    )
    expected = {artifact.logical_name: artifact for artifact in certificate.artifacts}
    if set(expected) != set(certified_artifact_names):
        return False
    for logical_name in certified_artifact_names:
        path_value = generation.artifacts.get(logical_name)
        if not path_value:
            return False
        path = Path(path_value)
        artifact = expected[logical_name]
        if (
            not path.is_file()
            or path.name != artifact.file_name
            or path.stat().st_size != artifact.size_bytes
            or _sha256(path) != artifact.sha256
        ):
            return False
    return True


def _build_cognitive_completion_certificate(
    *,
    workflow_id: str,
    cognitive_plan: CognitiveDesignPlan,
    scene: SceneSpec | None,
    requirement_coverage: RequirementCoverageReport | None,
    generation: GenerationResult | None,
    qa_report: ValidationReport | None,
    glb_inspection: GlbInspectionReport | None,
    geometry_validation: GeometryValidationReport | None,
    preview_inspection: PreviewInspectionReport | None,
    pre_blender_gate: QualityGateReport | None,
    post_blender_gate: QualityGateReport | None,
) -> CompletionCertificate:
    artifacts = _artifact_evidence(generation, _M0_CERTIFIED_ARTIFACTS)
    plan_sha256 = cognitive_plan_hash(cognitive_plan)
    mesh_qa = geometry_validation.mesh_qa if geometry_validation else None
    checks = {
        "cognitive_plan_present": True,
        "cognitive_plan_linked": bool(
            scene
            and scene.schema_version == "2.0.0"
            and scene.cognitive_plan_sha256 == plan_sha256
            and scene.design_intent_id == cognitive_plan.design_intent.intent_id
            and scene.component_graph_id == cognitive_plan.component_graph.graph_id
            and scene.asset_decision_plan_id == cognitive_plan.asset_decision_plan.plan_id
            and scene.specialist_route_id == cognitive_plan.specialist_route.route_id
        ),
        "scene_spec_present": scene is not None,
        "requirement_coverage_passed": bool(requirement_coverage and requirement_coverage.passed),
        "pre_blender_gate_passed": bool(pre_blender_gate and pre_blender_gate.passed),
        "real_blender_generation": bool(
            generation and generation.status == "generated" and generation.mode == "real_blender"
        ),
        "required_artifacts_regular_files": len(artifacts) == len(_M0_CERTIFIED_ARTIFACTS),
        "artifact_hashes_recorded": len(artifacts) == len(_M0_CERTIFIED_ARTIFACTS)
        and all(item.size_bytes > 0 and bool(item.sha256) for item in artifacts),
        "qa_report_passed": bool(qa_report and qa_report.status == "passed"),
        "glb_binary_integrity_passed": bool(
            glb_inspection
            and glb_inspection.structural_qa_passed
            and glb_inspection.binary_chunk_count > 0
            and glb_inspection.valid_primitive_count == glb_inspection.primitive_count
            and glb_inspection.primitive_count > 0
        ),
        "geometry_program_mesh_coverage_complete": bool(
            glb_inspection
            and glb_inspection.checks.get("geometry_program_mesh_coverage") is True
        ),
        "geometry_validation_passed": bool(
            geometry_validation and geometry_validation.status == "passed"
        ),
        "mesh_qa_passed": bool(mesh_qa and mesh_qa.mesh_qa_passed),
        "preview_qa_passed": bool(preview_inspection and preview_inspection.preview_qa_passed),
        "post_blender_gate_passed": bool(post_blender_gate and post_blender_gate.passed),
        "no_critical_fallback": bool(
            generation and generation.mode == "real_blender" and generation.status == "generated"
        ),
        "component_proof_verified": bool(scene and _component_proof_verified(generation, scene)),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return CompletionCertificate(
        schema_version="1.3.0",
        workflow_id=workflow_id,
        status="issued" if not blockers else "rejected",
        evaluated_at=datetime.now(UTC),
        requirements_sha256=plan_sha256,
        cognitive_plan_sha256=plan_sha256,
        scene_spec_sha256=scene_spec_hash(scene) if scene else "0" * 64,
        generation_mode=generation.mode if generation else None,
        artifacts=artifacts,
        checks=checks,
        blockers=blockers,
    )


def _verify_cognitive_completion_certificate(
    certificate: CompletionCertificate,
    *,
    cognitive_plan: CognitiveDesignPlan | None,
    scene: SceneSpec | None,
    generation: GenerationResult | None,
) -> bool:
    if (
        certificate.status != "issued"
        or not certificate.checks
        or not all(certificate.checks.values())
        or cognitive_plan is None
        or scene is None
        or generation is None
    ):
        return False
    plan_sha256 = cognitive_plan_hash(cognitive_plan)
    if (
        certificate.requirements_sha256 != plan_sha256
        or certificate.cognitive_plan_sha256 != plan_sha256
        or certificate.scene_spec_sha256 != scene_spec_hash(scene)
        or scene.cognitive_plan_sha256 != plan_sha256
    ):
        return False
    expected = {artifact.logical_name: artifact for artifact in certificate.artifacts}
    if set(expected) != set(_M0_CERTIFIED_ARTIFACTS):
        return False
    for logical_name in _M0_CERTIFIED_ARTIFACTS:
        path_value = generation.artifacts.get(logical_name)
        if not path_value:
            return False
        path = Path(path_value)
        artifact = expected[logical_name]
        if (
            not path.is_file()
            or path.name != artifact.file_name
            or path.stat().st_size != artifact.size_bytes
            or _sha256(path) != artifact.sha256
        ):
            return False
    return True


def _artifact_evidence(
    generation: GenerationResult | None,
    logical_names: tuple[str, ...],
) -> list[CertifiedArtifact]:
    if generation is None:
        return []
    artifacts: list[CertifiedArtifact] = []
    for logical_name in logical_names:
        value = generation.artifacts.get(logical_name)
        path = Path(value) if value else None
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            continue
        artifacts.append(
            CertifiedArtifact(
                logical_name=logical_name,  # type: ignore[arg-type]
                file_name=path.name,
                size_bytes=path.stat().st_size,
                sha256=_sha256(path),
            )
        )
    return artifacts


def _component_proof_verified(
    generation: GenerationResult | None,
    scene: SceneSpec,
) -> bool:
    if generation is None:
        return False
    value = generation.artifacts.get("component_proofs")
    metadata_value = generation.artifacts.get("metadata")
    if not value or not metadata_value:
        return False
    proof_path = Path(value)
    metadata_path = Path(metadata_value)
    try:
        import json

        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected = proof.get("report_sha256")
    unsigned = {key: value for key, value in proof.items() if key != "report_sha256"}
    actual = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    proof_metadata = metadata.get("component_proof")
    expected_roles = (
        {component.role_id for component in scene.assembly_plan.components}
        if scene.assembly_plan is not None and scene.assembly_plan.schema_version == "1.1.0"
        else set()
    )
    component_roles = {
        component.get("role_id")
        for component in proof.get("components", [])
        if isinstance(component, dict)
    }
    program_ids = {
        item.get("geometry_program", {}).get("program_id")
        for item in proof.get("geometry_programs", [])
        if isinstance(item, dict)
    }
    proofs = [
        *proof.get("components", []),
        *proof.get("geometry_programs", []),
    ]
    proof_strategies = {"reuse", "adapt", "compose", "procedural_generate"}
    return bool(
        proof_path.is_file()
        and metadata_path.is_file()
        and proof.get("scene_id") == scene.scene_id
        and isinstance(expected, str)
        and expected == actual
        and isinstance(proof_metadata, dict)
        and proof_metadata.get("sha256") == _sha256(proof_path)
        and proof_metadata.get("report_sha256") == expected
        and proof_metadata.get("passed") is True
        and component_roles == expected_roles
        and program_ids == {program.program_id for program in scene.geometry_programs}
        and proof.get("operation_execution", {}).get("passed") is True
        and all(item.get("strategy") in proof_strategies for item in proofs)
        and all(item.get("qa", {}).get("passed") is True for item in proofs)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
