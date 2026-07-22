from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.parametric import (
    BoundingBoxM,
    GenerationStrategy,
    GeometrySource,
    MeshQAReport,
)


class GeometryValidationReport(StrictModel):
    status: str = Field(min_length=1)
    geometry_source: GeometrySource = "unknown"
    generation_strategy: GenerationStrategy = "unknown"
    checks: dict[str, bool] = Field(default_factory=dict)
    object_counts: dict[str, int] = Field(default_factory=dict)
    missing_objects: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    height_tolerance_m: float = Field(default=0.5, gt=0)
    azimuth_tolerance_deg: float = Field(default=5.0, gt=0)
    bounding_box_m: BoundingBoxM | None = None
    mesh_qa: MeshQAReport | None = None
    mesh_qa_level: Literal[
        "mesh_level_spatial_basic",
        "mesh_level_transform_basic",
        "mesh_level_basic",
        "metadata_only",
        "not_available",
    ] = "metadata_only"
