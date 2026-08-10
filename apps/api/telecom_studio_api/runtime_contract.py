from __future__ import annotations

from collections.abc import Callable
from typing import Any

_MultimodalHealthProvider = Callable[[], dict[str, dict[str, Any]]]
_multimodal_health_provider: _MultimodalHealthProvider | None = None
_multimodal_enabled = False
_multimodal_key_configured = False
_multimodal_max_images = 3
_multimodal_max_image_bytes = 20_000_000

_UNSUPPORTED_ACTIONS = [
    {
        "action": "cancel",
        "reason": "Le runtime local ne possède pas encore de signal d'annulation fiable.",
        "future_requirement": "Ajouter une cancellation coopérative par workflow_id.",
    },
    {
        "action": "pause",
        "reason": "Les nœuds LangGraph et Blender ne sont pas pausable aujourd'hui.",
        "future_requirement": "Introduire un broker/runtime durable avec états suspendus.",
    },
    {
        "action": "resume",
        "reason": "Aucun état de pause persistant n'existe dans le contrat backend v1.",
        "future_requirement": "Reprendre depuis checkpoint durable après une vraie pause.",
    },
    {
        "action": "retry",
        "reason": (
            "Le retry produit doit relancer un nouveau design avec corrections, "
            "pas rejouer un workflow existant."
        ),
        "future_requirement": (
            "Définir un retry contrôlé qui copie le contexte sans muter l'ancien workflow."
        ),
    },
    {
        "action": "human_in_loop",
        "reason": "Le workflow ne s'interrompt pas encore pour validation humaine intermédiaire.",
        "future_requirement": (
            "Ajouter des checkpoints validables par l'utilisateur avant Blender/QA."
        ),
    },
    {
        "action": "websocket_runtime",
        "reason": "Le transport live actuel est push_sse local-first, pas WebSocket.",
        "future_requirement": (
            "Ajouter WebSocket seulement si le frontend prouve que SSE ne suffit plus."
        ),
    },
]


def unsupported_actions() -> list[dict[str, str]]:
    return [dict(item) for item in _UNSUPPORTED_ACTIONS]


def runtime_capabilities() -> dict[str, Any]:
    return {
        "streaming_transport": "push_sse",
        "event_source": "push_sse",
        "replay_source": "workflow_events_jsonl",
        "workflow_id_source": "workflow_id",
        "local_process_only": True,
        "broker": "jsonl_replay_plus_in_memory_queue",
        "can_stream_events": True,
        "can_poll_status": True,
        "can_download_artifacts": True,
        "can_view_versions": True,
        "can_edit_completed_design": True,
        "can_rollback_versions": True,
        "can_cancel": False,
        "can_pause": False,
        "can_resume": False,
        "can_retry_same_workflow": False,
        "can_human_in_loop": False,
        "websocket_runtime": False,
        "multimodal_intelligence": _multimodal_intelligence_capability(),
        "limitations": [
            (
                "SSE est local-process: replay JSONL puis queue mémoire live jusqu'à "
                "l'événement terminal."
            ),
            "Pas de cancellation/pause/retry durable dans le contrat backend v1.",
            "Le frontend doit utiliser workflow_id comme identifiant runtime.",
        ],
    }


def configure_multimodal_intelligence(
    *,
    enabled: bool,
    key_configured: bool,
    max_images_per_request: int,
    max_image_bytes: int,
    health_provider: _MultimodalHealthProvider | None,
) -> None:
    """Bind public capability truth to the configured runtime and live health state."""

    if not 1 <= max_images_per_request <= 3:
        raise ValueError("multimodal max_images_per_request must be between 1 and 3")
    if not 1 <= max_image_bytes <= 20_000_000:
        raise ValueError("multimodal max_image_bytes must be between 1 and 20000000")
    global _multimodal_enabled
    global _multimodal_key_configured
    global _multimodal_max_images
    global _multimodal_max_image_bytes
    global _multimodal_health_provider
    _multimodal_enabled = enabled
    _multimodal_key_configured = key_configured
    _multimodal_max_images = max_images_per_request
    _multimodal_max_image_bytes = max_image_bytes
    _multimodal_health_provider = health_provider


def _multimodal_intelligence_capability() -> dict[str, Any]:
    configured = _multimodal_enabled and _multimodal_key_configured
    status = "configured_unverified" if configured else "disabled"
    last_error = None
    if configured and _multimodal_health_provider is not None:
        try:
            health = _multimodal_health_provider()
            states = [
                str(health.get(capability, {}).get("status") or "configured_unverified")
                for capability in ("multimodal_interpretation", "asset_visual_review")
            ]
            if any(state == "failed" for state in states):
                status = "failed"
                last_error = next(
                    (
                        str(health.get(capability, {}).get("last_error") or "")[:160]
                        for capability in (
                            "multimodal_interpretation",
                            "asset_visual_review",
                        )
                        if health.get(capability, {}).get("status") == "failed"
                    ),
                    "vision capability failed",
                )
            elif states and all(state == "operational" for state in states):
                status = "operational"
        except Exception:
            status = "failed"
            last_error = "vision_health_probe_failed"
    return {
        "status": status,
        "enabled": configured,
        "requires_project_consent": True,
        "max_images_per_request": _multimodal_max_images,
        "max_image_bytes": _multimodal_max_image_bytes,
        "remote_processing": True,
        "capabilities": (
            ["multimodal_interpretation", "asset_visual_review"] if configured else []
        ),
        "visual_design_critic": "disabled_until_m5",
        "last_error": last_error,
    }


