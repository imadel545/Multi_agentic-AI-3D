from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel

TowerStructure = Literal["lattice", "monopole", "rooftop_mast", "small_cell_pole"]
FoundationType = Literal["concrete_pad", "rooftop_anchored", "pole_base", "unknown"]
TowerMaterial = Literal["galvanized_steel", "painted_steel", "concrete", "unknown"]


class TowerCharacteristics(StrictModel):
    structure: TowerStructure
    leg_count: int = Field(default=4, ge=1, le=4)
    base_width_m: float | None = Field(default=None, gt=0, le=30)
    top_width_m: float | None = Field(default=None, gt=0, le=30)
    foundation_type: FoundationType = "unknown"
    has_platform: bool = False
    platform_count: int = Field(default=0, ge=0, le=12)
    has_ladder: bool = False
    has_lightning_rod: bool = False
    has_aviation_light: bool = False
    material: TowerMaterial = "galvanized_steel"

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
        if not self.has_platform and self.platform_count != 0:
            raise ValueError("platform_count must be 0 when has_platform is false")
        if self.has_platform and self.platform_count == 0:
            raise ValueError("platform_count must be at least 1 when has_platform is true")
        return self
