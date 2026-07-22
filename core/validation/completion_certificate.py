from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from core.contracts.completion import (
    CertifiedArtifact,
    CompletionCertificate,
    RequirementCoverageReport,
)
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.performance import requirements_hash, scene_spec_hash
from core.services.blender_runner import GenerationResult

_CERTIFIED_ARTIFACTS = ("glb", "preview", "metadata", "build_lock")


def build_completion_certificate(
    *,
    workflow_id: str,
    requirements: RequirementSpec | None,
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
    artifacts = _artifact_evidence(generation)
    requirements_sha256 = requirements_hash(requirements) if requirements else "0" * 64
    scene_sha256 = scene_spec_hash(scene) if scene else "0" * 64
    mesh_qa = geometry_validation.mesh_qa if geometry_validation else None
    checks = {
        "requirements_present": requirements is not None,
        "scene_spec_present": scene is not None,
        "requirement_coverage_passed": bool(requirement_coverage and requirement_coverage.passed),
        "pre_blender_gate_passed": bool(pre_blender_gate and pre_blender_gate.passed),
        "real_blender_generation": bool(
            generation and generation.status == "generated" and generation.mode == "real_blender"
        ),
        "required_artifacts_regular_files": len(artifacts) == len(_CERTIFIED_ARTIFACTS),
        "artifact_hashes_recorded": len(artifacts) == len(_CERTIFIED_ARTIFACTS)
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
    blockers = [name for name, passed in checks.items() if not passed]
    return CompletionCertificate(
        workflow_id=workflow_id,
        status="issued" if not blockers else "rejected",
        evaluated_at=datetime.now(UTC),
        requirements_sha256=requirements_sha256,
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
    scene: SceneSpec | None,
    generation: GenerationResult | None,
) -> bool:
    if (
        certificate is None
        or certificate.status != "issued"
        or not certificate.checks
        or not all(certificate.checks.values())
        or requirements is None
        or scene is None
        or generation is None
        or certificate.requirements_sha256 != requirements_hash(requirements)
        or certificate.scene_spec_sha256 != scene_spec_hash(scene)
    ):
        return False
    expected = {artifact.logical_name: artifact for artifact in certificate.artifacts}
    if set(expected) != set(_CERTIFIED_ARTIFACTS):
        return False
    for logical_name in _CERTIFIED_ARTIFACTS:
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


def _artifact_evidence(generation: GenerationResult | None) -> list[CertifiedArtifact]:
    if generation is None:
        return []
    artifacts: list[CertifiedArtifact] = []
    for logical_name in _CERTIFIED_ARTIFACTS:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
