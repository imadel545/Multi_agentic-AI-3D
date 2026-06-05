import time
from pathlib import Path

from pydantic import ValidationError

from core.contracts.assets import AssetManifest
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.services.blender_runner import GenerationResult
from core.validation.scene_validator import validate_scene_spec

POST_BLENDER_QA_THRESHOLD = 0.95
MIN_REAL_BLENDER_MODEL_BYTES = 1024


def evaluate_pre_blender_gate(
    requirements: RequirementSpec | None,
    requirement_report: ValidationReport | None,
    scene: SceneSpec | None,
    scene_report: ValidationReport | None,
    selected_assets: list[AssetManifest],
    all_assets: list[AssetManifest],
    repair_attempts: int,
    max_repair_attempts: int,
) -> QualityGateReport:
    started = time.perf_counter()
    checks: dict[str, bool] = {}
    critical_errors: list[str] = []
    warnings: list[str] = []

    checks["requirements_valid"] = _requirements_valid(requirements)
    checks["rules_valid"] = requirement_report is not None and requirement_report.status == "passed"
    checks["assets_selected"] = bool(selected_assets)
    checks["assets_valid"] = bool(selected_assets) and all(
        asset.is_validated for asset in selected_assets
    )
    checks["assets_network_compatible"] = _assets_network_compatible(
        requirements,
        selected_assets,
    )
    checks["assets_tower_compatible"] = _assets_tower_compatible(requirements, selected_assets)
    checks["scene_spec_valid"] = _scene_valid(scene, all_assets)
    checks["scene_report_valid"] = scene_report is not None and scene_report.status == "passed"
    checks["repair_attempts_valid"] = repair_attempts <= max_repair_attempts
    checks["no_critical_errors"] = not (
        (requirement_report and requirement_report.errors) or (scene_report and scene_report.errors)
    )

    for name, passed in checks.items():
        if not passed:
            critical_errors.append(name)
    if requirement_report:
        warnings.extend(warning.code for warning in requirement_report.warnings)
    if scene_report:
        warnings.extend(warning.code for warning in scene_report.warnings)
    return QualityGateReport(
        stage="pre_blender",
        passed=not critical_errors,
        checks=checks,
        critical_errors=critical_errors,
        warnings=warnings,
        duration_ms=_duration_ms(started),
    )


def evaluate_post_blender_gate(
    generation: GenerationResult | None,
    qa_report: ValidationReport | None,
    glb_inspection: GlbInspectionReport | None = None,
    preview_inspection: PreviewInspectionReport | None = None,
    geometry_validation: GeometryValidationReport | None = None,
) -> QualityGateReport:
    started = time.perf_counter()
    artifacts = generation.artifacts if generation else {}
    glb_path = Path(artifacts.get("glb", ""))
    preview_path = Path(artifacts.get("preview", ""))
    metadata_path = Path(artifacts.get("metadata", ""))
    model_exists = glb_path.exists()
    artifact_size_bytes = glb_path.stat().st_size if model_exists else 0
    checks = {
        "generation_mode_explicit": bool(generation and generation.mode),
        "model_exists": model_exists
        and (
            generation is None
            or generation.mode != "real_blender"
            or artifact_size_bytes >= MIN_REAL_BLENDER_MODEL_BYTES
        ),
        "preview_exists": preview_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "artifact_size_valid": artifact_size_bytes > 0,
        "qa_score_valid": qa_report is not None
        and qa_report.score >= POST_BLENDER_QA_THRESHOLD
        and qa_report.status == "passed",
        "critical_warnings_absent": not [
            warning
            for warning in (qa_report.warnings if qa_report else [])
            if warning.severity == "error"
        ],
        "glb_structure_valid": glb_inspection is not None and glb_inspection.structural_qa_passed,
        "expected_objects_present": glb_inspection is not None
        and glb_inspection.checks.get("expected_objects_present", False),
        "minimum_node_count_valid": glb_inspection is not None
        and glb_inspection.checks.get("minimum_node_count_valid", False),
        "real_blender_glb_parse_required": generation is not None
        and (
            generation.mode != "real_blender"
            or (
                glb_inspection is not None
                and glb_inspection.inspection_mode == "glb_parse"
                and glb_inspection.format_valid
            )
        ),
        "geometry_validation_valid": geometry_validation is not None
        and geometry_validation.status == "passed",
        "preview_resolution_valid": preview_inspection is not None
        and preview_inspection.minimum_resolution_valid,
        "preview_visual_quality_valid": generation is not None
        and preview_inspection is not None
        and (generation.mode != "real_blender" or preview_inspection.visual_quality_valid),
    }
    critical_errors = [name for name, passed in checks.items() if not passed]
    warnings = [warning.code for warning in qa_report.warnings] if qa_report else []
    if glb_inspection:
        warnings.extend(glb_inspection.warnings)
    if geometry_validation:
        warnings.extend(geometry_validation.warnings)
    if preview_inspection:
        warnings.extend(preview_inspection.warnings)
    details = {
        "glb_inspection": glb_inspection.model_dump() if glb_inspection else None,
        "geometry_validation": geometry_validation.model_dump() if geometry_validation else None,
        "preview_inspection": preview_inspection.model_dump() if preview_inspection else None,
    }
    return QualityGateReport(
        stage="post_blender",
        passed=not critical_errors,
        checks=checks,
        details=details,
        critical_errors=critical_errors,
        warnings=warnings,
        duration_ms=_duration_ms(started),
    )


def _requirements_valid(requirements: RequirementSpec | None) -> bool:
    if requirements is None:
        return False
    try:
        RequirementSpec.model_validate(requirements.model_dump())
    except ValidationError:
        return False
    return True


def _scene_valid(scene: SceneSpec | None, assets: list[AssetManifest]) -> bool:
    if scene is None:
        return False
    try:
        SceneSpec.model_validate(scene.model_dump())
    except ValidationError:
        return False
    return validate_scene_spec(scene, assets).status == "passed"


def _assets_network_compatible(
    requirements: RequirementSpec | None,
    selected_assets: list[AssetManifest],
) -> bool:
    if requirements is None or not selected_assets:
        return False
    return all(requirements.network_type in asset.compatible_networks for asset in selected_assets)


def _assets_tower_compatible(
    requirements: RequirementSpec | None,
    selected_assets: list[AssetManifest],
) -> bool:
    if requirements is None or not selected_assets:
        return False
    tower_types = {
        tower_type
        for asset in selected_assets
        if asset.type == "tower"
        for tower_type in asset.compatible_tower_types
    }
    acceptable_tower_types = {requirements.tower_type, *tower_types}
    return all(
        not asset.compatible_tower_types
        or any(tower_type in asset.compatible_tower_types for tower_type in acceptable_tower_types)
        or asset.type == "tower"
        for asset in selected_assets
    )


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
