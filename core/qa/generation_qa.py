import json
from pathlib import Path

from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.services.blender_runner import GenerationResult


class GenerationQA:
    def validate(
        self,
        scene: SceneSpec,
        generation: GenerationResult,
        glb_inspection: GlbInspectionReport,
        preview_inspection: PreviewInspectionReport,
        geometry_validation: GeometryValidationReport,
        allow_fallback: bool = False,
    ) -> ValidationReport:
        glb_path = Path(generation.artifacts.get("glb", ""))
        preview_path = Path(generation.artifacts.get("preview", ""))
        metadata_path = Path(generation.artifacts.get("metadata", ""))
        metadata = _load_metadata(metadata_path)
        asset_imports = metadata.get("asset_imports", [])
        expected_asset_placements = (
            1
            + len(scene.sectors)
            + sum(1 for sector in scene.sectors if sector.radio_asset_id)
            + len(scene.accessory_assets)
        )

        checks = {
            "glb_exists": glb_path.exists(),
            "glb_size_valid": glb_path.exists() and glb_path.stat().st_size > 32,
            "preview_exists": preview_path.exists(),
            "preview_size_valid": preview_path.exists() and preview_path.stat().st_size > 32,
            "metadata_exists": metadata_path.exists(),
            "metadata_sector_count_valid": metadata.get("sector_count") == len(scene.sectors),
            "metadata_scene_id_valid": metadata.get("scene_id") == scene.scene_id,
            "metadata_generation_mode_valid": metadata.get("generation_mode") == generation.mode,
            "metadata_assets_used_valid": scene.tower.asset_id in metadata.get("assets_used", []),
            "metadata_azimuths_valid": metadata.get("azimuths_deg")
            == [sector.azimuth_deg for sector in scene.sectors],
            "metadata_antenna_heights_valid": metadata.get("antenna_heights_m")
            == [sector.install_height_m for sector in scene.sectors],
            "metadata_mechanical_tilts_valid": metadata.get("mechanical_tilts_deg")
            == [sector.mechanical_tilt_deg for sector in scene.sectors],
            "metadata_visual_elements_valid": metadata.get("visual_elements")
            == scene.visual_elements.model_dump(),
            "metadata_accessory_assets_valid": _metadata_accessory_assets_valid(metadata, scene),
            "metadata_preview_camera_valid": isinstance(metadata.get("preview_camera"), dict)
            and bool(metadata["preview_camera"].get("camera")),
            "metadata_segment_connectivity_valid": _segment_connectivity_valid(metadata),
            "metadata_asset_imports_present": isinstance(asset_imports, list)
            and len(asset_imports) >= expected_asset_placements,
            "metadata_asset_import_modes_valid": _asset_import_modes_valid(asset_imports),
            "metadata_asset_import_summary_valid": _asset_import_summary_valid(
                metadata.get("asset_import_summary"), asset_imports
            ),
            "metadata_imported_glb_records_valid": _imported_glb_records_valid(asset_imports),
            "metadata_asset_fallbacks_visible": _asset_fallbacks_visible(asset_imports),
            "metadata_no_missing_asset_without_fallback": not any(
                record.get("import_mode") == "missing_file" for record in asset_imports
            ),
            "generation_real_blender": generation.status == "generated"
            and generation.mode == "real_blender",
            "glb_inspection_available": glb_inspection.inspection_mode == "glb_parse",
            "glb_structure_valid": glb_inspection.structural_qa_passed,
            "expected_objects_present": glb_inspection.checks.get(
                "expected_objects_present", False
            ),
            "preview_inspection_available": preview_inspection.inspection_mode == "png_parse",
            "preview_resolution_valid": preview_inspection.minimum_resolution_valid,
            "preview_visual_quality_valid": preview_inspection.visual_quality_valid,
            "geometry_validation_valid": geometry_validation.status == "passed",
        }
        warnings = []
        if generation.status == "fallback":
            warnings.append(
                ValidationIssue(
                    code="BLENDER_FALLBACK_USED",
                    message=f"Blender generation used fallback mode: {generation.mode}.",
                    severity="warning",
                )
            )
        if generation.error:
            warnings.append(
                ValidationIssue(
                    code="BLENDER_GENERATION_ERROR",
                    message=generation.error,
                    severity="warning",
                )
            )
        warnings.extend(
            ValidationIssue(
                code=f"GLB_INSPECTION_{warning}",
                message=f"GLB inspection warning: {warning}",
                severity="warning",
            )
            for warning in glb_inspection.warnings
        )
        warnings.extend(
            ValidationIssue(
                code=f"PREVIEW_INSPECTION_{warning}",
                message=f"Preview inspection warning: {warning}",
                severity="warning",
            )
            for warning in preview_inspection.warnings
        )
        warnings.extend(
            ValidationIssue(
                code=f"GEOMETRY_VALIDATION_{warning}",
                message=f"Geometry validation warning: {warning}",
                severity="warning",
            )
            for warning in geometry_validation.warnings
        )
        warnings.extend(_asset_import_warnings(asset_imports))
        errors = [
            ValidationIssue(code=code.upper(), message=f"QA check failed: {code}", severity="error")
            for code, passed in checks.items()
            if not passed
        ]
        errors.extend(
            ValidationIssue(
                code=f"GEOMETRY_VALIDATION_{error}",
                message=f"Geometry validation failed: {error}",
                severity="error",
            )
            for error in geometry_validation.critical_errors
        )
        score = sum(1 for passed in checks.values() if passed) / len(checks)
        return ValidationReport(
            design_id=scene.scene_id,
            status="passed" if not errors else "failed",
            score=score,
            checks=checks,
            warnings=warnings,
            errors=errors,
            glb_inspection=glb_inspection.model_dump(),
            geometry_validation=geometry_validation.model_dump(),
            preview_inspection=preview_inspection.model_dump(),
        )


