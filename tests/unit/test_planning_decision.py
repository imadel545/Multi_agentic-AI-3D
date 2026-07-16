import json

import httpx
import pytest
from pydantic import ValidationError

from core.contracts.planning_decision import (
    PlanningCandidate,
    PlanningCandidateProvenance,
    PlanningCurrentValues,
    PlanningDecisionRequest,
    PlanningMemoryRisk,
    PlanningModelDecision,
)
from core.llm.planning_decision import (
    GroqPlanningDecisionClient,
    resolve_model_decision,
)


def test_gpt_oss_selects_only_validated_candidates() -> None:
    calls = []

    def post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _response(
            url,
            {
                "selections": [
                    _selection("antenna_install_height_m", "select_candidate", "rag:hba:1"),
                    _selection("beamwidth_deg", "keep_current"),
                    _selection("include_cables", "select_candidate", "memory:cables:1"),
                    _selection("include_sector_beams", "keep_current"),
                ]
            },
        )

    result = GroqPlanningDecisionClient(
        api_key="test-key",
        timeout_s=9,
        max_completion_tokens=512,
        post=post,
    ).decide(_request())

    assert result.resolved_values.antenna_install_height_m == 25
    assert result.resolved_values.include_cables is False
    assert result.resolved_values.beamwidth_deg == 65
    assert result.diagnostics.status == "primary"
    assert result.diagnostics.fallback_used is False
    assert calls[0]["timeout"] == 9
    assert calls[0]["json"]["model"] == "openai/gpt-oss-120b"
    assert calls[0]["json"]["max_completion_tokens"] == 512
    assert calls[0]["json"]["response_format"]["json_schema"]["strict"] is True
    assert (
        "value"
        not in calls[0]["json"]["response_format"]["json_schema"]["schema"]["properties"][
            "selections"
        ]["items"]["properties"]
    )


def test_unknown_candidate_is_rejected_and_fallback_is_visible() -> None:
    def post(url, headers, json, timeout):
        return _response(
            url,
            {
                "selections": [
                    _selection("antenna_install_height_m", "select_candidate", "unknown"),
                    _selection("beamwidth_deg", "keep_current"),
                    _selection("include_cables", "keep_current"),
                    _selection("include_sector_beams", "keep_current"),
                ]
            },
        )

    result = GroqPlanningDecisionClient(api_key="test-key", post=post).decide(_request())

    assert result.resolved_values == _request().current_values
    assert result.diagnostics.status == "deterministic_fallback"
    assert result.diagnostics.fallback_used is True
    assert result.diagnostics.fallback_reason == "model_output_rejected"
    assert {selection.action for selection in result.selections} == {"keep_current"}


def test_explicitly_protected_field_cannot_be_overridden() -> None:
    decision = PlanningModelDecision.model_validate(
        {
            "selections": [
                _selection("antenna_install_height_m", "keep_current"),
                _selection("beamwidth_deg", "select_candidate", "rag:beamwidth:1"),
                _selection("include_cables", "keep_current"),
                _selection("include_sector_beams", "keep_current"),
            ]
        }
    )

    with pytest.raises(ValueError, match="protected field"):
        resolve_model_decision(_request(), decision, model_name="openai/gpt-oss-120b")


def test_candidate_from_another_field_cannot_be_selected() -> None:
    decision = PlanningModelDecision.model_validate(
        {
            "selections": [
                _selection("antenna_install_height_m", "select_candidate", "rag:beamwidth:1"),
                _selection("beamwidth_deg", "keep_current"),
                _selection("include_cables", "keep_current"),
                _selection("include_sector_beams", "keep_current"),
            ]
        }
    )

    with pytest.raises(ValueError, match="belongs to"):
        resolve_model_decision(_request(), decision, model_name="openai/gpt-oss-120b")


