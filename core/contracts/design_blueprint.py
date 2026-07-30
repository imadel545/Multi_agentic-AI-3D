from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from core.contracts.assets import GeometryFidelity
from core.contracts.common import AssetType, DetailLevel, NetworkType, StrictModel
from core.contracts.parametric import GenerationStrategy
from core.contracts.runtime import ActorKind, DecisionAuthority

BlueprintId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SemanticRoleId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9._-]*$",
    ),
]


class BlueprintAssetQuery(StrictModel):
    """Declarative catalog query; never a filesystem path or Blender command."""

    asset_type: AssetType
    network_type: NetworkType
    compatible_tower_type: str = Field(min_length=1, max_length=80)
    required_capability_tags: list[str] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def validate_unique_tags(self) -> BlueprintAssetQuery:
        if len(self.required_capability_tags) != len(set(self.required_capability_tags)):
            raise ValueError("required_capability_tags must be unique")
        return self


class BlueprintParameter(StrictModel):
    """One bounded, typed parameter selected outside Blender."""

    parameter_id: SemanticRoleId
    value_type: Literal["number", "integer", "boolean", "enum", "vector3"]
    number_value: float | None = None
    integer_value: int | None = None
    boolean_value: bool | None = None
    enum_value: str | None = Field(default=None, max_length=96)
    vector3_value: tuple[float, float, float] | None = None
    unit: str | None = Field(default=None, max_length=32)
    source: Literal["requirement", "planning_decision", "asset_manifest", "derived_rule"]

    @model_validator(mode="after")
    def validate_discriminated_value(self) -> BlueprintParameter:
        values = {
            "number": self.number_value,
            "integer": self.integer_value,
            "boolean": self.boolean_value,
            "enum": self.enum_value,
            "vector3": self.vector3_value,
        }
        populated = [name for name, value in values.items() if value is not None]
        if populated != [self.value_type]:
            raise ValueError(
                f"value_type={self.value_type!r} requires exactly its matching value field"
            )
        return self


class ComponentIntent(StrictModel):
    intent_id: BlueprintId
    semantic_role_id: SemanticRoleId
    asset_type: AssetType
    instance_strategy_id: Literal["single", "per_sector"]
    quantity: int = Field(ge=1, le=256)
    asset_query: BlueprintAssetQuery
    resolved_asset_id: str | None = Field(default=None, min_length=1, max_length=120)
    generation_strategy: GenerationStrategy
    geometry_profile_id: str | None = Field(default=None, min_length=1, max_length=120)
    geometry_fidelity: GeometryFidelity
    placement_strategy_id: SemanticRoleId
    parameters: list[BlueprintParameter] = Field(default_factory=list, max_length=48)
    required: bool = True
    provenance: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_intent(self) -> ComponentIntent:
        if self.instance_strategy_id == "single" and self.quantity != 1:
            raise ValueError("single component intent must have quantity=1")
        parameter_ids = [parameter.parameter_id for parameter in self.parameters]
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError("component parameter IDs must be unique")
        if any("/" in item or "\\" in item for item in self.provenance):
            raise ValueError("blueprint provenance accepts identifiers, not filesystem paths")
        return self


class ConnectionIntent(StrictModel):
    connection_id: BlueprintId
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    source_intent_id: BlueprintId
    target_intent_id: BlueprintId
    source_connector_role: SemanticRoleId
    target_connector_role: SemanticRoleId
    route_strategy_id: SemanticRoleId
    required: bool = True
    provenance: list[str] = Field(min_length=1, max_length=12)


class BlueprintConstraint(StrictModel):
    constraint_id: BlueprintId
    domain: SemanticRoleId
    field_path: str = Field(
        min_length=1,
        max_length=180,
        pattern=r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*(?:\[\])?$",
    )
    operator: Literal["equals", "minimum", "maximum", "present"]
    value: float | int | bool | str | tuple[float, ...] | None = None
    source: Literal["requirement", "planning_decision", "asset_manifest", "derived_rule"]

    @model_validator(mode="after")
    def validate_value(self) -> BlueprintConstraint:
        if self.operator == "present" and self.value is not None:
            raise ValueError("present constraint cannot carry a value")
        if self.operator != "present" and self.value is None:
            raise ValueError(f"{self.operator} constraint requires a value")
        return self


