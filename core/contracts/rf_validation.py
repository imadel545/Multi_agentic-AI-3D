from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.validation import ValidationIssue


class RfValidationReport(StrictModel):
    status: str = Field(default="passed", pattern="^(passed|failed|warning)$")
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    azimuth_spacing_deg: list[float] = Field(default_factory=list)
    min_spacing_deg: float = Field(default=0.0, ge=0.0)
    overlap_sectors: list[tuple[str, str]] = Field(default_factory=list)
    rf_score: float = Field(default=1.0, ge=0.0, le=1.0)
