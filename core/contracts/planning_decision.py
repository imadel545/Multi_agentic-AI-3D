from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from core.contracts.common import StrictModel

PlanningField = Literal[
    "antenna_install_height_m",
    "beamwidth_deg",
    "include_cables",
    "include_sector_beams",
]
PlanningSource = Literal["rag", "memory"]
PlanningSelectionAction = Literal["keep_current", "select_candidate"]
CandidateId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]

PLANNING_FIELDS: tuple[PlanningField, ...] = (
    "antenna_install_height_m",
    "beamwidth_deg",
    "include_cables",
    "include_sector_beams",
)


class StrictDecisionModel(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, strict=True)


class PlanningCurrentValues(StrictDecisionModel):
    antenna_install_height_m: float = Field(gt=0, le=150)
    beamwidth_deg: float = Field(gt=0, le=360)
    include_cables: bool
    include_sector_beams: bool


class PlanningCandidateProvenance(StrictDecisionModel):
    source: PlanningSource
    reference_id: str = Field(min_length=1, max_length=120)
    rank: int = Field(ge=1, le=100)
    score: float | None = None
    collection: str | None = Field(default=None, max_length=120)
    document_name: str | None = Field(default=None, max_length=180)
    excerpt: str | None = Field(default=None, max_length=320)


class PlanningCandidate(StrictDecisionModel):
    candidate_id: CandidateId
    field: PlanningField
    value: float | bool
    provenance: PlanningCandidateProvenance

    @model_validator(mode="after")
    def validate_value_type(self) -> PlanningCandidate:
        boolean_fields = {"include_cables", "include_sector_beams"}
        if self.field in boolean_fields and type(self.value) is not bool:
            raise ValueError(f"{self.field} requires a boolean candidate value")
        if self.field not in boolean_fields and isinstance(self.value, bool):
            raise ValueError(f"{self.field} requires a numeric candidate value")
        if self.field == "antenna_install_height_m" and not 0 < float(self.value) <= 150:
            raise ValueError("antenna_install_height_m candidate is outside the global range")
        if self.field == "beamwidth_deg" and not 0 < float(self.value) <= 360:
            raise ValueError("beamwidth_deg candidate is outside the global range")
        return self


class PlanningMemoryRisk(StrictDecisionModel):
    risk_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    severity: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1, max_length=240)
    related_candidate_ids: list[CandidateId] = Field(default_factory=list, max_length=8)


class PlanningDecisionRequest(StrictDecisionModel):
    current_values: PlanningCurrentValues
    protected_fields: list[PlanningField] = Field(default_factory=list, max_length=4)
    candidates: list[PlanningCandidate] = Field(default_factory=list, max_length=24)
    memory_risks: list[PlanningMemoryRisk] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_references(self) -> PlanningDecisionRequest:
        if len(set(self.protected_fields)) != len(self.protected_fields):
            raise ValueError("protected_fields must be unique")

        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_id values must be unique")

        risk_ids = [risk.risk_id for risk in self.memory_risks]
        if len(set(risk_ids)) != len(risk_ids):
            raise ValueError("risk_id values must be unique")

        known_candidates = set(candidate_ids)
        for risk in self.memory_risks:
            if len(set(risk.related_candidate_ids)) != len(risk.related_candidate_ids):
                raise ValueError(
                    f"memory risk {risk.risk_id!r} contains duplicate candidate references"
                )
            unknown = set(risk.related_candidate_ids) - known_candidates
            if unknown:
                raise ValueError(
                    f"memory risk {risk.risk_id!r} references unknown candidates: {sorted(unknown)}"
                )
        return self


class PlanningModelSelection(StrictDecisionModel):
    field: PlanningField
    action: PlanningSelectionAction
    candidate_id: CandidateId | None
    reason: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_action(self) -> PlanningModelSelection:
        if self.action == "keep_current" and self.candidate_id is not None:
            raise ValueError("keep_current cannot include candidate_id")
        if self.action == "select_candidate" and not self.candidate_id:
            raise ValueError("select_candidate requires candidate_id")
        return self


class PlanningModelDecision(StrictDecisionModel):
    selections: list[PlanningModelSelection] = Field(min_length=4, max_length=4)


class ResolvedPlanningSelection(StrictDecisionModel):
    field: PlanningField
    action: PlanningSelectionAction
    candidate_id: str | None
    current_value: float | bool
    selected_value: float | bool
    reason: str = Field(min_length=1, max_length=240)
    provenance: PlanningCandidateProvenance | None = None


class PlanningDecisionDiagnostics(StrictDecisionModel):
    provider: Literal["groq"] = "groq"
    model_name: str = Field(min_length=1, max_length=160)
    status: Literal["primary", "deterministic_fallback"]
    fallback_used: bool
    fallback_reason: str | None = Field(default=None, max_length=160)
    latency_ms: int = Field(ge=0)
    response_format: Literal["strict_json_schema"] = "strict_json_schema"

    @model_validator(mode="after")
    def validate_fallback_truth(self) -> PlanningDecisionDiagnostics:
        if self.fallback_used != (self.status == "deterministic_fallback"):
            raise ValueError("fallback_used must match diagnostics status")
        if self.fallback_used and not self.fallback_reason:
            raise ValueError("deterministic fallback requires fallback_reason")
        if not self.fallback_used and self.fallback_reason is not None:
            raise ValueError("primary decision cannot include fallback_reason")
        return self


class PlanningDecisionResult(StrictDecisionModel):
    resolved_values: PlanningCurrentValues
    selections: list[ResolvedPlanningSelection] = Field(min_length=4, max_length=4)
    diagnostics: PlanningDecisionDiagnostics