def test_free_value_or_unknown_field_is_rejected_by_strict_contract() -> None:
    payload = {
        "selections": [
            {**_selection("antenna_install_height_m", "keep_current"), "value": 99.0},
            _selection("beamwidth_deg", "keep_current"),
            _selection("include_cables", "keep_current"),
            _selection("include_sector_beams", "keep_current"),
        ]
    }

    with pytest.raises(ValidationError):
        PlanningModelDecision.model_validate(payload)

    payload["selections"][0] = _selection("tower_height_m", "keep_current")
    with pytest.raises(ValidationError):
        PlanningModelDecision.model_validate(payload)


def test_request_rejects_unknown_memory_risk_candidate() -> None:
    payload = _request().model_dump()
    payload["memory_risks"][0]["related_candidate_ids"] = ["missing:candidate"]

    with pytest.raises(ValidationError, match="unknown candidates"):
        PlanningDecisionRequest.model_validate(payload)


def test_request_rejects_out_of_range_candidate_before_provider_call() -> None:
    payload = _request().model_dump()
    payload["candidates"][0]["value"] = 151.0

    with pytest.raises(ValidationError, match="outside the global range"):
        PlanningDecisionRequest.model_validate(payload)


def test_timeout_uses_explicit_deterministic_fallback() -> None:
    def post(url, headers, json, timeout):
        raise httpx.ReadTimeout("deadline exceeded", request=httpx.Request("POST", url))

    result = GroqPlanningDecisionClient(api_key="test-key", post=post).decide(_request())

    assert result.diagnostics.fallback_used is True
    assert result.diagnostics.fallback_reason == "provider_timeout"
    assert result.resolved_values == _request().current_values


def test_duplicate_or_missing_decision_field_is_rejected() -> None:
    decision = PlanningModelDecision.model_validate(
        {
            "selections": [
                _selection("antenna_install_height_m", "keep_current"),
                _selection("beamwidth_deg", "keep_current"),
                _selection("include_cables", "keep_current"),
                _selection("include_cables", "keep_current"),
            ]
        }
    )

    with pytest.raises(ValueError, match="duplicate field"):
        resolve_model_decision(_request(), decision, model_name="openai/gpt-oss-120b")


def _request() -> PlanningDecisionRequest:
    return PlanningDecisionRequest(
        current_values=PlanningCurrentValues(
            antenna_install_height_m=24.0,
            beamwidth_deg=65.0,
            include_cables=True,
            include_sector_beams=True,
        ),
        protected_fields=["beamwidth_deg"],
        candidates=[
            PlanningCandidate(
                candidate_id="rag:hba:1",
                field="antenna_install_height_m",
                value=25.0,
                provenance=PlanningCandidateProvenance(
                    source="rag",
                    reference_id="telecom-rule-18",
                    rank=1,
                    score=0.93,
                    collection="telecom_rules",
                    document_name="installation_rules.md",
                    excerpt="For this tower profile, use 25 m when the source leaves HBA open.",
                ),
            ),
            PlanningCandidate(
                candidate_id="rag:beamwidth:1",
                field="beamwidth_deg",
                value=90.0,
                provenance=PlanningCandidateProvenance(
                    source="rag",
                    reference_id="coverage-rule-4",
                    rank=1,
                ),
            ),
            PlanningCandidate(
                candidate_id="memory:cables:1",
                field="include_cables",
                value=False,
                provenance=PlanningCandidateProvenance(
                    source="memory",
                    reference_id="validated-scene-12",
                    rank=1,
                    score=0.81,
                ),
            ),
        ],
        memory_risks=[
            PlanningMemoryRisk(
                risk_id="memory-age-1",
                severity="medium",
                summary="The remembered scene used a different tower family.",
                related_candidate_ids=["memory:cables:1"],
            )
        ],
    )


def _selection(field: str, action: str, candidate_id: str | None = None) -> dict:
    return {
        "field": field,
        "action": action,
        "candidate_id": candidate_id,
        "reason": "Selected the strongest bounded evidence.",
    }


def _response(url: str, payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )
