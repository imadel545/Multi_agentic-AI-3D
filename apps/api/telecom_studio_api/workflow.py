import json
import shutil
import tempfile
import uuid
from pathlib import Path

from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.orchestration import DesignOrchestrator, OrchestratorResult
from core.services.asset_registry import AssetRegistry
from core.validation import validate_scene_spec


class WorkflowService:
    def __init__(
        self,
        registry: AssetRegistry,
        outputs_dir: Path,
        orchestrator: DesignOrchestrator,
    ) -> None:
        self.registry = registry
        self.outputs_dir = outputs_dir
        self.orchestrator = orchestrator

    def create_design(
        self,
        requirements_text: str,
        detail_level: str,
        use_llm: bool | None = None,
    ) -> dict:
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        output_dir = self.outputs_dir / workflow_id
        output_dir.mkdir(parents=True, exist_ok=False)

        result = self.orchestrator.run(
            workflow_id=workflow_id,
            requirements_text=requirements_text,
            detail_level=detail_level,
            output_dir=output_dir,
            use_llm=use_llm,
        )

        self._write_result_files(output_dir, requirements_text, result)
        self._make_archive(output_dir)
        self._write_status(workflow_id, result.status, output_dir, result)
        return {"workflow_id": workflow_id, "status": result.status}

    def get_status(self, workflow_id: str) -> dict:
        status_path = self.outputs_dir / workflow_id / "status.json"
        if not status_path.exists():
            raise KeyError(workflow_id)
        return json.loads(status_path.read_text(encoding="utf-8"))

    def archive_path(self, workflow_id: str) -> Path:
        path = self.outputs_dir / workflow_id / "artifacts.zip"
        if not path.exists():
            raise KeyError(workflow_id)
        return path

    def validate_scene(self, scene: SceneSpec) -> ValidationReport:
        return validate_scene_spec(scene, self.registry.list_assets())

    def _write_status(
        self, workflow_id: str, status: str, output_dir: Path, result: OrchestratorResult
    ) -> None:
        report = result.report
        artifacts = {
            "requirements_spec": str(output_dir / "requirements_spec.json"),
            "extraction_report": str(output_dir / "extraction_report.json"),
            "scene_spec": str(output_dir / "scene_spec.json"),
            "validation_report": str(output_dir / "validation_report.json"),
            "quality_gates": str(output_dir / "quality_gates.json"),
            "qa_report": str(output_dir / "qa_report.json"),
            "generation_report": str(output_dir / "generation_report.json"),
            "glb_inspection": str(output_dir / "glb_inspection.json"),
            "geometry_validation": str(output_dir / "geometry_validation.json"),
            "preview_inspection": str(output_dir / "preview_inspection.json"),
            "memory_recall": str(output_dir / "memory_recall.json"),
            "technical_report": str(output_dir / "technical_report.md"),
            "glb": str(output_dir / "design.glb"),
            "preview": str(output_dir / "preview.png"),
            "metadata": str(output_dir / "scene_metadata.json"),
            "download": str(output_dir / "artifacts.zip"),
            "trace": str(output_dir / "workflow_trace.json"),
        }
        payload = {
            "workflow_id": workflow_id,
            "status": status,
            "artifacts": artifacts,
            "llm_provider": result.llm_provider,
            "llm_fallback_used": result.llm_fallback_used,
            "rag_context_count": len(result.rag_context),
            "memory_hits": result.memory_recall.memory_hits if result.memory_recall else 0,
            "memory_context_count": result.memory_recall.memory_context_count
            if result.memory_recall
            else 0,
            "generation_mode": result.generation.mode if result.generation else None,
            "blender_available": result.generation.blender_available if result.generation else None,
            "qa_score": result.qa_report.score if result.qa_report else None,
            "tower_characteristics_summary": _tower_characteristics_summary(result),
            "glb_inspection_summary": _glb_inspection_summary(result),
            "geometry_validation_summary": _geometry_validation_summary(result),
            "preview_inspection_summary": _preview_inspection_summary(result),
            "structural_qa_passed": result.glb_inspection.structural_qa_passed
            if result.glb_inspection
            else None,
            "expected_objects_present": result.glb_inspection.checks.get("expected_objects_present")
            if result.glb_inspection
            else None,
            "total_duration_ms": result.total_duration_ms,
            "total_workflow_duration_ms": result.metrics["total_workflow_duration_ms"],
            "metrics": result.metrics,
            "quality_gates": [gate.model_dump() for gate in result.quality_gate_reports],
            "download_url": f"/designs/{workflow_id}/download",
            "trace_path": str(output_dir / "workflow_trace.json"),
            "warnings": [warning.model_dump() for warning in report.warnings],
            "errors": [error.model_dump() for error in report.errors],
        }
        self._write_json(output_dir / "status.json", payload)

    def _write_result_files(
        self,
        output_dir: Path,
        requirements_text: str,
        result: OrchestratorResult,
    ) -> None:
        if result.requirements:
            self._write_json(
                output_dir / "requirements_spec.json", result.requirements.model_dump()
            )
            self._write_json(output_dir / "extraction_report.json", _extraction_report(result))
        if result.scene:
            self._write_json(output_dir / "scene_spec.json", result.scene.model_dump())
        self._write_json(output_dir / "validation_report.json", result.report.model_dump())
        self._write_json(
            output_dir / "quality_gates.json",
            {"reports": [gate.model_dump() for gate in result.quality_gate_reports]},
        )
        if result.requirement_report:
            self._write_json(
                output_dir / "requirement_validation_report.json",
                result.requirement_report.model_dump(),
            )
        if result.scene_report:
            self._write_json(
                output_dir / "scene_validation_report.json", result.scene_report.model_dump()
            )
        if result.qa_report:
            self._write_json(output_dir / "qa_report.json", result.qa_report.model_dump())
        if result.generation:
            self._write_json(output_dir / "generation_report.json", result.generation.model_dump())
        if result.glb_inspection:
            self._write_json(output_dir / "glb_inspection.json", result.glb_inspection.model_dump())
        if result.geometry_validation:
            self._write_json(
                output_dir / "geometry_validation.json",
                result.geometry_validation.model_dump(),
            )
        if result.preview_inspection:
            self._write_json(
                output_dir / "preview_inspection.json",
                result.preview_inspection.model_dump(),
            )
        self._write_json(output_dir / "rag_context.json", {"results": result.rag_context})
        if result.memory_recall:
            self._write_json(output_dir / "memory_recall.json", result.memory_recall.model_dump())
        self._write_json(output_dir / "workflow_trace.json", result.workflow_trace.model_dump())
        self._write_technical_report(output_dir / "technical_report.md", requirements_text, result)

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _write_technical_report(
        path: Path,
        requirements_text: str,
        result: OrchestratorResult,
    ) -> None:
        scene = result.scene
        generation_mode = result.generation.mode if result.generation else "not_run"
        memory_hits = result.memory_recall.memory_hits if result.memory_recall else 0
        path.write_text(
            "\n".join(
                [
                    f"# Technical Report — {result.workflow_id}",
                    "",
                    "## Input",
                    requirements_text,
                    "",
                    "## Scene",
                    f"- Network: {scene.network_type if scene else 'not_planned'}",
                    f"- Tower asset: {scene.tower.asset_id if scene else 'not_planned'}",
                    f"- Tower height: {scene.tower.height_m if scene else 'not_planned'} m",
                    f"- Tower characteristics: {_tower_characteristics_text(result)}",
                    f"- Sectors: {len(scene.sectors) if scene else 0}",
                    "",
                    "## Generation",
                    f"- Mode: {generation_mode}",
                    f"- RAG results: {len(result.rag_context)}",
                    f"- Memory hits: {memory_hits}",
                    f"- Total duration: {result.total_duration_ms} ms",
                    f"- Quality gates: {len(result.quality_gate_reports)}",
                    f"- Structural QA: {_structural_qa_status(result)}",
                    f"- Geometry QA: {_geometry_qa_status(result)}",
                    "",
                    "## Validation",
                    f"- Status: {result.report.status}",
                    f"- Score: {result.report.score:.2f}",
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _make_archive(output_dir: Path) -> None:
        target = output_dir / "artifacts.zip"
        if target.exists():
            target.unlink()
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_base = Path(temp_dir) / "artifacts"
            archive_path = shutil.make_archive(str(archive_base), "zip", output_dir)
            Path(archive_path).replace(target)


def _extraction_report(result: OrchestratorResult) -> dict:
    warnings = result.requirements.warnings if result.requirements else []
    repaired_fields = []
    inferred_fields = []
    for warning in warnings:
        if warning.code == "LLM_FIELD_REPAIRED":
            repaired_fields.append(warning.message)
        if warning.code.startswith("DEFAULT_"):
            inferred_fields.append(warning.code)
    confidence = 0.9
    if result.llm_fallback_used:
        confidence = 0.65
    confidence = max(0.1, confidence - (0.05 * len(warnings)))
    return {
        "provider": result.llm_provider,
        "fallback_used": result.llm_fallback_used,
        "error": result.llm_error,
        "repaired_fields": repaired_fields,
        "inferred_fields": inferred_fields,
        "confidence": round(confidence, 2),
        "warnings": [warning.model_dump() for warning in warnings],
    }


def _glb_inspection_summary(result: OrchestratorResult) -> dict | None:
    if result.glb_inspection is None:
        return None
    return {
        "inspection_mode": result.glb_inspection.inspection_mode,
        "file_exists": result.glb_inspection.file_exists,
        "file_size_bytes": result.glb_inspection.file_size_bytes,
        "format_valid": result.glb_inspection.format_valid,
        "node_count": result.glb_inspection.node_count,
        "mesh_count": result.glb_inspection.mesh_count,
        "material_count": result.glb_inspection.material_count,
        "structural_qa_passed": result.glb_inspection.structural_qa_passed,
        "expected_objects_present": result.glb_inspection.checks.get("expected_objects_present"),
        "critical_errors": result.glb_inspection.critical_errors,
    }


def _tower_characteristics_summary(result: OrchestratorResult) -> dict | None:
    if result.scene is None:
        return None
    return result.scene.tower.characteristics.model_dump()


def _tower_characteristics_text(result: OrchestratorResult) -> str:
    summary = _tower_characteristics_summary(result)
    if summary is None:
        return "not_planned"
    return (
        f"{summary['structure']}, {summary['leg_count']} legs, "
        f"base {summary['base_width_m']}m, top {summary['top_width_m']}m, "
        f"foundation {summary['foundation_type']}"
    )


def _geometry_validation_summary(result: OrchestratorResult) -> dict | None:
    if result.geometry_validation is None:
        return None
    return {
        "status": result.geometry_validation.status,
        "checks": result.geometry_validation.checks,
        "object_counts": result.geometry_validation.object_counts,
        "missing_objects": result.geometry_validation.missing_objects,
        "critical_errors": result.geometry_validation.critical_errors,
    }


def _preview_inspection_summary(result: OrchestratorResult) -> dict | None:
    if result.preview_inspection is None:
        return None
    return {
        "inspection_mode": result.preview_inspection.inspection_mode,
        "file_exists": result.preview_inspection.file_exists,
        "file_size_bytes": result.preview_inspection.file_size_bytes,
        "width": result.preview_inspection.width,
        "height": result.preview_inspection.height,
        "format": result.preview_inspection.format,
        "minimum_resolution_valid": result.preview_inspection.minimum_resolution_valid,
        "visual_quality_valid": result.preview_inspection.visual_quality_valid,
        "luminance_mean": result.preview_inspection.luminance_mean,
        "luminance_stddev": result.preview_inspection.luminance_stddev,
        "non_dark_pixel_ratio": result.preview_inspection.non_dark_pixel_ratio,
        "preview_qa_passed": result.preview_inspection.preview_qa_passed,
        "critical_errors": result.preview_inspection.critical_errors,
    }


def _structural_qa_status(result: OrchestratorResult) -> str:
    if result.glb_inspection is None:
        return "not_run"
    status = "passed" if result.glb_inspection.structural_qa_passed else "failed"
    return f"{status} ({result.glb_inspection.inspection_mode})"


def _geometry_qa_status(result: OrchestratorResult) -> str:
    if result.geometry_validation is None:
        return "not_run"
    return result.geometry_validation.status
