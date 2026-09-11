from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

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
    logical_name: Literal[
        "glb",
        "preview",
        "metadata",
        "component_proofs",
        "constraint_evidence",
        "tower_access_evidence",
        "build_lock",
    ]
    file_name: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompletionCertificate(StrictModel):
    schema_version: Literal["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"] = "1.0.0"
    workflow_id: str = Field(min_length=1)
    status: Literal["issued", "rejected"]
    evaluated_at: datetime
    requirements_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    design_blueprint_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    cognitive_plan_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    constraint_evidence_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    tower_access_evidence_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    scene_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation_mode: str | None = None
    artifacts: list[CertifiedArtifact] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_hashes_for_issued_evidence_schemas(self) -> CompletionCertificate:
        if (
            self.schema_version == "1.4.0"
            and self.status == "issued"
            and self.constraint_evidence_sha256 is None
        ):
            raise ValueError("completion certificate 1.4 requires constraint evidence hash")
        if (
            self.schema_version == "1.5.0"
            and self.status == "issued"
            and self.tower_access_evidence_sha256 is None
        ):
            raise ValueError("completion certificate 1.5 requires tower access evidence hash")
        if (
            self.schema_version == "1.5.0"
            and self.status == "issued"
            and any(artifact.logical_name == "constraint_evidence" for artifact in self.artifacts)
            and self.constraint_evidence_sha256 is None
        ):
            raise ValueError(
                "completion certificate 1.5 requires constraint evidence hash when present"
            )
        return self
