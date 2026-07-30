from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import AssetType, NetworkType, StrictModel


class DimensionsM(StrictModel):
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    height: float = Field(gt=0)


class PanelAntennaGeometryProfile(StrictModel):
    """Bounded procedural detail contract for a generic sector antenna.

    The profile is selected from an asset manifest/blueprint.  It describes
    supported builder parameters; it is not free-form Blender code.
    """

    family: Literal["sector_panel_v1"] = "sector_panel_v1"
    rear_mount_rail_count: int = Field(default=2, ge=2, le=4)
    bottom_port_count: int = Field(default=4, ge=2, le=8)
    radome_bevel_ratio: float = Field(default=0.035, ge=0.01, le=0.08)


class RadioGeometryProfile(StrictModel):
    """Bounded procedural detail and mounting contract for a generic RRU."""

    family: Literal["rru_enclosure_v1"] = "rru_enclosure_v1"
    heat_sink_fin_count: int = Field(default=8, ge=4, le=16)
    bottom_connector_count: int = Field(default=4, ge=2, le=8)
    mounting_rail_count: int = Field(default=2, ge=2, le=4)
    enclosure_bevel_ratio: float = Field(default=0.04, ge=0.01, le=0.08)
    vertical_offset_m: float = Field(default=1.0, ge=0.25, le=3.0)
    radial_inset_m: float = Field(default=0.08, ge=0.0, le=0.5)
    include_status_indicator: bool = True
    include_label_plate: bool = True


class MountZone(StrictModel):
    name: str = Field(min_length=1)
    min_height_m: float = Field(ge=0)
    max_height_m: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "MountZone":
        if self.max_height_m < self.min_height_m:
            raise ValueError("max_height_m must be greater than or equal to min_height_m")
        return self


AssetQualificationStatus = Literal[
    "qualified_for_generation",
    "reference_only",
    "quarantined_unverified",
]
AssetGenerationMode = Literal[
    "parametric_generated",
    "imported_glb_exact",
]
GeometryFidelity = Literal[
    "schematic",
    "technical_generic",
    "vendor_qualified",
]


class AssetQualification(StrictModel):
    """Auditable authorization for using an asset in the generation path.

    File presence is deliberately insufficient. Exact GLB import requires a
    pinned file hash plus verified mesh integrity, dimensions, pivot and
    orientation. Parametric templates remain useful without authorizing their
    companion GLB for import.
    """

    status: AssetQualificationStatus = "quarantined_unverified"
    allowed_generation_modes: list[AssetGenerationMode] = Field(default_factory=list)
    verified_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    units: Literal["meters"] = "meters"
    mesh_integrity_verified: bool = False
    dimensions_verified: bool = False
    pivot_verified: bool = False
    orientation_verified: bool = False
    qualification_method: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_import_authorization(self) -> "AssetQualification":
        if len(self.allowed_generation_modes) != len(set(self.allowed_generation_modes)):
            raise ValueError("allowed_generation_modes must be unique")
        if self.status != "qualified_for_generation" and self.allowed_generation_modes:
            raise ValueError("only qualified assets may declare generation modes")
        if "imported_glb_exact" in self.allowed_generation_modes:
            required_checks = (
                self.verified_file_sha256,
                self.mesh_integrity_verified,
                self.dimensions_verified,
                self.pivot_verified,
                self.orientation_verified,
            )
            if not all(required_checks):
                raise ValueError(
                    "imported_glb_exact requires a pinned hash and all geometry checks"
                )
        return self


class AssetManifest(StrictModel):
    asset_id: str = Field(min_length=1)
    type: AssetType
    file: str = Field(min_length=1)
    height_m: float | None = Field(default=None, gt=0)
    dimensions_m: DimensionsM | None = None
    compatible_networks: list[NetworkType]
    compatible_tower_types: list[str] = Field(default_factory=list)
    mount_zones: list[MountZone] = Field(default_factory=list)
    status: str = "validated"
    version: str = "1.0.0"
    geometry_fidelity: GeometryFidelity = "schematic"
    source: Literal[
        "vendor_expected",
        "vendor_supplied",
        "cc0",
        "cc_by",
        "royalty_free",
        "internal_cleaned",
        "internal_test_minimal",
        "internal_project_generated",
    ] = "vendor_expected"
    license: str | None = None
    attribution_required: bool = False
    attribution: str | None = None
    original_url: str | None = None
    original_author: str | None = None
    normalized_by: str | None = None
    pivot_policy: str | None = None
    front_axis: str | None = None
    import_fallback_allowed: bool = True
    adaptation_profile_id: str | None = Field(default=None, min_length=1)
    panel_geometry_profile: PanelAntennaGeometryProfile | None = None
    radio_geometry_profile: RadioGeometryProfile | None = None
    qualification: AssetQualification = Field(default_factory=AssetQualification)

    @model_validator(mode="after")
    def validate_geometry_profile_role(self) -> "AssetManifest":
        if self.panel_geometry_profile is not None and self.type != "antenna":
            raise ValueError("panel_geometry_profile is only valid for antenna assets")
        if self.radio_geometry_profile is not None and self.type != "radio":
            raise ValueError("radio_geometry_profile is only valid for radio assets")
        return self

    @property
    def is_validated(self) -> bool:
        return self.status == "validated"

    @property
    def is_generation_eligible(self) -> bool:
        return self.is_validated and self.qualification.status == "qualified_for_generation"

    def allows_generation_mode(self, mode: AssetGenerationMode) -> bool:
        return self.is_generation_eligible and mode in self.qualification.allowed_generation_modes
