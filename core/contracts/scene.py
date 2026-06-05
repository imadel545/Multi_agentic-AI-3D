from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.contracts.common import NetworkType, StrictModel
from core.contracts.tower import TowerCharacteristics


class SceneAssetPlacement(StrictModel):
    asset_id: str = Field(min_length=1)
    position: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0], min_length=3, max_length=3)
    height_m: float = Field(gt=0)
    characteristics: TowerCharacteristics = Field(
        default_factory=lambda: TowerCharacteristics(
            structure="lattice",
            leg_count=4,
            base_width_m=4.0,
            top_width_m=1.0,
            foundation_type="concrete_pad",
            material="galvanized_steel",
        )
    )


class SectorSpec(StrictModel):
    sector_id: str = Field(min_length=1)
    antenna_asset_id: str = Field(min_length=1)
    radio_asset_id: str | None = None
    install_height_m: float = Field(gt=0)
    azimuth_deg: float = Field(ge=0, lt=360)
    mechanical_tilt_deg: float = Field(default=3.0, ge=-15, le=30)
    electrical_tilt_deg: float = Field(default=0.0, ge=-15, le=30)
    beamwidth_deg: float = Field(gt=0, le=360)
    beam_radius_m: float = Field(default=8.0, gt=0)
    include_cable: bool = True
    include_label: bool = True


class VisualElements(StrictModel):
    include_sector_beams: bool = True
    include_azimuth_arrows: bool = True
    include_height_markers: bool = True
    include_labels: bool = True


class PreviewSpec(StrictModel):
    camera: Literal["isometric", "front", "top"] = "isometric"
    resolution: list[int] = Field(default_factory=lambda: [1920, 1080], min_length=2, max_length=2)

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: list[int]) -> list[int]:
        width, height = value
        if width < 320 or height < 240:
            raise ValueError("preview resolution is too small")
        return value


class ExportSpec(StrictModel):
    formats: list[Literal["glb", "gltf", "png", "json_report"]] = Field(
        default_factory=lambda: ["glb", "png", "json_report"]
    )


class SceneSpec(StrictModel):
    schema_version: str = "1.0.0"
    scene_id: str = Field(min_length=1)
    units: Literal["meters"] = "meters"
    network_type: NetworkType
    tower: SceneAssetPlacement
    sectors: list[SectorSpec] = Field(min_length=1)
    visual_elements: VisualElements = Field(default_factory=VisualElements)
    preview: PreviewSpec = Field(default_factory=PreviewSpec)
    export: ExportSpec = Field(default_factory=ExportSpec)

    @model_validator(mode="after")
    def validate_scene_geometry(self) -> "SceneSpec":
        for sector in self.sectors:
            if sector.install_height_m > self.tower.height_m:
                raise ValueError(
                    f"{sector.sector_id} install_height_m exceeds tower height "
                    f"({sector.install_height_m} > {self.tower.height_m})"
                )
        return self
