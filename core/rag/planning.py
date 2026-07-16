from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.contracts.planning_decision import PLANNING_FIELDS, PlanningDecisionResult
from core.contracts.requirements import RequirementSpec

DecisionStatus = Literal["applied", "rejected", "no_op"]

SUPPORTED_PLANNING_HINT_FIELDS = frozenset(
    {
        "antenna_install_height_m",
        "beamwidth_deg",
        "include_cables",
        "include_sector_beams",
    }
)

_INFERENCE_WARNING_FIELDS = {
    "DEFAULT_INSTALL_HEIGHT_USED": frozenset({"antenna_install_height_m"}),
    "DEFAULT_BEAMWIDTH_USED": frozenset({"beamwidth_deg"}),
    "DEFAULT_CABLES_USED": frozenset({"include_cables"}),
    "DEFAULT_BEAMS_USED": frozenset({"include_sector_beams"}),
}


@dataclass(frozen=True)
class RagPlanningResolution:
    antenna_install_height_m: float
    beamwidth_deg: float
    include_cables: bool
    include_sector_beams: bool
    decisions: tuple[dict[str, object], ...]

    @property
    def used_for_planning(self) -> bool:
        return any(decision["status"] == "applied" for decision in self.decisions)

    @property
    def applied_fields(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(decision["field"])
                    for decision in self.decisions
                    if decision["status"] == "applied"
                }
            )
        )


@dataclass(frozen=True)
class RagPlanningCandidate:
    field: str
    value: object
    context_index: int
    provenance: dict[str, object]

    @property
    def candidate_id(self) -> str:
        return f"rag:{self.context_index + 1}:{self.field}"


@dataclass(frozen=True)
class RagPlanningEvidence:
    current_values: dict[str, object]
    inferred_fields: frozenset[str]
    candidates: tuple[RagPlanningCandidate, ...]
    rejected_decisions: tuple[dict[str, object], ...]


def resolve_planning_hints(
    requirements: RequirementSpec,
    contexts: list[dict] | None,
) -> RagPlanningResolution:
    """Resolve RAG hints without overriding source-backed requirements.

    Retrieval order is already the reranker's relevance order. Only the first
    valid candidate for an inferred field can be applied; every other candidate
    is recorded as rejected or no-op. The contexts are annotated in place so the
    existing rag_context artifact carries the decision trail and only applied
    hints remain under ``planning_hints``.
    """

    evidence = collect_planning_evidence(requirements, contexts)
    current_values = evidence.current_values
    resolved_values = dict(current_values)
    inferred_fields = evidence.inferred_fields
    decisions = list(evidence.rejected_decisions)
    valid_candidates: dict[str, list[RagPlanningCandidate]] = {
        field: [] for field in SUPPORTED_PLANNING_HINT_FIELDS
    }
    for candidate in evidence.candidates:
        valid_candidates[candidate.field].append(candidate)

    for field in sorted(SUPPORTED_PLANNING_HINT_FIELDS):
        candidates = valid_candidates[field]
        if not candidates:
            continue
        selected = candidates[0]
        current_value = current_values[field]
        if _same_value(selected.value, current_value):
            status: DecisionStatus = "no_op"
            reason = "requirement_already_satisfied"
        elif field not in inferred_fields:
            status = "rejected"
            reason = "source_requirement_protected"
        else:
            status = "applied"
            reason = "highest_ranked_candidate_for_inferred_field"
            resolved_values[field] = selected.value
        decisions.append(
            _decision(
                field=field,
                status=status,
                reason=reason,
                candidate_value=selected.value,
                current_value=current_value,
                selected=True,
                context_index=selected.context_index,
                provenance=selected.provenance,
            )
        )
        for candidate in candidates[1:]:
            duplicate = _same_value(candidate.value, selected.value)
            decisions.append(
                _decision(
                    field=field,
                    status="no_op" if duplicate else "rejected",
                    reason="duplicate_candidate" if duplicate else "lower_ranked_conflict",
                    candidate_value=candidate.value,
                    current_value=current_value,
                    selected=False,
                    context_index=candidate.context_index,
                    provenance=candidate.provenance,
                )
            )

    decisions.sort(key=lambda item: (int(item["context_index"]), str(item["field"])))
    _annotate_contexts(contexts or [], decisions)
    return _resolution(resolved_values, decisions)


