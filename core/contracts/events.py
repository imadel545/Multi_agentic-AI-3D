from typing import Any, Literal

from pydantic import Field

from core.contracts.common import StrictModel


class WorkflowEvent(StrictModel):
    event_type: Literal[
        "design_created",
        "validated_requirements_received",
        "edit_patch_created",
        "edit_patch_applied",
        "edit_patch_rejected",
        "blender_started",
        "blender_completed",
        "blender_failed",
        "qa_started",
        "qa_completed",
        "qa_failed",
        "version_created",
        "version_rolled_back",
        "workflow_completed",
        "workflow_failed",
    ]
    workflow_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
