"""Product-oriented API layer.

Transforms technical backend status/events into user-facing responses.
The future chat-first/3D-first frontend should consume these endpoints
instead of parsing raw JSON technical reports.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.api.telecom_studio_api.config import settings
from apps.api.telecom_studio_api.runtime_contract import (
    llm_available_from_workflow_service,
    llm_truth,
    memory_status,
    runtime_capabilities,
    unsupported_actions,
)
from apps.api.telecom_studio_api.workflow import WorkflowService
from core.contracts.assembly_evidence import AssemblyConstraintEvidence
from core.contracts.scene import RuntimeAssetMetadata, SceneSpec
from core.contracts.sector_preview import SectorPreviewEvidence
from core.contracts.tower_access_evidence import TowerAccessEvidence
from core.services.asset_inventory import AssetInventoryService
from core.services.blender_runtime import output_reports_qualified_blender
from core.services.scene_versioning import COVERAGE_GAP_LABELS


class ProductService:
    def __init__(
        self,
        workflow_service: WorkflowService,
        asset_inventory_service: AssetInventoryService,
    ) -> None:
        self.workflow_service = workflow_service
        self.asset_inventory_service = asset_inventory_service

    def studio_summary(self) -> dict:
        designs = self.workflow_service.list_designs(limit=200, offset=0)
        inventory = self.asset_inventory_service.inspect()
        inventory_status = _inventory_status(inventory)
        blender_available = _blender_available()
        groq_available = bool(settings.resolved_groq_api_key)
        llm_available = llm_available_from_workflow_service(self.workflow_service)
        rag = _rag_summary(self.workflow_service.orchestrator.rag_service)
        memory = memory_status(getattr(self.workflow_service.orchestrator, "memory_service", None))

        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        summaries = []
        for design in designs:
            status = design.get("status", "unknown")
            if status in counts:
                counts[status] += 1
            elif status in {"legacy_unverified", "integrity_failed"}:
                counts["failed"] += 1
            summaries.append(
                {
                    "workflow_id": design.get("workflow_id"),
                    "status": status,
                    "created_at": design.get("created_at"),
                    "qa_score": design.get("qa_score"),
                    "generation_mode": design.get("generation_mode"),
                    "completion_certificate_status": design.get("completion_certificate_status"),
                    "current_operation": _operation_for_status(status),
                }
            )

        return {
            "designs": summaries,
            "total_designs": len(designs),
            "active_designs": counts["running"] + counts["pending"],
            "completed_designs": counts["completed"],
            "failed_designs": counts["failed"],
            "pending_designs": counts["pending"],
            "asset_inventory_status": inventory_status,
            "asset_count": int(inventory.get("asset_count") or 0),
            "real_glb_asset_count": int(inventory.get("real_glb_asset_count") or 0),
            "import_qualified_glb_count": int(inventory.get("import_qualified_glb_count") or 0),
            "generation_eligible_asset_count": int(
                inventory.get("generation_eligible_asset_count") or 0
            ),
            "reference_only_asset_count": int(inventory.get("reference_only_asset_count") or 0),
            "missing_file_count": int(inventory.get("missing_file_count") or 0),
            "blender_available": blender_available,
            "groq_available": groq_available,
            "llm_available": llm_available,
            "rag_embedding_provider": rag["embedding_provider"],
            "rag_status": rag["status"],
            "rag_degraded": rag["degraded"],
            "rag_reranker": rag["reranker"],
            "rag_reranker_status": rag["reranker_status"],
            "rag_reranker_provider": rag["reranker_provider"],
            "rag_reranker_model": rag["reranker_model"],
            "rag_reranker_degraded_reason": rag["reranker_degraded_reason"],
            "rag_operational_status": rag["operational_status"],
            "rag_last_operation": rag["last_operation"],
            "rag_reindex_url": "/rag/reindex",
            "memory_vector_reindex_url": "/memory/vector/reindex",
            **memory,
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "warnings": _studio_warnings(inventory, rag),
        }

    def user_summary(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        events = self.workflow_service.get_events(workflow_id)
        issues = _collect_user_issues(status, events)
        qa_summary = _qa_summary(status)
        next_action = _next_recommended_action(status, issues)
        llm = llm_truth(status, workflow_service=self.workflow_service)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "current_operation": _current_operation(status, events),
            "next_recommended_action": next_action,
            "qa_summary": qa_summary,
            "human_readable_issues": issues,
            "active_version": status.get("active_version_id"),
            "multimodal_consent": status.get("multimodal_consent", "disabled"),
            "generation_mode": status.get("generation_mode"),
            "generation_strategy": status.get("generation_strategy"),
            "geometry_source": status.get("geometry_source"),
            "mesh_qa_level": status.get("mesh_qa_level"),
            "mesh_qa_passed": status.get("mesh_qa_passed"),
            "extraction_provider": llm["extraction_provider"],
            "llm_provider": status.get("llm_provider"),
            "llm_available": llm["llm_available"],
            "llm_fallback_used": status.get("llm_fallback_used"),
            "llm_fallback_reason": llm["llm_fallback_reason"],
            "input_analysis_status": status.get("input_analysis_status", "unavailable"),
            "asset_quality_summary": _asset_quality_summary(status),
            "limitations": _collect_limitations(status),
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
        }

    def current_operation(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        events = self.workflow_service.get_events(workflow_id)
        issues = _collect_user_issues(status, events)
        active_operation = status.get("active_operation")
        runtime = (
            _runtime_from_active_operation(active_operation)
            if isinstance(active_operation, dict)
            else _current_runtime_state(events)
        )
        backend_status = status.get("status", "unknown")
        current_operation = _current_operation(status, events)
        task_started_at, task_finished_at = _task_event_bounds(events)
        terminal_statuses = {
            "completed",
            "failed",
            "legacy_unverified",
            "integrity_failed",
        }
        if backend_status in terminal_statuses and not isinstance(active_operation, dict):
            event_status = "completed" if backend_status == "completed" else "failed"
            runtime = {
                "node": "workflow",
                "phase": "workflow",
                "source": "status",
                "operation": _event_to_human(f"workflow_{event_status}", {}),
                "node_status": event_status,
                "timestamp": runtime.get("timestamp"),
            }
        current_node = runtime.get("node")
        phase = runtime.get("phase")
        llm = llm_truth(status, workflow_service=self.workflow_service)
        human_label = (
            runtime.get("operation")
            if runtime.get("source") == "persisted_active_operation"
            or (current_node == "workflow" and runtime.get("operation"))
            else _trace_node_label(current_node)
            if current_node
            else current_operation
        )
        return {
            "workflow_id": workflow_id,
            "status": backend_status,
            "phase": phase,
            "current_operation": current_operation,
            "human_label": human_label,
            "progress_message": current_operation,
            "progress_label": _progress_label(status),
            "next_recommended_action": _next_recommended_action(status, issues),
            "progress_indicator": _progress_indicator(status),
            "current_phase": phase,
            "current_node": current_node,
            "event_source": "push_sse" if events else "status",
            "state_source": runtime.get("source", "status"),
            "is_running": backend_status in {"pending", "running"},
            "is_terminal": backend_status in terminal_statuses,
            "last_event_at": runtime.get("timestamp"),
            "task_started_at": task_started_at,
            "task_finished_at": task_finished_at,
            "generation_mode": status.get("generation_mode"),
            "generation_strategy": status.get("generation_strategy"),
            "geometry_source": status.get("geometry_source"),
            "mesh_qa_level": status.get("mesh_qa_level"),
            "mesh_qa_passed": status.get("mesh_qa_passed"),
            "extraction_provider": llm["extraction_provider"],
            "llm_provider": status.get("llm_provider"),
            "llm_available": llm["llm_available"],
            "llm_fallback_used": status.get("llm_fallback_used"),
            "llm_fallback_reason": llm["llm_fallback_reason"],
            "qa_score": status.get("qa_score"),
            "human_warnings_count": sum(1 for issue in issues if issue["severity"] == "warning"),
            "human_errors_count": sum(1 for issue in issues if issue["severity"] == "error"),
            "runtime_capabilities": runtime_capabilities(),
            "unsupported_actions": unsupported_actions(),
            "available_actions": _available_actions(status, issues),
        }

    def user_issues(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        events = self.workflow_service.get_events(workflow_id)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "human_readable_issues": _collect_user_issues(status, events),
        }

    def viewer_bundle(self, workflow_id: str) -> dict:
        try:
            status, verified_snapshot = self.workflow_service.get_viewer_status_snapshot(
                workflow_id
            )
        except KeyError as exc:
            raise ProductNotFound(workflow_id) from exc
        runtime = runtime_capabilities()
        active_version = (
            verified_snapshot.version_id
            if verified_snapshot is not None
            else status.get("active_version_id")
        )
        base_url = f"/designs/{workflow_id}/artifacts"
        viewer_artifacts = []
        issues = _collect_user_issues(status, self.workflow_service.get_events(workflow_id))
        llm = llm_truth(status, workflow_service=self.workflow_service)
        verified_artifacts = (
            verified_snapshot.artifact_paths if verified_snapshot is not None else {}
        )

        def _artifact(name: str, content_type: str, filename: str) -> dict:
            url = f"{base_url}/{filename}"
            if active_version:
                url = f"{url}?version_id={active_version}"
            path = verified_artifacts.get(filename)
            return {
                "name": name,
                "url": url,
                "content_type": content_type,
                "available": path is not None and path.exists(),
            }

        viewer_artifacts.append(_artifact("design.glb", "model/gltf-binary", "glb"))
        viewer_artifacts.append(_artifact("preview.png", "image/png", "preview"))
        viewer_artifacts.append(_artifact("preview_front.png", "image/png", "preview_front"))
        viewer_artifacts.append(_artifact("preview_side.png", "image/png", "preview_side"))
        viewer_artifacts.append(_artifact("preview_top.png", "image/png", "preview_top"))
        viewer_artifacts.append(_artifact("preview_closeup.png", "image/png", "preview_closeup"))
        viewer_artifacts.append(_artifact("scene_metadata.json", "application/json", "metadata"))
        viewer_artifacts.append(
            _artifact("component_proofs.json", "application/json", "component_proofs")
        )
        viewer_artifacts.append(
            _artifact("requirements_spec.json", "application/json", "requirements_spec")
        )
        viewer_artifacts.append(
            _artifact("extraction_report.json", "application/json", "extraction_report")
        )
        viewer_artifacts.append(
            _artifact(
                "input_analysis_receipt.json",
                "application/json",
                "input_analysis_receipt",
            )
        )
        viewer_artifacts.append(_artifact("scene_spec.json", "application/json", "scene_spec"))
        viewer_artifacts.append(
            _artifact("assembly_plan.json", "application/json", "assembly_plan")
        )
        viewer_artifacts.append(
            _artifact("constraint_evidence.json", "application/json", "constraint_evidence")
        )
        viewer_artifacts.append(
            _artifact(
                "sector_preview_evidence.json",
                "application/json",
                "sector_preview_evidence",
            )
        )
        viewer_artifacts.append(
            _artifact(
                "tower_access_evidence.json",
                "application/json",
                "tower_access_evidence",
            )
        )
        viewer_artifacts.append(_artifact("qa_report.json", "application/json", "qa_report"))
        viewer_artifacts.append(
            _artifact("generation_report.json", "application/json", "generation_report")
        )
        viewer_artifacts.append(_artifact("rag_evidence.json", "application/json", "rag_evidence"))
        viewer_artifacts.append(
            _artifact("planning_decision.json", "application/json", "planning_decision")
        )
        viewer_artifacts.append(
            _artifact("cognitive_plan.json", "application/json", "cognitive_plan")
        )
        viewer_artifacts.append(
            _artifact(
                "capability_observations.json",
                "application/json",
                "capability_observations",
            )
        )
        viewer_artifacts.append(
            _artifact("geometry_validation.json", "application/json", "geometry_validation")
        )
        viewer_artifacts.append(
            _artifact("requirement_coverage.json", "application/json", "requirement_coverage")
        )
        viewer_artifacts.append(
            _artifact(
                "completion_certificate.json",
                "application/json",
                "completion_certificate",
            )
        )
        viewer_artifacts.append(
            _artifact("technical_report.md", "text/markdown", "technical_report")
        )
        viewer_artifacts.append(
            _artifact(
                "llm_decision_provenance.json",
                "application/json",
                "llm_decision_provenance",
            )
        )
        primary_glb = _artifact_by_name(viewer_artifacts, "design.glb")
        preview = _artifact_by_name(viewer_artifacts, "preview.png")
        metadata = _artifact_by_name(viewer_artifacts, "scene_metadata.json")
        component_proofs = _artifact_by_name(viewer_artifacts, "component_proofs.json")
        requirements_spec = _artifact_by_name(viewer_artifacts, "requirements_spec.json")
        extraction_report = _artifact_by_name(viewer_artifacts, "extraction_report.json")
        input_analysis_receipt = _artifact_by_name(viewer_artifacts, "input_analysis_receipt.json")
        scene_spec = _artifact_by_name(viewer_artifacts, "scene_spec.json")
        assembly_plan = _artifact_by_name(viewer_artifacts, "assembly_plan.json")
        constraint_evidence = _artifact_by_name(viewer_artifacts, "constraint_evidence.json")
        tower_access_evidence = _artifact_by_name(viewer_artifacts, "tower_access_evidence.json")
        qa_report = _artifact_by_name(viewer_artifacts, "qa_report.json")
        generation_report = _artifact_by_name(viewer_artifacts, "generation_report.json")
        rag_evidence = _artifact_by_name(viewer_artifacts, "rag_evidence.json")
        geometry_validation = _artifact_by_name(viewer_artifacts, "geometry_validation.json")
        requirement_coverage = _artifact_by_name(viewer_artifacts, "requirement_coverage.json")
        completion_certificate = _artifact_by_name(viewer_artifacts, "completion_certificate.json")
        cognitive_plan = _artifact_by_name(viewer_artifacts, "cognitive_plan.json")
        capability_observations = _artifact_by_name(
            viewer_artifacts, "capability_observations.json"
        )
        report = _artifact_by_name(viewer_artifacts, "technical_report.md")
        llm_decision_provenance = _artifact_by_name(
            viewer_artifacts, "llm_decision_provenance.json"
        )
        verified_scene = (
            verified_snapshot.scene
            if verified_snapshot is not None and "scene_spec" in verified_artifacts
            else None
        )
        verified_assembly_plan = (
            verified_snapshot.assembly_plan
            if verified_snapshot is not None and "assembly_plan" in verified_artifacts
            else None
        )
        constraint_evidence_path = verified_artifacts.get("constraint_evidence")
        sector_preview_evidence_path = verified_artifacts.get("sector_preview_evidence")
        tower_access_evidence_path = verified_artifacts.get("tower_access_evidence")

        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "active_version": active_version,
            "version_id": verified_snapshot.version_id if verified_snapshot is not None else None,
            "multimodal_consent": status.get("multimodal_consent", "disabled"),
            "multimodal_intelligence": runtime["multimodal_intelligence"],
            "asset_decision_summary": _asset_decision_summary(verified_assembly_plan),
            "assembly_constraint_summary": _assembly_constraint_summary_from_path(
                constraint_evidence_path
            ),
            "sector_previews": _sector_preview_summaries_from_path(
                sector_preview_evidence_path,
                workflow_id=workflow_id,
                version_id=active_version,
            ),
            "tower_access_summary": _tower_access_summary_from_path(
                tower_access_evidence_path,
                scene=verified_scene,
            ),
            "visual_review": _visual_review_summary(
                status,
                runtime["multimodal_intelligence"],
            ),
            "generation_mode": status.get("generation_mode"),
            "generation_strategy": status.get("generation_strategy"),
            "geometry_source": status.get("geometry_source"),
            "mesh_qa_level": status.get("mesh_qa_level"),
            "mesh_qa_passed": status.get("mesh_qa_passed"),
            "qa_score": status.get("qa_score"),
            "asset_import_summary": status.get("asset_import_summary"),
            "geometry_fidelity_summary": _geometry_fidelity_summary(verified_scene),
            "geometry_program_summary": _geometry_program_summary(verified_scene),
            "human_warnings_count": sum(1 for issue in issues if issue["severity"] == "warning"),
            "human_errors_count": sum(1 for issue in issues if issue["severity"] == "error"),
            "primary_glb_url": _available_artifact_url(primary_glb),
            "preview_url": _available_artifact_url(preview),
            "report_url": _available_artifact_url(report),
            "metadata_url": _available_artifact_url(metadata),
            "component_proofs_url": _available_artifact_url(component_proofs),
            "requirements_spec_url": _available_artifact_url(requirements_spec),
            "extraction_report_url": _available_artifact_url(extraction_report),
            "input_analysis_receipt_url": _available_artifact_url(input_analysis_receipt),
            "scene_spec_url": _available_artifact_url(scene_spec),
            "assembly_plan_url": _available_artifact_url(assembly_plan),
            "constraint_evidence_url": _available_artifact_url(constraint_evidence),
            "tower_access_evidence_url": _available_artifact_url(tower_access_evidence),
            "qa_report_url": _available_artifact_url(qa_report),
            "generation_report_url": _available_artifact_url(generation_report),
            "rag_evidence_url": _available_artifact_url(rag_evidence),
            "geometry_validation_url": _available_artifact_url(geometry_validation),
            "requirement_coverage_url": _available_artifact_url(requirement_coverage),
            "completion_certificate_url": _available_artifact_url(completion_certificate),
            "requirement_coverage_passed": status.get("requirement_coverage_passed"),
            "requirement_coverage_ratio": status.get("requirement_coverage_ratio"),
            "completion_certificate_status": status.get("completion_certificate_status"),
            "design_domain": status.get("design_domain"),
            "cognitive_plan_sha256": status.get("cognitive_plan_sha256"),
            "cognitive_plan_url": _available_artifact_url(cognitive_plan),
            "capability_observations_url": _available_artifact_url(capability_observations),
            "extraction_provider": llm["extraction_provider"],
            "llm_provider": status.get("llm_provider"),
            "llm_available": llm["llm_available"],
            "llm_fallback_used": status.get("llm_fallback_used"),
            "llm_fallback_reason": llm["llm_fallback_reason"],
            "llm_decision_provenance": status.get("llm_decision_provenance"),
            "llm_decision_provenance_url": _available_artifact_url(llm_decision_provenance),
            "input_analysis": status.get("input_analysis"),
            "input_analysis_status": status.get("input_analysis_status", "unavailable"),
            "rag_context_count": status.get("rag_context_count"),
            "rag_planning_summary": status.get("rag_planning_summary"),
            "rag_reranker_provider": status.get("rag_reranker_provider"),
            "rag_reranker_model": _public_rag_reranker_model(
                provider=status.get("rag_reranker_provider"),
                status=status.get("rag_reranker_status"),
                model=status.get("rag_reranker_model"),
            ),
            "rag_reranker_status": status.get("rag_reranker_status"),
            "rag_reranker_degraded_reason": status.get("rag_reranker_degraded_reason"),
            "rag_retrieval_status": status.get("rag_retrieval_status"),
            "rag_retrieval_degraded_reason": status.get("rag_retrieval_degraded_reason"),
            "memory_context_count": status.get("memory_context_count"),
            "qa_summary": _viewer_qa_summary(status),
            "viewer_artifacts": viewer_artifacts,
            "limitations": _collect_limitations(status),
            "runtime_capabilities": runtime,
            "unsupported_actions": unsupported_actions(),
            "available_actions": _available_actions(status, issues),
        }

    def timeline_summary(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        events = self.workflow_service.get_events(workflow_id)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "event_source": "push_sse",
            "timeline_steps": _events_to_timeline(events, status),
        }

    def _status_or_raise(self, workflow_id: str) -> dict:
        try:
            return self.workflow_service.get_status(workflow_id)
        except KeyError as exc:
            raise ProductNotFound(workflow_id) from exc


class ProductNotFound(Exception):
    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"workflow not found: {workflow_id}")


def _inventory_status(inventory: dict) -> str:
    status = inventory.get("status")
    if isinstance(status, str) and status:
        return status
    entries = inventory.get("entries", [])
    if not entries:
        return "unknown"
    total = len(entries)
    ready = sum(
        1
        for entry in entries
        if entry.get("asset_import_mode") in {"imported_glb", "imported_glb_exact"}
    )
    fallback = sum(
        1 for entry in entries if entry.get("effective_generation_mode") == "procedural_fallback"
    )
    if ready == total and total > 0:
        return "ready_for_import"
    if fallback > 0:
        return "partial_import_ready"
    return "incomplete"


def _blender_available() -> bool:
    binary = _resolve_blender_binary(settings.resolved_blender_binary)
    if binary is None:
        return False
    try:
        stat = binary.stat()
    except OSError:
        return False
    return _probe_blender_runtime(str(binary), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=8)
def _probe_blender_runtime(binary: str, _mtime_ns: int, _size: int) -> bool:
    """Treat Blender as available only after a real headless startup succeeds."""

    marker = "TELECOM_STUDIO_BLENDER_READY"
    try:
        completed = _run_blender_probe(
            [binary, "--background", "--factory-startup", "--python-expr", f'print("{marker}")']
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = f"{completed.stdout}\n{completed.stderr}"
    return (
        completed.returncode == 0 and marker in output and output_reports_qualified_blender(output)
    )


def _run_blender_probe(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Single subprocess boundary for the Blender readiness probe.

    Keeping this separate from resolution and caching lets the test harness
    reject an accidental real Blender startup without patching subprocess
    globally or weakening the production smoke.
    """

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def _rag_summary(rag_service: Any | None) -> dict:
    if rag_service is None:
        return {
            "embedding_provider": None,
            "status": "disabled",
            "degraded": True,
            "reranker": None,
            "reranker_status": "disabled",
            "reranker_provider": None,
            "reranker_model": None,
            "reranker_degraded_reason": None,
            "operational_status": "disabled",
            "last_operation": None,
        }
    health = rag_service.health_snapshot()
    provider = getattr(getattr(rag_service, "embedding_provider", None), "name", None)
    if not provider:
        return {
            "embedding_provider": None,
            "status": "unknown",
            "degraded": True,
            "reranker": _rag_reranker_name(rag_service),
            "reranker_status": _rag_reranker_status(rag_service),
            "reranker_provider": _rag_reranker_provider(rag_service),
            "reranker_model": _rag_reranker_model(rag_service),
            "reranker_degraded_reason": _rag_reranker_degraded_reason(rag_service),
            "operational_status": str(health.get("status") or "unknown"),
            "last_operation": health.get("operation"),
        }
    provider_name = str(provider)
    operational_status = str(health.get("status") or "unverified")
    if operational_status == "failed":
        status = "configured_but_last_operation_failed"
        degraded = True
    elif operational_status != "operational":
        status = "configured_unverified"
        degraded = True
    elif provider_name.startswith("nvidia:"):
        status = "primary_nvidia_embedding"
        degraded = False
    elif provider_name.startswith("hashing-"):
        status = "deterministic_hash_fallback"
        degraded = True
    else:
        status = "custom_provider"
        degraded = True
    return {
        "embedding_provider": provider_name,
        "status": status,
        "degraded": degraded,
        "reranker": _rag_reranker_name(rag_service),
        "reranker_status": _rag_reranker_status(rag_service),
        "reranker_provider": _rag_reranker_provider(rag_service),
        "reranker_model": _rag_reranker_model(rag_service),
        "reranker_degraded_reason": _rag_reranker_degraded_reason(rag_service),
        "operational_status": operational_status,
        "last_operation": health.get("operation"),
    }


