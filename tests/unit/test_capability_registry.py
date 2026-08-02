from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from core.contracts.capabilities import (
    CapabilityCost,
    CapabilityDefinition,
    CapabilityInvocation,
)
from core.services.capability_registry import CapabilityRegistration, CapabilityRegistry
from core.services.geometry_capabilities import geometry_capability_registry


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doubled: int


def _definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="geometry.test_double@1.0.0",
        description="Double a bounded integer for registry verification.",
        input_schema=Input.model_json_schema(),
        output_schema=Output.model_json_schema(),
        compatible_domains=["generic"],
        capability_tags=["geometry_program"],
        cost=CapabilityCost(
            class_name="negligible",
            estimated_seconds=0.001,
            estimated_memory_mb=1,
        ),
        permissions=["mutate_plan"],
        timeout_s=1.0,
        possible_errors=["CAPABILITY_ARGUMENTS_INVALID"],
        version="1.0.0",
        generated_proofs=["test_observation"],
    )


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            CapabilityRegistration(
                definition=_definition(),
                input_model=Input,
                output_model=Output,
                executor=lambda item: {"doubled": item.value * 2},
            )
        ]
    )


def test_registry_discovers_validates_and_executes_registered_capability() -> None:
    registry = _registry()

    discovered = registry.discover(domain="generic", required_tags=["geometry_program"])
    observation = registry.execute(
        CapabilityInvocation(
            capability_id="geometry.test_double@1.0.0",
            arguments={"value": 4},
            requested_permissions=["mutate_plan"],
            correlation_id="test:double",
        )
    )

    assert [item.capability_id for item in discovered] == ["geometry.test_double@1.0.0"]
    assert observation.status == "completed"
    assert observation.output == {"doubled": 8}
    assert observation.proof_refs == ["test_observation"]


def test_registry_fails_closed_for_unknown_invalid_or_forbidden_invocations() -> None:
    registry = _registry()

    unknown = registry.execute(
        CapabilityInvocation(
            capability_id="geometry.invented@1.0.0",
            arguments={},
            correlation_id="test:unknown",
        )
    )
    invalid = registry.execute(
        CapabilityInvocation(
            capability_id="geometry.test_double@1.0.0",
            arguments={"value": "four"},
            correlation_id="test:invalid",
        )
    )
    forbidden = registry.execute(
        CapabilityInvocation(
            capability_id="geometry.test_double@1.0.0",
            arguments={"value": 4},
            requested_permissions=["execute_blender"],
            correlation_id="test:forbidden",
        )
    )

    assert unknown.error_code == "CAPABILITY_UNKNOWN"
    assert invalid.error_code == "CAPABILITY_ARGUMENTS_INVALID"
    assert forbidden.error_code == "CAPABILITY_PERMISSION_DENIED"


def test_geometry_capability_registry_exposes_only_governed_v1_v2_operations() -> None:
    registry = geometry_capability_registry()
    discovered = registry.discover(
        domain="generic",
        required_tags=["geometry_program", "deterministic_compiler"],
    )
    identifiers = {item.capability_id for item in discovered}

    assert "geometry.extrude_profile@2.0.0" in identifiers
    assert "geometry.boolean_exact@2.0.0" in identifiers
    assert "geometry.terrain_surface@2.0.0" in identifiers
    assert "geometry.anchor@2.0.0" in identifiers
    assert all("python" not in identifier for identifier in identifiers)
