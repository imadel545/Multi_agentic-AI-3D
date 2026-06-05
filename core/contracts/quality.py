from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel

QualityGateStage = Literal["pre_blender", "post_blender"]


class QualityGateCheck(StrictModel):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = ""


class QualityGateReport(StrictModel):
    stage: QualityGateStage
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    details: dict = Field(default_factory=dict)
    critical_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
