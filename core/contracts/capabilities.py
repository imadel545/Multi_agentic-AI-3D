from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel


class CapabilityCost(StrictModel):
    """Bounded execution cost used by supervisors before a tool is selected."""

    class_name: Literal["negligible", "low", "medium", "high"]
    estimated_seconds: float = Field(ge=0.0, le=3600.0)
    estimated_memory_mb: int = Field(ge=0, le=32768)


class CapabilityLimits(StrictModel):
    max_input_bytes: int = Field(default=262_144, ge=1, le=16_777_216)
    max_output_bytes: int = Field(default=1_048_576, ge=1, le=67_108_864)
    max_operations: int = Field(default=1, ge=1, le=4096)
    notes: list[str] = Field(default_factory=list, max_length=16)


class CapabilityDefinition(StrictModel):
    """Public, versioned contract for one executable deterministic capability.

    JSON schemas are descriptive discovery data. Runtime validation is performed
    again by the registry with its locally registered Pydantic models.
    """

    capability_id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9._-]*@[1-9][0-9]*\.[0-9]+\.[0-9]+$",
    )
    description: str = Field(min_length=12, max_length=600)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    compatible_domains: list[str] = Field(min_length=1, max_length=32)
    capability_tags: list[str] = Field(default_factory=list, max_length=32)
    cost: CapabilityCost
    limits: CapabilityLimits = Field(default_factory=CapabilityLimits)
    permissions: list[
        Literal[
            "read_catalog",
            "read_scene",
            "mutate_plan",
            "mutate_scene_spec",
            "execute_blender",
            "write_artifact",
            "quality_gate",
        ]
    ] = Field(default_factory=list, max_length=8)
    timeout_s: float = Field(gt=0.0, le=3600.0)
    possible_errors: list[str] = Field(default_factory=list, max_length=32)
    version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
    generated_proofs: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_definition(self) -> CapabilityDefinition:
        embedded_version = self.capability_id.rsplit("@", 1)[1]
        if embedded_version != self.version:
            raise ValueError("capability ID version must match version")
        for field_name in (
            "compatible_domains",
            "capability_tags",
            "permissions",
            "possible_errors",
            "generated_proofs",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
        return self


class CapabilityInvocation(StrictModel):
    capability_id: str = Field(min_length=3, max_length=120)
    arguments: dict[str, Any]
    requested_permissions: list[str] = Field(default_factory=list, max_length=8)
    correlation_id: str = Field(min_length=1, max_length=120)
    attempt: int = Field(default=1, ge=1, le=2)


class CapabilityObservation(StrictModel):
    capability_id: str
    correlation_id: str
    status: Literal["completed", "rejected", "failed", "timed_out"]
    duration_ms: int = Field(ge=0)
    attempt: int = Field(ge=1, le=2)
    output: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=600)
    proof_refs: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_outcome(self) -> CapabilityObservation:
        if self.status == "completed":
            if self.output is None or self.error_code is not None:
                raise ValueError("completed observation requires output and no error")
        elif self.error_code is None:
            raise ValueError("non-completed observation requires an error code")
        return self