def _rag_reranker_name(rag_service: Any) -> str:
    reranker = getattr(rag_service, "_reranker", None)
    return str(getattr(reranker, "name", "not_loaded"))


def _rag_reranker_status(rag_service: Any) -> str:
    reranker = getattr(rag_service, "_reranker", None)
    status = getattr(reranker, "status", None)
    if isinstance(status, str) and status:
        return status
    name = _rag_reranker_name(rag_service)
    if name == "passthrough":
        return "passthrough_no_rerank"
    if name.startswith("nvidia:"):
        return "primary_nvidia_reranker"
    if name == "not_loaded":
        return "not_loaded"
    return "custom"


def _rag_reranker_provider(rag_service: Any) -> str | None:
    reranker = getattr(rag_service, "_reranker", None)
    value = getattr(reranker, "provider", None)
    if value:
        return str(value)
    value = getattr(rag_service, "_reranker_provider_name", None)
    return str(value) if value else None


def _rag_reranker_model(rag_service: Any) -> str | None:
    reranker = getattr(rag_service, "_reranker", None)
    if reranker is not None:
        value = getattr(reranker, "model_name", None)
        return str(value) if value else None
    value = getattr(rag_service, "_reranker_model", None)
    return str(value) if value else None


def _public_rag_reranker_model(
    *,
    provider: Any,
    status: Any,
    model: Any,
) -> str | None:
    if provider in {"passthrough", "disabled", "none"} or status == "passthrough_no_rerank":
        return None
    return str(model) if model else None


