from typing import Any, Literal

from pydantic import Field, field_validator

from core.contracts.common import StrictModel
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport


class PatchOperation(StrictModel):
    op: Literal["replace", "add", "remove"] = Field(default="replace")
    path: str = Field(min_length=1)
    value: Any = None

    @field_validator("path")
    @classmethod
    def path_must_be_allowed(cls, value: str) -> str:
        allowed_tower_characteristics = {
            "structure",
            "leg_count",
            "base_width_m",
            "top_width_m",
            "foundation_type",
            "has_platform",
            "platform_count",
            "has_ladder",
            "has_lightning_rod",
            "has_aviation_light",
            "material",
        }
        allowed_sector_paths = {
            "azimuth_deg",
            "install_height_m",
            "mechanical_tilt_deg",
            "electrical_tilt_deg",
            "beamwidth_deg",
            "include_cable",
            "include_label",
        }
        allowed_visual_paths = {
            "include_sector_beams",
            "include_azimuth_arrows",
            "include_height_markers",
            "include_labels",
            "include_power_cabinet",
            "include_gps_antenna",
        }
        if value == "/tower/height_m":
            return value
        if value.startswith("/tower/characteristics/"):
            parts = value.split("/")
            if len(parts) == 4 and parts[3] in allowed_tower_characteristics:
                return value
        if value.startswith("/sectors/"):
            parts = value.split("/")
            if (
                len(parts) == 4
                and (parts[2] == "*" or parts[2].isdigit())
                and parts[3] in allowed_sector_paths
            ):
                return value
        if value.startswith("/visual_elements/"):
            parts = value.split("/")
            if len(parts) == 3 and parts[2] in allowed_visual_paths:
                return value
        raise ValueError(f"Patch path not allowed: {value}")


class ScenePatch(StrictModel):
    edit_description: str = Field(min_length=1)
    operations: list[PatchOperation] = Field(min_length=1)
    edit_llm_provider: str | None = None
    edit_llm_fallback_used: bool = False
    edit_llm_fallback_reason: str | None = Field(default=None, max_length=160)


class SceneEditResult(StrictModel):
    workflow_id: str = Field(min_length=1)
    edit_id: str = Field(min_length=1)
    status: Literal["applied", "rejected", "failed"] = "applied"
    original_scene: SceneSpec | None = None
    patched_scene: SceneSpec | None = None
    patch: ScenePatch | None = None
    validation_report: ValidationReport | None = None
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    version_id: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    generation_mode: str | None = None
    qa_score: float | None = None
    llm_provider: str | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = Field(default=None, max_length=160)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
