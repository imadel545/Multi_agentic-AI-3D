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
    ) -> ValidationReport:
        glb_path = Path(generation.artifacts.get("glb", ""))
        preview_path = Path(generation.artifacts.get("preview", ""))
        metadata_path = Path(generation.artifacts.get("metadata", ""))
        metadata = _load_metadata(metadata_path)

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
            "metadata_preview_camera_valid": isinstance(metadata.get("preview_camera"), dict)
            and bool(metadata["preview_camera"].get("camera")),
            "generation_completed_or_fallback": generation.status in {"generated", "fallback"},
            "glb_inspection_available": glb_inspection.inspection_mode
            in {"glb_parse", "metadata_fallback"},
            "glb_structure_valid": glb_inspection.structural_qa_passed,
            "expected_objects_present": glb_inspection.checks.get(
                "expected_objects_present", False
            ),
            "preview_inspection_available": preview_inspection.inspection_mode == "png_parse",
            "preview_resolution_valid": preview_inspection.minimum_resolution_valid,
            "preview_visual_quality_valid": generation.mode != "real_blender"
            or preview_inspection.visual_quality_valid,
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
