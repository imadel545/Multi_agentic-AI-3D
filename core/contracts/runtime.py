from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.memory import MemoryRecallResult


class AgentStepTrace(StrictModel):
    node: str = Field(min_length=1)
    status: Literal["passed", "failed", "skipped"] = "passed"
    detail: str = ""
    duration_ms: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    route: str | None = None
    attempt: int | None = Field(default=None, ge=0)


class WorkflowTrace(StrictModel):
    workflow_id: str = Field(min_length=1)
    total_duration_ms: int = Field(default=0, ge=0)
    steps: list[AgentStepTrace] = Field(default_factory=list)
    route_history: list[dict] = Field(default_factory=list)
    quality_gates: list[dict] = Field(default_factory=list)
    glb_inspection: dict | None = None
    preview_inspection: dict | None = None
    metrics: dict[str, int | float | str | bool | None] = Field(default_factory=dict)


class MemoryEvent(StrictModel):
    workflow_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)


__all__ = [
    "AgentStepTrace",
    "MemoryEvent",
    "MemoryRecallResult",
    "WorkflowTrace",
]
