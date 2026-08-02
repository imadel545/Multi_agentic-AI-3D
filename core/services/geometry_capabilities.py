from __future__ import annotations

from pydantic import BaseModel

from core.contracts.capabilities import CapabilityCost, CapabilityDefinition
from core.contracts.geometry_program import (
    GeometryArrayNode,
    GeometryBooleanNode,
    GeometryCurveNode,
    GeometryExtrudeNode,
    GeometryInstanceNode,
    GeometryModifierNode,
    GeometryPrimitiveNode,
    GeometryProfileNode,
    GeometryProgramAnchor,
    GeometryProgramConnector,
    GeometryProgramSemanticGroup,
    GeometryRevolveNode,
    GeometrySweepNode,
    GeometryTerrainNode,
)
from core.services.capability_registry import CapabilityRegistration, CapabilityRegistry

GEOMETRY_NODE_CAPABILITY_IDS = {
    "primitive": "geometry.primitive@1.0.0",
    "curve": "geometry.curve@1.0.0",
    "instance": "geometry.instance@1.0.0",
    "profile": "geometry.profile_2d@2.0.0",
    "extrude": "geometry.extrude_profile@2.0.0",
    "revolve": "geometry.revolve_profile@2.0.0",
    "sweep": "geometry.sweep_profile@2.0.0",
    "array": "geometry.linear_array@2.0.0",
    "boolean": "geometry.boolean_exact@2.0.0",
    "modifier": "geometry.bounded_modifier@2.0.0",
    "terrain": "geometry.terrain_surface@2.0.0",
}

_NODE_MODELS: dict[str, type[BaseModel]] = {
    "primitive": GeometryPrimitiveNode,
    "curve": GeometryCurveNode,
    "instance": GeometryInstanceNode,
    "profile": GeometryProfileNode,
    "extrude": GeometryExtrudeNode,
    "revolve": GeometryRevolveNode,
    "sweep": GeometrySweepNode,
    "array": GeometryArrayNode,
    "boolean": GeometryBooleanNode,
    "modifier": GeometryModifierNode,
    "terrain": GeometryTerrainNode,
}

_DESCRIPTIONS = {
    "primitive": "Create a bounded box, cylinder, cone or UV sphere in meters.",
    "curve": "Create a bounded polyline or cyclic curve with a fixed bevel depth.",
    "instance": "Create a linked deterministic instance of an existing program node.",
    "profile": "Declare a validated planar profile for controlled downstream operations.",
    "extrude": "Extrude a closed planar profile through a bounded distance in meters.",
    "revolve": "Revolve a non-negative radial profile around its governed local axis.",
    "sweep": "Sweep a closed planar profile along a validated bounded polyline path.",
    "array": "Create a bounded linear array from a validated mesh-producing source.",
    "boolean": "Apply an exact union, difference or intersection to validated mesh operands.",
    "modifier": "Apply only the declared bevel, solidify or mirror modifier contract.",
    "terrain": "Create a bounded deterministic terrain heightfield from meter elevations.",
}


def geometry_capability_registry() -> CapabilityRegistry:
    registrations = [
        _registration(
            capability_id=GEOMETRY_NODE_CAPABILITY_IDS[kind],
            description=_DESCRIPTIONS[kind],
            model=model,
            version=GEOMETRY_NODE_CAPABILITY_IDS[kind].rsplit("@", 1)[1],
            cost_class="medium" if kind in {"boolean", "terrain"} else "low",
            seconds=2.0 if kind in {"boolean", "terrain"} else 0.5,
        )
        for kind, model in _NODE_MODELS.items()
    ]
    registrations.extend(
        [
            _registration(
                capability_id="geometry.anchor@2.0.0",
                description="Declare a bounded local attachment frame on a generated node.",
                model=GeometryProgramAnchor,
                version="2.0.0",
                cost_class="negligible",
                seconds=0.1,
            ),
            _registration(
                capability_id="geometry.connector@2.0.0",
                description="Declare a typed connector referencing a validated geometry anchor.",
                model=GeometryProgramConnector,
                version="2.0.0",
                cost_class="negligible",
                seconds=0.1,
            ),
            _registration(
                capability_id="geometry.semantic_group@2.0.0",
                description="Group validated geometry nodes under a stable semantic role.",
                model=GeometryProgramSemanticGroup,
                version="2.0.0",
                cost_class="negligible",
                seconds=0.1,
            ),
        ]
    )
    return CapabilityRegistry(registrations)


def capability_id_for_geometry_node(kind: str) -> str:
    try:
        return GEOMETRY_NODE_CAPABILITY_IDS[kind]
    except KeyError as exc:
        raise ValueError(f"GEOMETRY_CAPABILITY_UNKNOWN_NODE_KIND:{kind}") from exc


def _registration(
    *,
    capability_id: str,
    description: str,
    model: type[BaseModel],
    version: str,
    cost_class: str,
    seconds: float,
) -> CapabilityRegistration:
    definition = CapabilityDefinition(
        capability_id=capability_id,
        description=description,
        input_schema=model.model_json_schema(),
        output_schema=model.model_json_schema(),
        compatible_domains=["generic", "telecom", "architecture", "environment"],
        capability_tags=["geometry_program", "deterministic_compiler"],
        cost=CapabilityCost(
            class_name=cost_class,  # type: ignore[arg-type]
            estimated_seconds=seconds,
            estimated_memory_mb=64,
        ),
        permissions=["mutate_scene_spec"],
        timeout_s=5.0,
        possible_errors=[
            "CAPABILITY_ARGUMENTS_INVALID",
            "CAPABILITY_PERMISSION_DENIED",
            "CAPABILITY_EXECUTION_FAILED",
        ],
        version=version,
        generated_proofs=["validated_geometry_program_operation"],
    )
    return CapabilityRegistration(
        definition=definition,
        input_model=model,
        output_model=model,
        executor=lambda validated: validated,
    )
