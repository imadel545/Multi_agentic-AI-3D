from typing import Literal

from pydantic import Field, field_validator, model_serializer, model_validator

from core.contracts.assembly import AssemblyPlan
from core.contracts.assets import (
    DimensionsM,
    GeometryFidelity,
    PanelAntennaGeometryProfile,
    RadioGeometryProfile,
)
from core.contracts.common import AssetType, DetailLevel, NetworkType, StrictModel
from core.contracts.geometry_program import GeometryProgram
from core.contracts.parametric import GenerationStrategy, GeometrySource
from core.contracts.rigid_relations import RigidComponentRelation
from core.contracts.tower import TowerCharacteristics


class RuntimeAssetMetadata(StrictModel):
    geometry_fidelity: GeometryFidelity = "schematic"
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
    builder_profile_id: str | None = Field(default=None, min_length=1, max_length=120)


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
    antenna_geometry_profile: PanelAntennaGeometryProfile | None = None
    radio_geometry_profile: RadioGeometryProfile | None = None
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
    schema_version: Literal["1.0.0", "2.0.0"] = "1.0.0"
    scene_id: str = Field(min_length=1)
    units: Literal["meters"] = "meters"
    design_domain: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9._-]*$",
    )
    design_intent_id: str | None = Field(default=None, min_length=1, max_length=120)
    component_graph_id: str | None = Field(default=None, min_length=1, max_length=120)
    asset_decision_plan_id: str | None = Field(default=None, min_length=1, max_length=120)
    specialist_route_id: str | None = Field(default=None, min_length=1, max_length=120)
    cognitive_plan_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    network_type: NetworkType | None = None
    detail_level: DetailLevel = "high"
    tower: SceneAssetPlacement | None = None
    sectors: list[SectorSpec] = Field(default_factory=list)
    visual_elements: VisualElements = Field(default_factory=VisualElements)
    accessory_assets: list[SceneAccessoryPlacement] = Field(default_factory=list)
    assembly_plan: AssemblyPlan | None = None
    geometry_programs: list[GeometryProgram] = Field(default_factory=list, max_length=32)
    rigid_component_relations: list[RigidComponentRelation] = Field(
        default_factory=list, max_length=24, exclude_if=lambda value: not value
    )
    preview: PreviewSpec = Field(default_factory=PreviewSpec)
    export: ExportSpec = Field(default_factory=ExportSpec)

    @model_validator(mode="after")
    def validate_scene_geometry(self) -> "SceneSpec":
        program_ids = {program.program_id for program in self.geometry_programs}
        exact_ids = {
            program.program_id
            for program in self.geometry_programs
            if len(program.nodes) == 1 and program.nodes[0].kind == "exact_asset"
        }
        relation_ids = [relation.relationship_id for relation in self.rigid_component_relations]
        driven_ids = [relation.source_program_id for relation in self.rigid_component_relations]
        if len(set(relation_ids)) != len(relation_ids) or len(set(driven_ids)) != len(driven_ids):
            raise ValueError("Rigid relation IDs and driven components must be unique.")
        for relation in self.rigid_component_relations:
            if (
                self.schema_version != "2.0.0"
                or relation.source_program_id == relation.target_program_id
                or not {relation.source_program_id, relation.target_program_id} <= program_ids
                or not {relation.source_program_id, relation.target_program_id} <= exact_ids
            ):
                raise ValueError("Rigid relation requires two distinct generic programs.")
        if self.schema_version == "1.0.0":
            if self.design_domain is not None:
                raise ValueError("SceneSpec 1.0 does not accept a generic design domain")
            if self.network_type is None or self.tower is None or not self.sectors:
                raise ValueError("SceneSpec 1.0 requires telecom network, tower and sectors")
        else:
            if self.design_domain is None:
                raise ValueError("SceneSpec 2.0 requires a design domain")
            cognitive_links = (
                self.design_intent_id,
                self.component_graph_id,
                self.asset_decision_plan_id,
                self.specialist_route_id,
                self.cognitive_plan_sha256,
            )
            if any(value is None for value in cognitive_links):
                raise ValueError("SceneSpec 2.0 requires complete cognitive planning links")
            if not self.geometry_programs and self.assembly_plan is None:
                raise ValueError(
                    "SceneSpec 2.0 requires governed geometry or a trusted assembly plan"
                )
        sector_ids = [sector.sector_id for sector in self.sectors]
        if len(sector_ids) != len(set(sector_ids)):
            raise ValueError("sector_id values must be unique")
        accessory_ids = [asset.asset_id for asset in self.accessory_assets]
        if len(accessory_ids) != len(set(accessory_ids)):
            raise ValueError("accessory asset_id values must be unique")
        program_ids = [program.program_id for program in self.geometry_programs]
        if len(program_ids) != len(set(program_ids)):
            raise ValueError("geometry program IDs must be unique")
        if self.tower is not None:
            if self.tower.position != [0.0, 0.0, 0.0]:
                raise ValueError("tower.position is not operational and must remain [0, 0, 0]")
            if self.tower.rotation_deg != [0.0, 0.0, 0.0]:
                raise ValueError("tower.rotation_deg is not operational and must remain [0, 0, 0]")
            if self.tower.scale != [1.0, 1.0, 1.0]:
                raise ValueError("tower.scale is not operational and must remain [1, 1, 1]")
        for sector in self.sectors:
            if self.tower is None:
                raise ValueError("sector geometry requires a tower placement")
            if sector.install_height_m > self.tower.height_m:
                raise ValueError(
                    f"{sector.sector_id} install_height_m exceeds tower height "
                    f"({sector.install_height_m} > {self.tower.height_m})"
                )
        return self

    @model_serializer(mode="wrap")
    def serialize_scene(self, handler):
        """Keep the legacy SceneSpec 1.0 byte shape stable for certificate hashes."""

        payload = handler(self)
        if self.schema_version == "1.0.0":
            for field_name in (
                "design_domain",
                "design_intent_id",
                "component_graph_id",
                "asset_decision_plan_id",
                "specialist_route_id",
                "cognitive_plan_sha256",
            ):
                payload.pop(field_name, None)
        return payload
