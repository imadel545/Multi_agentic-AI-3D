from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel


class ValidationIssue(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: Literal["info", "warning", "error"] = "warning"


class ValidationReport(StrictModel):
    design_id: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    score: float = Field(ge=0, le=1)
    checks: dict[str, bool]
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    glb_inspection: dict | None = None
    preview_inspection: dict | None = None