def collect_planning_evidence(
    requirements: RequirementSpec,
    contexts: list[dict] | None,
) -> RagPlanningEvidence:
    """Validate RAG candidates before any deterministic or model decision."""

    current_values: dict[str, object] = {
        "antenna_install_height_m": requirements.antenna_install_height_m,
        "beamwidth_deg": requirements.beamwidth_deg,
        "include_cables": requirements.include_cables,
        "include_sector_beams": requirements.include_beams,
    }
    inferred_fields = frozenset(_inferred_fields(requirements))
    rejected_decisions: list[dict[str, object]] = []
    candidates: list[RagPlanningCandidate] = []

    for context_index, context in enumerate(contexts or []):
        for field, value in _raw_hints(context).items():
            provenance = _provenance(context, context_index)
            if field not in SUPPORTED_PLANNING_HINT_FIELDS:
                rejected_decisions.append(
                    _decision(
                        field=field,
                        status="rejected",
                        reason="planner_field_not_supported",
                        candidate_value=value,
                        current_value=None,
                        selected=False,
                        context_index=context_index,
                        provenance=provenance,
                    )
                )
                continue
            if mismatch := _scope_mismatch(requirements, context):
                rejected_decisions.append(
                    _decision(
                        field=field,
                        status="rejected",
                        reason=mismatch,
                        candidate_value=value,
                        current_value=current_values[field],
                        selected=False,
                        context_index=context_index,
                        provenance=provenance,
                    )
                )
                continue
            normalized, error = _validated_value(field, value, requirements)
            if error:
                rejected_decisions.append(
                    _decision(
                        field=field,
                        status="rejected",
                        reason=error,
                        candidate_value=value,
                        current_value=current_values[field],
                        selected=False,
                        context_index=context_index,
                        provenance=provenance,
                    )
                )
                continue
            candidates.append(
                RagPlanningCandidate(
                    field=field,
                    value=normalized,
                    context_index=context_index,
                    provenance=provenance,
                )
            )

    return RagPlanningEvidence(
        current_values=current_values,
        inferred_fields=inferred_fields,
        candidates=tuple(candidates),
        rejected_decisions=tuple(rejected_decisions),
    )


def apply_bounded_planning_decision(
    requirements: RequirementSpec,
    contexts: list[dict] | None,
    result: PlanningDecisionResult,
) -> RagPlanningResolution:
    """Apply a GPT-OSS result that can reference only prevalidated candidates."""

    evidence = collect_planning_evidence(requirements, contexts)
    candidates_by_id = {candidate.candidate_id: candidate for candidate in evidence.candidates}
    selections = {selection.field: selection for selection in result.selections}
    if set(selections) != set(PLANNING_FIELDS) or len(selections) != len(result.selections):
        raise ValueError("planning decision must resolve each controlled field exactly once")
    decisions = list(evidence.rejected_decisions)
    resolved_values = dict(evidence.current_values)
    selected_ids = {
        selection.candidate_id for selection in result.selections if selection.candidate_id
    }
    if selected_ids - set(candidates_by_id):
        raise ValueError("planning decision references candidates outside current RAG evidence")
    for selection in result.selections:
        if not selection.candidate_id:
            continue
        candidate = candidates_by_id[selection.candidate_id]
        if candidate.field != selection.field:
            raise ValueError("planning decision references a candidate for another field")
        if candidate.field not in evidence.inferred_fields:
            raise ValueError("planning decision attempted to override a protected requirement")
        resolved_values[candidate.field] = candidate.value

    for candidate in evidence.candidates:
        selection = selections[candidate.field]
        selected = selection.candidate_id == candidate.candidate_id
        current_value = evidence.current_values[candidate.field]
        if selected:
            status: DecisionStatus = (
                "no_op" if _same_value(candidate.value, current_value) else "applied"
            )
            reason = (
                "requirement_already_satisfied"
                if status == "no_op"
                else "gpt_oss_selected_validated_candidate"
            )
        elif candidate.field not in evidence.inferred_fields:
            status = "rejected"
            reason = "source_requirement_protected"
        elif _same_value(candidate.value, current_value):
            status = "no_op"
            reason = "requirement_already_satisfied"
        else:
            status = "rejected"
            reason = (
                "planning_decision_fallback_keep_current"
                if result.diagnostics.fallback_used
                else "gpt_oss_candidate_not_selected"
            )
        decisions.append(
            _decision(
                field=candidate.field,
                status=status,
                reason=reason,
                candidate_value=candidate.value,
                current_value=current_value,
                selected=selected,
                context_index=candidate.context_index,
                provenance=candidate.provenance,
            )
        )

    decisions.sort(key=lambda item: (int(item["context_index"]), str(item["field"])))
    _annotate_contexts(contexts or [], decisions)
    return _resolution(resolved_values, decisions)


