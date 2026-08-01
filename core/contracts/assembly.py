from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import Field, model_validator

from core.contracts.assets import (
    AllowedAssetParameter,
    AssetAnchor,
    AssetConnector,
    AssetTransformPermissions,
    DimensionsM,
)
from core.contracts.common import StrictModel


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


class BuilderProfileSnapshot(StrictModel):
    profile_id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=32)
    asset_types: list[str] = Field(min_length=1, max_length=16)
    allowed_generation_modes: list[Literal["parametric_generated", "imported_glb_exact"]] = Field(
        min_length=1, max_length=2
    )
    worker_handler: Literal[
        "tower_structure",
        "sector_equipment",
        "mount_bracket",
        "radio_enclosure",
        "cable_route",
        "ground_cabinet",
        "gps_radome",
    ]
    geometry_family: Literal["panel", "microwave_dish"] | None = None
    instance_strategy: Literal["single", "per_sector"]
    allowed_parameter_ids: list[str] = Field(default_factory=list, max_length=48)
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_profile_snapshot(self) -> BuilderProfileSnapshot:
        if len(self.asset_types) != len(set(self.asset_types)):
            raise ValueError("builder asset types must be unique")
        if len(self.allowed_generation_modes) != len(set(self.allowed_generation_modes)):
            raise ValueError("builder generation modes must be unique")
        if len(self.allowed_parameter_ids) != len(set(self.allowed_parameter_ids)):
            raise ValueError("builder parameter IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"profile_sha256"})
        current_hash = _canonical_sha256(payload)
        legacy_payload = {key: value for key, value in payload.items() if key != "geometry_family"}
        legacy_hash = _canonical_sha256(legacy_payload)
        is_legacy_without_geometry_family = (
            "geometry_family" not in self.model_fields_set
            and self.geometry_family is None
            and self.profile_sha256 == legacy_hash
        )
        if self.worker_handler == "sector_equipment" and not (
            self.geometry_family is not None or is_legacy_without_geometry_family
        ):
            raise ValueError("sector equipment builders require a geometry family")
        if self.profile_sha256 != current_hash and not is_legacy_without_geometry_family:
            raise ValueError("builder profile snapshot hash mismatch")
        return self


class AssetManifestSnapshot(StrictModel):
    """Immutable, self-hashed manifest boundary copied into SceneSpec."""

    asset_id: str = Field(min_length=1, max_length=120)
    asset_type: str = Field(min_length=1, max_length=48)
    manifest_version: str = Field(min_length=1, max_length=32)
    manifest_file_name: str = Field(
        min_length=6,
        max_length=180,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$",
    )
    source_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_file: str = Field(min_length=1, max_length=400)
    generation_mode: Literal["parametric_generated", "imported_glb_exact"]
    units: Literal["meters"] = "meters"
    verified_file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    builder_profile_id: str = Field(min_length=1, max_length=120)
    dimensions_m: DimensionsM | None = None
    anchors: list[AssetAnchor] = Field(default_factory=list, max_length=48)
    connectors: list[AssetConnector] = Field(default_factory=list, max_length=64)
    allowed_parameters: list[AllowedAssetParameter] = Field(default_factory=list, max_length=48)
    transform_permissions: AssetTransformPermissions | None = None
    import_fallback_allowed: bool = False

    @model_validator(mode="after")
    def validate_snapshot(self) -> AssetManifestSnapshot:
        parameter_ids = [parameter.parameter_id for parameter in self.allowed_parameters]
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError("asset manifest snapshot parameter IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"snapshot_sha256"})
        if _canonical_sha256(payload) != self.snapshot_sha256:
            raise ValueError("asset manifest snapshot hash mismatch")
        if self.generation_mode == "imported_glb_exact":
            if self.verified_file_sha256 is None:
                raise ValueError("exact asset snapshot requires a pinned GLB hash")
            if self.transform_permissions is None:
                raise ValueError("exact asset snapshot requires transform permissions")
            if self.import_fallback_allowed:
                raise ValueError("exact asset snapshot cannot authorize fallback")
        return self

    def anchor(self, anchor_id: str) -> AssetAnchor:
        match = next((anchor for anchor in self.anchors if anchor.anchor_id == anchor_id), None)
        if match is None:
            raise ValueError(f"unknown anchor {anchor_id!r} for asset {self.asset_id!r}")
        return match

    def connector(self, connector_id: str) -> AssetConnector:
        match = next(
            (connector for connector in self.connectors if connector.connector_id == connector_id),
            None,
        )
        if match is None:
            raise ValueError(f"unknown connector {connector_id!r} for asset {self.asset_id!r}")
        return match


class AssemblyFrame(StrictModel):
    position_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    up: tuple[float, float, float]

    @model_validator(mode="after")
    def validate_frame(self) -> AssemblyFrame:
        normal_length = math.sqrt(sum(component * component for component in self.normal))
        up_length = math.sqrt(sum(component * component for component in self.up))
        if normal_length <= 1e-9 or up_length <= 1e-9:
            raise ValueError("assembly frame vectors must be non-zero")
        dot = sum(self.normal[index] * self.up[index] for index in range(3)) / (
            normal_length * up_length
        )
        if abs(dot) >= 1.0 - 1e-7:
            raise ValueError("assembly frame normal and up vectors must not be parallel")
        return self


class ResolvedAssemblyInstance(StrictModel):
    instance_id: str = Field(min_length=1, max_length=120)
    apply_to_role_id: str = Field(min_length=1, max_length=96)
    source_frame_world: AssemblyFrame
    target_frame_world: AssemblyFrame
    translation_m: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    route_points_m: list[tuple[float, float, float]] = Field(default_factory=list, max_length=32)
    resolved_parameters: dict[str, float | int | bool | str] = Field(
        default_factory=dict,
        max_length=24,
    )
    connector_error_m: float = Field(ge=0.0, le=1000.0)

    @model_validator(mode="after")
    def validate_scale(self) -> ResolvedAssemblyInstance:
        if any(component <= 0 for component in self.scale):
            raise ValueError("assembly instance scale must be positive")
        return self


class AssemblyOperation(StrictModel):
    operation_id: str = Field(min_length=1, max_length=160)
    connection_id: str = Field(min_length=1, max_length=120)
    operation_type: Literal["place_component", "route_connection", "validate_connection"]
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    source_role_id: str = Field(min_length=1, max_length=96)
    source_asset_id: str = Field(min_length=1, max_length=120)
    source_connector_id: str = Field(min_length=1, max_length=96)
    source_anchor: AssetAnchor
    target_role_id: str = Field(min_length=1, max_length=96)
    target_asset_id: str = Field(min_length=1, max_length=120)
    target_connector_id: str = Field(min_length=1, max_length=96)
    target_anchor: AssetAnchor
    builder_profile_id: str = Field(min_length=1, max_length=120)
    tolerance_m: float = Field(gt=0.0, le=1.0)
    instances: list[ResolvedAssemblyInstance] = Field(min_length=1, max_length=256)
    provenance: list[str] = Field(min_length=3, max_length=16)
    operation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_operation_hash(self) -> AssemblyOperation:
        instance_ids = [instance.instance_id for instance in self.instances]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("assembly operation instance IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"operation_sha256"})
        if _canonical_sha256(payload) != self.operation_sha256:
            raise ValueError("assembly operation hash mismatch")
        return self


class AssetCandidateScore(StrictModel):
    asset_id: str = Field(min_length=1, max_length=120)
    total_score: float = Field(ge=0, le=100)
    compatibility_score: float = Field(ge=0, le=100)
    generation_score: float = Field(ge=0, le=100)
    dimensional_score: float = Field(ge=0, le=100)
    reasons: list[str] = Field(min_length=1, max_length=12)


class AssemblyComponentSelection(StrictModel):
    role_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    asset_type: str = Field(min_length=1, max_length=48)
    required: bool = True
    candidate_scores: list[AssetCandidateScore] = Field(default_factory=list, max_length=24)
    selected_asset_id: str | None = Field(default=None, min_length=1, max_length=120)
    builder_profile_id: str = Field(min_length=1, max_length=120)
    generation_strategy: Literal[
        "imported_glb_exact", "internal_project_generated", "procedural_fallback"
    ]
    allowed_parameter_ids: list[str] = Field(default_factory=list, max_length=32)
    parameter_values: dict[str, float | int | bool | str] = Field(
        default_factory=dict,
        max_length=48,
    )
    manifest_snapshot: AssetManifestSnapshot | None = None
    builder_profile: BuilderProfileSnapshot | None = None
    requirement_links: list[str] = Field(default_factory=list, max_length=16)
    blueprint_links: list[str] = Field(default_factory=list, max_length=16)
    selection_reason: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def validate_selection(self) -> AssemblyComponentSelection:
        candidate_ids = [candidate.asset_id for candidate in self.candidate_scores]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate scores must have unique asset IDs")
        if len(self.allowed_parameter_ids) != len(set(self.allowed_parameter_ids)):
            raise ValueError("component allowed parameter IDs must be unique")
        if self.selected_asset_id is not None and self.selected_asset_id not in candidate_ids:
            raise ValueError("selected asset must be one of the scored candidates")
        if (
            self.required
            and self.selected_asset_id is None
            and self.generation_strategy != "procedural_fallback"
        ):
            raise ValueError("required component needs an asset or a procedural fallback")
        if not set(self.parameter_values).issubset(self.allowed_parameter_ids):
            raise ValueError("component parameter values exceed the manifest allowlist")
        validate_component_parameter_contract(self)
        return self


def validate_component_parameter_contract(component: AssemblyComponentSelection) -> None:
    """Validate component values against the immutable manifest and builder snapshots.

    This function is intentionally callable again by the compiler because nested
    dictionaries can be mutated after Pydantic model construction.
    """

    snapshot = component.manifest_snapshot
    if snapshot is None:
        return
    manifest_parameters = {
        parameter.parameter_id: parameter for parameter in snapshot.allowed_parameters
    }
    manifest_parameter_ids = set(manifest_parameters)
    if set(component.allowed_parameter_ids) != manifest_parameter_ids:
        raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_ALLOWLIST_MISMATCH:{component.role_id}")
    if component.builder_profile is not None:
        builder_parameter_ids = set(component.builder_profile.allowed_parameter_ids)
        if not manifest_parameter_ids.issubset(builder_parameter_ids):
            raise ValueError(f"ASSEMBLY_COMPONENT_BUILDER_PARAMETER_MISMATCH:{component.role_id}")
    for parameter_id, value in component.parameter_values.items():
        contract = manifest_parameters.get(parameter_id)
        if contract is None:
            raise ValueError(
                f"ASSEMBLY_COMPONENT_PARAMETER_NOT_AUTHORIZED:{component.role_id}:{parameter_id}"
            )
        _validate_component_parameter_value(component.role_id, parameter_id, value, contract)


def _validate_component_parameter_value(
    role_id: str,
    parameter_id: str,
    value: float | int | bool | str,
    contract: AllowedAssetParameter,
) -> None:
    error_suffix = f"{role_id}:{parameter_id}"
    if contract.value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:{error_suffix}")
        return
    if contract.value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:{error_suffix}")
    elif contract.value_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:{error_suffix}")
    elif contract.value_type == "enum":
        if not isinstance(value, str):
            raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:{error_suffix}")
        if value not in contract.enum_values:
            raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_ENUM_INVALID:{error_suffix}")
        return
    if not math.isfinite(float(value)):
        raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:{error_suffix}")
    if contract.minimum is not None and float(value) < contract.minimum:
        raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_BELOW_MIN:{error_suffix}")
    if contract.maximum is not None and float(value) > contract.maximum:
        raise ValueError(f"ASSEMBLY_COMPONENT_PARAMETER_ABOVE_MAX:{error_suffix}")


class AssemblyConnection(StrictModel):
    connection_id: str = Field(min_length=1, max_length=120)
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    source_role_id: str = Field(min_length=1, max_length=96)
    source_connector_id: str = Field(min_length=1, max_length=96)
    target_role_id: str = Field(min_length=1, max_length=96)
    target_connector_id: str = Field(min_length=1, max_length=96)
    required: bool = True


class AssemblyPlan(StrictModel):
    schema_version: Literal["1.0.0", "1.1.0"] = "1.0.0"
    workflow_id: str = Field(min_length=1, max_length=120)
    units: Literal["meters"] = "meters"
    components: list[AssemblyComponentSelection] = Field(min_length=3, max_length=32)
    connections: list[AssemblyConnection] = Field(min_length=1, max_length=64)
    selection_authority: Literal["llm_bounded", "deterministic_fallback"]
    selection_provider: str | None = Field(default=None, min_length=1, max_length=80)
    selection_model: str | None = Field(default=None, min_length=1, max_length=160)
    selection_capability: Literal["asset_selection"] = "asset_selection"
    selection_contract_version: str = Field(
        default="bounded_asset_selection@1.1.0",
        min_length=1,
        max_length=80,
    )
    llm_fallback_used: bool
    llm_fallback_reason: str | None = Field(default=None, max_length=160)
    compilation_status: Literal["legacy_uncompiled", "declared", "resolved"] = "legacy_uncompiled"
    manifest_catalog_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    operations: list[AssemblyOperation] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def validate_plan(self) -> AssemblyPlan:
        roles = [component.role_id for component in self.components]
        if len(roles) != len(set(roles)):
            raise ValueError("assembly roles must be unique")
        known = set(roles)
        for connection in self.connections:
            if connection.source_role_id not in known or connection.target_role_id not in known:
                raise ValueError("assembly connection references an unknown role")
        if self.llm_fallback_used != (self.selection_authority == "deterministic_fallback"):
            raise ValueError("selection authority must match fallback truth")
        if self.llm_fallback_used and not self.llm_fallback_reason:
            raise ValueError("fallback plan requires a reason")
        if self.schema_version == "1.1.0":
            if self.compilation_status == "legacy_uncompiled":
                raise ValueError("assembly plan 1.1 requires an explicit compilation status")
            if not self.manifest_catalog_sha256:
                raise ValueError("assembly plan 1.1 requires the manifest catalog hash")
            for component in self.components:
                if component.selected_asset_id is None:
                    raise ValueError("assembly plan 1.1 requires a manifest-backed component")
                snapshot = component.manifest_snapshot
                profile = component.builder_profile
                if snapshot is None or profile is None:
                    raise ValueError("assembly plan 1.1 requires manifest and builder snapshots")
                if snapshot.asset_id != component.selected_asset_id:
                    raise ValueError("component manifest snapshot asset mismatch")
                if snapshot.builder_profile_id != component.builder_profile_id:
                    raise ValueError("component builder profile does not match its manifest")
                if profile.profile_id != component.builder_profile_id:
                    raise ValueError("component builder snapshot mismatch")
                if component.asset_type not in profile.asset_types:
                    raise ValueError("builder profile does not support the component asset type")
                manifest_mode = (
                    "imported_glb_exact"
                    if component.generation_strategy == "imported_glb_exact"
                    else "parametric_generated"
                )
                if manifest_mode not in profile.allowed_generation_modes:
                    raise ValueError("builder profile does not support the generation mode")
                validate_component_parameter_contract(component)
            if self.compilation_status == "resolved":
                operation_connections = {operation.connection_id for operation in self.operations}
                missing_operations = {
                    connection.connection_id
                    for connection in self.connections
                    if connection.required and connection.connection_id not in operation_connections
                }
                if missing_operations:
                    raise ValueError(
                        "required assembly connections are not compiled: "
                        f"{sorted(missing_operations)}"
                    )
                if not self.operations:
                    raise ValueError("resolved assembly plan requires executable operations")
        return self