class BlueprintSpecialistDecision(StrictModel):
    specialist_id: BlueprintId
    domain: SemanticRoleId
    status: Literal["passed", "warning", "failed"]
    actor_kind: ActorKind
    decision_authority: DecisionAuthority
    checks: dict[str, bool] = Field(default_factory=dict, max_length=64)
    warning_codes: list[str] = Field(default_factory=list, max_length=32)
    error_codes: list[str] = Field(default_factory=list, max_length=32)


class BlueprintIssue(StrictModel):
    code: str = Field(min_length=1, max_length=96, pattern=r"^[A-Z][A-Z0-9_]*$")
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=320)


class DesignBlueprint(StrictModel):
    """Planning intent between requirements and SceneSpec.

    SceneSpec remains the sole source of truth for generated geometry.  This
    contract exists to make composition, specialist authority and compilation
    coverage explicit and hashable.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    blueprint_id: BlueprintId
    workflow_id: BlueprintId
    requirements_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    planning_resolution_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    network_type: NetworkType
    detail_level: DetailLevel
    component_intents: list[ComponentIntent] = Field(min_length=2, max_length=256)
    connection_intents: list[ConnectionIntent] = Field(default_factory=list, max_length=512)
    constraints: list[BlueprintConstraint] = Field(default_factory=list, max_length=256)
    required_specialist_domains: list[SemanticRoleId] = Field(min_length=1, max_length=32)
    specialist_decisions: list[BlueprintSpecialistDecision] = Field(
        min_length=1,
        max_length=32,
    )
    planning_fields_applied: list[str] = Field(default_factory=list, max_length=16)
    open_issues: list[BlueprintIssue] = Field(default_factory=list, max_length=64)
    composition_mode: Literal["validated_catalog_deterministic"] = "validated_catalog_deterministic"
    source_of_truth: Literal["planning_only_scene_spec_controls_generation"] = (
        "planning_only_scene_spec_controls_generation"
    )

    @model_validator(mode="after")
    def validate_references_and_specialists(self) -> DesignBlueprint:
        intent_ids = [intent.intent_id for intent in self.component_intents]
        if len(intent_ids) != len(set(intent_ids)):
            raise ValueError("component intent IDs must be unique")
        known_intents = set(intent_ids)
        connection_ids = [item.connection_id for item in self.connection_intents]
        if len(connection_ids) != len(set(connection_ids)):
            raise ValueError("connection intent IDs must be unique")
        for connection in self.connection_intents:
            if (
                connection.source_intent_id not in known_intents
                or connection.target_intent_id not in known_intents
            ):
                raise ValueError("connection intent references an unknown component intent")
        constraint_ids = [constraint.constraint_id for constraint in self.constraints]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("blueprint constraint IDs must be unique")
        domains = [decision.domain for decision in self.specialist_decisions]
        if len(domains) != len(set(domains)):
            raise ValueError("specialist domains must be unique")
        if len(self.required_specialist_domains) != len(set(self.required_specialist_domains)):
            raise ValueError("required specialist domains must be unique")
        missing = set(self.required_specialist_domains) - set(domains)
        if missing:
            raise ValueError(f"required specialist domains are missing: {sorted(missing)}")
        failed = [
            decision.domain
            for decision in self.specialist_decisions
            if decision.domain in self.required_specialist_domains and decision.status == "failed"
        ]
        if failed:
            raise ValueError(f"required specialist decisions failed: {sorted(failed)}")
        if any(issue.severity == "error" for issue in self.open_issues):
            raise ValueError("a generation blueprint cannot contain unresolved error issues")
        return self


class BlueprintCoverageCheck(StrictModel):
    path: str = Field(min_length=1, max_length=180)
    expected: object
    actual: object
    passed: bool


class BlueprintCoverageReport(StrictModel):
    blueprint_id: BlueprintId
    stage: Literal["requirements_to_blueprint", "blueprint_to_scene"]
    passed: bool
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    checks: list[BlueprintCoverageCheck] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)
