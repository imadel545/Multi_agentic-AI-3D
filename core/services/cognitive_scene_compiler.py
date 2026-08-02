from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from core.contracts.capabilities import CapabilityInvocation, CapabilityObservation
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.contracts.common import DetailLevel
from core.contracts.geometry_program import GeometryProgram
from core.contracts.scene import PreviewSpec, SceneSpec, VisualElements
from core.services.capability_registry import CapabilityRegistry
from core.services.geometry_capabilities import (
    capability_id_for_geometry_node,
    geometry_capability_registry,
)


@dataclass(frozen=True)
class CognitiveSceneCompilation:
    scene: SceneSpec
    capability_observations: tuple[CapabilityObservation, ...]


def cognitive_plan_hash(plan: CognitiveDesignPlan) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CognitiveSceneCompiler:
    """Compile a validated cognitive plan into the single authoritative SceneSpec."""

    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry or geometry_capability_registry()

    def compile(
        self,
        *,
        workflow_id: str,
        plan: CognitiveDesignPlan,
        geometry_programs: list[GeometryProgram],
        detail_level: DetailLevel = "high",
    ) -> SceneSpec:
        return self.compile_with_observations(
            workflow_id=workflow_id,
            plan=plan,
            geometry_programs=geometry_programs,
            detail_level=detail_level,
        ).scene

    def compile_with_observations(
        self,
        *,
        workflow_id: str,
        plan: CognitiveDesignPlan,
        geometry_programs: list[GeometryProgram],
        detail_level: DetailLevel = "high",
    ) -> CognitiveSceneCompilation:
        if plan.design_intent.clarification_required:
            raise ValueError("COGNITIVE_PLAN_REQUIRES_CLARIFICATION")
        blocked = [
            decision.component_id
            for decision in plan.asset_decision_plan.decisions
            if decision.strategy in {"clarify", "unsupported"}
        ]
        if blocked:
            raise ValueError(f"COGNITIVE_COMPONENTS_BLOCKED:{sorted(blocked)}")

        graph_components = {
            component.component_id: component for component in plan.component_graph.components
        }
        program_by_role = {program.semantic_role: program for program in geometry_programs}
        if len(program_by_role) != len(geometry_programs):
            raise ValueError("COGNITIVE_GEOMETRY_PROGRAM_ROLES_DUPLICATED")
        generated_strategies = {"procedural_generate", "compose_and_generate"}
        for decision in plan.asset_decision_plan.decisions:
            component = graph_components[decision.component_id]
            if decision.strategy in generated_strategies:
                program = program_by_role.get(component.semantic_role)
                if program is None:
                    raise ValueError(
                        "COGNITIVE_GEOMETRY_PROGRAM_MISSING:"
                        f"{decision.component_id}:{component.semantic_role}"
                    )
                if program.requested_quantity != component.quantity:
                    raise ValueError(
                        "COGNITIVE_GEOMETRY_QUANTITY_MISMATCH:"
                        f"{decision.component_id}"
                    )
            elif decision.strategy in {"reuse", "adapt", "compose"}:
                raise ValueError(
                    "COGNITIVE_GENERIC_ASSET_ASSEMBLY_NOT_COMPILED:"
                    f"{decision.component_id}:{decision.strategy}"
                )

        required_roles = {
            graph_components[decision.component_id].semantic_role
            for decision in plan.asset_decision_plan.decisions
            if decision.strategy in generated_strategies
        }
        extra_roles = set(program_by_role) - required_roles
        if extra_roles:
            raise ValueError(f"COGNITIVE_GEOMETRY_PROGRAM_UNPLANNED:{sorted(extra_roles)}")
        for decision in plan.asset_decision_plan.decisions:
            for capability_id in decision.required_capability_ids:
                self.capability_registry.definition(capability_id)
        observations = self._validate_program_capabilities(workflow_id, geometry_programs)
        scene = SceneSpec(
            schema_version="2.0.0",
            scene_id=workflow_id,
            design_domain=plan.design_intent.domain,
            design_intent_id=plan.design_intent.intent_id,
            component_graph_id=plan.component_graph.graph_id,
            asset_decision_plan_id=plan.asset_decision_plan.plan_id,
            specialist_route_id=plan.specialist_route.route_id,
            cognitive_plan_sha256=cognitive_plan_hash(plan),
            detail_level=detail_level,
            geometry_programs=geometry_programs,
            visual_elements=VisualElements(
                include_sector_beams=False,
                include_azimuth_arrows=False,
                include_height_markers=False,
                include_labels=False,
            ),
            preview=PreviewSpec(camera="isometric"),
        )
        return CognitiveSceneCompilation(
            scene=scene,
            capability_observations=tuple(observations),
        )

    def _validate_program_capabilities(
        self,
        workflow_id: str,
        programs: list[GeometryProgram],
    ) -> list[CapabilityObservation]:
        observations: list[CapabilityObservation] = []
        items: list[tuple[str, object, str]] = []
        for program in programs:
            items.extend(
                (
                    capability_id_for_geometry_node(node.kind),
                    node,
                    f"node:{program.program_id}:{node.node_id}",
                )
                for node in program.nodes
            )
            items.extend(
                ("geometry.anchor@2.0.0", anchor, f"anchor:{program.program_id}:{anchor.anchor_id}")
                for anchor in program.anchors
            )
            items.extend(
                (
                    "geometry.connector@2.0.0",
                    connector,
                    f"connector:{program.program_id}:{connector.connector_id}",
                )
                for connector in program.connectors
            )
            items.extend(
                (
                    "geometry.semantic_group@2.0.0",
                    group,
                    f"semantic_group:{program.program_id}:{group.group_id}",
                )
                for group in program.semantic_groups
            )
        for capability_id, value, suffix in items:
            observation = self.capability_registry.execute(
                CapabilityInvocation(
                    capability_id=capability_id,
                    arguments=value.model_dump(mode="json"),
                    requested_permissions=["mutate_scene_spec"],
                    correlation_id=f"{workflow_id}:{suffix}",
                )
            )
            if observation.status != "completed":
                raise ValueError(
                    f"COGNITIVE_CAPABILITY_REJECTED:{capability_id}:{observation.error_code}"
                )
            observations.append(observation)
        return observations
