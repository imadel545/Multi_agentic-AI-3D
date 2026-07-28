"""Product-oriented API layer.

Transforms technical backend status/events into user-facing responses.
The future chat-first/3D-first frontend should consume these endpoints
instead of parsing raw JSON technical reports.
"""

from __future__ import annotations

import json
import os
import shutil
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
from core.services.asset_inventory import AssetInventoryService


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
            elif status == "running":
                counts["running"] += 1
            summaries.append(
                {
                    "workflow_id": design.get("workflow_id"),
                    "status": status,
                    "created_at": design.get("created_at"),
                    "qa_score": design.get("qa_score"),
                    "generation_mode": design.get("generation_mode"),
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
        if backend_status in {"completed", "failed"} and not isinstance(active_operation, dict):
            runtime = {
                "node": "workflow",
                "phase": "workflow",
                "source": "status",
                "operation": _event_to_human(f"workflow_{backend_status}", {}),
                "node_status": backend_status,
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
            "is_terminal": backend_status in {"completed", "failed"},
            "last_event_at": runtime.get("timestamp"),
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
        status = self._status_or_raise(workflow_id)
        active_version = status.get("active_version_id")
        base_url = f"/designs/{workflow_id}/artifacts"
        viewer_artifacts = []
        issues = _collect_user_issues(status, self.workflow_service.get_events(workflow_id))
        llm = llm_truth(status, workflow_service=self.workflow_service)

        def _artifact(name: str, content_type: str, filename: str) -> dict:
            url = f"{base_url}/{filename}"
            if active_version:
                url = f"{url}?version_id={active_version}"
            path = self._artifact_path_or_none(workflow_id, filename, active_version)
            return {
                "name": name,
                "url": url,
                "content_type": content_type,
                "available": path is not None and path.exists(),
            }

        viewer_artifacts.append(_artifact("design.glb", "model/gltf-binary", "glb"))
        viewer_artifacts.append(_artifact("preview.png", "image/png", "preview"))
        viewer_artifacts.append(_artifact("scene_metadata.json", "application/json", "metadata"))
        viewer_artifacts.append(
            _artifact("requirements_spec.json", "application/json", "requirements_spec")
        )
        viewer_artifacts.append(
            _artifact("extraction_report.json", "application/json", "extraction_report")
        )
        viewer_artifacts.append(_artifact("scene_spec.json", "application/json", "scene_spec"))
        viewer_artifacts.append(_artifact("qa_report.json", "application/json", "qa_report"))
        viewer_artifacts.append(
            _artifact("generation_report.json", "application/json", "generation_report")
        )
        viewer_artifacts.append(_artifact("rag_evidence.json", "application/json", "rag_evidence"))
        viewer_artifacts.append(
            _artifact("planning_decision.json", "application/json", "planning_decision")
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
        primary_glb = _artifact_by_name(viewer_artifacts, "design.glb")
        preview = _artifact_by_name(viewer_artifacts, "preview.png")
        metadata = _artifact_by_name(viewer_artifacts, "scene_metadata.json")
        requirements_spec = _artifact_by_name(viewer_artifacts, "requirements_spec.json")
        extraction_report = _artifact_by_name(viewer_artifacts, "extraction_report.json")
        scene_spec = _artifact_by_name(viewer_artifacts, "scene_spec.json")
        qa_report = _artifact_by_name(viewer_artifacts, "qa_report.json")
        generation_report = _artifact_by_name(viewer_artifacts, "generation_report.json")
        rag_evidence = _artifact_by_name(viewer_artifacts, "rag_evidence.json")
        geometry_validation = _artifact_by_name(viewer_artifacts, "geometry_validation.json")
        requirement_coverage = _artifact_by_name(viewer_artifacts, "requirement_coverage.json")
        completion_certificate = _artifact_by_name(viewer_artifacts, "completion_certificate.json")
        report = _artifact_by_name(viewer_artifacts, "technical_report.md")

        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "active_version": active_version,
            "generation_mode": status.get("generation_mode"),
            "generation_strategy": status.get("generation_strategy"),
            "geometry_source": status.get("geometry_source"),
            "mesh_qa_level": status.get("mesh_qa_level"),
            "mesh_qa_passed": status.get("mesh_qa_passed"),
            "qa_score": status.get("qa_score"),
            "asset_import_summary": status.get("asset_import_summary"),
            "human_warnings_count": sum(1 for issue in issues if issue["severity"] == "warning"),
            "human_errors_count": sum(1 for issue in issues if issue["severity"] == "error"),
            "primary_glb_url": _available_artifact_url(primary_glb),
            "preview_url": _available_artifact_url(preview),
            "report_url": _available_artifact_url(report),
            "metadata_url": _available_artifact_url(metadata),
            "requirements_spec_url": _available_artifact_url(requirements_spec),
            "extraction_report_url": _available_artifact_url(extraction_report),
            "scene_spec_url": _available_artifact_url(scene_spec),
            "qa_report_url": _available_artifact_url(qa_report),
            "generation_report_url": _available_artifact_url(generation_report),
            "rag_evidence_url": _available_artifact_url(rag_evidence),
            "geometry_validation_url": _available_artifact_url(geometry_validation),
            "requirement_coverage_url": _available_artifact_url(requirement_coverage),
            "completion_certificate_url": _available_artifact_url(completion_certificate),
            "requirement_coverage_passed": status.get("requirement_coverage_passed"),
            "requirement_coverage_ratio": status.get("requirement_coverage_ratio"),
            "completion_certificate_status": status.get("completion_certificate_status"),
            "extraction_provider": llm["extraction_provider"],
            "llm_provider": status.get("llm_provider"),
            "llm_available": llm["llm_available"],
            "llm_fallback_used": status.get("llm_fallback_used"),
            "llm_fallback_reason": llm["llm_fallback_reason"],
            "rag_context_count": status.get("rag_context_count"),
            "rag_planning_summary": status.get("rag_planning_summary"),
            "rag_reranker_provider": status.get("rag_reranker_provider"),
            "rag_reranker_model": status.get("rag_reranker_model"),
            "rag_reranker_status": status.get("rag_reranker_status"),
            "rag_reranker_degraded_reason": status.get("rag_reranker_degraded_reason"),
            "memory_context_count": status.get("memory_context_count"),
            "qa_summary": _viewer_qa_summary(status),
            "viewer_artifacts": viewer_artifacts,
            "limitations": _collect_limitations(status),
            "runtime_capabilities": runtime_capabilities(),
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

    def _artifact_path_or_none(
        self, workflow_id: str, artifact_name: str, version_id: str | None
    ) -> Path | None:
        try:
            return self.workflow_service.artifact_path(
                workflow_id, artifact_name, version_id=version_id
            )
        except KeyError:
            return None


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
    ready = sum(1 for entry in entries if entry.get("asset_import_mode") == "imported_glb")
    fallback = sum(
        1 for entry in entries if entry.get("effective_generation_mode") == "procedural_fallback"
    )
    if ready == total and total > 0:
        return "ready_for_import"
    if fallback > 0:
        return "partial_import_ready"
    return "incomplete"


def _blender_available() -> bool:
    return _resolve_blender_binary(settings.resolved_blender_binary) is not None


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
    elif provider_name.startswith("sentence-transformers:"):
        status = "local_sentence_transformers_explicit"
        degraded = True
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
    if name.startswith("cross-encoder:"):
        return "explicit_local_reranker"
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
    value = getattr(reranker, "model_name", None)
    if value:
        return str(value)
    value = getattr(rag_service, "_reranker_model", None)
    return str(value) if value else None


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
                "/Applications/Blender.app/Contents/MacOS/Blender",
                "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
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
    if backend_status == "failed":
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
    if backend_status == "failed":
        return "failed"
    return "running"


def _progress_label(status: dict) -> str:
    backend_status = status.get("status", "unknown")
    return {
        "pending": "En attente",
        "running": "En cours",
        "completed": "Terminé",
        "failed": "Échec",
    }.get(backend_status, str(backend_status))


def _available_actions(status: dict, issues: list[dict]) -> list[str]:
    backend_status = status.get("status", "unknown")
    if backend_status in {"pending", "running"}:
        return ["view_timeline"]
    if backend_status == "failed":
        return ["view_issues", "view_timeline", "retry_with_changes"]
    actions = ["open_viewer", "download_artifacts", "view_timeline", "edit_design"]
    if status.get("active_version_id"):
        actions.append("view_versions")
    if issues:
        actions.append("review_issues")
    return actions


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
        "mesh_qa_level": status.get("mesh_qa_level"),
        "mesh_qa_passed": status.get("mesh_qa_passed"),
        "qa_score": status.get("qa_score"),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "warnings": [warning for warning in warnings if warning],
        "errors": [error for error in errors if error],
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
        if asset.get("import_mode") in {"imported_glb", "stretched_imported_glb"}
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
    if asset_summary.get("procedural_fallback_count", 0) and not any(
        i.get("technical_code") == "ASSET_IMPORT_PROCEDURAL_FALLBACK_INFERRED" for i in issues
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
    issues.extend(_collect_runtime_event_issues(events or [], status))
    return issues


def _collect_runtime_event_issues(events: list[dict], status: dict) -> list[dict]:
    issues: list[dict] = []
    seen: set[str] = set()
    workflow_status = status.get("status", "unknown")
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
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        detail = str(errors[0]) if errors else str(payload.get("detail") or "Étape échouée.")
        issues.append(
            {
                "title": f"{_trace_node_label(node)} en mode dégradé",
                "severity": "error" if workflow_status == "failed" else "warning",
                "impact": detail,
                "recommended_action": _runtime_node_recommended_action(node),
                "technical_code": f"RUNTIME_NODE_FAILED:{node}",
            }
        )
    return issues


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
    "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR": {
        "title": "Asset interne minimal",
        "impact": "Le design est valide techniquement mais l'asset n'est pas vendor-grade.",
        "recommended_action": "Remplacer plus tard par un asset constructeur réaliste.",
    },
    "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE": {
        "title": "Asset interne minimal",
        "impact": "Le design est valide techniquement mais l'asset n'est pas vendor-grade.",
        "recommended_action": "Remplacer plus tard par un asset constructeur réaliste.",
    },
    "ASSET_IMPORT_INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE": {
        "title": "Asset interne nettoyé",
        "impact": (
            "L'asset est importable mais reste une ressource interne, pas un modèle constructeur."
        ),
        "recommended_action": "Remplacer par un asset vendor-grade avant livraison finale.",
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


def _event_status(event_type: str, workflow_status: str, *, index: int, total: int) -> str:
    if event_type == "node_failed":
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
    }
    return mapping.get(node, node.replace("_", " ").capitalize())


def _studio_warnings(inventory: dict, rag: dict | None = None) -> list[dict]:
    warnings: list[dict] = []
    if not _blender_available():
        warnings.append(
            {
                "title": "Blender non installé",
                "severity": "warning",
                "impact": (
                    "Aucun design ne produira de vrai GLB tant que Blender n'est pas installé."
                ),
                "recommended_action": "Installez Blender 4.5+ et redémarrez l'API.",
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