def _rag_reranker_degraded_reason(rag_service: Any) -> str | None:
    reranker = getattr(rag_service, "_reranker", None)
    value = getattr(reranker, "degraded_reason", None)
    return str(value) if value else None


def _resolve_blender_binary(binary: str) -> Path | None:
    candidates = [os.getenv("BLENDER_BINARY"), binary]
    if binary == "blender":
        candidates.extend(
            [
                shutil.which("blender"),
                "/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender",
                "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
                "/Applications/Blender.app/Contents/MacOS/Blender",
                "/Applications/Blender 4.4.app/Contents/MacOS/Blender",
                "/Applications/Blender 4.3.app/Contents/MacOS/Blender",
            ]
        )
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return path
        resolved = shutil.which(str(candidate))
        if resolved:
            return Path(resolved)
    return None


def _operation_for_status(status: str) -> str:
    mapping = {
        "pending": "En attente de traitement",
        "running": "Génération en cours",
        "completed": "Design terminé",
        "failed": "Échec de la génération",
        "legacy_unverified": "Résultat historique non certifié",
        "integrity_failed": "Intégrité du résultat en échec",
    }
    return mapping.get(status, status)


def _current_operation(status: dict, events: list[dict] | None = None) -> str:
    backend_status = status.get("status", "unknown")
    active_operation = status.get("active_operation")
    if isinstance(active_operation, dict) and active_operation.get("status") == "running":
        return str(active_operation.get("human_label") or "Opération en cours")
    metrics = status.get("metrics", {})
    runtime = _current_runtime_state(events or [])
    if backend_status in {"pending", "running"} and runtime.get("node"):
        return runtime["operation"]
    if backend_status == "pending":
        return "Le design est en file d'attente et va démarrer."
    if backend_status in {"failed", "legacy_unverified", "integrity_failed"}:
        return "Le design a échoué. Consultez les problèmes pour corriger la situation."
    if backend_status == "completed":
        return "Le design est terminé. Vous pouvez l'inspecter en 3D."
    if runtime.get("node"):
        return runtime["operation"]
    running_step = metrics.get("current_step")
    if running_step:
        return f"Étape en cours : {running_step}"
    return f"Traitement en cours ({backend_status})"


def _runtime_from_active_operation(operation: dict) -> dict:
    kind = str(operation.get("kind") or "operation")
    return {
        "node": kind,
        "phase": "revision" if kind == "edit" else kind,
        "source": "persisted_active_operation",
        "operation": str(operation.get("human_label") or "Opération en cours"),
        "node_status": str(operation.get("status") or "running"),
        "timestamp": operation.get("started_at"),
    }


def _current_runtime_state(events: list[dict]) -> dict:
    for event in reversed(events):
        event_type = event.get("event_type")
        payload = event.get("payload")
        if event_type == "node_started" and isinstance(payload, dict):
            node = payload.get("node")
            if not isinstance(node, str):
                continue
            return {
                "node": node,
                "phase": payload.get("phase"),
                "source": "runtime_events",
                "operation": str(
                    payload.get("progress_message")
                    or f"Étape en cours : {_trace_node_label(node)}."
                ),
                "node_status": "running",
                "timestamp": event.get("timestamp"),
            }
        if event_type in {"node_completed", "node_failed", "node_skipped"} and isinstance(
            payload, dict
        ):
            node = payload.get("node")
            if not isinstance(node, str):
                continue
            return {
                "node": node,
                "phase": payload.get("phase"),
                "source": "runtime_events",
                "operation": _next_operation_after_node(node, payload),
                "node_status": payload.get("status"),
                "timestamp": event.get("timestamp"),
            }
        if event_type in {"workflow_completed", "workflow_failed"}:
            event_data = payload if isinstance(payload, dict) else {}
            return {
                "node": "workflow",
                "phase": "workflow",
                "source": "runtime_events",
                "operation": _event_to_human(event_type, event_data),
                "node_status": "completed" if event_type == "workflow_completed" else "failed",
                "timestamp": event.get("timestamp"),
            }
    return {"source": "status"}


def _task_event_bounds(events: list[dict]) -> tuple[str | None, str | None]:
    """Return the latest generation/edit bounds from the complete event journal."""

    start_index: int | None = None
    start_event: dict[str, Any] | None = None
    for index, event in enumerate(events):
        if event.get("event_type") in {"design_created", "edit_requested"}:
            start_index = index
            start_event = event

    if start_index is None or start_event is None:
        return None, None

    started_at = start_event.get("timestamp")
    started_at = started_at if isinstance(started_at, str) and started_at else None
    start_payload = start_event.get("payload")
    edit_id = (
        start_payload.get("edit_id")
        if start_event.get("event_type") == "edit_requested"
        and isinstance(start_payload, dict)
        and isinstance(start_payload.get("edit_id"), str)
        else None
    )
    terminal_types = {
        "workflow_completed",
        "workflow_failed",
        "edit_outcome",
        "edit_patch_applied",
        "edit_patch_rejected",
    }
    for event in events[start_index + 1 :]:
        if event.get("event_type") not in terminal_types:
            continue
        payload = event.get("payload")
        if edit_id is not None and (
            not isinstance(payload, dict) or payload.get("edit_id") != edit_id
        ):
            continue
        finished_at = event.get("timestamp")
        return started_at, finished_at if isinstance(finished_at, str) else None
    return started_at, None


def _next_operation_after_node(node: str, payload: dict) -> str:
    if payload.get("status") == "failed":
        return f"Échec pendant : {_trace_node_label(node)}."
    next_step = {
        "extract_requirements": "Recherche RAG",
        "use_validated_requirements": "Recherche RAG",
        "retrieve_rag_context": "Rappel mémoire",
        "memory_recall": "Sélection des assets",
        "select_assets": "Validation des exigences",
        "asset_fallback_handler": "Validation des exigences avec fallback asset visible",
        "validate_requirements": "Planification de la scène",
        "plan_scene": "Validation SceneSpec",
        "validate_scene": "Contrôle qualité pré-Blender",
        "scene_repair_handler": "Nouvelle validation SceneSpec",
        "pre_blender_gate": "Génération Blender",
        "generate_blender": "Contrôle qualité",
        "blender_failure_handler": "Analyse qualité après échec Blender",
        "qa_generation": "Contrôle qualité final",
        "post_blender_gate": "Écriture mémoire",
        "memory_writeback": "Finalisation du workflow",
    }.get(node)
    if next_step:
        return (
            f"Dernière étape terminée : {_trace_node_label(node)}. Prochaine étape : {next_step}."
        )
    return f"Dernière étape terminée : {_trace_node_label(node)}."


def _progress_indicator(status: dict) -> str | None:
    backend_status = status.get("status", "unknown")
    if backend_status == "pending":
        return "queued"
    if backend_status == "completed":
        return "done"
    if backend_status in {"failed", "legacy_unverified", "integrity_failed"}:
        return "failed"
    return "running"


