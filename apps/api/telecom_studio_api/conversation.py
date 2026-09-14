"""Read-only conversation projection over the durable workflow event journal.

Only recorded user text is attributed to the user. Execution notices are system
messages, never fabricated LLM answers or a second authority for design versions.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from core.services.dependent_constraints import edit_failure_user_text
from core.services.event_log import EventLogReadResult

_TECHNICAL_EDIT_FAILURE = re.compile(
    r"(?:traceback|\b(?:key|type|value|validation|runtime|lookup)error\b|exception|"
    r"scenespec|fallback patch|platform_count|platform_levels_m|mount_zones_valid|"
    r"assembly_[a-z0-9_]+|blueprint_not_compiled|requirement_not_covered|"
    r"not grounded in (?:the )?(?:edit )?prompt|unrequested sector|undeclared capability|"
    r"unknown adaptation capability|contradicts the prompt|"
    r"\[type=|\b(?:does not|could not|cannot|must match|mismatch|invalid|unavailable)\b|"
    r"/(?:tower|sectors|visual_elements|accessory_assets)/|\.py(?::\d+)?)",
    re.IGNORECASE,
)


class ConversationMessage(BaseModel):
    message_id: str
    role: Literal["user", "system"]
    text: str
    timestamp: str
    operation_id: str | None = None
    target_semantic_root: str | None = None
    version_id: str | None = None


class ConversationView(BaseModel):
    workflow_id: str
    history_status: Literal["recorded", "legacy_partial", "damaged"]
    messages: list[ConversationMessage] = Field(default_factory=list)


def project_conversation(workflow_id: str, journal: EventLogReadResult) -> ConversationView:
    messages = []
    recorded = False
    for event in journal.events:
        payload = event.payload
        message = payload.get("conversation_message")
        if isinstance(message, dict) and message.get("role") in {"user", "system"}:
            text = message.get("text")
            role = message["role"]
            recorded = recorded or event.event_type == "design_created"
        elif event.event_type == "edit_patch_created":
            # Historical edit prompts were recorded verbatim, including rejected edits.
            text, role = payload.get("prompt"), "user"
        elif event.event_type in {"workflow_completed", "workflow_failed", "version_rolled_back"}:
            text = {
                "workflow_completed": (
                    "La génération est terminée. Consultez le résultat et ses vérifications."
                ),
                "workflow_failed": "La génération n’a pas abouti.",
                "version_rolled_back": "La version précédente a été restaurée.",
            }[event.event_type]
            role = "system"
        else:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        failed_edit_notice = _is_failed_edit_notice(event.event_type, role, payload)
        if failed_edit_notice and _TECHNICAL_EDIT_FAILURE.search(text):
            text = _project_edit_failure(text, payload)
        # New edits already have a durable request message before validation.
        if event.event_type == "edit_patch_created" and any(
            item.operation_id == payload.get("edit_id") and item.role == "user" for item in messages
        ):
            continue

        def string_value(key: str, data: dict = payload) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        messages.append(
            ConversationMessage(
                message_id=event.event_id,
                role=role,
                text=text,
                timestamp=event.timestamp,
                operation_id=string_value("edit_id"),
                target_semantic_root=string_value("target_semantic_root"),
                version_id=string_value("version_id"),
            )
        )
    return ConversationView(
        workflow_id=workflow_id,
        history_status="damaged"
        if not journal.diagnostics.healthy
        else ("recorded" if recorded else "legacy_partial"),
        messages=messages,
    )


def _is_failed_edit_notice(event_type: str, role: str, payload: dict) -> bool:
    return (
        event_type == "edit_outcome"
        and role == "system"
        and (
            payload.get("status") == "failed"
            or payload.get("edit_result_status") in {"failed", "rejected"}
        )
    )


def _project_edit_failure(text: str, payload: dict) -> str:
    detail = edit_failure_user_text(text).strip()
    if detail and detail[-1] not in ".!?":
        detail = f"{detail}."
    prefix = (
        "La modification a été refusée : "
        if payload.get("edit_result_status") == "rejected"
        else "La modification n’a pas pu être appliquée : "
    )
    return f"{prefix}{detail} La version précédente reste disponible."
