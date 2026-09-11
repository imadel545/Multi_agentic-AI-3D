from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel


class SectorPreviewVisualInspection(StrictModel):
    """Framing measurements calibrated for a compact sector subassembly."""

    inspection_mode: Literal["png_parse", "not_available"]
    file_exists: bool
    file_size_bytes: int = Field(ge=0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    format: str | None = None
    minimum_resolution_valid: bool
    subject_pixel_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_bbox_width_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_bbox_height_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_contrast_mean: float | None = Field(default=None, ge=0.0)
    subject_center_x_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_touches_frame: bool
    checks: dict[str, bool]
    critical_errors: list[str] = Field(default_factory=list)
    visual_quality_passed: bool


class SectorPreviewEvidenceItem(StrictModel):
    """One Blender-rendered sector inspection image bound to an exported GLB."""

    preview_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    sector_id: str = Field(min_length=1)
    file_name: str = Field(pattern=r"^preview_sector_[a-f0-9]{16}\.png$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0)
    semantic_roots: list[str] = Field(min_length=1)
    expected_roles: list[str] = Field(min_length=1)
    exported_roles: list[str] = Field(min_length=1)
    framed_roles: list[str] = Field(min_length=1)
    post_blender_identity_verified: bool
    visual_inspection: SectorPreviewVisualInspection


class SectorPreviewEvidence(StrictModel):
    """Independent post-Blender evidence for sector inspection previews.

    This reports framing and identity evidence only.  It does not upgrade any
    component to manufacturer-qualified geometry or installation approval.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    scene_id: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    measurement_scope: Literal["exported_glb_semantics_and_rendered_sector_preview"]
    glb_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    previews: list[SectorPreviewEvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
