from typing import Any, Literal

from pydantic import Field, field_validator

from core.contracts.common import StrictModel
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport


class PatchOperation(StrictModel):
    op: Literal["replace", "add", "remove"] = Field(default="replace")
    path: str = Field(min_length=1)
    value: Any = None

    @field_validator("path")
    @classmethod
    def path_must_be_a_safe_pointer(cls, value: str) -> str:
        parts = value.split("/")
        if not value.startswith("/") or len(parts) < 3:
            raise ValueError("Patch path must be an absolute JSON pointer")
        if any(part in {"", ".", ".."} for part in parts[1:]):
            raise ValueError("Patch path contains an invalid segment")
        return value


class ScenePatch(StrictModel):
    edit_description: str = Field(min_length=1)
    operations: list[PatchOperation] = Field(min_length=1)
    edit_llm_provider: str | None = None
    edit_llm_fallback_used: bool = False
    edit_llm_fallback_reason: str | None = Field(default=None, max_length=160)
    capability_catalog_hash: str | None = None
    adaptation_tools: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class SceneEditResult(StrictModel):
    workflow_id: str = Field(min_length=1)
    edit_id: str = Field(min_length=1)
    status: Literal["applied", "rejected", "failed"] = "applied"
    original_scene: SceneSpec | None = None
    patched_scene: SceneSpec | None = None
    patch: ScenePatch | None = None
    validation_report: ValidationReport | None = None
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    version_id: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    generation_mode: str | None = None
    qa_score: float | None = None
    llm_provider: str | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = Field(default=None, max_length=160)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
