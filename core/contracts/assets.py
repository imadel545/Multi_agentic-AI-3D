import math
from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import AssetType, NetworkType, StrictModel


class DimensionsM(StrictModel):
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    height: float = Field(gt=0)


class AssetBoundingBoxM(StrictModel):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @model_validator(mode="after")
    def validate_extents(self) -> "AssetBoundingBoxM":
        if any(self.maximum[index] <= self.minimum[index] for index in range(3)):
            raise ValueError("asset bounding box maximum must exceed minimum on every axis")
        return self


AssetSourceFormat = Literal[
    "blend",
    "brep",
    "dwg",
    "dxf",
    "fbx",
    "glb",
    "gltf",
    "iges",
    "ifc",
    "obj",
    "procedural",
    "step",
    "stl",
    "unknown",
]
AssetGeometryStatus = Literal[
    "exact_import",
    "neutral_format_conversion",
    "mesh_conversion",
    "reconstructed_parametric",
    "procedural_generated",
    "reference_only",
    "source_only",
    "unsupported",
]


class AssetRepresentation(StrictModel):
    representation_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9._-]*$",
    )
    role: Literal["master", "viewer", "lod"]
    format: AssetSourceFormat
    file: str = Field(min_length=1, max_length=400)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    units: Literal["meters", "millimeters", "centimeters", "inches", "unknown"]
    derived_from_representation_id: str | None = Field(default=None, max_length=96)
    tessellation_tolerance_m: float | None = Field(default=None, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_lineage(self) -> "AssetRepresentation":
        if self.role == "master" and self.derived_from_representation_id is not None:
            raise ValueError("master representation cannot declare a derived representation")
        if self.role != "master" and self.derived_from_representation_id is None:
            raise ValueError("derived asset representation must identify its source representation")
        return self


class AssetPreview(StrictModel):
    view: Literal["front", "side", "top", "perspective", "closeup"]
    file: str = Field(min_length=1, max_length=400)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int = Field(ge=64, le=16384)
    height_px: int = Field(ge=64, le=16384)
    qa_status: Literal["not_run", "passed", "failed", "review_required"] = "not_run"


class AssetLod(StrictModel):
    lod_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9._-]*$")
    representation_id: str = Field(min_length=1, max_length=96)
    maximum_screen_error_px: float | None = Field(default=None, gt=0.0, le=4096.0)
    triangle_count: int | None = Field(default=None, ge=1, le=100_000_000)


class AssetCompatibilityRules(StrictModel):
    compatible_roles: list[str] = Field(default_factory=list, max_length=48)
    required_connector_kinds: list[
        Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    ] = Field(default_factory=list, max_length=12)
    incompatible_roles: list[str] = Field(default_factory=list, max_length=48)
    maximum_adaptation_effort: Literal["none", "low", "medium", "high"] = "none"

    @model_validator(mode="after")
    def validate_rules(self) -> "AssetCompatibilityRules":
        if len(self.compatible_roles) != len(set(self.compatible_roles)):
            raise ValueError("compatible asset roles must be unique")
        if len(self.incompatible_roles) != len(set(self.incompatible_roles)):
            raise ValueError("incompatible asset roles must be unique")
        if set(self.compatible_roles) & set(self.incompatible_roles):
            raise ValueError("asset role cannot be both compatible and incompatible")
        if len(self.required_connector_kinds) != len(set(self.required_connector_kinds)):
            raise ValueError("required connector kinds must be unique")
        return self


class AssetQaEvidence(StrictModel):
    status: Literal["not_run", "passed", "failed", "limited"] = "not_run"
    report_file: str | None = Field(default=None, min_length=1, max_length=400)
    report_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checks: list[str] = Field(default_factory=list, max_length=64)
    limitations: list[str] = Field(default_factory=list, max_length=64)


