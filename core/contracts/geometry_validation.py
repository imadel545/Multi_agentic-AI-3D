from pydantic import Field

from core.contracts.common import StrictModel


class GeometryValidationReport(StrictModel):
    status: str = Field(min_length=1)
    checks: dict[str, bool] = Field(default_factory=dict)
    object_counts: dict[str, int] = Field(default_factory=dict)
    missing_objects: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    height_tolerance_m: float = Field(default=0.5, gt=0)
    azimuth_tolerance_deg: float = Field(default=5.0, gt=0)
