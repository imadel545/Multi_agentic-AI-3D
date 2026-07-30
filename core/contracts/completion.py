from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from core.contracts.common import StrictModel


class RequirementCoverageCheck(StrictModel):
    path: str = Field(min_length=1)
    expected: Any
    actual: Any
    source: Literal["requirements", "planning_resolution"] = "requirements"
    passed: bool


class RequirementCoverageReport(StrictModel):
    workflow_id: str = Field(min_length=1)
    passed: bool
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    checks: list[RequirementCoverageCheck] = Field(default_factory=list)
    approved_deviations: list[dict[str, Any]] = Field(default_factory=list)
    critical_errors: list[str] = Field(default_factory=list)


class CertifiedArtifact(StrictModel):
    logical_name: Literal["glb", "preview", "metadata", "build_lock"]
    file_name: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompletionCertificate(StrictModel):
    schema_version: Literal["1.0.0", "1.1.0"] = "1.0.0"
    workflow_id: str = Field(min_length=1)
    status: Literal["issued", "rejected"]
    evaluated_at: datetime
    requirements_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    design_blueprint_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    scene_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation_mode: str | None = None
    artifacts: list[CertifiedArtifact] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