def _resolution(
    values: dict[str, object], decisions: list[dict[str, object]]
) -> RagPlanningResolution:
    return RagPlanningResolution(
        antenna_install_height_m=float(values["antenna_install_height_m"]),
        beamwidth_deg=float(values["beamwidth_deg"]),
        include_cables=bool(values["include_cables"]),
        include_sector_beams=bool(values["include_sector_beams"]),
        decisions=tuple(decisions),
    )


def _inferred_fields(requirements: RequirementSpec) -> set[str]:
    inferred: set[str] = set()
    for warning in requirements.warnings:
        inferred.update(_INFERENCE_WARNING_FIELDS.get(warning.code, ()))
    return inferred


def _raw_hints(context: dict) -> dict[str, object]:
    payload = context.get("payload")
    if not isinstance(payload, dict):
        return {}
    candidates = payload.get("planning_hint_candidates")
    if isinstance(candidates, dict):
        return {str(key): value for key, value in candidates.items()}
    hints = payload.get("planning_hints")
    if not isinstance(hints, dict):
        return {}
    return {str(key): value for key, value in hints.items()}


def _validated_value(
    field: str,
    value: object,
    requirements: RequirementSpec,
) -> tuple[object, str | None]:
    if field in {"include_cables", "include_sector_beams"}:
        if type(value) is not bool:
            return value, "invalid_boolean_hint"
        return value, None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value, "invalid_numeric_hint"
    normalized = float(value)
    if field == "beamwidth_deg" and not 1.0 <= normalized <= 360.0:
        return normalized, "hint_out_of_range"
    if field == "antenna_install_height_m" and not (
        0.1 <= normalized <= requirements.tower_height_m
    ):
        return normalized, "hint_out_of_range"
    return normalized, None


def _scope_mismatch(requirements: RequirementSpec, context: dict) -> str | None:
    payload = context.get("payload")
    if not isinstance(payload, dict):
        return None
    if not _matches_scope(payload.get("network_type"), requirements.network_type):
        return "network_scope_mismatch"
    if not _matches_scope(payload.get("tower_type"), requirements.tower_type):
        return "tower_scope_mismatch"
    return None


def _matches_scope(candidate: object, expected: str) -> bool:
    if candidate is None or candidate == "":
        return True
    if isinstance(candidate, str):
        return candidate == expected
    if isinstance(candidate, list):
        return expected in candidate
    return False


def _provenance(context: dict, context_index: int) -> dict[str, object]:
    payload = context.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    text = context.get("text")
    return {
        "rank": context_index + 1,
        "collection": context.get("collection"),
        "doc_id": context.get("doc_id"),
        "score": context.get("score"),
        "filename": payload.get("filename"),
        "source_path": _portable_source_path(payload.get("source_path")),
        "excerpt": str(text)[:320] if isinstance(text, str) and text.strip() else None,
    }


def _portable_source_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path.name if path.is_absolute() else value


def _decision(
    *,
    field: str,
    status: DecisionStatus,
    reason: str,
    candidate_value: object,
    current_value: object,
    selected: bool,
    context_index: int,
    provenance: dict[str, object],
) -> dict[str, object]:
    return {
        "field": field,
        "status": status,
        "reason": reason,
        "candidate_value": candidate_value,
        "current_value": current_value,
        "selected": selected,
        "context_index": context_index,
        "provenance": provenance,
    }


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, int | float):
        return abs(left - float(right)) <= 1e-9
    return left == right


def _annotate_contexts(contexts: list[dict], decisions: list[dict[str, object]]) -> None:
    for context_index, context in enumerate(contexts):
        payload = context.get("payload")
        if not isinstance(payload, dict):
            continue
        original_hints = _raw_hints(context)
        context_decisions = [
            decision for decision in decisions if decision["context_index"] == context_index
        ]
        applied_hints = {
            str(decision["field"]): decision["candidate_value"]
            for decision in context_decisions
            if decision["status"] == "applied"
        }
        payload["planning_hint_candidates"] = original_hints
        payload["planning_hints"] = applied_hints
        payload["planning_decisions"] = context_decisions
        payload["rag_planning_applied"] = bool(applied_hints)
