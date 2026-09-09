from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel

ASSEMBLY_ANGULAR_TOLERANCE_DEG = 1.0
"""Maximum normal-opposition and up-alignment error accepted by evidence v1."""


def canonical_evidence_sha256(payload: dict[str, Any]) -> str:
    """Hash a JSON-compatible evidence payload using the project canonical form."""

    payload = _without_absent_resolved_support(payload)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _without_absent_resolved_support(value: Any) -> Any:
    """Keep the additive support field compatible with pre-support v1 payloads."""

    if isinstance(value, dict):
        return {
            key: _without_absent_resolved_support(item)
            for key, item in value.items()
            if not (key == "resolved_support" and item is None)
        }
    if isinstance(value, list):
        return [_without_absent_resolved_support(item) for item in value]
    return value


class ResolvedEndpointSupport(StrictModel):
    """Exact exported mesh node supporting one operation-resolved endpoint."""

    connection_id: str = Field(min_length=1, max_length=120)
    operation_id: str = Field(min_length=1, max_length=160)
    instance_id: str = Field(min_length=1, max_length=120)
    endpoint: Literal["source", "target"]
    role_id: str = Field(min_length=1, max_length=96)
    resolved_anchor_id: str = Field(min_length=1, max_length=96)
    support_anchor_id: str = Field(min_length=1, max_length=96)
    gltf_node_index: int = Field(ge=0)
    gltf_node_name: str | None = Field(default=None, min_length=1, max_length=300)
    gltf_mesh_index: int = Field(ge=0)


