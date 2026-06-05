from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel

InspectionMode = Literal["glb_parse", "metadata_fallback", "not_available"]


class GlbInspectionReport(StrictModel):
    inspection_mode: InspectionMode
    file_exists: bool
    file_size_bytes: int = Field(ge=0)
    format_valid: bool
    node_count: int = Field(default=0, ge=0)
    mesh_count: int = Field(default=0, ge=0)
    material_count: int = Field(default=0, ge=0)
    object_names: list[str] = Field(default_factory=list)
    expected_object_prefixes_found: dict[str, bool] = Field(default_factory=dict)
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
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
    preview_qa_passed: bool = False