def _load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_import_modes_valid(asset_imports: list) -> bool:
    valid_modes = {
        "imported_glb",
        "stretched_imported_glb",
        "procedural_fallback",
        "missing_file",
        "parametric_generated",
        "internal_project_generated",
    }
    if not isinstance(asset_imports, list):
        return False
    for record in asset_imports:
        if not isinstance(record, dict):
            return False
        if record.get("import_mode") not in valid_modes:
            return False
        if record.get("effective_generation_mode") not in valid_modes:
            return False
    return True


def _metadata_accessory_assets_valid(metadata: dict, scene: SceneSpec) -> bool:
    expected_ids = {accessory.asset_id for accessory in scene.accessory_assets}
    raw = metadata.get("accessory_assets")
    if not expected_ids:
        return raw in ([], None) or raw == []
    if not isinstance(raw, list):
        return False
    actual_ids = {entry.get("asset_id") for entry in raw if isinstance(entry, dict)}
    return expected_ids.issubset(actual_ids)


def _segment_connectivity_valid(metadata: dict) -> bool:
    report = metadata.get("segment_connectivity")
    return (
        isinstance(report, dict)
        and report.get("status") == "passed"
        and report.get("passed") is True
        and isinstance(report.get("evaluated_segment_count"), int)
        and report["evaluated_segment_count"] > 0
        and report.get("failed_segment_count") == 0
        and isinstance(report.get("maximum_endpoint_error_m"), (int, float))
        and isinstance(report.get("tolerance_m"), (int, float))
        and report["maximum_endpoint_error_m"] <= report["tolerance_m"]
    )


def _asset_import_summary_valid(summary: object, asset_imports: list) -> bool:
    if not isinstance(summary, dict):
        return False
    if summary.get("asset_count") != len(asset_imports):
        return False
    modes = summary.get("modes")
    if not isinstance(modes, dict):
        return False
    for mode in {
        "imported_glb",
        "stretched_imported_glb",
        "procedural_fallback",
        "missing_file",
        "parametric_generated",
        "internal_project_generated",
    }:
        expected = sum(1 for record in asset_imports if record.get("import_mode") == mode)
        if summary.get(f"{mode}_count") is not None and summary.get(f"{mode}_count") != expected:
            return False
        if modes.get(mode, 0) != expected:
            return False
    return True


def _imported_glb_records_valid(asset_imports: list) -> bool:
    for record in asset_imports:
        if not isinstance(record, dict):
            return False
        if record.get("import_mode") not in {"imported_glb", "stretched_imported_glb"}:
            continue
        if record.get("asset_file_exists") is not True:
            return False
        if record.get("asset_import_success") is not True:
            return False
        if not record.get("imported_object_names"):
            return False
    return True


def _asset_fallbacks_visible(asset_imports: list) -> bool:
    visible_codes = {
        "PROCEDURAL_FALLBACK_USED",
        "BLENDER_FALLBACK_ASSET_IMPORT_SKIPPED",
    }
    for record in asset_imports:
        if not isinstance(record, dict):
            return False
        if record.get("import_mode") != "procedural_fallback":
            continue
        warnings = set(record.get("warnings", []))
        if not warnings.intersection(visible_codes):
            return False
    return True


def _asset_import_warnings(asset_imports: list) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    for record in asset_imports:
        if not isinstance(record, dict):
            continue
        asset_id = record.get("asset_id", "unknown_asset")
        mode = record.get("import_mode")
        if mode == "procedural_fallback":
            warnings.append(
                ValidationIssue(
                    code="ASSET_IMPORT_PROCEDURAL_FALLBACK",
                    message=f"{asset_id} used procedural fallback instead of a real GLB import.",
                    severity="warning",
                )
            )
        for warning in record.get("warnings", []):
            warnings.append(
                ValidationIssue(
                    code=f"ASSET_IMPORT_{warning}",
                    message=f"{asset_id}: {warning}",
                    severity="warning",
                )
            )
    return warnings
