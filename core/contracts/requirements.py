from pydantic import Field, field_validator, model_validator

from core.contracts.common import DetailLevel, NetworkType, StrictModel, WarningItem
from core.contracts.repair import RepairEvent
from core.contracts.tower import TowerCharacteristics


class RequirementSpec(StrictModel):
    network_type: NetworkType = "5G"
    site_type: str = "telecom_site"
    tower_type: str = Field(min_length=1)
    tower_height_m: float = Field(gt=0, le=150)
    tower_characteristics: TowerCharacteristics = Field(
        default_factory=lambda: TowerCharacteristics(
            structure="lattice",
            leg_count=4,
            base_width_m=4.0,
            top_width_m=1.0,
            foundation_type="concrete_pad",
            material="galvanized_steel",
        )
    )
    sector_count: int = Field(ge=1, le=12)
    antenna_type: str = "panel_5g"
    antenna_install_height_m: float = Field(gt=0, le=150)
    azimuths_deg: list[float]
    mechanical_tilt_deg: float = Field(default=3.0, ge=-15, le=30)
    electrical_tilt_deg: float = Field(default=0.0, ge=-15, le=30)
    beamwidth_deg: float = Field(default=65.0, gt=0, le=360)
    include_rru: bool = True
    include_cables: bool = True
    include_beams: bool = True
    include_labels: bool = True
    include_power_cabinet: bool = False
    include_gps_antenna: bool = False
    detail_level: DetailLevel = "high"
    warnings: list[WarningItem] = Field(default_factory=list)
    repair_events: list[RepairEvent] = Field(default_factory=list)

    @field_validator("azimuths_deg")
    @classmethod
    def azimuths_are_valid(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("at least one azimuth is required")
        invalid = [azimuth for azimuth in value if azimuth < 0 or azimuth >= 360]
        if invalid:
            raise ValueError(f"azimuths must be in [0, 360): {invalid}")
        return value

    @model_validator(mode="after")
    def validate_consistency(self) -> "RequirementSpec":
        if len(self.azimuths_deg) != self.sector_count:
            raise ValueError("sector_count must match len(azimuths_deg)")
        if self.antenna_install_height_m > self.tower_height_m:
            raise ValueError("antenna_install_height_m cannot exceed tower_height_m")
        return self
