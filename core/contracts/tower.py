from typing import Annotated, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel

TowerStructure = Literal["lattice", "monopole", "rooftop_mast", "small_cell_pole"]
FoundationType = Literal["concrete_pad", "rooftop_anchored", "pole_base", "unknown"]
TowerMaterial = Literal["galvanized_steel", "painted_steel", "concrete", "unknown"]
PlatformLevelM = Annotated[float, Field(gt=0, le=150)]


class TowerAccessGeometryProfile(StrictModel):
    """Bounded internal geometry policy for a lattice tower access assembly.

    This profile is authored with the tower manifest and carried into the
    SceneSpec.  It is deliberately a procedural contract, not evidence of a
    manufacturer installation, worker-safety certification, or structural
    capacity.  ``platform_levels_m`` remains user/design intent on
    :class:`TowerCharacteristics`; the legacy ratios preserve placement for
    pre-level-count requests until the controlled worker consumes this profile.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    family: Literal["lattice_tower_access_v1"] = "lattice_tower_access_v1"
    platform_width_m: float = Field(default=2.2, ge=1.0, le=6.0)
    platform_depth_m: float = Field(default=2.2, ge=1.0, le=6.0)
    platform_thickness_m: float = Field(default=0.08, ge=0.02, le=0.25)
    platform_guardrail_height_m: float = Field(default=1.1, ge=0.8, le=1.5)
    platform_guardrail_radius_m: float = Field(default=0.02, ge=0.008, le=0.08)
    platform_toe_board_height_m: float = Field(default=0.12, ge=0.05, le=0.3)
    platform_toe_board_thickness_m: float = Field(default=0.025, ge=0.01, le=0.12)
    platform_tower_clearance_m: float = Field(default=0.2, ge=0.05, le=2.0)
    platform_support_radius_m: float = Field(default=0.025, ge=0.008, le=0.08)
    platform_support_tangent_offset_ratio: float = Field(default=0.3, ge=0.1, le=0.5)
    ladder_width_m: float = Field(default=0.45, ge=0.3, le=1.2)
    ladder_rail_radius_m: float = Field(default=0.018, ge=0.008, le=0.08)
    ladder_rung_radius_m: float = Field(default=0.014, ge=0.006, le=0.06)
    ladder_rung_spacing_m: float = Field(default=0.3, ge=0.18, le=0.45)
    ladder_base_clearance_m: float = Field(default=0.5, ge=0.0, le=3.0)
    ladder_top_clearance_m: float = Field(default=0.5, ge=0.0, le=3.0)
    ladder_tower_clearance_m: float = Field(default=0.2, ge=0.05, le=2.0)
    access_face_azimuth_deg: float = Field(default=180.0, ge=0.0, lt=360.0)
    legacy_platform_start_height_ratio: float = Field(default=0.55, ge=0.05, le=0.9)
    legacy_platform_span_height_ratio: float = Field(default=0.35, ge=0.0, le=0.85)

    @model_validator(mode="after")
    def validate_legacy_platform_policy(self) -> "TowerAccessGeometryProfile":
        if self.legacy_platform_start_height_ratio + self.legacy_platform_span_height_ratio > 0.95:
            raise ValueError("legacy platform placement must remain below the tower top")
        if self.platform_toe_board_thickness_m > self.platform_depth_m / 2:
            raise ValueError("platform toe-board thickness must fit within platform depth")
        return self


class TowerCharacteristics(StrictModel):
    structure: TowerStructure
    leg_count: int = Field(default=4, ge=1, le=4)
    base_width_m: float | None = Field(default=None, gt=0, le=30)
    top_width_m: float | None = Field(default=None, gt=0, le=30)
    foundation_type: FoundationType = "unknown"
    has_platform: bool = False
    platform_count: int = Field(default=0, ge=0, le=12)
    platform_levels_m: list[PlatformLevelM] = Field(
        default_factory=list,
        max_length=12,
        exclude_if=lambda value: not value,
    )
    has_ladder: bool = False
    has_lightning_rod: bool = False
    has_aviation_light: bool = False
    material: TowerMaterial = "galvanized_steel"

    @model_validator(mode="before")
    @classmethod
    def derive_platform_presence_from_explicit_levels(cls, value: object) -> object:
        """Keep legacy count-only payloads valid while canonicalising explicit levels.

        An explicit level list unambiguously requests platforms.  When a caller
        omits the redundant boolean/count, derive them without accepting an
        explicit contradictory value.  The after-validator below remains the
        source of truth for all invariant checks.
        """

        if not isinstance(value, dict):
            return value
        levels = value.get("platform_levels_m")
        if not isinstance(levels, list) or not levels:
            return value
        normalized = dict(value)
        if "has_platform" not in normalized:
            normalized["has_platform"] = True
        if "platform_count" not in normalized:
            normalized["platform_count"] = len(levels)
        return normalized

    @model_validator(mode="after")
    def validate_taper(self) -> "TowerCharacteristics":
        if (
            self.base_width_m is not None
            and self.top_width_m is not None
            and self.top_width_m > self.base_width_m
        ):
            raise ValueError("top_width_m cannot exceed base_width_m")
        if self.structure == "lattice" and self.leg_count < 3:
            raise ValueError("lattice towers require at least 3 legs")
        if not self.has_platform and self.platform_levels_m:
            raise ValueError("platform_levels_m must be empty when has_platform is false")
        if not self.has_platform and self.platform_count != 0:
            raise ValueError("platform_count must be 0 when has_platform is false")
        if self.has_platform and self.platform_count == 0:
            raise ValueError("platform_count must be at least 1 when has_platform is true")
        if self.platform_levels_m:
            if len(self.platform_levels_m) != self.platform_count:
                raise ValueError("platform_count must match len(platform_levels_m)")
            if len(set(self.platform_levels_m)) != len(self.platform_levels_m):
                raise ValueError("platform_levels_m must not contain duplicate levels")
            if any(
                next_level <= current_level
                for current_level, next_level in zip(
                    self.platform_levels_m,
                    self.platform_levels_m[1:],
                    strict=False,
                )
            ):
                raise ValueError("platform_levels_m must be strictly ascending")
        return self
