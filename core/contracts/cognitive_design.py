from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel
from core.contracts.geometry_program import GeometryProgramVector3


class DesignFunction(StrictModel):
    function_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    description: str = Field(min_length=4, max_length=500)
    priority: Literal["required", "preferred", "optional"] = "required"


class DesignConstraint(StrictModel):
    constraint_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    subject_role: str = Field(min_length=1, max_length=96)
    property_path: str = Field(min_length=1, max_length=180)
    operator: Literal[
        "equals", "minimum", "maximum", "between", "contains", "connected_to", "clearance"
    ]
    value: Any
    unit: str | None = Field(default=None, max_length=32)
    tolerance: float | None = Field(default=None, ge=0.0, le=1000.0)
    source: Literal["user", "document", "llm_inference", "domain_pack", "derived"]
    requires_confirmation: bool = False


class DesignIntent(StrictModel):
    """Domain-neutral interpretation of a user request before geometry exists."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    intent_id: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9._-]*$")
    title: str = Field(min_length=3, max_length=180)
    source_request: str = Field(min_length=3, max_length=12_000)
    coordinate_frame: Literal["meters_z_up"] = "meters_z_up"
    functions: list[DesignFunction] = Field(min_length=1, max_length=64)
    constraints: list[DesignConstraint] = Field(default_factory=list, max_length=256)
    requested_fidelity: Literal["schematic", "technical_generic", "reference_qualified"]
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    missing_information: list[str] = Field(default_factory=list, max_length=32)
    clarification_required: bool = False
    llm_provider: str = Field(min_length=1, max_length=120)
    llm_model: str = Field(min_length=1, max_length=160)
    source_prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_intent(self) -> DesignIntent:
        function_ids = [item.function_id for item in self.functions]
        constraint_ids = [item.constraint_id for item in self.constraints]
        if len(function_ids) != len(set(function_ids)):
            raise ValueError("design function IDs must be unique")
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("design constraint IDs must be unique")
        if self.clarification_required != bool(self.missing_information):
            raise ValueError("clarification truth must match missing information")
        return self


class ComponentPort(StrictModel):
    port_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    kind: Literal["anchor", "mechanical", "route", "power", "data", "fluid", "semantic"]
    position_m: GeometryProgramVector3
    direction: GeometryProgramVector3
    compatible_kinds: list[str] = Field(default_factory=list, max_length=16)


class ComponentNode(StrictModel):
    component_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9._-]*$")
    semantic_role: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    parent_component_id: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=4, max_length=800)
    quantity: int = Field(default=1, ge=1, le=512)
    functions: list[str] = Field(min_length=1, max_length=32)
    target_dimensions_m: GeometryProgramVector3 | None = None
    material_intent: list[str] = Field(default_factory=list, max_length=16)
    ports: list[ComponentPort] = Field(default_factory=list, max_length=64)
    required: bool = True
    minimum_detail_parts: int = Field(default=1, ge=1, le=512)


class ComponentRelationship(StrictModel):
    relationship_id: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "parent_child",
        "connected",
        "supported_by",
        "aligned_with",
        "distributed_on",
        "inside",
        "adjacent",
        "clearance",
    ]
    source_component_id: str
    target_component_id: str
    source_port_id: str | None = None
    target_port_id: str | None = None
    required: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=24)


class ComponentGraph(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    graph_id: str = Field(min_length=1, max_length=120)
    intent_id: str = Field(min_length=1, max_length=120)
    components: list[ComponentNode] = Field(min_length=1, max_length=512)
    relationships: list[ComponentRelationship] = Field(default_factory=list, max_length=1024)

    @model_validator(mode="after")
    def validate_graph(self) -> ComponentGraph:
        ids = [item.component_id for item in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("component IDs must be unique")
        known = set(ids)
        ports = {
            component.component_id: {port.port_id for port in component.ports}
            for component in self.components
        }
        parents = {item.component_id: item.parent_component_id for item in self.components}
        for component in self.components:
            if component.parent_component_id is not None:
                if component.parent_component_id not in known:
                    raise ValueError("component parent is unknown")
                if component.parent_component_id == component.component_id:
                    raise ValueError("component cannot parent itself")
        for component_id in ids:
            visited: set[str] = set()
            current: str | None = component_id
            while current is not None:
                if current in visited:
                    raise ValueError("component hierarchy contains a cycle")
                visited.add(current)
                current = parents[current]
        relationship_ids = [item.relationship_id for item in self.relationships]
        if len(relationship_ids) != len(set(relationship_ids)):
            raise ValueError("relationship IDs must be unique")
        for relationship in self.relationships:
            if (
                relationship.source_component_id not in known
                or relationship.target_component_id not in known
            ):
                raise ValueError("relationship references an unknown component")
            if (
                relationship.source_port_id is not None
                and relationship.source_port_id
                not in ports[relationship.source_component_id]
            ):
                raise ValueError("relationship source port is unknown")
            if (
                relationship.target_port_id is not None
                and relationship.target_port_id
                not in ports[relationship.target_component_id]
            ):
                raise ValueError("relationship target port is unknown")
        return self


class AssetCandidateEvidence(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal[
        "full_design", "subassembly", "component", "procedural_generator", "document_reference"
    ]
    qualified: bool
    compatibility_score: float = Field(ge=0.0, le=100.0)
    function_score: float = Field(ge=0.0, le=100.0)
    dimension_score: float = Field(ge=0.0, le=100.0)
    material_score: float = Field(ge=0.0, le=100.0)
    provenance_score: float = Field(ge=0.0, le=100.0)
    estimated_cost: float = Field(ge=0.0, le=100.0)
    qa_risk: float = Field(ge=0.0, le=100.0)
    allowed_strategies: list[
        Literal["reuse", "adapt", "compose", "compose_and_generate", "procedural_generate"]
    ] = Field(default_factory=list, max_length=5)
    allowed_parameter_ids: list[str] = Field(default_factory=list, max_length=64)
    limitations: list[str] = Field(default_factory=list, max_length=32)


class ComponentAssetDecision(StrictModel):
    component_id: str
    strategy: Literal[
        "reuse",
        "adapt",
        "compose",
        "compose_and_generate",
        "procedural_generate",
        "clarify",
        "unsupported",
    ]
    candidates: list[AssetCandidateEvidence] = Field(default_factory=list, max_length=48)
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=16)
    selected_parameter_values: dict[str, Any] = Field(default_factory=dict, max_length=64)
    required_capability_ids: list[str] = Field(default_factory=list, max_length=64)
    rationale: str = Field(min_length=8, max_length=1000)
    decision_authority: Literal["llm_bounded"] = "llm_bounded"

    @model_validator(mode="after")
    def validate_decision(self) -> ComponentAssetDecision:
        candidate_by_id = {item.candidate_id: item for item in self.candidates}
        if len(candidate_by_id) != len(self.candidates):
            raise ValueError("asset candidate IDs must be unique per component")
        if not set(self.selected_candidate_ids).issubset(candidate_by_id):
            raise ValueError("selected asset candidate was not supplied")
        asset_strategies = {"reuse", "adapt", "compose", "compose_and_generate"}
        if self.strategy in asset_strategies and not self.selected_candidate_ids:
            raise ValueError("selected strategy requires at least one candidate")
        for candidate_id in self.selected_candidate_ids:
            candidate = candidate_by_id[candidate_id]
            if not candidate.qualified:
                raise ValueError("an unqualified asset cannot be selected")
            if self.strategy not in candidate.allowed_strategies:
                raise ValueError("selected strategy is not authorized by the asset")
        allowed_parameters = {
            parameter_id
            for candidate_id in self.selected_candidate_ids
            for parameter_id in candidate_by_id[candidate_id].allowed_parameter_ids
        }
        if not set(self.selected_parameter_values).issubset(allowed_parameters):
            raise ValueError("asset parameter selection exceeds the allowlist")
        return self


class AssetDecisionPlan(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_id: str = Field(min_length=1, max_length=120)
    graph_id: str = Field(min_length=1, max_length=120)
    decisions: list[ComponentAssetDecision] = Field(min_length=1, max_length=512)
    llm_provider: str = Field(min_length=1, max_length=120)
    llm_model: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_plan(self) -> AssetDecisionPlan:
        component_ids = [item.component_id for item in self.decisions]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("asset decisions must be unique per component")
        return self


class SpecialistDescriptor(StrictModel):
    specialist_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    description: str = Field(min_length=8, max_length=500)
    compatible_domains: list[str] = Field(min_length=1, max_length=32)
    capability_ids: list[str] = Field(min_length=1, max_length=64)
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    required_gate: bool = False


class SpecialistRouteStep(StrictModel):
    specialist_id: str
    objective: str = Field(min_length=8, max_length=600)
    input_component_ids: list[str] = Field(default_factory=list, max_length=128)
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    execution_wave: int = Field(ge=0, le=31)


class SpecialistRoutePlan(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    route_id: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=80)
    steps: list[SpecialistRouteStep] = Field(min_length=1, max_length=32)
    rationale: str = Field(min_length=8, max_length=1000)
    llm_provider: str = Field(min_length=1, max_length=120)
    llm_model: str = Field(min_length=1, max_length=160)

    def validate_against_registry(
        self,
        descriptors: list[SpecialistDescriptor],
        component_ids: set[str],
    ) -> None:
        registry = {item.specialist_id: item for item in descriptors}
        selected = {step.specialist_id for step in self.steps}
        if len(selected) != len(self.steps):
            raise ValueError("specialist route contains duplicate specialists")
        unknown = selected - set(registry)
        if unknown:
            raise ValueError(f"specialist route contains unknown specialists: {sorted(unknown)}")
        required = {
            item.specialist_id
            for item in descriptors
            if item.required_gate
            and (
                self.domain in item.compatible_domains
                or "generic" in item.compatible_domains
            )
        }
        if not required.issubset(selected):
            missing = sorted(required - selected)
            raise ValueError(f"required specialist gates are missing: {missing}")
        step_by_id = {step.specialist_id: step for step in self.steps}
        for step in self.steps:
            descriptor_dependencies = set(registry[step.specialist_id].depends_on)
            missing_dependencies = descriptor_dependencies - selected
            if missing_dependencies:
                raise ValueError(
                    "specialist route omitted required dependencies: "
                    f"{sorted(missing_dependencies)}"
                )
            if not set(step.input_component_ids).issubset(component_ids):
                raise ValueError("specialist route references an unknown component")
            if set(step.depends_on) != descriptor_dependencies:
                raise ValueError("specialist dependencies differ from the closed registry")
            for dependency in step.depends_on:
                if step_by_id[dependency].execution_wave >= step.execution_wave:
                    raise ValueError("specialist dependency must execute in an earlier wave")


class CognitiveDesignPlan(StrictModel):
    design_intent: DesignIntent
    component_graph: ComponentGraph
    asset_decision_plan: AssetDecisionPlan
    specialist_route: SpecialistRoutePlan

    @model_validator(mode="after")
    def validate_links(self) -> CognitiveDesignPlan:
        if self.component_graph.intent_id != self.design_intent.intent_id:
            raise ValueError("component graph does not belong to the design intent")
        if self.asset_decision_plan.graph_id != self.component_graph.graph_id:
            raise ValueError("asset decision plan does not belong to the component graph")
        component_ids = {item.component_id for item in self.component_graph.components}
        decision_ids = {item.component_id for item in self.asset_decision_plan.decisions}
        if decision_ids != component_ids:
            raise ValueError("every component requires exactly one asset decision")
        return self


class DesignRouteDecision(StrictModel):
    """Bounded routing decision made before choosing the legacy or cognitive graph."""

    route: Literal["telecom_v1", "generic_cognitive_v1", "blocked"]
    inferred_domain: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9._-]*$",
    )
    rationale: str = Field(min_length=8, max_length=600)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=160)
    fallback_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=600)
