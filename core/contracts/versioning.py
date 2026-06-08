from typing import Any

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.scene import SceneSpec


class SceneVersion(StrictModel):
    version_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    parent_version_id: str | None = None
    scene: SceneSpec
    created_at: str = Field(min_length=1)
    edit_description: str | None = None
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    artifact_dir: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    qa_score: float | None = None
    generation_mode: str | None = None
    active: bool = False
