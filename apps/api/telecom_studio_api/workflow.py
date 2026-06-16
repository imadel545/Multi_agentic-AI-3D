import json
import queue
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import SceneEditResult
from core.contracts.validation import ValidationReport
from core.orchestration import DesignOrchestrator, OrchestratorResult
from core.services.asset_registry import AssetRegistry
from core.services.cleanup_service import CleanupService
from core.services.diff_engine import DiffEngine
from core.services.event_log import EventLogService
from core.services.patch_applier import PatchApplier
from core.services.scene_versioning import SceneVersioningService
from core.validation import validate_scene_spec

from .runtime_contract import (
    extraction_provider_label,
    llm_available_from_workflow_service,
    llm_fallback_reason,
    llm_truth,
    runtime_capabilities,
    unsupported_actions,
)


class WorkflowService:
    def __init__(
        self,
        registry: AssetRegistry,
        outputs_dir: Path,
        orchestrator: DesignOrchestrator,
        scene_edit_agent: SceneEditAgent,
    ) -> None:
        self.registry = registry
        self.outputs_dir = outputs_dir
        self.orchestrator = orchestrator
        self.scene_edit_agent = scene_edit_agent
        self.patch_applier = PatchApplier()
        self.versioning = SceneVersioningService(outputs_dir)
        self.event_log = EventLogService(outputs_dir)
        self.cleanup_service = CleanupService(outputs_dir)
        self.diff_engine = DiffEngine()
        self._lock = threading.Lock()
        self._event_queues: dict[str, queue.Queue] = {}
        self.orchestrator.set_runtime_event_sink(self.event_log.emit)

    def _sync_output_services(self) -> None:
        if self.versioning.outputs_dir == self.outputs_dir:
            return
        self.versioning = SceneVersioningService(self.outputs_dir)
        self.event_log = EventLogService(self.outputs_dir)
        self.cleanup_service = CleanupService(self.outputs_dir)
        self.orchestrator.set_runtime_event_sink(self.event_log.emit)

    def _event_sink_for(self, workflow_id: str):
        def _sink(workflow_id_: str, event_type: str, payload: dict) -> None:
            self._emit_workflow_event(workflow_id_, event_type, payload)

        return _sink

    def _emit_workflow_event(self, workflow_id: str, event_type: str, payload: dict) -> dict:
        payload = _normalized_event_payload(event_type, payload)
        event = self.event_log.emit(workflow_id, event_type, payload)
        event_payload = event.model_dump()
        q = self._event_queues.get(workflow_id)
        if q is not None:
            try:
                q.put_nowait(event_payload)
            except queue.Full:
                pass
        return event_payload

    def _register_workflow_queue(self, workflow_id: str) -> queue.Queue:
        with self._lock:
            q = queue.Queue(maxsize=1000)
            self._event_queues[workflow_id] = q
            return q

    def _unregister_workflow_queue(self, workflow_id: str) -> None:
        with self._lock:
            self._event_queues.pop(workflow_id, None)

    def create_design(
        self,
        requirements_text: str,
        detail_level: str,
        use_llm: bool | None = None,
        _synchronous: bool = False,
    ) -> dict:
        self._sync_output_services()
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        output_dir = self.outputs_dir / workflow_id
        output_dir.mkdir(parents=True, exist_ok=False)

        self._write_pending_status(workflow_id, output_dir, detail_level, use_llm)
        self._register_workflow_queue(workflow_id)
        self._emit_workflow_event(
            workflow_id, "design_created", {"detail_level": detail_level, "use_llm": use_llm}
        )

        def _run() -> None:
            self.orchestrator.set_runtime_event_sink(self._event_sink_for(workflow_id))
            try:
                self._write_running_status(workflow_id, output_dir)
                result = self.orchestrator.run(
                    workflow_id=workflow_id,
                    requirements_text=requirements_text,
                    detail_level=detail_level,
                    output_dir=output_dir,
                    use_llm=use_llm,
                )
                self._write_result_files(output_dir, requirements_text, result)
                self._write_status(workflow_id, "running", output_dir, result)
                self._make_archive(output_dir)
                self._write_status(workflow_id, "running", output_dir, result)
                version_dir: Path | None = None
                if result.scene:
                    version = self.versioning.save_version(
                        workflow_id,
                        result.scene,
                        edit_description="initial",
                        status=result.status,
                        qa_score=result.qa_report.score if result.qa_report else None,
                        generation_mode=result.generation.mode if result.generation else None,
                        activate=True,
                    )
                    version_dir = self.versioning.version_artifacts_dir(
                        workflow_id, version.version_id
                    )
                    self._copy_artifact_files(output_dir, version_dir)
                    self._write_status(
                        workflow_id,
                        result.status,
                        version_dir,
                        result,
                        version_id=version.version_id,
                        active_version_id=version.version_id,
                    )
                    self._make_archive(version_dir)
                    self._write_status(
                        workflow_id,
                        result.status,
                        version_dir,
                        result,
                        version_id=version.version_id,
                        active_version_id=version.version_id,
                    )
                    version_status = self._read_json(version_dir / "status.json")
                    self.versioning.update_version(
                        workflow_id,
                        version.version_id,
                        status=result.status,
                        artifact_dir=str(version_dir),
                        artifacts=version_status.get("artifacts", {}),
                        qa_score=result.qa_report.score if result.qa_report else None,
                        generation_mode=result.generation.mode if result.generation else None,
                        active=True,
                    )
                self._emit_result_product_events(
                    workflow_id,
                    result,
                    version_id=self.versioning.active_version_id(workflow_id),
                )
                self._emit_workflow_event(
                    workflow_id,
                    "workflow_completed" if result.status != "failed" else "workflow_failed",
                    {
                        "status": result.status,
                        "duration_ms": result.total_duration_ms,
                        "version_id": self.versioning.active_version_id(workflow_id),
                        "node": "workflow",
                    },
                )
                if version_dir is not None:
                    self._copy_active_status_to_root(workflow_id, version_dir)
                else:
                    self._write_status(workflow_id, result.status, output_dir, result)
                self._make_archive(output_dir)
            except Exception as exc:
                self._emit_user_issue_event(
                    workflow_id,
                    {
                        "code": "WORKFLOW_EXCEPTION",
                        "message": str(exc),
                        "severity": "error",
                    },
                )
                self._emit_workflow_event(
                    workflow_id,
                    "workflow_failed",
                    {"error": str(exc), "error_type": type(exc).__name__},
                )
                # Write a minimal failed status
                self._write_failed_status(workflow_id, output_dir, str(exc))
            finally:
                self._unregister_workflow_queue(workflow_id)
                self.orchestrator.set_runtime_event_sink(self.event_log.emit)

        if _synchronous:
            _run()
            try:
                status = self.get_status(workflow_id)
                return {"workflow_id": workflow_id, "status": status["status"]}
            except KeyError:
                return {"workflow_id": workflow_id, "status": "failed"}

        thread = threading.Thread(target=_run, name=f"workflow-{workflow_id}")
        thread.start()
        return {"workflow_id": workflow_id, "status": "pending"}

    def create_design_from_requirements(
        self,
        requirements: RequirementSpec,
        *,
        detail_level: str,
        source_label: str = "project_design_spec",
        _synchronous: bool = False,
    ) -> dict:
        self._sync_output_services()
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        output_dir = self.outputs_dir / workflow_id
        output_dir.mkdir(parents=True, exist_ok=False)
        context_text = _requirements_context_text(requirements, source_label)
        self._write_pending_status(workflow_id, output_dir, detail_level, use_llm=False)
        self._register_workflow_queue(workflow_id)
        self._emit_workflow_event(
            workflow_id,
            "design_created",
            {"detail_level": detail_level, "use_llm": False, "source": source_label},
        )

        def _run() -> None:
            self.orchestrator.set_runtime_event_sink(self._event_sink_for(workflow_id))
            try:
                self._write_running_status(workflow_id, output_dir)
                self._emit_workflow_event(
                    workflow_id,
                    "validated_requirements_received",
                    {"source": source_label, "node": "use_validated_requirements"},
                )
                result = self.orchestrator.run_requirements(
                    workflow_id=workflow_id,
                    requirements=requirements,
                    detail_level=detail_level,
                    output_dir=output_dir,
                    source_label=source_label,
                )
                self._write_result_files(output_dir, context_text, result)
                self._write_status(workflow_id, "running", output_dir, result)
                self._make_archive(output_dir)
                self._write_status(workflow_id, "running", output_dir, result)
                version_dir: Path | None = None
                if result.scene:
                    version = self.versioning.save_version(
                        workflow_id,
                        result.scene,
                        edit_description=f"initial from {source_label}",
                        status=result.status,
                        qa_score=result.qa_report.score if result.qa_report else None,
                        generation_mode=result.generation.mode if result.generation else None,
                        activate=True,
                    )
                    version_dir = self.versioning.version_artifacts_dir(
                        workflow_id, version.version_id
                    )
                    self._copy_artifact_files(output_dir, version_dir)
                    self._write_status(
                        workflow_id,
                        result.status,
                        version_dir,
                        result,
                        version_id=version.version_id,
                        active_version_id=version.version_id,
                    )
                    self._make_archive(version_dir)
                    self._write_status(
                        workflow_id,
                        result.status,
                        version_dir,
                        result,
                        version_id=version.version_id,
                        active_version_id=version.version_id,
                    )
                    version_status = self._read_json(version_dir / "status.json")
                    self.versioning.update_version(
                        workflow_id,
                        version.version_id,
                        status=result.status,
                        artifact_dir=str(version_dir),
                        artifacts=version_status.get("artifacts", {}),
                        qa_score=result.qa_report.score if result.qa_report else None,
                        generation_mode=result.generation.mode if result.generation else None,
                        active=True,
                    )
                self._emit_result_product_events(
                    workflow_id,
                    result,
                    version_id=self.versioning.active_version_id(workflow_id),
                )
                self._emit_workflow_event(
                    workflow_id,
                    "workflow_completed" if result.status != "failed" else "workflow_failed",
                    {
                        "status": result.status,
                        "duration_ms": result.total_duration_ms,
                        "version_id": self.versioning.active_version_id(workflow_id),
                        "node": "workflow",
                    },
                )
                if version_dir is not None:
                    self._copy_active_status_to_root(workflow_id, version_dir)
                else:
                    self._write_status(workflow_id, result.status, output_dir, result)
                self._make_archive(output_dir)
            except Exception as exc:
                self._emit_user_issue_event(
                    workflow_id,
                    {
                        "code": "WORKFLOW_EXCEPTION",
                        "message": str(exc),
                        "severity": "error",
                    },
                )
                self._emit_workflow_event(
                    workflow_id,
                    "workflow_failed",
                    {"error": str(exc), "error_type": type(exc).__name__},
                )
                self._write_failed_status(workflow_id, output_dir, str(exc))
            finally:
                self._unregister_workflow_queue(workflow_id)
                self.orchestrator.set_runtime_event_sink(self.event_log.emit)

        if _synchronous:
            _run()
            try:
                status = self.get_status(workflow_id)
                return {"workflow_id": workflow_id, "status": status["status"]}
            except KeyError:
                return {"workflow_id": workflow_id, "status": "failed"}

        thread = threading.Thread(target=_run, name=f"workflow-{workflow_id}")
        thread.start()
        return {"workflow_id": workflow_id, "status": "pending"}

    def _run_scene_revision_with_sink(
        self,
        workflow_id: str,
        scene: SceneSpec,
        output_dir: Path,
        detail_level: str,
        revision_id: str,
    ) -> OrchestratorResult:
        self._register_workflow_queue(workflow_id)
        self.orchestrator.set_runtime_event_sink(self._event_sink_for(workflow_id))
        try:
            return self.orchestrator.run_scene_revision(
                workflow_id=workflow_id,
                scene=scene,
                output_dir=output_dir,
                detail_level=detail_level,
                revision_id=revision_id,
            )
        finally:
            self._unregister_workflow_queue(workflow_id)
            self.orchestrator.set_runtime_event_sink(self.event_log.emit)

    def get_status(self, workflow_id: str) -> dict:
        self._sync_output_services()
        status_path = self.outputs_dir / workflow_id / "status.json"
        if not status_path.exists():
            raise KeyError(workflow_id)
        return json.loads(status_path.read_text(encoding="utf-8"))

    def get_public_status(self, workflow_id: str) -> dict:
        """Return a frontend-safe status payload without local filesystem paths."""
        status = self.get_status(workflow_id)
        payload = _public_status_payload(workflow_id, status)
        payload.update(llm_truth(payload, workflow_service=self))
        payload["runtime_capabilities"] = runtime_capabilities()
        payload["unsupported_actions"] = unsupported_actions()
        return payload

    def archive_path(self, workflow_id: str) -> Path:
        self._sync_output_services()
        status = self.get_status(workflow_id)
        artifact_path = status.get("artifacts", {}).get("download")
        path = (
            Path(artifact_path)
            if artifact_path
            else self.outputs_dir / workflow_id / "artifacts.zip"
        )
        if not path.exists():
            raise KeyError(workflow_id)
        return path

    def artifact_path(
        self,
        workflow_id: str,
        artifact_name: str,
        version_id: str | None = None,
    ) -> Path:
        self._sync_output_services()
        if artifact_name not in _ALLOWED_ARTIFACT_FILES:
            raise KeyError(artifact_name)
        workflow_dir = (self.outputs_dir / workflow_id).resolve()
        if not workflow_dir.exists():
            raise KeyError(workflow_id)

        path: Path | None = None
        if version_id:
            version = self.versioning.get_version(workflow_id, version_id)
            if version is None or not version.artifact_dir:
                raise KeyError(version_id)
            artifact_dir = Path(version.artifact_dir).resolve()
            path = artifact_dir / _ALLOWED_ARTIFACT_FILES[artifact_name]
        else:
            status = self.get_status(workflow_id)
            artifact_value = status.get("artifacts", {}).get(artifact_name)
            path = Path(artifact_value).resolve() if artifact_value else None
            if path is None:
                path = workflow_dir / _ALLOWED_ARTIFACT_FILES[artifact_name]

        if path is None or not path.exists() or not path.is_file():
            raise KeyError(artifact_name)
        try:
            path.relative_to(workflow_dir)
        except ValueError as exc:
            raise KeyError(artifact_name) from exc
        return path

    def list_designs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        self._sync_output_services()
        designs = []
        if not self.outputs_dir.exists():
            return designs
        dirs = sorted(
            [d for d in self.outputs_dir.iterdir() if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for workflow_dir in dirs[offset : offset + limit]:
            status_path = workflow_dir / "status.json"
            if status_path.exists():
                try:
                    payload = json.loads(status_path.read_text(encoding="utf-8"))
                    designs.append(
                        {
                            "workflow_id": payload.get("workflow_id"),
                            "status": payload.get("status"),
                            "created_at": payload.get("metrics", {}).get("started_at"),
                            "qa_score": payload.get("qa_score"),
                            "generation_mode": payload.get("generation_mode"),
                        }
                    )
                except (OSError, json.JSONDecodeError):
                    continue
        return designs

    def delete_design(self, workflow_id: str) -> None:
        self._sync_output_services()
        output_dir = self.outputs_dir / workflow_id
        if not output_dir.exists():
            raise KeyError(workflow_id)
        try:
            deleted = self.cleanup_service.delete_workflow(workflow_id)
        except ValueError as exc:
            raise KeyError(workflow_id) from exc
        if not deleted:
            raise KeyError(workflow_id)

    def parse_requirements(
        self,
        requirements_text: str,
        detail_level: str,
        use_llm: bool | None = None,
    ) -> dict:
        extraction = self.orchestrator.extractor.extract(
            requirements_text, detail_level, enabled=use_llm
        )
        llm_available = llm_available_from_workflow_service(self)
        fallback_reason = llm_fallback_reason(
            provider=extraction.provider,
            fallback_used=extraction.fallback_used,
            use_llm=use_llm,
            error=extraction.error,
            llm_available=llm_available,
        )
        return {
            "requirements": (
                extraction.requirements.model_dump() if extraction.requirements else None
            ),
            "warnings": (
                [w.model_dump() for w in extraction.requirements.warnings]
                if extraction.requirements
                else []
            ),
            "errors": _extraction_errors(extraction.error),
            "provider": extraction.provider,
            "extraction_provider": extraction_provider_label(
                extraction.provider, extraction.fallback_used, fallback_reason
            ),
            "fallback_used": extraction.fallback_used,
            "llm_fallback_reason": fallback_reason,
        }

    def validate_scene(self, scene: SceneSpec) -> ValidationReport:
        return validate_scene_spec(scene, self.registry.list_assets())

    def edit_design(self, workflow_id: str, edit_prompt: str) -> SceneEditResult:
        self._sync_output_services()
        active_version = self.versioning.get_active_version(workflow_id)
        if active_version is None:
            return SceneEditResult(
                workflow_id=workflow_id,
                edit_id=f"edit_{uuid.uuid4().hex[:8]}",
                status="failed",
                errors=[
                    {
                        "code": "NO_ACTIVE_VERSION",
                        "message": "No active scene version found for workflow.",
                        "severity": "error",
                    }
                ],
            )
        original_scene = active_version.scene
        edit_id = f"edit_{uuid.uuid4().hex[:8]}"

        self._emit_workflow_event(
            workflow_id,
            "edit_patch_created",
            {
                "edit_id": edit_id,
                "prompt": edit_prompt,
                "version_id": active_version.version_id,
                "agent": "SceneEditAgent",
            },
        )

        try:
            patch = self.scene_edit_agent.create_patch(workflow_id, original_scene, edit_prompt)
        except Exception as exc:
            self._emit_workflow_event(
                workflow_id,
                "edit_patch_rejected",
                {"edit_id": edit_id, "reason": str(exc)},
            )
            return SceneEditResult(
                workflow_id=workflow_id,
                edit_id=edit_id,
                status="failed",
                original_scene=original_scene,
                errors=[
                    {
                        "code": "EDIT_CREATION_FAILED",
                        "message": str(exc),
                        "severity": "error",
                    }
                ],
            )

        patched_scene, validation_report = self.patch_applier.apply(original_scene, patch)

        if validation_report.status == "failed":
            self._emit_workflow_event(
                workflow_id,
                "edit_patch_rejected",
                {
                    "edit_id": edit_id,
                    "reason": "validation_failed",
                    "errors": [e.model_dump() for e in validation_report.errors],
                },
            )
            return SceneEditResult(
                workflow_id=workflow_id,
                edit_id=edit_id,
                status="rejected",
                original_scene=original_scene,
                patch=patch,
                validation_report=validation_report,
                errors=validation_report.errors,
            )

        diff_summary = self.diff_engine.diff_scenes(original_scene, patched_scene)
        version = self.versioning.save_version(
            workflow_id,
            patched_scene,
            parent_version_id=active_version.version_id,
            edit_description=patch.edit_description,
            diff_summary=diff_summary,
            status="generating",
            activate=False,
        )
        version_output_dir = self.versioning.version_artifacts_dir(workflow_id, version.version_id)
        self._emit_workflow_event(
            workflow_id,
            "version_created",
            {
                "edit_id": edit_id,
                "version_id": version.version_id,
                "parent_version_id": active_version.version_id,
            },
        )
        result = self._run_scene_revision_with_sink(
            workflow_id=workflow_id,
            scene=patched_scene,
            output_dir=version_output_dir,
            detail_level="high",
            revision_id=version.version_id,
        )
        self._write_result_files(version_output_dir, edit_prompt, result)
        self._write_json(version_output_dir / "scene_patch.json", patch.model_dump())
        self._write_json(version_output_dir / "scene_diff.json", diff_summary)
        self._write_status(
            workflow_id,
            result.status,
            version_output_dir,
            result,
            version_id=version.version_id,
            active_version_id=self.versioning.active_version_id(workflow_id),
        )
        self._make_archive(version_output_dir)
        self._write_status(
            workflow_id,
            result.status,
            version_output_dir,
            result,
            version_id=version.version_id,
            active_version_id=self.versioning.active_version_id(workflow_id),
        )
        version_status = self._read_json(version_output_dir / "status.json")
        self.versioning.update_version(
            workflow_id,
            version.version_id,
            status=result.status,
            artifact_dir=str(version_output_dir),
            artifacts=version_status.get("artifacts", {}),
            qa_score=result.qa_report.score if result.qa_report else None,
            generation_mode=result.generation.mode if result.generation else None,
            active=False,
        )

        self._emit_workflow_event(
            workflow_id,
            "blender_completed"
            if result.generation and result.generation.status in {"generated", "fallback"}
            else "blender_failed",
            {
                "mode": result.generation.mode if result.generation else None,
                "error": result.generation.error if result.generation else None,
                "version_id": version.version_id,
                "node": "generate_blender",
            },
        )
        self._emit_workflow_event(
            workflow_id,
            "qa_completed" if result.status == "completed" else "qa_failed",
            {
                "version_id": version.version_id,
                "qa_score": result.qa_report.score if result.qa_report else None,
                "node": "qa_generation",
            },
        )

        if result.status != "completed":
            self.versioning.update_version(workflow_id, version.version_id, status="failed")
            self._emit_workflow_event(
                workflow_id,
                "edit_patch_rejected",
                {
                    "edit_id": edit_id,
                    "version_id": version.version_id,
                    "reason": "revision_quality_failed",
                    "errors": [e.model_dump() for e in result.report.errors],
                },
            )
            return SceneEditResult(
                workflow_id=workflow_id,
                edit_id=edit_id,
                status="failed",
                original_scene=original_scene,
                patched_scene=patched_scene,
                patch=patch,
                validation_report=result.report,
                diff_summary=diff_summary,
                version_id=version.version_id,
                artifacts=version_status.get("artifacts", {}),
                generation_mode=result.generation.mode if result.generation else None,
                qa_score=result.qa_report.score if result.qa_report else None,
                llm_provider=patch.edit_llm_provider,
                llm_fallback_used=patch.edit_llm_fallback_used,
                errors=result.report.errors,
                warnings=[*validation_report.warnings, *result.report.warnings],
            )

        self.versioning.update_version(workflow_id, version.version_id, active=True)
        self.versioning.rollback(workflow_id, version.version_id)
        self._write_status(
            workflow_id,
            result.status,
            version_output_dir,
            result,
            version_id=version.version_id,
            active_version_id=version.version_id,
        )
        self._copy_active_status_to_root(workflow_id, version_output_dir)
        self._emit_workflow_event(
            workflow_id,
            "edit_patch_applied",
            {"edit_id": edit_id, "version_id": version.version_id, "status": result.status},
        )

        return SceneEditResult(
            workflow_id=workflow_id,
            edit_id=edit_id,
            status="applied",
            original_scene=original_scene,
            patched_scene=patched_scene,
            patch=patch,
            validation_report=validation_report,
            diff_summary=diff_summary,
            version_id=version.version_id,
            artifacts=version_status.get("artifacts", {}),
            generation_mode=result.generation.mode if result.generation else None,
            qa_score=result.qa_report.score if result.qa_report else None,
            llm_provider=patch.edit_llm_provider,
            llm_fallback_used=patch.edit_llm_fallback_used,
            warnings=[*validation_report.warnings, *result.report.warnings],
        )

    def public_edit_response(self, result: SceneEditResult) -> dict:
        artifacts = _public_artifact_urls(
            result.workflow_id,
            result.artifacts,
            version_id=result.version_id,
        )
        llm = llm_truth(
            {
                "llm_provider": result.llm_provider,
                "llm_fallback_used": result.llm_fallback_used,
            },
            workflow_service=self,
        )
        response = {
            "workflow_id": result.workflow_id,
            "edit_id": result.edit_id,
            "status": result.status,
            "edit_status": result.status,
            "message": _edit_result_message(result),
            "version_id": result.version_id,
            "diff_summary": result.diff_summary,
            "patch": result.patch.model_dump() if result.patch else None,
            "validation_report": result.validation_report.model_dump()
            if result.validation_report
            else None,
            "artifacts": artifacts,
            "generation_mode": result.generation_mode,
            "qa_score": result.qa_score,
            "extraction_provider": llm["extraction_provider"],
            "llm_provider": result.llm_provider,
            "llm_available": llm["llm_available"],
            "llm_fallback_used": result.llm_fallback_used,
            "llm_fallback_reason": llm["llm_fallback_reason"],
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
            "viewer_bundle_url": f"/designs/{result.workflow_id}/viewer-bundle",
            "timeline_url": f"/designs/{result.workflow_id}/timeline-summary",
            "user_issues_url": f"/designs/{result.workflow_id}/user-issues",
            "current_operation_url": f"/designs/{result.workflow_id}/current-operation",
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "available_actions": _edit_available_actions(result),
        }
        return response

    def list_versions(self, workflow_id: str) -> list[dict]:
        self._sync_output_services()
        versions = self.versioning.list_versions(workflow_id)
        return [
            {
                "version_id": v.version_id,
                "parent_version_id": v.parent_version_id,
                "created_at": v.created_at,
                "edit_description": v.edit_description,
                "diff_summary": v.diff_summary,
                "status": v.status,
                "active": v.active,
                "artifact_dir": v.artifact_dir,
                "artifacts": v.artifacts,
                "qa_score": v.qa_score,
                "generation_mode": v.generation_mode,
            }
            for v in versions
        ]

    def list_versions_public(self, workflow_id: str) -> list[dict]:
        self._sync_output_services()
        versions = self.versioning.list_versions(workflow_id)
        return [
            {
                "version_id": v.version_id,
                "parent_version_id": v.parent_version_id,
                "created_at": v.created_at,
                "edit_description": v.edit_description,
                "diff_summary": v.diff_summary,
                "status": v.status,
                "active": v.active,
                "artifacts": _public_artifact_urls(
                    workflow_id,
                    v.artifacts,
                    version_id=v.version_id,
                ),
                "qa_score": v.qa_score,
                "generation_mode": v.generation_mode,
            }
            for v in versions
        ]

    def rollback_version(self, workflow_id: str, version_id: str) -> dict:
        self._sync_output_services()
        version = self.versioning.rollback(workflow_id, version_id)
        if version is None:
            raise KeyError(version_id)
        if not version.artifact_dir:
            raise KeyError(version_id)
        self._copy_active_status_to_root(workflow_id, Path(version.artifact_dir))
        self._emit_workflow_event(
            workflow_id,
            "version_rolled_back",
            {
                "version_id": version_id,
                "status": "completed",
                "human_label": "Version restaurée",
                "progress_message": "La version active a été restaurée.",
            },
        )
        status = self.get_status(workflow_id)
        return {
            "workflow_id": workflow_id,
            "version_id": version_id,
            "active_version_id": version_id,
            "rolled_back": True,
            "status": "rolled_back",
            "message": "La version active a été restaurée.",
            "viewer_bundle_url": f"/designs/{workflow_id}/viewer-bundle",
            "timeline_url": f"/designs/{workflow_id}/timeline-summary",
            "user_issues_url": f"/designs/{workflow_id}/user-issues",
            "current_operation_url": f"/designs/{workflow_id}/current-operation",
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "available_actions": _status_available_actions(status),
        }

    def get_events(self, workflow_id: str) -> list[dict]:
        self._sync_output_services()
        return [
            e.model_dump() | {"event_source": "workflow_events_jsonl"}
            for e in self.event_log.list_events(workflow_id)
        ]

    def stream_events(self, workflow_id: str):
        """Yield events for a workflow in near real-time.

        First yields all persisted events, then listens to the in-memory queue
        for new events until the workflow emits a terminal event.
        """
        self._sync_output_services()
        seen_event_ids: set[str] = set()
        q = self._event_queues.get(workflow_id)
        terminal = {"workflow_completed", "workflow_failed"}

        for event in self.get_events(workflow_id):
            seen_event_ids.add(_event_identity(event))
            yield event | {"event_source": "push_sse"}
            if event.get("event_type") in terminal:
                return

        if q is None:
            return

        while True:
            if self._event_queues.get(workflow_id) is not q and q.empty():
                for event in self.get_events(workflow_id):
                    identity = _event_identity(event)
                    if identity in seen_event_ids:
                        continue
                    seen_event_ids.add(identity)
                    yield event | {"event_source": "push_sse"}
                return

            try:
                event = q.get(timeout=1.0)
            except queue.Empty:
                continue
            if event is not None:
                identity = _event_identity(event)
                if identity in seen_event_ids:
                    continue
                seen_event_ids.add(identity)
                yield event | {"event_source": "push_sse"}
                if event.get("event_type") in terminal:
                    return

    def workflow_exists(self, workflow_id: str) -> bool:
        self._sync_output_services()
        return (self.outputs_dir / workflow_id).exists()

    def _emit_result_product_events(
        self,
        workflow_id: str,
        result: OrchestratorResult,
        *,
        version_id: str | None,
    ) -> None:
        if result.generation is not None and result.generation.artifacts:
            artifacts = _public_artifact_urls(
                workflow_id,
                result.generation.artifacts,
                version_id=version_id,
            )
            self._emit_workflow_event(
                workflow_id,
                "artifact_ready",
                {
                    "node": "generate_blender",
                    "phase": "viewer",
                    "status": result.generation.status,
                    "version_id": version_id,
                    "generation_mode": result.generation.mode,
                    "artifact_refs": list(artifacts.values()),
                    "artifacts": artifacts,
                    "human_label": "Préparation du viewer 3D",
                    "progress_message": "Les artefacts du viewer 3D sont disponibles.",
                },
            )
        if result.qa_report is not None:
            geometry = result.geometry_validation
            self._emit_workflow_event(
                workflow_id,
                "qa_completed" if result.qa_report.status == "passed" else "qa_failed",
                {
                    "node": "qa_generation",
                    "phase": "qa",
                    "status": result.qa_report.status,
                    "version_id": version_id,
                    "qa_score": result.qa_report.score,
                    "mesh_qa_level": geometry.mesh_qa_level if geometry else None,
                    "mesh_qa_passed": geometry.mesh_qa.mesh_qa_passed
                    if geometry and geometry.mesh_qa
                    else None,
                    "geometry_source": geometry.geometry_source if geometry else None,
                    "generation_strategy": geometry.generation_strategy if geometry else None,
                    "warnings": [warning.code for warning in result.qa_report.warnings],
                    "errors": [error.code for error in result.qa_report.errors],
                    "human_label": "Vérification géométrique",
                    "progress_message": "Le contrôle qualité du modèle 3D est terminé.",
                },
            )
        for warning in result.report.warnings:
            self._emit_user_issue_event(workflow_id, warning.model_dump())
        for error in result.report.errors:
            self._emit_user_issue_event(workflow_id, error.model_dump())

    def _emit_user_issue_event(self, workflow_id: str, issue: dict) -> None:
        self._emit_workflow_event(
            workflow_id,
            "user_issue_created",
            {
                "phase": "issues",
                "status": issue.get("severity", "warning"),
                "code": issue.get("code"),
                "message": issue.get("message"),
                "severity": issue.get("severity", "warning"),
                "human_label": _issue_event_title(issue),
                "progress_message": issue.get("message") or "Une issue utilisateur a été créée.",
            },
        )

    def _write_status(
        self,
        workflow_id: str,
        status: str,
        output_dir: Path,
        result: OrchestratorResult,
        version_id: str | None = None,
        active_version_id: str | None = None,
    ) -> None:
        report = result.report
        asset_import_metadata = _asset_import_metadata(output_dir)
        llm_available = llm_available_from_workflow_service(self)
        llm_reason = llm_fallback_reason(
            provider=result.llm_provider,
            fallback_used=result.llm_fallback_used,
            use_llm=result.metrics.get("use_llm"),
            error=result.llm_error,
            llm_available=llm_available,
        )
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
            "version_id": version_id,
            "active_version_id": active_version_id,
            "artifacts": artifacts,
            "extraction_provider": extraction_provider_label(
                result.llm_provider, result.llm_fallback_used, llm_reason
            ),
            "llm_provider": result.llm_provider,
            "llm_available": llm_available,
            "llm_fallback_used": result.llm_fallback_used,
            "llm_fallback_reason": llm_reason,
            "rag_context_count": len(result.rag_context),
            "memory_hits": result.memory_recall.memory_hits if result.memory_recall else 0,
            "memory_context_count": result.memory_recall.memory_context_count
            if result.memory_recall
            else 0,
            "generation_mode": result.generation.mode if result.generation else None,
            "generation_strategy": result.geometry_validation.generation_strategy
            if result.geometry_validation
            else None,
            "geometry_source": result.geometry_validation.geometry_source
            if result.geometry_validation
            else None,
            "mesh_qa_level": result.geometry_validation.mesh_qa_level
            if result.geometry_validation
            else None,
            "mesh_qa_passed": result.geometry_validation.mesh_qa.mesh_qa_passed
            if result.geometry_validation and result.geometry_validation.mesh_qa
            else None,
            "blender_available": result.generation.blender_available if result.generation else None,
            "qa_score": result.qa_report.score if result.qa_report else None,
            "tower_characteristics_summary": _tower_characteristics_summary(result),
            "glb_inspection_summary": _glb_inspection_summary(result),
            "geometry_validation_summary": _geometry_validation_summary(result),
            "preview_inspection_summary": _preview_inspection_summary(result),
            "asset_import_summary": asset_import_metadata.get("asset_import_summary"),
            "asset_imports": asset_import_metadata.get("asset_imports"),
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
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "warnings": [warning.model_dump() for warning in report.warnings],
            "errors": [error.model_dump() for error in report.errors],
            "tower_validation": result.tower_validation.model_dump()
            if result.tower_validation
            else None,
            "rf_validation": result.rf_validation.model_dump() if result.rf_validation else None,
        }
        self._write_json(output_dir / "status.json", payload)

    def _write_running_status(self, workflow_id: str, output_dir: Path) -> None:
        status_path = output_dir / "status.json"
        if not status_path.exists():
            return
        try:
            payload = self._read_json(status_path)
        except (OSError, json.JSONDecodeError):
            return
        payload["status"] = "running"
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        payload["metrics"] = metrics | {"status": "running"}
        self._write_json(status_path, payload)

    def _write_failed_status(self, workflow_id: str, output_dir: Path, error: str) -> None:
        payload = {
            "workflow_id": workflow_id,
            "status": "failed",
            "artifacts": {},
            "errors": [{"code": "WORKFLOW_EXCEPTION", "message": error, "severity": "error"}],
            "warnings": [],
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
        }
        self._write_json(output_dir / "status.json", payload)

    def _write_pending_status(
        self,
        workflow_id: str,
        output_dir: Path,
        detail_level: str,
        use_llm: bool | None,
    ) -> None:
        payload = {
            "workflow_id": workflow_id,
            "status": "pending",
            "version_id": None,
            "active_version_id": None,
            "artifacts": {},
            "warnings": [],
            "errors": [],
            "extraction_provider": None,
            "llm_provider": None,
            "llm_available": llm_available_from_workflow_service(self),
            "llm_fallback_used": None,
            "llm_fallback_reason": None,
            "rag_context_count": 0,
            "memory_hits": 0,
            "memory_context_count": 0,
            "generation_mode": None,
            "blender_available": None,
            "qa_score": None,
            "quality_gates": [],
            "download_url": None,
            "trace_path": None,
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "metrics": {
                "status": "pending",
                "detail_level": detail_level,
                "use_llm": use_llm,
            },
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _copy_artifact_files(source_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in source_dir.iterdir():
            if not path.is_file():
                continue
            shutil.copy2(path, target_dir / path.name)

    def _copy_active_status_to_root(self, workflow_id: str, version_dir: Path) -> None:
        root_status = self.outputs_dir / workflow_id / "status.json"
        version_status = version_dir / "status.json"
        if not version_status.exists():
            raise KeyError(workflow_id)
        root_status.write_text(version_status.read_text(encoding="utf-8"), encoding="utf-8")

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
    provider = result.llm_provider
    if provider and provider.startswith("groq:") and not result.llm_fallback_used:
        mode = "structured_llm"
    elif result.llm_fallback_used or provider in {None, "deterministic"}:
        mode = "deterministic_fallback"
    else:
        mode = "validated_requirements"
    return {
        "mode": mode,
        "provider": provider,
        "model_name": _llm_model_name(provider),
        "fallback_used": result.llm_fallback_used,
        "error": result.llm_error,
        "source": provider,
        "validated_schema": True,
        "schema_name": "RequirementSpec",
        "rag_used_for_extraction": False,
        "rag_context_count": len(result.rag_context),
        "repaired_fields": repaired_fields,
        "inferred_fields": inferred_fields,
        "confidence": round(confidence, 2),
        "confidence_method": "heuristic_from_provider_fallback_and_warning_count",
        "critical_fields": _critical_requirement_fields(result.requirements),
        "warnings": [warning.model_dump() for warning in warnings],
    }


def _llm_model_name(provider: str | None) -> str | None:
    if provider and provider.startswith("groq:"):
        return provider.split(":", 1)[1]
    if provider == "deterministic":
        return None
    return provider


def _critical_requirement_fields(requirements: RequirementSpec | None) -> dict:
    if requirements is None:
        return {}
    return {
        "network_type": requirements.network_type,
        "tower_type": requirements.tower_type,
        "tower_height_m": requirements.tower_height_m,
        "sector_count": requirements.sector_count,
        "antenna_install_height_m": requirements.antenna_install_height_m,
        "azimuths_deg": requirements.azimuths_deg,
        "include_rru": requirements.include_rru,
        "include_cables": requirements.include_cables,
        "include_power_cabinet": requirements.include_power_cabinet,
        "include_gps_antenna": requirements.include_gps_antenna,
    }


def _requirements_context_text(requirements: RequirementSpec, source_label: str) -> str:
    return "\n".join(
        [
            f"source: {source_label}",
            f"network_type: {requirements.network_type}",
            f"tower_type: {requirements.tower_type}",
            f"tower_height_m: {requirements.tower_height_m}",
            f"sector_count: {requirements.sector_count}",
            "azimuths_deg: " + ", ".join(str(value) for value in requirements.azimuths_deg),
            f"antenna_install_height_m: {requirements.antenna_install_height_m}",
            f"include_rru: {requirements.include_rru}",
            f"include_cables: {requirements.include_cables}",
        ]
    )


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


def _extraction_errors(error: str | None) -> list[dict]:
    if not error:
        return []
    return [
        {
            "code": "LLM_EXTRACTION_ERROR",
            "message": error,
            "severity": "warning",
        }
    ]


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
    mesh_qa = result.geometry_validation.mesh_qa
    return {
        "status": result.geometry_validation.status,
        "geometry_source": result.geometry_validation.geometry_source,
        "generation_strategy": result.geometry_validation.generation_strategy,
        "mesh_qa_level": result.geometry_validation.mesh_qa_level,
        "mesh_qa_passed": mesh_qa.mesh_qa_passed if mesh_qa else None,
        "bounding_box_m": result.geometry_validation.bounding_box_m.model_dump()
        if result.geometry_validation.bounding_box_m
        else None,
        "checks": result.geometry_validation.checks,
        "object_counts": result.geometry_validation.object_counts,
        "missing_objects": result.geometry_validation.missing_objects,
        "critical_errors": result.geometry_validation.critical_errors,
        "mesh_qa_limitations": mesh_qa.limitations if mesh_qa else [],
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


def _asset_import_metadata(output_dir: Path) -> dict:
    metadata_path = output_dir / "scene_metadata.json"
    if not metadata_path.exists():
        return {"asset_import_summary": None, "asset_imports": None}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"asset_import_summary": None, "asset_imports": None}
    return {
        "asset_import_summary": metadata.get("asset_import_summary"),
        "asset_imports": metadata.get("asset_imports"),
    }


def _public_status_payload(workflow_id: str, status: dict) -> dict:
    payload = dict(status)
    active_version_id = payload.get("active_version_id")
    payload["artifacts"] = _public_artifact_urls(
        workflow_id,
        payload.get("artifacts") or {},
        version_id=None,
    )
    payload["trace_url"] = _artifact_url(workflow_id, "trace")
    payload["trace_path"] = None
    payload["download_url"] = f"/designs/{workflow_id}/download"
    payload["available_actions"] = _status_available_actions(payload)
    payload["asset_imports"] = _public_asset_imports(payload.get("asset_imports"))
    if active_version_id:
        payload["active_version_artifacts"] = _public_artifact_urls(
            workflow_id,
            status.get("artifacts") or {},
            version_id=active_version_id,
        )
    return payload


def _public_asset_imports(asset_imports: object) -> list[dict] | None:
    if asset_imports is None:
        return None
    if not isinstance(asset_imports, list):
        return []
    public_imports = []
    for record in asset_imports:
        if not isinstance(record, dict):
            continue
        public = dict(record)
        public.pop("resolved_path", None)
        public.pop("local_path", None)
        public.pop("filesystem_path", None)
        public_imports.append(public)
    return public_imports


def _public_artifact_urls(
    workflow_id: str,
    artifacts: dict | None,
    version_id: str | None = None,
) -> dict[str, str]:
    if not isinstance(artifacts, dict):
        return {}
    public = {}
    for artifact_name in artifacts:
        if artifact_name not in _ALLOWED_ARTIFACT_FILES:
            continue
        if artifact_name == "download" and version_id is None:
            public[artifact_name] = f"/designs/{workflow_id}/download"
        else:
            public[artifact_name] = _artifact_url(workflow_id, artifact_name, version_id)
    return public


def _artifact_url(
    workflow_id: str,
    artifact_name: str,
    version_id: str | None = None,
) -> str:
    url = f"/designs/{workflow_id}/artifacts/{artifact_name}"
    if version_id:
        return f"{url}?version_id={version_id}"
    return url


def _status_available_actions(status: dict) -> list[str]:
    backend_status = status.get("status", "unknown")
    if backend_status in {"pending", "running"}:
        return ["view_timeline"]
    if backend_status == "failed":
        return ["view_issues", "view_timeline", "retry_with_changes"]
    actions = ["open_viewer", "download_artifacts", "view_timeline", "edit_design"]
    if status.get("active_version_id"):
        actions.append("view_versions")
    if status.get("warnings") or status.get("errors"):
        actions.append("review_issues")
    return actions


def _edit_result_message(result: SceneEditResult) -> str:
    if result.status == "applied":
        return "L'édition a été appliquée et une nouvelle version est disponible."
    if result.status == "rejected":
        return "L'édition a été rejetée par la validation SceneSpec."
    if result.errors:
        return result.errors[0].message
    return "L'édition a échoué."


def _edit_available_actions(result: SceneEditResult) -> list[str]:
    if result.status == "applied":
        return ["open_viewer", "view_timeline", "view_versions", "review_issues"]
    if result.status == "rejected":
        return ["review_issues", "edit_prompt_again"]
    return ["review_issues", "edit_prompt_again"]


def _event_identity(event: dict) -> str:
    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    return json.dumps(
        {
            "event_type": event.get("event_type"),
            "workflow_id": event.get("workflow_id"),
            "timestamp": event.get("timestamp"),
            "payload": event.get("payload"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _normalized_event_payload(event_type: str, payload: dict) -> dict:
    normalized = dict(payload)
    node = str(normalized.get("node") or _event_default_node(event_type))
    phase = str(normalized.get("phase") or _event_default_phase(event_type, node))
    status = str(normalized.get("status") or _event_default_status(event_type))
    human_label = str(normalized.get("human_label") or _event_human_label(event_type, node))
    progress_message = str(
        normalized.get("progress_message")
        or _event_progress_message(event_type, status, human_label)
    )
    normalized["node"] = node
    normalized["phase"] = phase
    normalized["status"] = status
    normalized["human_label"] = human_label
    normalized["progress_message"] = progress_message
    normalized.setdefault("duration_ms", None)
    if not isinstance(normalized.get("warnings"), list):
        normalized["warnings"] = []
    if not isinstance(normalized.get("errors"), list):
        normalized["errors"] = []
    if not isinstance(normalized.get("artifact_refs"), list):
        normalized["artifact_refs"] = []
    return normalized


def _event_default_node(event_type: str) -> str:
    if event_type in {"qa_completed", "qa_failed"}:
        return "qa_generation"
    if event_type in {"blender_completed", "blender_failed", "artifact_ready"}:
        return "generate_blender"
    if event_type.startswith("edit_"):
        return "edit"
    if event_type.startswith("version_"):
        return "versioning"
    if event_type == "user_issue_created":
        return "issues"
    return "workflow"


def _event_default_phase(event_type: str, node: str) -> str:
    if node in {"generate_blender", "blender_failure_handler"}:
        return "blender" if event_type != "artifact_ready" else "viewer"
    if node == "qa_generation":
        return "qa"
    if node == "edit":
        return "edit"
    if node == "versioning":
        return "versioning"
    if node == "issues":
        return "issues"
    return "workflow"


def _event_default_status(event_type: str) -> str:
    if event_type.endswith("_failed") or event_type in {"workflow_failed", "edit_patch_rejected"}:
        return "failed"
    if event_type in {"design_created", "validated_requirements_received"}:
        return "running"
    if event_type == "user_issue_created":
        return "warning"
    return "completed"


def _event_human_label(event_type: str, node: str) -> str:
    mapping = {
        "design_created": "Design créé",
        "validated_requirements_received": "Exigences validées reçues",
        "workflow_completed": "Design prêt",
        "workflow_failed": "Workflow en échec",
        "artifact_ready": "Préparation du viewer 3D",
        "qa_completed": "Vérification géométrique terminée",
        "qa_failed": "Vérification géométrique en échec",
        "user_issue_created": "Issue utilisateur créée",
        "edit_patch_created": "Patch d'édition créé",
        "edit_patch_rejected": "Patch d'édition rejeté",
        "edit_patch_applied": "Édition appliquée",
        "version_created": "Version créée",
        "version_rolled_back": "Version restaurée",
        "blender_completed": "Génération Blender terminée",
        "blender_failed": "Génération Blender en échec",
    }
    return mapping.get(event_type, node.replace("_", " ").capitalize())


def _event_progress_message(event_type: str, status: str, human_label: str) -> str:
    mapping = {
        "design_created": "Le backend prépare le workflow de génération.",
        "validated_requirements_received": (
            "Le backend utilise les exigences consolidées du document pack."
        ),
        "workflow_completed": "Le design est prêt pour inspection 3D.",
        "workflow_failed": "Le design n'a pas pu être terminé.",
        "artifact_ready": "Les artefacts du viewer 3D sont disponibles.",
        "qa_completed": "Le contrôle qualité du modèle 3D est terminé.",
        "qa_failed": "Le contrôle qualité a détecté un blocage.",
        "user_issue_created": "Une limitation ou erreur est visible pour l'utilisateur.",
        "edit_patch_created": "Le backend prépare une modification de SceneSpec.",
        "edit_patch_rejected": "L'édition a été refusée avec une raison exploitable.",
        "edit_patch_applied": "La nouvelle version du design est disponible.",
        "version_created": "Une version locale a été créée.",
        "version_rolled_back": "La version active a été restaurée.",
        "blender_completed": "Blender a terminé la génération 3D.",
        "blender_failed": "Blender n'a pas produit un résultat valide.",
    }
    return mapping.get(event_type, f"{human_label} : {status}.")


def _issue_event_title(issue: dict) -> str:
    code = str(issue.get("code") or "")
    if code == "WORKFLOW_EXCEPTION":
        return "Échec du workflow"
    if code.startswith("ASSET_"):
        return "Issue asset détectée"
    if code.startswith("BLENDER_"):
        return "Issue Blender détectée"
    if code.startswith("QA_") or code.startswith("GEOMETRY_"):
        return "Issue qualité détectée"
    if issue.get("severity") == "error":
        return "Erreur détectée"
    return "Avertissement détecté"


def _structural_qa_status(result: OrchestratorResult) -> str:
    if result.glb_inspection is None:
        return "not_run"
    status = "passed" if result.glb_inspection.structural_qa_passed else "failed"
    return f"{status} ({result.glb_inspection.inspection_mode})"


def _geometry_qa_status(result: OrchestratorResult) -> str:
    if result.geometry_validation is None:
        return "not_run"
    return result.geometry_validation.status


_ALLOWED_ARTIFACT_FILES = {
    "requirements_spec": "requirements_spec.json",
    "extraction_report": "extraction_report.json",
    "scene_spec": "scene_spec.json",
    "validation_report": "validation_report.json",
    "quality_gates": "quality_gates.json",
    "qa_report": "qa_report.json",
    "generation_report": "generation_report.json",
    "glb_inspection": "glb_inspection.json",
    "geometry_validation": "geometry_validation.json",
    "preview_inspection": "preview_inspection.json",
    "memory_recall": "memory_recall.json",
    "technical_report": "technical_report.md",
    "glb": "design.glb",
    "preview": "preview.png",
    "metadata": "scene_metadata.json",
    "download": "artifacts.zip",
    "trace": "workflow_trace.json",
    "scene_patch": "scene_patch.json",
    "scene_diff": "scene_diff.json",
}
