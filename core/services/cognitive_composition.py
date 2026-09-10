"""Resolve a bounded catalog composition into real rigid placements.

This first relation matches orientation and applies an explicit world offset.
It does not imply contact, fastening, clearance or collision certification.
"""

from core.contracts.cognitive_design import CognitiveDesignPlan
from core.contracts.geometry_program import GeometryProgramTransform, GeometryProgramVector3
from core.contracts.rigid_relations import RigidComponentRelation
from core.services.cognitive_asset_reuse import compile_asset_reuse


def compile_catalog_composition(registry, plan: CognitiveDesignPlan):
    decisions = {d.component_id: d for d in plan.asset_decision_plan.decisions}
    components = {c.component_id: c for c in plan.component_graph.components}
    composed = {key for key, decision in decisions.items() if decision.strategy == "compose"}
    if not composed:
        return {}, []
    exact = {key for key, d in decisions.items() if d.strategy in {"compose", "reuse"}}
    incoming = {}
    for relation in plan.component_graph.relationships:
        if not relation.required or not (
            {relation.source_component_id, relation.target_component_id} & exact
        ):
            continue
        if (
            relation.kind != "aligned_with"
            or relation.source_component_id not in composed
            or relation.target_component_id not in exact
            or relation.source_component_id == relation.target_component_id
            or relation.source_port_id is not None
            or relation.target_port_id is not None
            or set(relation.parameters) != {"offset_world_m"}
        ):
            raise ValueError("COGNITIVE_COMPOSITION_RELATION_UNSUPPORTED")
        if relation.source_component_id in incoming:
            raise ValueError("COGNITIVE_COMPOSITION_MULTIPLE_DRIVERS")
        incoming[relation.source_component_id] = relation
    if set(incoming) != composed:
        raise ValueError("COGNITIVE_COMPOSITION_REQUIRES_ALIGNMENT_DRIVER")
    placements = {}
    for key in exact:
        decision = decisions[key]
        if components[key].parent_component_id:
            raise ValueError("COGNITIVE_COMPOSITION_PARENT_UNSUPPORTED")
        if key not in composed:
            if decision.placement is None:
                raise ValueError("COGNITIVE_REUSE_REQUIRES_EXPLICIT_PLACEMENT")
            placements[key] = decision.placement
        elif decision.placement is not None:
            raise ValueError("COGNITIVE_COMPOSITION_PLACEMENT_MUST_BE_DERIVED")
    pending = set(composed)
    while pending:
        ready = [key for key in sorted(pending) if incoming[key].target_component_id in placements]
        if not ready:
            raise ValueError("COGNITIVE_COMPOSITION_CYCLE")
        for key in ready:
            relation = incoming[key]
            offset = GeometryProgramVector3.model_validate(relation.parameters["offset_world_m"])
            target = placements[relation.target_component_id]
            placements[key] = GeometryProgramTransform(
                translation_m=GeometryProgramVector3(
                    **{
                        axis: getattr(target.translation_m, axis) + getattr(offset, axis)
                        for axis in "xyz"
                    }
                ),
                rotation_deg=target.rotation_deg,
            )
            pending.remove(key)
    # Reuse admission remains the authority for roles, source hashes, singleton
    # scope and transform permissions. Only relations resolved above are removed
    # from this internal validation view, never from the persisted cognitive plan.
    admission_plan = plan.model_copy(deep=True)
    admission_plan.component_graph.relationships = [
        r
        for r in admission_plan.component_graph.relationships
        if r.relationship_id not in {r.relationship_id for r in incoming.values()}
    ]
    programs = {}
    for key in exact:
        decision = decisions[key].model_copy(update={"placement": placements[key]})
        programs[key] = compile_asset_reuse(registry, admission_plan, components[key], decision)
        if key in composed:
            programs[key] = programs[key].model_copy(
                update={"generator_model": "catalog_rigid_composition"}
            )
    relations = [
        RigidComponentRelation(
            relationship_id=relation.relationship_id,
            source_program_id=programs[key].program_id,
            target_program_id=programs[relation.target_component_id].program_id,
            offset_world_m=GeometryProgramVector3.model_validate(
                relation.parameters["offset_world_m"]
            ),
        )
        for key, relation in incoming.items()
    ]
    return programs, relations
