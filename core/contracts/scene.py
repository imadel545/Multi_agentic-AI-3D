from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.contracts.assets import DimensionsM
from core.contracts.common import AssetType, NetworkType, StrictModel
from core.contracts.parametric import GenerationStrategy, GeometrySource
from core.contracts.tower import TowerCharacteristics


class RuntimeAssetMetadata(StrictModel):
    license: str | None = None
    attribution_required: bool = False
    attribution: str | None = None
    original_url: str | None = None
    original_author: str | None = None
    normalized_by: str | None = None
    pivot_policy: str | None = None
    front_axis: str | None = None
    qualification_status: str | None = None
    allowed_generation_modes: list[str] = Field(default_factory=list)
    verified_file_sha256: str | None = None
    qualification_method: str | None = None
    qualification_limitations: list[str] = Field(default_factory=list)


class SceneAssetPlacement(StrictModel):
    asset_id: str = Field(min_length=1)
    asset_file: str | None = None
    asset_source: str | None = None
    asset_metadata: RuntimeAssetMetadata = Field(default_factory=RuntimeAssetMetadata)
    import_fallback_allowed: bool = True
    dimensions_m: DimensionsM | None = None
    position: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0], min_length=3, max_length=3)
    generation_strategy: GenerationStrategy = "parametric_generated"
    geometry_source: GeometrySource = "unknown"
    generation_reason: str = "default parametric generation target"

    @field_validator("scale")
    @classmethod
    def validate_scale_positive(cls, value: list[float]) -> list[float]:
        for i, v in enumerate(value):
            if v <= 0:
                raise ValueError(f"scale[{i}] must be positive, got {v}")
        return value

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
    antenna_asset_file: str | None = None
    antenna_asset_source: str | None = None
    antenna_asset_metadata: RuntimeAssetMetadata = Field(default_factory=RuntimeAssetMetadata)
    antenna_import_fallback_allowed: bool = True
    antenna_generation_strategy: GenerationStrategy = "internal_project_generated"
    antenna_geometry_source: GeometrySource = "unknown"
    antenna_generation_reason: str = "asset policy not resolved"
    radio_asset_id: str | None = None
    radio_asset_file: str | None = None
    radio_asset_source: str | None = None
    radio_asset_metadata: RuntimeAssetMetadata = Field(default_factory=RuntimeAssetMetadata)
    radio_import_fallback_allowed: bool = True
    radio_generation_strategy: GenerationStrategy = "internal_project_generated"
    radio_geometry_source: GeometrySource = "unknown"
    radio_generation_reason: str = "asset policy not resolved"
    install_height_m: float = Field(gt=0)
    azimuth_deg: float = Field(ge=0, lt=360)
    mechanical_tilt_deg: float = Field(default=3.0, ge=-15, le=30)
    electrical_tilt_deg: float = Field(default=0.0, ge=-15, le=30)
    beamwidth_deg: float = Field(gt=0, le=360)
    beam_radius_m: float = Field(default=8.0, gt=0)
    antenna_dimensions_m: DimensionsM | None = None
    radio_dimensions_m: DimensionsM | None = None
    include_cable: bool = True
    include_label: bool = True


class SceneAccessoryPlacement(StrictModel):
    asset_id: str = Field(min_length=1)
    asset_file: str | None = None
    asset_source: str | None = None
    asset_metadata: RuntimeAssetMetadata = Field(default_factory=RuntimeAssetMetadata)
    import_fallback_allowed: bool = True
    asset_type: AssetType
    dimensions_m: DimensionsM | None = None
    position: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0], min_length=3, max_length=3)
    generation_strategy: GenerationStrategy = "internal_project_generated"
    geometry_source: GeometrySource = "unknown"
    generation_reason: str = "asset policy not resolved"
    placement_policy: Literal["derived_default", "user_defined"] = "derived_default"

    @field_validator("scale")
    @classmethod
    def validate_scale_positive(cls, value: list[float]) -> list[float]:
        for index, component in enumerate(value):
            if component <= 0:
                raise ValueError(f"scale[{index}] must be positive, got {component}")
        return value


class VisualElements(StrictModel):
    include_sector_beams: bool = True
    include_azimuth_arrows: bool = True
    include_height_markers: bool = True
    include_labels: bool = True
    include_power_cabinet: bool = False
    include_gps_antenna: bool = False


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

    @field_validator("formats")
    @classmethod
    def validate_operational_formats(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("export formats must be unique")
        if "gltf" in value:
            raise ValueError("gltf export is not operational; request glb instead")
        missing = {"glb", "png", "json_report"} - set(value)
        if missing:
            raise ValueError(
                "the verified pipeline requires glb, png and json_report; missing "
                + ", ".join(sorted(missing))
            )
        return value


class SceneSpec(StrictModel):
    schema_version: str = "1.0.0"
    scene_id: str = Field(min_length=1)
    units: Literal["meters"] = "meters"
    network_type: NetworkType
    tower: SceneAssetPlacement
    sectors: list[SectorSpec] = Field(min_length=1)
    visual_elements: VisualElements = Field(default_factory=VisualElements)
    accessory_assets: list[SceneAccessoryPlacement] = Field(default_factory=list)
    preview: PreviewSpec = Field(default_factory=PreviewSpec)
    export: ExportSpec = Field(default_factory=ExportSpec)

    @model_validator(mode="after")
    def validate_scene_geometry(self) -> "SceneSpec":
        if self.tower.position != [0.0, 0.0, 0.0]:
            raise ValueError("tower.position is not operational and must remain [0, 0, 0]")
        if self.tower.rotation_deg != [0.0, 0.0, 0.0]:
            raise ValueError("tower.rotation_deg is not operational and must remain [0, 0, 0]")
        if self.tower.scale != [1.0, 1.0, 1.0]:
            raise ValueError("tower.scale is not operational and must remain [1, 1, 1]")
        for sector in self.sectors:
            if sector.install_height_m > self.tower.height_m:
                raise ValueError(
                    f"{sector.sector_id} install_height_m exceeds tower height "
                    f"({sector.install_height_m} > {self.tower.height_m})"
                )
        return self