class MeasuredAssemblyFrame(StrictModel):
    """An anchor frame expressed in the authoritative SceneSpec coordinate system."""

    coordinate_space: Literal["scenespec_z_up_meters"] = "scenespec_z_up_meters"
    position_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    up: tuple[float, float, float]
    source: Literal["glb_fixed_anchor", "glb_resolved_anchor"]
    gltf_node_index: int | None = Field(default=None, ge=0)
    gltf_node_name: str | None = Field(default=None, min_length=1, max_length=300)
    resolved_support: ResolvedEndpointSupport | None = None

    @model_validator(mode="after")
    def validate_source_trace(self) -> MeasuredAssemblyFrame:
        if self.gltf_node_index is None:
            raise ValueError("GLB anchor evidence requires a glTF node index")
        if self.source == "glb_fixed_anchor" and self.resolved_support is not None:
            raise ValueError("fixed GLB anchors cannot claim resolved support geometry")
        normal_length = math.sqrt(sum(component * component for component in self.normal))
        up_length = math.sqrt(sum(component * component for component in self.up))
        if not math.isclose(normal_length, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("measured frame normal must be normalized")
        if not math.isclose(up_length, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("measured frame up must be normalized")
        if abs(sum(self.normal[index] * self.up[index] for index in range(3))) >= 1.0 - 1e-7:
            raise ValueError("measured frame normal and up must not be parallel")
        return self


class AssemblyConstraintMeasurement(StrictModel):
    measurement_id: str = Field(min_length=1, max_length=260)
    connection_id: str = Field(min_length=1, max_length=120)
    operation_id: str = Field(min_length=1, max_length=160)
    instance_id: str = Field(min_length=1, max_length=120)
    source_role_id: str = Field(min_length=1, max_length=96)
    source_connector_id: str = Field(min_length=1, max_length=96)
    source_anchor_id: str = Field(min_length=1, max_length=96)
    target_role_id: str = Field(min_length=1, max_length=96)
    target_connector_id: str = Field(min_length=1, max_length=96)
    target_anchor_id: str = Field(min_length=1, max_length=96)
    source_frame: MeasuredAssemblyFrame
    target_frame: MeasuredAssemblyFrame
    position_error_m: float = Field(ge=0.0, le=1000.0)
    position_tolerance_m: float = Field(gt=0.0, le=1.0)
    normal_opposition_error_deg: float = Field(ge=0.0, le=180.0)
    up_alignment_error_deg: float = Field(ge=0.0, le=180.0)
    angular_tolerance_deg: Literal[1.0] = ASSEMBLY_ANGULAR_TOLERANCE_DEG
    position_passed: bool
    normal_opposition_passed: bool
    up_alignment_passed: bool
    passed: bool

    @model_validator(mode="after")
    def validate_result_truth(self) -> AssemblyConstraintMeasurement:
        epsilon = 1e-12
        measured_position_error = math.dist(
            self.source_frame.position_m,
            self.target_frame.position_m,
        )
        measured_normal_error = _angle_deg(
            self.source_frame.normal,
            tuple(-component for component in self.target_frame.normal),
        )
        measured_up_error = _angle_deg(self.source_frame.up, self.target_frame.up)
        if not math.isclose(
            self.position_error_m,
            measured_position_error,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("position error does not match the measured frames")
        if not math.isclose(
            self.normal_opposition_error_deg,
            measured_normal_error,
            rel_tol=0.0,
            abs_tol=1e-7,
        ):
            raise ValueError("normal error does not match the measured frames")
        if not math.isclose(
            self.up_alignment_error_deg,
            measured_up_error,
            rel_tol=0.0,
            abs_tol=1e-7,
        ):
            raise ValueError("up error does not match the measured frames")
        expected_position = self.position_error_m <= self.position_tolerance_m + epsilon
        expected_normal = self.normal_opposition_error_deg <= self.angular_tolerance_deg + epsilon
        expected_up = self.up_alignment_error_deg <= self.angular_tolerance_deg + epsilon
        if self.position_passed != expected_position:
            raise ValueError("position result does not match the measured tolerance")
        if self.normal_opposition_passed != expected_normal:
            raise ValueError("normal result does not match the fixed angular tolerance")
        if self.up_alignment_passed != expected_up:
            raise ValueError("up result does not match the fixed angular tolerance")
        if self.passed != (expected_position and expected_normal and expected_up):
            raise ValueError("constraint result does not match its component checks")
        return self


class UnevaluatedAssemblyConnection(StrictModel):
    connection_id: str = Field(min_length=1, max_length=120)
    kind: Literal["power", "fiber", "rf", "grounding", "routing"]
    required: Literal[True] = True
    reason: Literal["non_mechanical_connection_not_evaluated_by_v1"] = (
        "non_mechanical_connection_not_evaluated_by_v1"
    )


class AssemblyConstraintEvidence(StrictModel):
    """Post-export geometric evidence for required AssemblyPlan 1.1 mechanics.

    Evidence v1 measures connector position, normal opposition and up alignment.
    It intentionally does not claim collision, contact, fastening, deformation,
    load, or electrical/routing continuity analysis.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    assembly_plan_schema_version: Literal["1.1.0"] = "1.1.0"
    workflow_id: str = Field(min_length=1, max_length=120)
    status: Literal["passed", "failed"]
    coordinate_space: Literal["scenespec_z_up_meters"] = "scenespec_z_up_meters"
    glb_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assembly_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    angular_tolerance_deg: Literal[1.0] = ASSEMBLY_ANGULAR_TOLERANCE_DEG
    expected_measurement_count: int = Field(ge=0, le=16_384)
    measured_constraint_count: int = Field(ge=0, le=16_384)
    failed_constraint_count: int = Field(ge=0, le=16_384)
    measurements: list[AssemblyConstraintMeasurement] = Field(
        default_factory=list,
        max_length=16_384,
    )
    unevaluated_required_connections: list[UnevaluatedAssemblyConnection] = Field(
        default_factory=list,
        max_length=64,
    )
    errors: list[str] = Field(default_factory=list, max_length=256)
    limitations: list[str] = Field(min_length=3, max_length=32)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_evidence_truth(self) -> AssemblyConstraintEvidence:
        measurement_ids = [item.measurement_id for item in self.measurements]
        if len(measurement_ids) != len(set(measurement_ids)):
            raise ValueError("assembly constraint measurement IDs must be unique")
        connection_ids = [item.connection_id for item in self.unevaluated_required_connections]
        if len(connection_ids) != len(set(connection_ids)):
            raise ValueError("unevaluated required connection IDs must be unique")
        if self.measured_constraint_count != len(self.measurements):
            raise ValueError("measured constraint count does not match the measurements")
        failed_count = sum(not item.passed for item in self.measurements)
        if self.failed_constraint_count != failed_count:
            raise ValueError("failed constraint count does not match the measurements")
        expected_pass = (
            self.expected_measurement_count > 0
            and self.measured_constraint_count == self.expected_measurement_count
            and self.failed_constraint_count == 0
            and not self.errors
        )
        if (self.status == "passed") != expected_pass:
            raise ValueError("assembly evidence status does not match its measured truth")
        payload = self.model_dump(mode="json", exclude={"evidence_sha256"})
        if canonical_evidence_sha256(payload) != self.evidence_sha256:
            raise ValueError("assembly constraint evidence hash mismatch")
        return self


def _angle_deg(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    # Measured unit vectors retain floating-point normalization residuals. Use
    # the same normalized dot product as the inspector; do not relax QA tolerance.
    left_length = math.sqrt(sum(component * component for component in left))
    right_length = math.sqrt(sum(component * component for component in right))
    normalized_left = tuple(component / left_length for component in left)
    normalized_right = tuple(component / right_length for component in right)
    cosine = max(
        -1.0,
        min(1.0, sum(normalized_left[index] * normalized_right[index] for index in range(3))),
    )
    return math.degrees(math.acos(cosine))