def _progress_label(status: dict) -> str:
    backend_status = status.get("status", "unknown")
    return {
        "pending": "En attente",
        "running": "En cours",
        "completed": "Terminé",
        "failed": "Échec",
        "legacy_unverified": "Non certifié",
        "integrity_failed": "Intégrité en échec",
    }.get(backend_status, str(backend_status))


def _available_actions(status: dict, issues: list[dict]) -> list[str]:
    backend_status = status.get("status", "unknown")
    if backend_status in {"pending", "running"}:
        return ["view_timeline"]
    if backend_status == "failed":
        return ["view_issues", "view_timeline", "retry_with_changes"]
    if backend_status in {"legacy_unverified", "integrity_failed"}:
        return ["view_issues", "view_timeline", "regenerate_for_certification"]
    actions = ["open_viewer", "download_artifacts", "view_timeline", "edit_design"]
    if status.get("active_version_id"):
        actions.extend(["view_versions", "rollback_version"])
    if issues:
        actions.append("review_issues")
    return actions


_GEOMETRY_FIDELITIES = ("schematic", "technical_generic", "vendor_qualified")


def _assembly_constraint_summary_from_path(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        evidence = AssemblyConstraintEvidence.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    max_position_error_m = max(
        (measurement.position_error_m for measurement in evidence.measurements),
        default=0.0,
    )
    max_angular_error_deg = max(
        (
            max(
                measurement.normal_opposition_error_deg,
                measurement.up_alignment_error_deg,
            )
            for measurement in evidence.measurements
        ),
        default=0.0,
    )
    required_connection_count = len(
        {measurement.connection_id for measurement in evidence.measurements}
        | {connection.connection_id for connection in evidence.unevaluated_required_connections}
    )
    resolved_support_count = sum(
        frame.resolved_support is not None
        for measurement in evidence.measurements
        for frame in (measurement.source_frame, measurement.target_frame)
    )
    return {
        "status": evidence.status,
        "measurement_scope": "exported_glb_anchor_frames",
        "required_connection_count": required_connection_count,
        "measured_instance_count": evidence.measured_constraint_count,
        "resolved_support_count": resolved_support_count,
        "max_position_error_m": float(max_position_error_m),
        "max_angular_error_deg": float(max_angular_error_deg),
        "limitations": evidence.limitations,
    }


def _sector_preview_summaries_from_path(
    path: Path | None,
    *,
    workflow_id: str,
    version_id: str | None,
) -> list[dict]:
    if path is None or not path.is_file():
        return []
    try:
        evidence = SectorPreviewEvidence.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    if evidence.status != "passed":
        return []
    result: list[dict] = []
    for preview in evidence.previews:
        url = f"/designs/{workflow_id}/sector-previews/{preview.preview_id}"
        if version_id:
            url = f"{url}?version_id={version_id}"
        inspection = preview.visual_inspection
        result.append(
            {
                "sector_id": preview.sector_id,
                "preview_url": url,
                "semantic_roots": preview.semantic_roots,
                "expected_roles": preview.expected_roles,
                "exported_roles": preview.exported_roles,
                "framed_roles": preview.framed_roles,
                "post_blender_identity_verified": preview.post_blender_identity_verified,
                "visual_framing_verified": inspection.visual_quality_passed,
                "subject_bbox_height_ratio": inspection.subject_bbox_height_ratio,
                "subject_contrast_mean": inspection.subject_contrast_mean,
                "limitations": evidence.limitations,
            }
        )
    return result


def _tower_access_summary_from_path(path: Path | None, *, scene: SceneSpec | None) -> dict | None:
    """Expose tower access only after the persisted GLB proof is internally coherent."""

    if path is None or not path.is_file() or scene is None:
        return None
    try:
        evidence = TowerAccessEvidence.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if (
        evidence.scene_id != scene.scene_id
        or evidence.status != "passed"
        or not all(evidence.checks.values())
    ):
        return None
    return {
        "semantic_root": evidence.semantic_root,
        "semantic_role": "tower_access",
        "interaction_mode": "inspection_only",
        "post_blender_geometry_verified": True,
        "requested_ladder": evidence.requested_ladder,
        "rung_count": evidence.ladder.rung_count if evidence.ladder else 0,
        "platform_levels_m": [item.requested_level_m for item in evidence.platforms],
        "measurement_scope": evidence.measurement_scope,
        "limitations": evidence.limitations,
    }


def _asset_decision_summary_from_path(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _asset_decision_summary(payload)


def _asset_decision_summary(assembly_plan: object) -> dict | None:
    if hasattr(assembly_plan, "model_dump"):
        payload = assembly_plan.model_dump(mode="json")
    elif isinstance(assembly_plan, dict):
        payload = assembly_plan
    else:
        return None
    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        return None
    components: list[dict[str, Any]] = []
    for raw in raw_components:
        if not isinstance(raw, dict):
            continue
        candidates = raw.get("candidate_scores")
        candidate_count = len(candidates) if isinstance(candidates, list) else 0
        semantic_strategy = _public_asset_strategy(raw)
        raw_risks = raw.get("selection_risks")
        risks = (
            [str(value)[:600] for value in raw_risks if isinstance(value, str)][:32]
            if isinstance(raw_risks, list)
            else []
        )
        components.append(
            {
                "component_id": raw.get("role_id"),
                "role_id": raw.get("role_id"),
                "asset_id": raw.get("selected_asset_id"),
                "considered_count": candidate_count,
                "rejected_count": max(0, candidate_count - 1),
                "strategy": semantic_strategy,
                "rationale": raw.get("selection_reason"),
                "risks": risks,
                "strategy_evidence": "planned_not_execution_verified",
            }
        )
    return {
        "components": components,
        "considered_asset_count": sum(
            int(item.get("considered_count") or 0) for item in components
        ),
        "selected_asset_count": sum(1 for item in components if item.get("asset_id")),
        "decision_authority": payload.get("selection_authority"),
        "fallback_used": bool(payload.get("llm_fallback_used")),
        "fallback_reason": payload.get("llm_fallback_reason"),
    }


def _visual_review_summary(status: dict, capability: dict[str, Any]) -> dict[str, Any]:
    persisted = status.get("visual_review")
    if isinstance(persisted, dict):
        raw_status = str(persisted.get("status") or "review_required")
        public_status = (
            raw_status
            if raw_status in {"not_requested", "passed_advisory", "review_required", "failed"}
            else "review_required"
        )
        raw_findings = persisted.get("findings", [])
        return {
            "status": public_status,
            "advisory_only": True,
            "summary": str(
                persisted.get("summary") or "Une revue visuelle consultative a été publiée."
            )[:800],
            "findings": [str(value)[:800] for value in raw_findings if isinstance(value, str)][:64],
            "limitations": [
                str(value) for value in persisted.get("limitations", []) if isinstance(value, str)
            ],
        }
    return {
        "status": "not_requested",
        "advisory_only": True,
        "summary": "Aucune revue sémantique distante n'a été exécutée pour ce résultat.",
        "findings": [],
        "limitations": [
            "La revue visuelle sémantique n'a pas été exécutée pour ce résultat.",
            "Le cadrage technique ne certifie ni l'intention, ni la fidélité constructeur.",
        ],
    }


def _public_asset_strategy(component: dict[str, Any]) -> str:
    declared = component.get("semantic_strategy")
    if declared in {
        "reuse_full_design",
        "adapt_full_design",
        "reuse_component",
        "adapt_component",
        "compose_assets",
        "compose_and_generate",
        "procedural_generate",
        "clarify",
        "unsupported",
    }:
        return str(declared)
    if declared == "reuse":
        return "reuse_component"
    if declared == "adapt":
        return "adapt_component"
    if declared == "compose":
        return "compose_assets"
    generation = component.get("generation_strategy")
    if generation == "imported_glb_exact":
        return "adapt_component" if component.get("parameter_values") else "reuse_component"
    return "procedural_generate"


def _geometry_fidelity_summary_from_path(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return _geometry_fidelity_summary(payload)


def _geometry_fidelity_summary(scene_spec: object) -> dict | None:
    """Return bounded component fidelity facts without exposing the raw SceneSpec."""
    try:
        scene = SceneSpec.model_validate(scene_spec)
    except (TypeError, ValueError):
        return None

    components: list[tuple[str, RuntimeAssetMetadata]] = [("tower", scene.tower.asset_metadata)]
    for sector in scene.sectors:
        components.append(("antenna", sector.antenna_asset_metadata))
        if sector.radio_asset_id:
            components.append(("radio", sector.radio_asset_metadata))
    components.extend(
        (accessory.asset_type, accessory.asset_metadata) for accessory in scene.accessory_assets
    )
    for program in scene.geometry_programs:
        components.extend(
            (
                program.semantic_role,
                RuntimeAssetMetadata(geometry_fidelity="technical_generic"),
            )
            for _ in range(program.requested_quantity)
        )

    counts = {fidelity: 0 for fidelity in _GEOMETRY_FIDELITIES}
    roles: dict[str, list[str]] = {fidelity: [] for fidelity in _GEOMETRY_FIDELITIES}
    for role, metadata in components:
        fidelity = metadata.geometry_fidelity
        counts[fidelity] += 1
        if role not in roles[fidelity]:
            roles[fidelity].append(role)

    return {
        "component_count": len(components),
        "counts": counts,
        "roles": roles,
    }


def _geometry_program_summary_from_path(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        scene = SceneSpec.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _geometry_program_summary(scene)


def _geometry_program_summary(scene_spec: object) -> dict | None:
    try:
        scene = SceneSpec.model_validate(scene_spec)
    except (TypeError, ValueError):
        return None
    programs = [
        {
            "program_id": program.program_id,
            "semantic_role": program.semantic_role,
            "requested_quantity": program.requested_quantity,
            "origin": (
                "catalog_asset"
                if any(node.kind == "exact_asset" for node in program.nodes)
                else "geometry_program"
            ),
            "node_count": len(program.nodes),
            "authorship": program.authorship,
            "generator_provider": program.generator_provider,
            "generator_model": program.generator_model,
            "structured_output_mode": program.structured_output_mode,
            "source_prompt_sha256": program.source_prompt_sha256,
            "source_description": program.source_description,
            "source_description_origin": program.source_description_origin,
            "placement_context": program.placement_context,
            "maximum_dimensions_m": (
                program.maximum_dimensions_m.model_dump(mode="json")
                if program.maximum_dimensions_m is not None
                else None
            ),
            "limitations": program.limitations,
            "deterministic_adjustments": program.deterministic_adjustments,
        }
        for program in scene.geometry_programs
    ]
    return {
        "program_count": len(programs),
        "generated_component_count": sum(
            program["requested_quantity"]
            for program in programs
            if program["origin"] == "geometry_program"
        ),
        "reused_component_count": sum(
            program["requested_quantity"]
            for program in programs
            if program["origin"] == "catalog_asset"
        ),
        "total_node_count": sum(program["node_count"] for program in programs),
        "repaired_program_count": sum(
            program["structured_output_mode"] == "json_object_repaired" for program in programs
        ),
        "programs": programs,
    }


def _artifact_by_name(artifacts: list[dict], name: str) -> dict | None:
    for artifact in artifacts:
        if artifact.get("name") == name:
            return artifact
    return None


def _available_artifact_url(artifact: dict | None) -> str | None:
    if artifact is None or artifact.get("available") is not True:
        return None
    url = artifact.get("url")
    return str(url) if isinstance(url, str) and url else None


def _qa_summary(status: dict) -> str:
    qa_score = status.get("qa_score")
    if qa_score is None:
        return "Qualité non encore évaluée."
    if qa_score >= 0.95:
        return f"Qualité excellente ({qa_score:.0%})."
    if qa_score >= 0.8:
        return f"Qualité acceptable ({qa_score:.0%}) avec quelques avertissements."
    if qa_score >= 0.5:
        return f"Qualité limitée ({qa_score:.0%}). Vérifiez les problèmes signalés."
    return f"Qualité insuffisante ({qa_score:.0%}). Un correctif est probablement nécessaire."


def _viewer_qa_summary(status: dict) -> dict:
    geometry = status.get("geometry_validation_summary") or {}
    glb = status.get("glb_inspection_summary") or {}
    preview = status.get("preview_inspection_summary") or {}
    if not isinstance(geometry, dict):
        geometry = {}
    if not isinstance(glb, dict):
        glb = {}
    if not isinstance(preview, dict):
        preview = {}
    checks = geometry.get("checks") if isinstance(geometry.get("checks"), dict) else {}
    checks_passed = sorted(name for name, passed in checks.items() if passed is True)
    checks_failed = sorted(name for name, passed in checks.items() if passed is False)
    qa_executed = bool(geometry or glb or preview) or any(
        status.get(field) is not None for field in ("mesh_qa_level", "mesh_qa_passed", "qa_score")
    )
    if not qa_executed:
        qa_status = "not_started"
    elif status.get("mesh_qa_passed") is False or checks_failed:
        qa_status = "failed"
    elif (
        status.get("mesh_qa_passed") is True
        and status.get("completion_certificate_status") == "issued"
    ):
        qa_status = "passed"
    else:
        qa_status = "incomplete"
    warnings = [
        item.get("code") or item.get("message")
        for item in status.get("warnings", [])
        if isinstance(item, dict)
    ]
    errors = [
        item.get("code") or item.get("message")
        for item in status.get("errors", [])
        if isinstance(item, dict)
    ]
    return {
        "qa_status": qa_status,
        "qa_executed": qa_executed,
        "blocked_before_qa": (
            not qa_executed
            and status.get("status") in {"failed", "legacy_unverified", "integrity_failed"}
        ),
        "mesh_qa_level": status.get("mesh_qa_level"),
        "mesh_qa_passed": status.get("mesh_qa_passed"),
        "qa_score": status.get("qa_score"),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "warnings": [warning for warning in warnings if warning],
        "errors": [error for error in errors if error] if qa_executed else [],
        "upstream_errors": [] if qa_executed else [error for error in errors if error],
        "limitations": _collect_limitations(status),
        "geometry_source": status.get("geometry_source"),
        "generation_strategy": status.get("generation_strategy"),
        "object_counts": geometry.get("object_counts"),
        "missing_objects": geometry.get("missing_objects"),
        "glb_parse_structural": glb.get("structural_qa_passed"),
        "preview_pixel_framing_qa": preview.get("inspection_mode") == "png_parse",
        "preview_subject_framing_valid": preview.get("subject_framing_valid"),
        "preview_subject_bbox_width_ratio": preview.get("subject_bbox_width_ratio"),
        "preview_subject_bbox_height_ratio": preview.get("subject_bbox_height_ratio"),
        "preview_subject_center_x_ratio": preview.get("subject_center_x_ratio"),
        "preview_subject_min_edge_margin_ratio": preview.get("subject_min_edge_margin_ratio"),
        "preview_subject_touches_frame": preview.get("subject_touches_frame"),
    }


def _asset_quality_summary(status: dict) -> str | None:
    asset_imports = status.get("asset_imports") or []
    if not asset_imports:
        asset_summary = status.get("asset_import_summary")
        if asset_summary:
            fallback = asset_summary.get("fallback_used", False)
            source = asset_summary.get("source", "unknown")
            if fallback:
                return f"Asset source : {source} (fallback utilisé)"
            return f"Asset source : {source}"
        return None
    fallback_count = sum(1 for a in asset_imports if a.get("fallback_used"))
    procedural_count = sum(
        1
        for a in asset_imports
        if a.get("import_mode") == "procedural_fallback"
        or a.get("effective_generation_mode") == "procedural_fallback"
    )
    missing_count = sum(
        1
        for a in asset_imports
        if a.get("import_mode") == "missing_file" or a.get("asset_file_exists") is False
    )
    internal_count = sum(
        1
        for a in asset_imports
        if str(a.get("asset_source") or a.get("source", "")).startswith("internal")
    )
    fallback_count = max(fallback_count, procedural_count)
    if fallback_count:
        return (
            f"{fallback_count} asset(s) en fallback procédural, "
            f"{missing_count} fichier(s) GLB manquant(s), {internal_count} asset(s) interne(s)."
        )
    imported_count = sum(
        1
        for asset in asset_imports
        if asset.get("import_mode")
        in {"imported_glb", "imported_glb_exact", "stretched_imported_glb"}
    )
    parametric_count = sum(
        1
        for asset in asset_imports
        if asset.get("import_mode") in {"parametric_generated", "internal_project_generated"}
    )
    return (
        f"{imported_count} mesh(es) GLB importé(s), "
        f"{parametric_count} composant(s) généré(s) par profil contrôlé."
    )


def _collect_limitations(status: dict) -> list[str]:
    limitations = []
    coverage_gaps = [
        COVERAGE_GAP_LABELS.get(str(gap), str(gap))
        for gap in status.get("certificate_coverage_gaps") or []
    ]
    if coverage_gaps:
        limitations.append(
            "Version vérifiée selon un contrat de certification antérieur "
            f"({status.get('certificate_contract_version') or 'inconnu'}) : "
            f"non couvert par cette version — {', '.join(coverage_gaps)}. "
            "Régénérez le design pour obtenir ces vérifications."
        )
    if status.get("completion_certificate_status") != "issued":
        limitations.append(
            "La preuve de complétion n'est pas vérifiable : ce résultat n'est pas certifié "
            "et ses artefacts ne sont pas publiés."
        )
    if status.get("blender_available") is False:
        limitations.append(
            "Blender n'est pas installé : le modèle 3D est un fallback, pas un vrai GLB."
        )
    if status.get("llm_fallback_used"):
        limitations.append("L'extraction a utilisé le fallback déterministe, pas le LLM.")
    generation_mode = status.get("generation_mode")
    if generation_mode and str(generation_mode).startswith("fallback"):
        limitations.append(f"Le mode de génération est un fallback ({generation_mode}).")
    if generation_mode and generation_mode != "real_blender":
        limitations.append(
            "Le résultat n'est pas product-grade tant que la génération n'est pas real_blender."
        )
    generation_strategy = status.get("generation_strategy")
    if generation_strategy == "stretched_imported_glb":
        limitations.append(
            "Un asset GLB a été étiré pour correspondre aux dimensions demandées ; "
            "la géométrie peut ne pas correspondre à un design d'ingénierie."
        )
    if generation_strategy == "procedural_fallback":
        limitations.append("La scène contient des géométries procédurales de remplacement.")
    mesh_qa_level = status.get("mesh_qa_level")
    if mesh_qa_level == "metadata_only":
        limitations.append("La QA géométrique ne vérifie que les métadonnées, pas les vertices.")
    if mesh_qa_level == "mesh_level_basic":
        limitations.append(
            "La QA géométrique est mesh_level_basic: elle vérifie structure, objets et dimensions "
            "principales, pas une conformité RF/structurelle vendor-grade."
        )
    if mesh_qa_level == "mesh_level_transform_basic":
        limitations.append(
            "La QA géométrique est mesh_level_transform_basic: elle lit des transforms GLB de base "
            "et une hauteur HBA approximative, sans collision/RF/vendor-grade."
        )
    if mesh_qa_level == "mesh_level_spatial_basic":
        limitations.append(
            "La QA mesh_level_spatial_basic contrôle les transforms RF et les recouvrements AABB "
            "des équipements primaires à partir des vertices GLB; ce n'est pas une collision "
            "triangle/BVH ni une certification d'ingénierie."
        )
    asset_summary = status.get("asset_import_summary") or {}
    if asset_summary.get("procedural_fallback_count", 0):
        limitations.append(
            "Au moins un asset a été remplacé par une géométrie procédurale faute de GLB réel."
        )
    return limitations


def _next_recommended_action(status: dict, issues: list[dict]) -> str:
    backend_status = status.get("status", "unknown")
    if backend_status == "pending":
        return "Patientez pendant que le design démarre."
    if backend_status == "failed":
        return "Relisez le prompt ou le document pack, corrigez les problèmes, puis relancez."
    if backend_status in {"legacy_unverified", "integrity_failed"}:
        return (
            "Les fichiers ont été mis en quarantaine. Relancez une génération pour produire "
            "un résultat certifié et vérifiable."
        )
    if backend_status == "completed":
        if issues:
            return "Le design est prêt, mais vérifiez les avertissements avant de valider."
        return "Le design est prêt. Vous pouvez l'inspecter, l'éditer ou télécharger les artefacts."
    return "Le traitement est en cours ; patientez ou consultez l'opération actuelle."


def _collect_user_issues(status: dict, events: list[dict] | None = None) -> list[dict]:
    issues: list[dict] = []
    for item in status.get("warnings", []):
        issue = _warning_to_user_issue(item)
        if issue:
            issues.append(issue)
    for item in status.get("errors", []):
        issue = _warning_to_user_issue(item)
        if issue:
            issue["severity"] = "error"
            issues.append(issue)
    has_explicit_user_error = any(issue.get("severity") == "error" for issue in issues)

    # Add inferred limitations as issues when no explicit warning exists
    if status.get("blender_available") is False and not any(
        i.get("technical_code") == "BLENDER_NOT_AVAILABLE" for i in issues
    ):
        issues.append(
            {
                "title": "Blender non disponible",
                "severity": "warning",
                "impact": (
                    "Le modèle 3D généré est un fallback texte/procédural, pas un vrai GLB Blender."
                ),
                "recommended_action": "Installez Blender 4.5+ pour obtenir un modèle 3D réel.",
                "technical_code": "BLENDER_NOT_AVAILABLE_INFERRED",
            }
        )
    if status.get("llm_fallback_used") and not any(
        i.get("technical_code") == "LLM_FALLBACK_USED" for i in issues
    ):
        reason = status.get("llm_fallback_reason")
        issues.append(
            {
                "title": "Extraction déterministe",
                "severity": "info",
                "impact": (
                    "Le LLM n'a pas été utilisé ; l'extraction repose sur des règles fixes."
                    + (f" Raison: {reason}." if reason else "")
                ),
                "recommended_action": (
                    "Configurez GROQ_API_KEY pour activer l'extraction intelligente."
                ),
                "technical_code": "LLM_FALLBACK_USED_INFERRED",
            }
        )
    generation_mode = status.get("generation_mode")
    if (
        generation_mode
        and generation_mode != "real_blender"
        and not any(
            i.get("technical_code") == "GENERATION_NOT_PRODUCT_GRADE_INFERRED" for i in issues
        )
    ):
        issues.append(
            {
                "title": "Génération 3D non product-grade",
                "severity": "warning",
                "impact": (
                    f"Le mode de génération est {generation_mode}; le résultat doit être "
                    "présenté comme dégradé."
                ),
                "recommended_action": (
                    "Corrigez Blender/assets puis relancez avant validation produit."
                ),
                "technical_code": "GENERATION_NOT_PRODUCT_GRADE_INFERRED",
            }
        )
    is_basic_mesh_qa = status.get("mesh_qa_level") in {
        "mesh_level_basic",
        "mesh_level_transform_basic",
        "mesh_level_spatial_basic",
    }
    if is_basic_mesh_qa and not any(
        i.get("technical_code") == "MESH_QA_BASIC_INFERRED" for i in issues
    ):
        mesh_level = status.get("mesh_qa_level")
        spatial = mesh_level == "mesh_level_spatial_basic"
        issues.append(
            {
                "title": "QA spatiale bornée" if spatial else "QA géométrique basique",
                "severity": "info",
                "impact": (
                    (
                        "La QA contrôle les transforms RF et les interférences AABB des "
                        "équipements primaires, mais pas les collisions triangle/BVH."
                    )
                    if spatial
                    else (
                        f"La QA {mesh_level} confirme des propriétés structurales de base, "
                        "pas une validation ingénierie complète."
                    )
                ),
                "recommended_action": (
                    "Afficher cette limite dans le drawer QA et ne pas annoncer une QA avancée."
                ),
                "technical_code": "MESH_QA_BASIC_INFERRED",
            }
        )
    asset_summary = status.get("asset_import_summary") or {}
    explicit_procedural_fallback_codes = {
        "ASSET_IMPORT_PROCEDURAL_FALLBACK",
        "ASSET_IMPORT_PROCEDURAL_FALLBACK_USED",
        "ASSET_IMPORT_PROCEDURAL_FALLBACK_INFERRED",
    }
    if asset_summary.get("procedural_fallback_count", 0) and not any(
        i.get("technical_code") in explicit_procedural_fallback_codes for i in issues
    ):
        issues.append(
            {
                "title": "Asset remplacé par une géométrie procédurale",
                "severity": "warning",
                "impact": (
                    "Un fichier GLB attendu manque ; Blender a créé une forme procédurale "
                    "à la place d'un asset réel."
                ),
                "recommended_action": (
                    "Ajouter le GLB manquant ou choisir un asset réellement importable "
                    "avant validation produit."
                ),
                "technical_code": "ASSET_IMPORT_PROCEDURAL_FALLBACK_INFERRED",
            }
        )
    planning_summary = status.get("rag_planning_summary") or {}
    if planning_summary.get("decision_fallback_used") and not any(
        i.get("technical_code") == "PLANNING_DECISION_FALLBACK_INFERRED" for i in issues
    ):
        reason = planning_summary.get("decision_fallback_reason") or "provider_unavailable"
        issues.append(
            {
                "title": "Décision de planification en repli",
                "severity": "info",
                "impact": (
                    "GPT-OSS n'a pas arbitré les candidats RAG. Le backend a conservé "
                    f"les valeurs déjà validées ({reason})."
                ),
                "recommended_action": (
                    "Le design reste déterministe; vérifiez les suggestions RAG si vous "
                    "souhaitez les appliquer explicitement."
                ),
                "technical_code": "PLANNING_DECISION_FALLBACK_INFERRED",
            }
        )
    # Runtime nodes stay available in the timeline. When the workflow already
    # published a product-level error, replaying every failed implementation
    # node as another user issue only duplicates the same root cause.
    if not has_explicit_user_error:
        issues.extend(_collect_runtime_event_issues(events or [], status))
    return _deduplicate_user_issues(issues)


def _deduplicate_user_issues(issues: list[dict]) -> list[dict]:
    """Collapse repeated sector-level signals into one actionable product issue."""
    deduplicated: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        technical_code = str(issue.get("technical_code") or issue.get("title") or "")
        if technical_code in {
            "ASSET_IMPORT_PROCEDURAL_FALLBACK",
            "ASSET_IMPORT_PROCEDURAL_FALLBACK_USED",
            "ASSET_IMPORT_PROCEDURAL_FALLBACK_INFERRED",
        }:
            technical_code = "ASSET_IMPORT_PROCEDURAL_FALLBACK"
        key = (
            technical_code,
            str(issue.get("severity") or "warning"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(issue)
    return deduplicated


def _collect_runtime_event_issues(events: list[dict], status: dict) -> list[dict]:
    issues: list[dict] = []
    failed_nodes: list[str] = []
    seen: set[str] = set()
    workflow_status = status.get("status", "unknown")
    if workflow_status == "completed" and not status.get("active_operation"):
        return issues
    for event in events:
        if event.get("event_type") != "node_failed":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        node = str(payload.get("node") or "unknown_node")
        if node in seen:
            continue
        seen.add(node)
        failed_nodes.append(node)

    # Failure-handler nodes describe deterministic routing after the primary
    # failure. They belong to the technical timeline, not beside the primary
    # product issue as another apparent root cause.
    handler_nodes = {
        "blender_failure_handler",
        "geometry_program_failure_handler",
        "qa_failure_handler",
        "quality_gate_failure_handler",
        "scene_repair_handler",
    }
    primary_nodes = [node for node in failed_nodes if node not in handler_nodes]
    user_issue_nodes = primary_nodes or failed_nodes[:1]
    for node in user_issue_nodes:
        issues.append(
            {
                "title": f"{_trace_node_label(node)} en mode dégradé",
                "severity": "error" if workflow_status == "failed" else "warning",
                "impact": _runtime_node_user_impact(node),
                "recommended_action": _runtime_node_recommended_action(node),
                "technical_code": f"RUNTIME_NODE_FAILED:{node}",
            }
        )
    return issues


def _runtime_node_user_impact(node: str) -> str:
    return {
        "retrieve_rag_context": (
            "Le contexte documentaire n'a pas pu être récupéré pour cette opération."
        ),
        "generate_blender": (
            "Blender n'a pas produit les livrables 3D requis pour cette opération."
        ),
        "blender_failure_handler": (
            "La récupération après l'échec Blender n'a pas permis de produire un résultat valide."
        ),
        "qa_generation": ("Les contrôles du résultat 3D n'ont pas validé cette opération."),
        "qa_failure_handler": ("Le résultat reste refusé après l'échec des contrôles qualité."),
        "plan_generated_geometry": (
            "Le spécialiste géométrique n'a pas produit un programme valide."
        ),
        "geometry_program_failure_handler": (
            "La demande hors catalogue a été bloquée avant Blender."
        ),
    }.get(node, "Une étape de cette opération n'a pas abouti.")


def _runtime_node_recommended_action(node: str) -> str:
    if node == "retrieve_rag_context":
        return (
            "Vérifiez Qdrant ou utilisez un serveur Qdrant externe si plusieurs processus "
            "accèdent au stockage local."
        )
    if node == "generate_blender":
        return "Vérifiez Blender, les assets et les artefacts avant de relancer."
    if node == "qa_generation":
        return "Ouvrez le résumé QA et corrigez les erreurs bloquantes avant validation."
    return "Consultez la timeline et les rapports techniques pour corriger cette étape."


_KNOWN_ISSUE_MAPPINGS: dict[str, dict[str, Any]] = {
    "WORKFLOW_INTERRUPTED": {
        "title": "Service interrompu pendant la génération",
        "impact": (
            "Le service local s'est interrompu avant la fin. Votre demande est conservée, "
            "mais aucun nouveau modèle validé n'a été publié."
        ),
        "recommended_action": (
            "Relancez cette demande lorsque le studio est disponible ou reprenez-la dans "
            "une nouvelle conversation."
        ),
    },
    "GEOMETRY_PROGRAM_GENERATION_FAILED": {
        "title": "Composant personnalisé non généré",
        "impact": (
            "La demande a été bloquée avant Blender : aucun nouveau modèle ni contrôle 3D "
            "n'a remplacé votre dernière version validée."
        ),
        "recommended_action": ("Corrigez la description du composant puis relancez la génération."),
    },
    "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR": {
        "title": "Asset interne minimal",
        "impact": (
            "La chaîne de génération est vérifiée, mais cet équipement reste une géométrie "
            "interne générique sans fidélité constructeur."
        ),
        "recommended_action": (
            "Vérifier le niveau de fidélité déclaré et utiliser un asset constructeur qualifié "
            "si une représentation exacte est requise."
        ),
    },
    "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE": {
        "title": "Asset interne minimal",
        "impact": (
            "La chaîne de génération est vérifiée, mais cet équipement reste une géométrie "
            "interne générique sans fidélité constructeur."
        ),
        "recommended_action": (
            "Vérifier le niveau de fidélité déclaré et utiliser un asset constructeur qualifié "
            "si une représentation exacte est requise."
        ),
    },
    "ASSET_IMPORT_INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE": {
        "title": "Asset interne nettoyé",
        "impact": (
            "L'asset est importable mais reste une ressource interne, pas un modèle constructeur."
        ),
        "recommended_action": "Remplacer par un asset vendor-grade avant livraison finale.",
    },
    "ASSET_IMPORT_INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE": {
        "title": "Composants internes non constructeur",
        "impact": (
            "Certains supports ou équipements proviennent de la bibliothèque interne et "
            "représentent leur fonction, sans fidélité à un modèle constructeur."
        ),
        "recommended_action": (
            "Inspecter la provenance par composant et remplacer les éléments concernés "
            "si une fidélité constructeur est exigée."
        ),
    },
    "ASSET_IMPORT_CC_BY_ASSET_NOT_VENDOR_GRADE": {
        "title": "Asset CC-BY non vendor-grade",
        "impact": "L'asset est réel/importé mais sa qualité et sa licence doivent rester visibles.",
        "recommended_action": (
            "Conserver l'attribution et prévoir un asset constructeur si nécessaire."
        ),
    },
    "ASSET_IMPORT_ATTRIBUTION_REQUIRED": {
        "title": "Attribution requise",
        "impact": "Un asset utilisé impose une attribution de licence.",
        "recommended_action": "Afficher l'attribution dans le rapport et les exports.",
    },
    "ASSET_IMPORT_ASSET_FILE_MISSING": {
        "title": "Fichier GLB manquant",
        "impact": "Un asset référencé par manifest n'a pas de fichier GLB local.",
        "recommended_action": (
            "Ajouter le fichier GLB ou refuser cet asset pour les workflows qualité."
        ),
    },
    "ASSET_IMPORT_PROCEDURAL_FALLBACK": {
        "title": "Fallback procédural d'asset",
        "impact": "La scène contient une géométrie générée à la place d'un asset GLB réel.",
        "recommended_action": (
            "Ajouter le GLB manquant avant de considérer le résultat prêt produit."
        ),
    },
    "ASSET_IMPORT_PROCEDURAL_FALLBACK_USED": {
        "title": "Composant généré procéduralement",
        "impact": (
            "Un composant sans asset GLB qualifié a été produit par le builder "
            "procédural déterministe."
        ),
        "recommended_action": (
            "Conserver cette provenance visible et ajouter un asset réel si une géométrie "
            "constructeur est requise."
        ),
    },
    "BLENDER_FALLBACK_USED": {
        "title": "Fallback Blender utilisé",
        "impact": "La génération n'est pas un vrai rendu Blender valide.",
        "recommended_action": "Corrigez Blender ou relancez avec un environnement valide.",
    },
    "FALLBACK_DETERMINISTIC_EXTRACTION_USED": {
        "title": "Extraction déterministe utilisée",
        "impact": "Les exigences ont été extraites avec des règles fixes, pas par LLM.",
        "recommended_action": "Vérifiez les champs clés et corrigez si nécessaire.",
    },
    "BLENDER_NOT_AVAILABLE": {
        "title": "Blender non disponible",
        "impact": "Le modèle 3D généré est un fallback, pas un vrai GLB Blender.",
        "recommended_action": "Installez Blender 4.5+ pour obtenir un modèle 3D réel.",
    },
    "QA_FALLBACK_ARTIFACT_APPROVED": {
        "title": "QA a validé un artefact fallback",
        "impact": "Le contrôle qualité a accepté un artefact qui n'est pas un vrai rendu 3D.",
        "recommended_action": "Corrigez le pipeline QA ou installez Blender.",
    },
    "DEFAULT_SECTOR_COUNT_USED": {
        "title": "Nombre de secteurs par défaut",
        "impact": (
            "Le nombre de secteurs n'a pas été précisé ; une valeur par défaut a été utilisée."
        ),
        "recommended_action": "Précisez le nombre de secteurs dans le brief.",
    },
    "DEFAULT_TOWER_HEIGHT_USED": {
        "title": "Hauteur de pylône par défaut",
        "impact": (
            "La hauteur de pylône n'a pas été précisée ; une valeur par défaut a été utilisée."
        ),
        "recommended_action": "Précisez la hauteur de pylône dans le brief.",
    },
    "DEFAULT_AZIMUTHS_USED": {
        "title": "Azimuts par défaut",
        "impact": "Les azimuts n'ont pas été précisés ; une valeur par défaut a été utilisée.",
        "recommended_action": "Précisez les azimuts dans le brief.",
    },
    "DEFAULT_ANTENNA_HEIGHT_USED": {
        "title": "Hauteur d'antenne par défaut",
        "impact": "La hauteur d'installation des antennes n'a pas été précisée.",
        "recommended_action": "Précisez la hauteur d'antenne dans le brief.",
    },
    "LLM_FIELD_REPAIRED": {
        "title": "Champ IA réparé par le backend",
        "impact": (
            "GPT-OSS a omis ou fragilisé un champ 3D supporté; le backend a restauré "
            "la valeur déterministe avant de générer la scène."
        ),
        "recommended_action": (
            "Afficher cette réparation comme signal de prudence et vérifier le SceneSpec."
        ),
    },
    "RF_BEAMWIDTH_NARROW": {
        "title": "Beamwidth à vérifier",
        "impact": (
            "Le beamwidth extrait ou déduit peut être trop étroit pour couvrir trois secteurs."
        ),
        "recommended_action": (
            "Vérifier la valeur RF dans le cahier de charge ou demander une correction."
        ),
    },
    "TOWER_PLATFORM_RECOMMENDED": {
        "title": "Plateforme pylône recommandée",
        "impact": (
            "Le site contient plusieurs équipements en hauteur; une plateforme ou un support "
            "technique peut être nécessaire pour rendre l'installation réaliste."
        ),
        "recommended_action": (
            "Ajouter une plateforme/support si le cahier de charge le confirme."
        ),
    },
    "TOWER_AVIATION_MARKING_REVIEW_REQUIRED": {
        "title": "Balisage aviation à vérifier",
        "impact": (
            "La hauteur a déclenché un contrôle préliminaire, mais elle ne suffit pas à "
            "déterminer seule si un balisage est légalement requis."
        ),
        "recommended_action": (
            "Confirmer la réglementation nationale, la proximité aéronautique et la décision "
            "de l'autorité compétente avant de figer le design."
        ),
    },
    # Compatibility for statuses persisted before the warning was renamed.
    "TOWER_AVIATION_LIGHT_RECOMMENDED": {
        "title": "Balisage aviation à vérifier",
        "impact": (
            "Un ancien contrôle de hauteur a signalé ce point; il ne constitue pas une "
            "conclusion réglementaire."
        ),
        "recommended_action": (
            "Confirmer la réglementation nationale, la proximité aéronautique et la décision "
            "de l'autorité compétente avant de figer le design."
        ),
    },
}


def _warning_to_user_issue(item: dict) -> dict | None:
    code = item.get("code", "")
    message = item.get("message", "")
    severity = item.get("severity", "warning")
    mapping = _KNOWN_ISSUE_MAPPINGS.get(code)
    if mapping:
        return {
            "title": mapping["title"],
            "severity": severity,
            "impact": mapping["impact"],
            "recommended_action": mapping["recommended_action"],
            "technical_code": code,
        }
    if isinstance(code, str) and code.startswith("GEOMETRY_VALIDATION_"):
        return {
            "title": "Contrôle géométrique refusé",
            "severity": severity,
            "impact": (
                "Blender a produit le modèle, mais une règle obligatoire de placement ou "
                "de géométrie a échoué. Ce résultat n'a pas été publié et la dernière "
                "version certifiée reste protégée."
            ),
            "recommended_action": (
                "Corrigez le placement ou les dimensions signalés dans Vérification, "
                "puis relancez la demande."
            ),
            "technical_code": "GEOMETRY_VALIDATION_FAILED",
        }
    # Generic fallback for unknown warnings
    return {
        "title": message.split(".")[0] if message else code,
        "severity": severity,
        "impact": message or "Un avertissement technique a été signalé.",
        "recommended_action": "Consultez le rapport technique pour plus de détails.",
        "technical_code": code,
    }


def _events_to_timeline(events: list[dict], status: dict) -> list[dict]:
    steps = []
    step_index: dict[str, int] = {}
    for index, event in enumerate(events):
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        data = payload if isinstance(payload, dict) else {}
        step_name = _event_step_name(event_type, data)
        human = _event_to_human(event_type, data)
        event_status = _event_status(
            event_type,
            status.get("status", "unknown"),
            data=data,
            index=index,
            total=len(events),
        )
        node = data.get("node") if isinstance(data.get("node"), str) else step_name
        artifact_refs = (
            data.get("artifact_refs") if isinstance(data.get("artifact_refs"), list) else []
        )
        row = {
            "step": step_name,
            "node": node,
            "label": human,
            "human_label": data.get("human_label") or human,
            "progress_message": data.get("progress_message") or human,
            "phase": data.get("phase") or _phase_for_step(step_name),
            "status": event_status,
            "timestamp": event.get("timestamp"),
            "started_at": event.get("timestamp") if event_type == "node_started" else None,
            "completed_at": event.get("timestamp")
            if event_status in {"completed", "failed", "skipped"}
            else None,
            "duration_ms": data.get("duration_ms"),
            "warnings_count": len(data.get("warnings") or []),
            "errors_count": len(data.get("errors") or []),
            "artifact_refs": [str(ref) for ref in artifact_refs],
            "human_readable": human,
        }
        if event_type == "node_started":
            step_index[step_name] = len(steps)
            steps.append(row)
            continue
        if (
            event_type in {"node_completed", "node_failed", "node_skipped"}
            and step_name in step_index
        ):
            existing = steps[step_index[step_name]]
            existing.update(
                {
                    "label": human,
                    "human_label": data.get("human_label") or existing.get("human_label"),
                    "progress_message": data.get("progress_message") or human,
                    "status": event_status,
                    "completed_at": event.get("timestamp"),
                    "duration_ms": data.get("duration_ms"),
                    "warnings_count": len(data.get("warnings") or []),
                    "errors_count": len(data.get("errors") or []),
                    "human_readable": human,
                }
            )
            continue
        steps.append(row)
    terminal_step = None
    if steps and steps[-1]["step"] in {"workflow_completed", "workflow_failed"}:
        terminal_step = steps.pop()
    steps.extend(_trace_to_timeline(status, existing_steps={step["step"] for step in steps}))
    if terminal_step:
        steps.append(terminal_step)
    # Ensure terminal state is represented
    if not steps or steps[-1]["step"] not in {"workflow_completed", "workflow_failed"}:
        backend_status = status.get("status", "unknown")
        if backend_status == "completed":
            steps.append(
                {
                    "step": "workflow_completed",
                    "node": "workflow",
                    "label": "Workflow terminé",
                    "human_label": "Workflow terminé",
                    "progress_message": "Le design est prêt pour inspection 3D.",
                    "phase": "workflow",
                    "status": "completed",
                    "timestamp": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": status.get("total_workflow_duration_ms")
                    or status.get("total_duration_ms"),
                    "warnings_count": len(status.get("warnings") or []),
                    "errors_count": len(status.get("errors") or []),
                    "artifact_refs": [],
                    "human_readable": "Le workflow s'est terminé avec succès.",
                }
            )
        elif backend_status == "failed":
            steps.append(
                {
                    "step": "workflow_failed",
                    "node": "workflow",
                    "label": "Workflow en échec",
                    "human_label": "Workflow en échec",
                    "progress_message": "Le design n'a pas pu être terminé.",
                    "phase": "workflow",
                    "status": "failed",
                    "timestamp": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": status.get("total_workflow_duration_ms")
                    or status.get("total_duration_ms"),
                    "warnings_count": len(status.get("warnings") or []),
                    "errors_count": len(status.get("errors") or []),
                    "artifact_refs": [],
                    "human_readable": "Le workflow a échoué.",
                }
            )
    return steps


def _event_status(
    event_type: str,
    workflow_status: str,
    *,
    data: dict,
    index: int,
    total: int,
) -> str:
    if event_type in {"node_failed", "edit_patch_rejected", "blender_failed", "qa_failed"}:
        return "failed"
    if event_type == "node_skipped":
        return "skipped"
    if event_type == "node_started":
        return "running"
    if event_type == "node_completed":
        return "completed"
    terminal = {"workflow_completed": "completed", "workflow_failed": "failed"}
    if event_type in terminal:
        return terminal[event_type]
    payload_status = data.get("status")
    if payload_status in {"failed", "rejected", "error"}:
        return "failed"
    if payload_status == "skipped":
        return "skipped"
    if payload_status in {"running", "pending"}:
        return "running"
    if payload_status in {"completed", "applied", "ready"}:
        return "completed"
    if workflow_status == "running" and index == total - 1:
        return "running"
    if workflow_status in {"completed", "failed"}:
        return "completed"
    return "running"


def _event_to_human(event_type: str, data: dict) -> str:
    if event_type in {"node_started", "node_completed", "node_failed", "node_skipped"}:
        node = str(data.get("node") or "workflow")
        label = _trace_node_to_human(node, data)
        if event_type == "node_started":
            return str(data.get("progress_message") or f"{label} démarré")
        if event_type == "node_failed":
            return f"{label} en échec"
        if event_type == "node_skipped":
            return f"{label} ignoré"
        return label
    mapping: dict[str, str] = {
        "design_created": "Design créé",
        "blender_started": "Génération 3D démarrée",
        "validated_requirements_received": "Exigences validées reçues",
        "workflow_completed": "Workflow terminé",
        "workflow_failed": "Workflow en échec",
        "edit_patch_created": "Patch d'édition créé",
        "edit_patch_rejected": "Patch d'édition rejeté",
        "edit_patch_applied": "Patch d'édition appliqué",
        "version_created": "Nouvelle version créée",
        "version_rolled_back": "Version restaurée",
        "blender_completed": "Génération 3D terminée",
        "blender_failed": "Génération 3D en échec",
        "qa_completed": "Contrôle qualité terminé",
        "qa_failed": "Contrôle qualité en échec",
        "artifact_ready": "Artefacts viewer prêts",
        "user_issue_created": "Issue utilisateur créée",
    }
    human = mapping.get(event_type, event_type.replace("_", " ").capitalize())
    if event_type == "workflow_failed" and data.get("error"):
        return f"{human} : {data['error']}"
    return human


def _event_step_name(event_type: str, payload: dict) -> str:
    if event_type in {"node_started", "node_completed", "node_failed", "node_skipped"}:
        node = payload.get("node")
        if isinstance(node, str) and node:
            return node
    return event_type


def _trace_to_timeline(status: dict, *, existing_steps: set[str]) -> list[dict]:
    trace_path = status.get("trace_path")
    if not trace_path:
        return []
    path = Path(trace_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    trace_steps = payload.get("steps", [])
    if not isinstance(trace_steps, list):
        return []
    timeline = []
    for trace in trace_steps:
        if not isinstance(trace, dict):
            continue
        node = trace.get("node")
        if not isinstance(node, str) or node in existing_steps:
            continue
        timeline.append(
            {
                "step": node,
                "node": node,
                "label": _trace_node_to_human(node, trace),
                "human_label": _trace_node_label(node),
                "progress_message": _trace_node_to_human(node, trace),
                "phase": trace.get("phase") or _phase_for_step(node),
                "status": _trace_status(trace),
                "timestamp": None,
                "started_at": None,
                "completed_at": None,
                "duration_ms": trace.get("duration_ms"),
                "warnings_count": len(trace.get("warnings") or []),
                "errors_count": len(trace.get("errors") or []),
                "artifact_refs": [],
                "human_readable": _trace_node_to_human(node, trace),
            }
        )
    return timeline


def _phase_for_step(step: str) -> str | None:
    return {
        "design_created": "workflow",
        "extract_requirements": "requirements",
        "use_validated_requirements": "requirements",
        "retrieve_rag_context": "rag",
        "memory_recall": "memory",
        "select_assets": "assets",
        "asset_fallback_handler": "assets",
        "validate_requirements": "requirements",
        "plan_scene": "scene",
        "validate_scene": "scene",
        "scene_repair_handler": "scene",
        "pre_blender_gate": "quality_gate",
        "generate_blender": "blender",
        "blender_failure_handler": "blender",
        "qa_generation": "qa",
        "post_blender_gate": "quality_gate",
        "qa_failure_handler": "qa",
        "memory_writeback": "memory",
        "workflow_completed": "workflow",
        "workflow_failed": "workflow",
        "artifact_ready": "viewer",
        "qa_completed": "qa",
        "qa_failed": "qa",
        "user_issue_created": "issues",
        "edit_patch_created": "edit",
        "edit_patch_rejected": "edit",
        "edit_patch_applied": "edit",
        "version_created": "versioning",
        "version_rolled_back": "versioning",
    }.get(step)


def _trace_status(trace: dict) -> str:
    status = trace.get("status")
    if status in {"passed", "completed"}:
        return "completed"
    if status == "failed":
        return "failed"
    if status == "skipped":
        return "skipped"
    return "completed"


def _trace_node_to_human(node: str, trace: dict) -> str:
    label = _trace_node_label(node)
    detail = trace.get("detail")
    return f"{label} ({detail})" if detail else label


def _trace_node_label(node: str) -> str:
    mapping = {
        "parse_requirements": "Extraction des exigences",
        "extract_requirements": "Extraction des exigences",
        "use_validated_requirements": "Lecture des exigences validées",
        "missing_data_handler": "Données manquantes",
        "retrieve_rag_context": "Recherche RAG",
        "memory_recall": "Rappel mémoire",
        "select_assets": "Sélection des assets",
        "asset_fallback_handler": "Sélection fallback des assets",
        "validate_requirements": "Validation des exigences",
        "rule_violation_handler": "Blocage par règle métier",
        "plan_scene": "Planification SceneSpec",
        "validate_scene": "Validation SceneSpec",
        "scene_repair_handler": "Réparation SceneSpec",
        "pre_blender_gate": "Contrôle avant Blender",
        "generate_blender": "Génération Blender",
        "blender_failure_handler": "Analyse d'échec Blender",
        "qa_generation": "Contrôle qualité",
        "post_blender_gate": "Contrôle final",
        "qa_failure_handler": "Analyse d'échec QA",
        "quality_gate_failure_handler": "Blocage qualité",
        "memory_writeback": "Écriture mémoire",
        "edit_prepare_revision": "Préparation de la révision",
        "plan_generated_geometry": "Conception géométrique spécialisée",
        "geometry_program_failure_handler": "Analyse de la géométrie générée",
    }
    return mapping.get(node, node.replace("_", " ").capitalize())


def _studio_warnings(inventory: dict, rag: dict | None = None) -> list[dict]:
    warnings: list[dict] = []
    if not _blender_available():
        warnings.append(
            {
                "title": "Blender indisponible ou invalide",
                "severity": "warning",
                "impact": (
                    "Aucun design ne produira de vrai GLB tant que le démarrage headless "
                    "de Blender échoue."
                ),
                "recommended_action": (
                    "Installez un Blender LTS compatible, vérifiez son smoke headless, "
                    "puis redémarrez l'API."
                ),
                "technical_code": "STUDIO_BLENDER_NOT_AVAILABLE",
            }
        )
    entries = inventory.get("entries", [])
    if entries and int(inventory.get("generation_eligible_asset_count") or 0) == 0:
        warnings.append(
            {
                "title": "Aucun composant 3D qualifié",
                "severity": "error",
                "impact": "La génération 3D ne dispose d'aucun profil d'asset autorisé.",
                "recommended_action": (
                    "Vérifiez les qualifications, manifests et fichiers sous assets/."
                ),
                "technical_code": "STUDIO_NO_QUALIFIED_ASSETS",
            }
        )
    missing_count = int(inventory.get("missing_file_count") or 0)
    if missing_count:
        warnings.append(
            {
                "title": "Inventaire asset partiel",
                "severity": "warning",
                "impact": (
                    f"{missing_count} asset(s) référencé(s) par manifest n'ont pas de GLB local."
                ),
                "recommended_action": "Ajouter les GLB manquants ou rendre leur fallback visible.",
                "technical_code": "STUDIO_PARTIAL_ASSET_INVENTORY",
            }
        )
    if rag and rag.get("degraded"):
        status = str(rag.get("status") or "unknown")
        if status == "configured_unverified":
            title = "RAG configuré mais non vérifié"
            impact = (
                "La configuration NVIDIA est présente, mais aucune opération réelle réussie "
                "ne prouve encore la disponibilité de la recherche."
            )
            recommended_action = (
                "Lancer une recherche de contrôle ou /rag/reindex et vérifier le résultat."
            )
        elif status == "configured_but_last_operation_failed":
            title = "RAG indisponible lors du dernier appel"
            impact = (
                "La dernière opération d'embedding ou de recherche a échoué; le contexte RAG "
                "n'est pas utilisable pour cette opération."
            )
            recommended_action = (
                "Vérifier la disponibilité du fournisseur NVIDIA, puis relancer une recherche "
                "de contrôle avant de réindexer."
            )
        else:
            title = "RAG en mode dégradé"
            impact = "La recherche de contexte n'utilise pas le modèle NVIDIA primaire."
            recommended_action = (
                "Vérifier le fournisseur d'embeddings configuré. Le mode déterministe reste "
                "réservé aux tests et au bootstrap."
            )
        warnings.append(
            {
                "title": title,
                "severity": "warning",
                "impact": impact,
                "recommended_action": recommended_action,
                "technical_code": f"STUDIO_RAG_DEGRADED:{status}",
            }
        )
    if rag and rag.get("reranker_degraded_reason"):
        warnings.append(
            {
                "title": "Reranker RAG dégradé",
                "severity": "warning",
                "impact": (
                    "Les résultats RAG sont disponibles, mais le reranking NVIDIA n'a pas été "
                    "appliqué."
                ),
                "recommended_action": (
                    "Vérifier la clé NVIDIA et le modèle reranker; le backend expose la raison "
                    "dans rag_reranker_degraded_reason."
                ),
                "technical_code": f"STUDIO_RAG_RERANKER_DEGRADED:{rag['reranker_degraded_reason']}",
            }
        )
    return warnings
