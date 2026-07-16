import uuid
from typing import Any

from pydantic import Field

from core.contracts.common import StrictModel


class WorkflowEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    sequence: int | None = Field(default=None, ge=1)
    event_type: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