def llm_available_from_extractor(extractor: Any | None) -> bool:
    if extractor is None:
        return False
    return bool(
        getattr(extractor, "provider", None) is not None and getattr(extractor, "enabled", False)
    )


def llm_available_from_workflow_service(workflow_service: Any | None) -> bool:
    orchestrator = getattr(workflow_service, "orchestrator", None)
    return llm_available_from_extractor(getattr(orchestrator, "extractor", None))


def llm_truth(
    status: dict[str, Any],
    *,
    workflow_service: Any | None = None,
    extractor: Any | None = None,
) -> dict[str, Any]:
    provider = status.get("llm_provider")
    fallback_used = status.get("llm_fallback_used")
    metrics = status.get("metrics") if isinstance(status.get("metrics"), dict) else {}
    use_llm = metrics.get("use_llm")

    if extractor is not None:
        llm_available = llm_available_from_extractor(extractor)
    elif workflow_service is not None:
        llm_available = llm_available_from_workflow_service(workflow_service)
    else:
        llm_available = bool(isinstance(provider, str) and provider.startswith("groq:"))

    fallback_reason = status.get("llm_fallback_reason")
    if fallback_reason is None:
        fallback_reason = llm_fallback_reason(
            provider=provider,
            fallback_used=fallback_used,
            use_llm=use_llm,
            error=status.get("llm_error"),
            llm_available=llm_available,
        )

    return {
        "extraction_provider": status.get("extraction_provider")
        or extraction_provider_label(provider, fallback_used, fallback_reason),
        "llm_available": llm_available,
        "llm_fallback_reason": fallback_reason,
    }


def extraction_provider_label(
    provider: Any,
    fallback_used: Any,
    fallback_reason: str | None = None,
) -> str | None:
    if isinstance(provider, str) and provider.startswith("groq:") and not fallback_used:
        return "groq"
    if fallback_used and fallback_reason not in {None, "deterministic_extraction_requested"}:
        return "fallback"
    if provider == "deterministic":
        return "deterministic"
    if fallback_used:
        return "fallback"
    return str(provider) if provider else None


def llm_fallback_reason(
    *,
    provider: Any,
    fallback_used: Any,
    use_llm: Any,
    error: Any,
    llm_available: bool,
) -> str | None:
    if not fallback_used:
        return None
    if error:
        return str(error)
    if use_llm is False:
        return "deterministic_extraction_requested"
    if not llm_available:
        return "groq_provider_unavailable_or_disabled"
    if provider == "deterministic":
        return "deterministic_extraction_used"
    return "llm_fallback_used"


def memory_status(memory_service: Any | None) -> dict[str, Any]:
    if memory_service is None:
        return {
            "memory_status": "disabled",
            "memory_backend": None,
            "workflow_memory_count": 0,
            "design_memory_count": 0,
            "document_pack_memory_count": 0,
            "document_pack_issue_memory_count": 0,
            "memory_vector_status": "disabled",
            "memory_vector_errors": [],
        }
    try:
        stats = memory_service.stats()
        index_health = memory_service.index_health()
    except Exception as exc:  # pragma: no cover - defensive status surface
        return {
            "memory_status": f"degraded:{type(exc).__name__}",
            "memory_backend": "sqlite",
            "workflow_memory_count": 0,
            "design_memory_count": 0,
            "document_pack_memory_count": 0,
            "document_pack_issue_memory_count": 0,
            "memory_vector_status": f"degraded:{type(exc).__name__}",
            "memory_vector_errors": [],
        }
    latest = index_health.get("latest_index_result") or {}
    compatibility = index_health.get("vector_compatibility") or {}
    outbox = index_health.get("vector_outbox") or {}
    latest_status = str(latest.get("status") or "not_indexed")
    index_failed = latest_status in {"failed", "partial"}
    outbox_status = str(outbox.get("status") or "idle")
    outbox_pending = outbox_status in {"pending", "attempt"}
    outbox_failed = outbox_status == "failed"
    migration_pending = bool(compatibility.get("degraded"))
    if outbox_failed or index_failed:
        vector_status = "failed"
    elif outbox_pending:
        vector_status = outbox_status
    else:
        vector_status = str(compatibility.get("status") or latest_status)
    vector_errors = []
    if outbox_failed or latest.get("errors"):
        vector_errors.append("vector_index_write_failed")
    elif outbox_pending:
        vector_errors.append("vector_projection_pending")
    if outbox_failed or index_failed:
        status = "degraded:vector_index"
    elif outbox_pending:
        status = "degraded:vector_projection_pending"
    elif migration_pending:
        status = "degraded:vector_migration_pending"
    else:
        status = "available"
    return {
        "memory_status": status,
        "memory_backend": "sqlite",
        "workflow_memory_count": int(stats.get("workflow_memory_count") or 0),
        "design_memory_count": int(stats.get("design_memory_count") or 0),
        "document_pack_memory_count": int(stats.get("document_pack_memory_count") or 0),
        "document_pack_issue_memory_count": int(stats.get("document_pack_issue_memory_count") or 0),
        "memory_vector_status": vector_status,
        "memory_vector_errors": vector_errors,
    }
