from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel


def canonical_tower_access_evidence_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


class TowerAccessLadderMeasurement(StrictModel):
    rail_count: int = Field(ge=0, le=8)
    rung_count: int = Field(ge=0, le=512)
    expected_rail_count: Literal[2] = 2
    expected_minimum_rung_count: int = Field(ge=2, le=512)
    expected_width_m: float = Field(gt=0, le=5)
    observed_width_m: float | None = Field(default=None, ge=0, le=5)
    expected_base_m: float = Field(ge=0, le=200)
    observed_base_m: float | None = Field(default=None, ge=0, le=200)
    expected_top_m: float = Field(ge=0, le=200)
    observed_top_m: float | None = Field(default=None, ge=0, le=200)
    expected_rung_spacing_m: float = Field(gt=0, le=2)
    observed_rung_spacing_m: float | None = Field(default=None, ge=0, le=2)
    passed: bool

    @model_validator(mode="after")
    def validate_passed_from_measurements(self) -> TowerAccessLadderMeasurement:
        tolerance = 0.035
        observed = (
            self.observed_width_m is not None
            and self.observed_base_m is not None
            and self.observed_top_m is not None
            and self.observed_rung_spacing_m is not None
        )
        expected = (
            observed
            and self.rail_count == self.expected_rail_count
            and self.rung_count >= self.expected_minimum_rung_count
            and abs(self.observed_width_m - self.expected_width_m) <= tolerance
            and abs(self.observed_base_m - self.expected_base_m) <= tolerance
            and abs(self.observed_top_m - self.expected_top_m) <= tolerance
            and abs(self.observed_rung_spacing_m - self.expected_rung_spacing_m) <= tolerance
        )
        if self.passed != expected:
            raise ValueError("ladder result does not match its exported measurements")
        return self


class TowerAccessPlatformMeasurement(StrictModel):
    platform_index: int = Field(ge=1, le=64)
    requested_level_m: float = Field(gt=0, le=200)
    observed_deck_top_m: float | None = Field(default=None, ge=0, le=200)
    elevation_error_m: float | None = Field(default=None, ge=0, le=20)
    expected_width_m: float = Field(gt=0, le=20)
    expected_depth_m: float = Field(gt=0, le=20)
    observed_width_m: float | None = Field(default=None, ge=0, le=20)
    observed_depth_m: float | None = Field(default=None, ge=0, le=20)
    guardrail_mesh_count: int = Field(ge=0, le=128)
    toe_board_mesh_count: int = Field(ge=0, le=32)
    support_mesh_count: int = Field(ge=0, le=32)
    support_tower_attachment_count: int | None = Field(
        default=None, ge=0, le=32, exclude_if=lambda value: value is None
    )
    support_deck_attachment_count: int | None = Field(
        default=None, ge=0, le=32, exclude_if=lambda value: value is None
    )
    minimum_support_radial_span_m: float | None = Field(
        default=None, ge=0, le=20, exclude_if=lambda value: value is None
    )
    minimum_support_vertical_drop_m: float | None = Field(
        default=None, ge=0, le=20, exclude_if=lambda value: value is None
    )
    passed: bool

    @model_validator(mode="after")
    def validate_passed_from_measurements(self) -> TowerAccessPlatformMeasurement:
        tolerance = 0.04
        observed = all(
            value is not None
            for value in (
                self.observed_deck_top_m,
                self.elevation_error_m,
                self.observed_width_m,
                self.observed_depth_m,
            )
        )
        support_shape = (
            self.support_tower_attachment_count,
            self.support_deck_attachment_count,
            self.minimum_support_radial_span_m,
            self.minimum_support_vertical_drop_m,
        )
        if any(value is not None for value in support_shape) and not all(
            value is not None for value in support_shape
        ):
            raise ValueError("platform support measurements must be complete")
        support_shape_valid = True
        if all(value is not None for value in support_shape):
            support_shape_valid = bool(
                self.support_tower_attachment_count >= 2
                and self.support_deck_attachment_count >= 2
                and self.minimum_support_radial_span_m >= self.expected_depth_m * 0.3
                and self.minimum_support_vertical_drop_m
                >= min(max(self.expected_depth_m * 0.15, 0.2), 0.5)
            )
        expected = (
            observed
            and self.elevation_error_m <= tolerance
            and abs(self.observed_width_m - self.expected_width_m) <= tolerance
            and abs(self.observed_depth_m - self.expected_depth_m) <= tolerance
            and self.guardrail_mesh_count >= 7
            and self.toe_board_mesh_count >= 3
            and self.support_mesh_count >= 2
            and support_shape_valid
        )
        if self.passed != expected:
            raise ValueError("platform result does not match its exported measurements")
        return self


class TowerAccessEvidence(StrictModel):
    """Independent post-Blender observation of bounded tower-access geometry.

    This evidence is deliberately limited to exported GLB identity, measured
    feature geometry, elevations and broad-phase equipment overlap.  It is not
    a structural, fall-protection, fastening, load, evacuation or installation
    approval.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    scene_id: str = Field(min_length=1, max_length=160)
    status: Literal["passed", "failed"]
    measurement_scope: Literal["exported_glb_tower_access_geometry"] = (
        "exported_glb_tower_access_geometry"
    )
    glb_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    semantic_root: str = Field(min_length=1, max_length=240)
    profile_family: Literal["lattice_tower_access_v1"]
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_ladder: bool
    expected_platform_count: int = Field(ge=0, le=64)
    ladder: TowerAccessLadderMeasurement | None = None
    platforms: list[TowerAccessPlatformMeasurement] = Field(default_factory=list, max_length=64)
    primary_equipment_deck_overlap_count: int = Field(ge=0, le=100_000)
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list, max_length=256)
    limitations: list[str] = Field(min_length=3, max_length=32)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_evidence_truth(self) -> TowerAccessEvidence:
        indices = [platform.platform_index for platform in self.platforms]
        if len(indices) != len(set(indices)):
            raise ValueError("tower access platform indexes must be unique")
        if self.expected_platform_count != len(self.platforms):
            raise ValueError("tower access platform count does not match measurements")
        if self.requested_ladder != (self.ladder is not None):
            raise ValueError("tower access ladder measurement does not match request")
        if self.checks.get("primary_equipment_deck_clearance") is not (
            self.primary_equipment_deck_overlap_count == 0
        ):
            raise ValueError("tower access clearance check does not match its observation")
        expected_pass = bool(self.checks) and all(self.checks.values()) and not self.errors
        if (self.status == "passed") != expected_pass:
            raise ValueError("tower access status does not match its measured checks")
        payload = self.model_dump(mode="json", exclude={"evidence_sha256"})
        if canonical_tower_access_evidence_sha256(payload) != self.evidence_sha256:
            raise ValueError("tower access evidence hash mismatch")
        return self