class AssetDecisionPacket(StrictModel):
    """Bounded asset evidence supplied to a selector; never an execution instruction."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    asset_id: str = Field(min_length=1, max_length=120)
    asset_type: AssetType
    family: str = Field(min_length=1, max_length=120)
    subtype: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=160)
    reference: str | None = Field(default=None, max_length=160)
    source_provenance: str = Field(min_length=1, max_length=600)
    license: str | None = Field(default=None, max_length=300)
    source_format: AssetSourceFormat
    source_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    geometry_status: AssetGeometryStatus
    conversion_method: str | None = Field(default=None, max_length=300)
    geometry_fidelity: Literal["schematic", "technical_generic", "vendor_qualified"]
    qualification_status: Literal[
        "qualified_for_generation", "reference_only", "quarantined_unverified"
    ]
    generation_eligible: bool
    milestone_evidence_eligible: bool
    dimensions_m: DimensionsM | None = None
    bounding_box_m: AssetBoundingBoxM | None = None
    master_representation: AssetRepresentation | None = None
    viewer_representation: AssetRepresentation | None = None
    previews: list[AssetPreview] = Field(default_factory=list, max_length=5)
    lods: list[AssetLod] = Field(default_factory=list, max_length=8)
    anchors: list["AssetAnchor"] = Field(default_factory=list, max_length=48)
    connectors: list["AssetConnector"] = Field(default_factory=list, max_length=64)
    editable_parameters: list["AllowedAssetParameter"] = Field(default_factory=list, max_length=48)
    transform_permissions: "AssetTransformPermissions | None" = None
    compatibility: AssetCompatibilityRules = Field(default_factory=AssetCompatibilityRules)
    builder_capability_id: str | None = Field(default=None, max_length=120)
    adapter_capability_id: str | None = Field(default=None, max_length=120)
    qa: AssetQaEvidence = Field(default_factory=AssetQaEvidence)
    qualification_version: str | None = Field(default=None, max_length=64)
    allowed_generation_modes: list[Literal["parametric_generated", "imported_glb_exact"]] = Field(
        default_factory=list, max_length=2
    )
    allowed_strategies: list[
        Literal[
            "reuse_full_design",
            "adapt_full_design",
            "reuse_component",
            "adapt_component",
            "compose_assets",
            "compose_and_generate",
            "procedural_generate",
            "clarify",
            "unsupported",
        ]
    ] = Field(default_factory=list, max_length=9)
    estimated_blender_cost: Literal["low", "medium", "high"] = "medium"
    rejection_risks: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_packet_truth(self) -> "AssetDecisionPacket":
        if len(self.previews) != len({preview.view for preview in self.previews}):
            raise ValueError("asset decision packet preview views must be unique")
        if self.generation_eligible != (
            self.qualification_status == "qualified_for_generation"
            and bool(self.allowed_generation_modes)
        ):
            raise ValueError("asset decision packet generation truth is inconsistent")
        if self.milestone_evidence_eligible:
            required_views = {"front", "side", "top", "perspective", "closeup"}
            published_views = {preview.view for preview in self.previews}
            complete_evidence = (
                self.generation_eligible
                and bool(self.source_provenance)
                and bool(self.license)
                and self.master_representation is not None
                and self.viewer_representation is not None
                and self.dimensions_m is not None
                and self.bounding_box_m is not None
                and bool(self.anchors)
                and bool(self.connectors)
                and published_views == required_views
                and all(preview.qa_status == "passed" for preview in self.previews)
                and self.qa.status == "passed"
                and self.qa.report_file is not None
                and self.qa.report_sha256 is not None
                and bool(self.qa.checks)
                and self.qualification_version is not None
            )
            if not complete_evidence:
                raise ValueError("milestone evidence flag requires complete professional proof")
        if self.geometry_status in {"source_only", "reference_only", "unsupported"}:
            if self.generation_eligible:
                raise ValueError("non-executable geometry cannot be generation eligible")
            executable = {
                "reuse_full_design",
                "adapt_full_design",
                "reuse_component",
                "adapt_component",
                "compose_assets",
                "compose_and_generate",
                "procedural_generate",
            }
            if executable & set(self.allowed_strategies):
                raise ValueError("non-executable geometry cannot authorize an execution strategy")
        return self


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


class AssetAnchor(StrictModel):
    """A named local-frame attachment point, expressed exclusively in meters."""

    anchor_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    position_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    up: tuple[float, float, float] = (0.0, 0.0, 1.0)
    placement_policy: Literal["fixed", "sector_tower_surface", "ground_route"] = "fixed"
    roles: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_frame(self) -> "AssetAnchor":
        normal_length = math.sqrt(sum(component * component for component in self.normal))
        up_length = math.sqrt(sum(component * component for component in self.up))
        if normal_length <= 1e-9:
            raise ValueError("asset anchor normal must be non-zero")
        if up_length <= 1e-9:
            raise ValueError("asset anchor up vector must be non-zero")
        cross = (
            self.normal[1] * self.up[2] - self.normal[2] * self.up[1],
            self.normal[2] * self.up[0] - self.normal[0] * self.up[2],
            self.normal[0] * self.up[1] - self.normal[1] * self.up[0],
        )
        if math.sqrt(sum(component * component for component in cross)) <= 1e-9:
            raise ValueError("asset anchor normal and up vectors must define a coherent frame")
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("asset anchor roles must be unique")
        return self


class AssetConnector(StrictModel):
    connector_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    gender: Literal["source", "target", "male", "female", "bidirectional"] = "bidirectional"
    anchor_id: str = Field(min_length=1, max_length=96)
    compatible_connector_kinds: list[
        Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    ] = Field(default_factory=list, max_length=12)
    tolerance_m: float = Field(default=0.01, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_compatibility(self) -> "AssetConnector":
        if len(self.compatible_connector_kinds) != len(set(self.compatible_connector_kinds)):
            raise ValueError("compatible connector kinds must be unique")
        if self.kind not in self.compatible_connector_kinds:
            raise ValueError("connector compatibility must include its own kind")
        return self


class AssetTransformPermissions(StrictModel):
    """Fail-closed transform allowlist for exact imported geometry."""

    translation_axes: list[Literal["x", "y", "z"]] = Field(default_factory=list, max_length=3)
    rotation_axes: list[Literal["x", "y", "z"]] = Field(default_factory=list, max_length=3)
    maximum_translation_m: float = Field(default=0.0, ge=0.0, le=1000.0)
    maximum_rotation_deg: float = Field(default=0.0, ge=0.0, le=3600.0)
    uniform_scale_allowed: bool = False
    non_uniform_scale_allowed: bool = False

    @model_validator(mode="after")
    def validate_permissions(self) -> "AssetTransformPermissions":
        if len(self.translation_axes) != len(set(self.translation_axes)):
            raise ValueError("translation axes must be unique")
        if len(self.rotation_axes) != len(set(self.rotation_axes)):
            raise ValueError("rotation axes must be unique")
        if self.non_uniform_scale_allowed and not self.uniform_scale_allowed:
            raise ValueError("non-uniform scale permission requires uniform scale permission")
        return self


class AllowedAssetParameter(StrictModel):
    parameter_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    value_type: Literal["number", "integer", "boolean", "enum"]
    unit: Literal["meters", "degrees", "count", "none"] = "none"
    minimum: float | None = None
    maximum: float | None = None
    enum_values: list[str] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AllowedAssetParameter":
        if self.value_type == "enum" and not self.enum_values:
            raise ValueError("enum parameters require enum_values")
        if self.value_type != "enum" and self.enum_values:
            raise ValueError("only enum parameters may declare enum_values")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("parameter minimum must not exceed maximum")
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
    family: str | None = Field(default=None, min_length=1, max_length=120)
    subtype: str | None = Field(default=None, min_length=1, max_length=120)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=160)
    reference: str | None = Field(default=None, min_length=1, max_length=160)
    source_provenance: str | None = Field(default=None, min_length=1, max_length=600)
    source_format: AssetSourceFormat | None = None
    source_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_contains_acis_3d_solids: bool = False
    geometry_status: AssetGeometryStatus | None = None
    conversion_method: str | None = Field(default=None, min_length=1, max_length=300)
    master_representation: AssetRepresentation | None = None
    viewer_representation: AssetRepresentation | None = None
    bounding_box_m: AssetBoundingBoxM | None = None
    preview_set: list[AssetPreview] = Field(default_factory=list, max_length=5)
    material_names: list[str] = Field(default_factory=list, max_length=64)
    lods: list[AssetLod] = Field(default_factory=list, max_length=8)
    compatibility_rules: AssetCompatibilityRules = Field(default_factory=AssetCompatibilityRules)
    adapter_capability_id: str | None = Field(default=None, min_length=1, max_length=120)
    qa_evidence: AssetQaEvidence = Field(default_factory=AssetQaEvidence)
    qualification_version: str | None = Field(default=None, min_length=1, max_length=64)
    cognitive_reuse_enabled: bool = False
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
    preview_file: str | None = Field(default=None, min_length=1)
    builder_profile_id: str | None = Field(default=None, min_length=1, max_length=120)
    capability_tags: list[str] = Field(default_factory=list, max_length=32)
    anchors: list[AssetAnchor] = Field(default_factory=list, max_length=48)
    connectors: list[AssetConnector] = Field(default_factory=list, max_length=64)
    allowed_parameters: list[AllowedAssetParameter] = Field(default_factory=list, max_length=48)
    transform_permissions: AssetTransformPermissions | None = None
    qualification: AssetQualification = Field(default_factory=AssetQualification)

    @model_validator(mode="after")
    def validate_geometry_profile_role(self) -> "AssetManifest":
        if self.panel_geometry_profile is not None and self.type != "antenna":
            raise ValueError("panel_geometry_profile is only valid for antenna assets")
        if self.radio_geometry_profile is not None and self.type != "radio":
            raise ValueError("radio_geometry_profile is only valid for radio assets")
        anchor_ids = {anchor.anchor_id for anchor in self.anchors}
        if len(anchor_ids) != len(self.anchors):
            raise ValueError("asset anchor IDs must be unique")
        if any(connector.anchor_id not in anchor_ids for connector in self.connectors):
            raise ValueError("asset connectors must reference a declared anchor")
        connector_ids = [connector.connector_id for connector in self.connectors]
        if len(connector_ids) != len(set(connector_ids)):
            raise ValueError("asset connector IDs must be unique")
        parameter_ids = [parameter.parameter_id for parameter in self.allowed_parameters]
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError("allowed asset parameter IDs must be unique")
        preview_views = [preview.view for preview in self.preview_set]
        if len(preview_views) != len(set(preview_views)):
            raise ValueError("asset preview views must be unique")
        representation_ids = [
            item.representation_id
            for item in (self.master_representation, self.viewer_representation)
            if item is not None
        ]
        if len(representation_ids) != len(set(representation_ids)):
            raise ValueError("asset representation IDs must be unique")
        if self.master_representation is not None and self.master_representation.role != "master":
            raise ValueError("master_representation must use the master role")
        if self.viewer_representation is not None and self.viewer_representation.role != "viewer":
            raise ValueError("viewer_representation must use the viewer role")
        if self.viewer_representation is not None:
            if self.master_representation is None:
                raise ValueError(
                    "viewer representation requires an immutable master representation"
                )
            if (
                self.viewer_representation.derived_from_representation_id
                != self.master_representation.representation_id
            ):
                raise ValueError("viewer representation lineage must reference the master")
        if self.geometry_status == "neutral_format_conversion":
            if self.master_representation is None or self.master_representation.format not in {
                "brep",
                "iges",
                "step",
            }:
                raise ValueError("neutral conversion requires a B-Rep/IGES/STEP master")
            if self.viewer_representation is None or not self.conversion_method:
                raise ValueError("neutral conversion requires a viewer derivative and method")
        if self.source_contains_acis_3d_solids and self.source_format != "dwg":
            raise ValueError("ACIS 3DSOLID evidence is valid only for a DWG source")
        if self.source_contains_acis_3d_solids and self.resolved_geometry_status not in {
            "neutral_format_conversion",
            "reconstructed_parametric",
            "source_only",
            "unsupported",
        }:
            raise ValueError("raw DWG ACIS solids require a neutral bridge or remain source-only")
        if self.resolved_geometry_status in {"reference_only", "source_only", "unsupported"}:
            if self.qualification.status == "qualified_for_generation":
                raise ValueError("non-executable asset geometry cannot be qualified for generation")
        if self.cognitive_reuse_enabled:
            if not self.is_generation_eligible:
                raise ValueError("cognitive reuse requires generation-qualified geometry")
            if not self.compatibility_rules.compatible_roles:
                raise ValueError("cognitive reuse requires declared compatible roles")
        if self.is_generation_eligible and self.builder_profile_id is None:
            raise ValueError("generation-eligible assets require a builder_profile_id")
        if self.allows_generation_mode("imported_glb_exact"):
            if self.transform_permissions is None:
                raise ValueError("imported_glb_exact requires explicit transform permissions")
            if self.import_fallback_allowed:
                raise ValueError("imported_glb_exact must fail closed without procedural fallback")
        return self

    @property
    def is_validated(self) -> bool:
        return self.status == "validated"

    @property
    def is_generation_eligible(self) -> bool:
        return self.is_validated and self.qualification.status == "qualified_for_generation"

    def allows_generation_mode(self, mode: AssetGenerationMode) -> bool:
        return self.is_generation_eligible and mode in self.qualification.allowed_generation_modes

    @property
    def resolved_family(self) -> str:
        return self.family or self.type

    @property
    def resolved_source_format(self) -> AssetSourceFormat:
        if self.source_format is not None:
            return self.source_format
        suffix = self.file.rsplit(".", 1)[-1].lower() if "." in self.file else "unknown"
        supported = {
            "blend",
            "dwg",
            "dxf",
            "fbx",
            "glb",
            "gltf",
            "iges",
            "ifc",
            "obj",
            "step",
            "stl",
        }
        return suffix if suffix in supported else "unknown"  # type: ignore[return-value]

    @property
    def resolved_geometry_status(self) -> AssetGeometryStatus:
        if self.geometry_status is not None:
            return self.geometry_status
        if self.allows_generation_mode("imported_glb_exact"):
            return "exact_import"
        if self.allows_generation_mode("parametric_generated"):
            return "reconstructed_parametric"
        if self.qualification.status == "reference_only":
            return "reference_only"
        return "source_only"

    @property
    def milestone_evidence_declaration_failures(self) -> list[str]:
        """Return incomplete declarations for the professional M1 evidence gate.

        Runtime generation qualification is deliberately weaker than milestone
        evidence. Existing parametric assets remain usable, but they cannot be
        counted as professional evidence until the filesystem-aware verifier
        independently validates the declared representations and reports.
        """

        failures: list[str] = []
        if not self.is_generation_eligible:
            failures.append("Asset is not qualified for generation.")
        if self.source == "internal_test_minimal":
            failures.append("Internal test-minimal geometry is excluded from milestone evidence.")
        if not self.source_provenance:
            failures.append("Source provenance is not explicitly documented.")
        if not self.license:
            failures.append("Asset licence is not explicitly documented.")
        if self.geometry_fidelity != "vendor_qualified":
            failures.append("Geometry fidelity is not vendor-qualified.")
        if not (self.source_file_sha256 or self.qualification.verified_file_sha256):
            failures.append("No immutable source or qualified representation hash is published.")
        if self.master_representation is None or self.viewer_representation is None:
            failures.append("Master and viewer representations are not both published.")
        elif self.master_representation.format not in {"brep", "iges", "step"}:
            failures.append("Professional master representation is not a neutral CAD format.")
        elif self.viewer_representation.format != "glb":
            failures.append("Professional viewer representation is not a GLB.")
        if self.viewer_representation is not None:
            if self.viewer_representation.file != self.file:
                failures.append("Manifest runtime file does not match the viewer representation.")
            if (
                self.qualification.verified_file_sha256
                != self.viewer_representation.sha256
            ):
                failures.append("Qualified runtime hash does not match the viewer representation.")
        if self.dimensions_m is None or self.bounding_box_m is None:
            failures.append("Qualified dimensions and bounding box are incomplete.")
        if not self.anchors or not self.connectors:
            failures.append("Qualified anchors and connectors are incomplete.")
        required_views = {"front", "side", "top", "perspective", "closeup"}
        published_views = {preview.view for preview in self.preview_set}
        if published_views != required_views or any(
            preview.qa_status != "passed" for preview in self.preview_set
        ):
            failures.append("Five QA-passed qualification previews are not published.")
        if (
            self.qa_evidence.status != "passed"
            or not self.qa_evidence.report_file
            or not self.qa_evidence.report_sha256
            or not self.qa_evidence.checks
        ):
            failures.append("Professional asset QA evidence is incomplete or has not passed.")
        if not self.qualification_version:
            failures.append("Qualification version is not published.")
        if self.resolved_geometry_status == "reconstructed_parametric" and not (
            self.conversion_method and self.source_provenance
        ):
            failures.append("Parametric reconstruction method and provenance are incomplete.")
        return failures
