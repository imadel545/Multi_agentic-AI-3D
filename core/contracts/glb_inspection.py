from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.parametric import BoundingBoxM

InspectionMode = Literal["glb_parse", "metadata_fallback", "not_available"]
SemanticInspectionMode = Literal[
    "semantic_extras",
    "mixed_semantic_name_based",
    "name_based",
    "not_available",
]


class GlbInspectionReport(StrictModel):
    inspection_mode: InspectionMode
    file_exists: bool
    file_size_bytes: int = Field(ge=0)
    format_valid: bool
    node_count: int = Field(default=0, ge=0)
    mesh_count: int = Field(default=0, ge=0)
    primitive_count: int = Field(default=0, ge=0)
    position_accessor_count: int = Field(default=0, ge=0)
    material_count: int = Field(default=0, ge=0)
    object_names: list[str] = Field(default_factory=list)
    semantic_inspection_mode: SemanticInspectionMode = "not_available"
    semantic_root_count: int = Field(default=0, ge=0)
    semantic_extras_root_count: int = Field(default=0, ge=0)
    semantic_extras_coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_object_counts: dict[str, int] = Field(default_factory=dict)
    semantic_sector_ids: dict[str, list[str]] = Field(default_factory=dict)
    expected_object_prefixes_found: dict[str, bool] = Field(default_factory=dict)
    bounding_box_m: BoundingBoxM | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    structural_qa_passed: bool = False


class PreviewInspectionReport(StrictModel):
    inspection_mode: Literal["png_parse", "not_available"]
    file_exists: bool
    file_size_bytes: int = Field(ge=0)
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    format: str | None = None
    minimum_resolution_valid: bool = False
    luminance_mean: float | None = None
    luminance_stddev: float | None = None
    non_dark_pixel_ratio: float | None = None
    subject_pixel_ratio: float | None = None
    subject_bbox_width_ratio: float | None = None
    subject_bbox_height_ratio: float | None = None
    subject_contrast_mean: float | None = None
    subject_center_x_ratio: float | None = None
    subject_min_edge_margin_ratio: float | None = None
    subject_touches_frame: bool = False
    subject_framing_valid: bool = False
    visual_quality_valid: bool = False
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    preview_qa_passed: bool = False
