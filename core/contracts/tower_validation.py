from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.validation import ValidationIssue


class TowerValidationReport(StrictModel):
    status: str = Field(default="passed", pattern="^(passed|failed|warning)$")
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    recommended_accessories: dict[str, bool] = Field(default_factory=dict)
    structural_score: float = Field(default=1.0, ge=0.0, le=1.0)
