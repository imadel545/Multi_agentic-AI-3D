from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel

GenerationStrategy = Literal[
    "parametric_generated",
    "imported_glb_exact",
    "stretched_imported_glb",
    "internal_project_generated",
    "procedural_fallback",
    "degraded",
    "unknown",
]

GeometrySource = Literal[
    "parametric_generated",
    "imported_glb_exact",
    "stretched_imported_glb",
    "internal_project_generated",
    "procedural_fallback",
    "degraded",
    "unknown",
]

MeshQALevel = Literal[
    "mesh_level_transform_basic",
    "mesh_level_basic",
    "metadata_only",
    "not_available",
]


class BoundingBoxM(StrictModel):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def depth(self) -> float:
        return self.max_z - self.min_z

    @property
    def height(self) -> float:
        # glTF is Y-up; tower height maps to the Y axis.
        return self.max_y - self.min_y


class MeshCheckResult(StrictModel):
    name: str
    passed: bool
    detail: str | None = None


class MeshQAReport(StrictModel):
    level: MeshQALevel = "mesh_level_basic"
    geometry_source: GeometrySource = "unknown"
    generation_strategy: GenerationStrategy = "unknown"
    glb_parse_ok: bool = False
    bounding_box_m: BoundingBoxM | None = None
    checks: list[MeshCheckResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    mesh_qa_passed: bool = False
    limitations: list[str] = Field(default_factory=list)


class ParametricGenerationRecord(StrictModel):
    object_role: str
    object_name: str
    asset_id: str | None = None
    generation_strategy: GenerationStrategy
    geometry_source: GeometrySource
    reason: str = Field(min_length=1)
    requested_dimensions_m: dict | None = None
    actual_bounding_box_m: BoundingBoxM | None = None
    warnings: list[str] = Field(default_factory=list)
