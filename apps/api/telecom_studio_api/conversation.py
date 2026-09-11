"""Read-only conversation projection over the durable workflow event journal.

Only recorded user text is attributed to the user. Execution notices are system
messages, never fabricated LLM answers or a second authority for design versions.
"""

from typing import Literal

from pydantic import BaseModel, Field

from core.services.event_log import EventLogReadResult


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
