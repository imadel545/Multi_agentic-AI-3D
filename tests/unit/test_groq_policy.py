from __future__ import annotations

import json

import httpx
import pytest

from core.llm.asset_selection import GroqAssetSelectionClient
from core.llm.groq_policy import GroqRequestPolicy, normalize_groq_base_url


def test_structured_output_policy_disables_streaming_and_tools() -> None:
    policy = GroqRequestPolicy(
        capability="test",
        reasoning_effort="medium",
        max_completion_tokens=512,
    )

    payload = policy.apply({"model": "openai/gpt-oss-120b"})

    assert payload["reasoning_effort"] == "medium"
    assert payload["max_completion_tokens"] == 512
    assert payload["stream"] is False
    assert "tools" not in payload
    with pytest.raises(ValueError, match="cannot be streamed"):
        policy.apply({"stream": True})
    with pytest.raises(ValueError, match="tool use"):
        policy.apply({"tools": [{"type": "function"}]})


def test_groq_base_url_requires_https_except_localhost() -> None:
    assert normalize_groq_base_url("https://api.groq.com/openai/v1/") == (
        "https://api.groq.com/openai/v1"
    )
    assert normalize_groq_base_url("http://localhost:9999/v1") == "http://localhost:9999/v1"
    with pytest.raises(ValueError, match="HTTPS"):
        normalize_groq_base_url("http://example.com/v1")


def test_asset_selector_rejects_an_asset_outside_the_role_candidates() -> None:
    def post(url, headers, json, timeout):
        request = httpx.Request("POST", url)
        content = {
            "selections": [{"role_id": "tower", "asset_id": "ANTENNA_1", "reason": "invalid role"}]
        }
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": json_module(content)}}]},
        )

    selections, diagnostics = GroqAssetSelectionClient(
        api_key="test-key",
        post=post,
    ).decide(slots=[{"role_id": "tower", "candidate_asset_ids": ["TOWER_1"]}])

    assert selections == {}
    assert diagnostics["fallback_reason"] == "model_output_rejected"


def test_asset_selector_chooses_only_a_scored_candidate_and_allowed_strategy() -> None:
    captured = {}

    def post(url, headers, json, timeout):
        del headers, timeout
        captured.update(json)
        request = httpx.Request("POST", url)
        content = {
            "selections": {
                "tower": {
                    "choice_id": "choice_0001",
                    "reason": "Best dimensional score within the allowed strategy.",
                }
            }
        }
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": json_module(content)}}]},
        )

    slots = [
        {
            "role_id": "tower",
            "candidate_asset_ids": ["TOWER_1"],
            "candidates": [
                {
                    "asset_id": "TOWER_1",
                    "score": {"total_score": 92.0, "dimensional_score": 98.0},
                    "dimensions_m": {"width": 4.0, "depth": 4.0, "height": 30.0},
                    "allowed_generation_strategies": ["internal_project_generated"],
                    "allowed_semantic_strategies": ["compose_assets"],
                }
            ],
        }
    ]

    selections, diagnostics = GroqAssetSelectionClient(
        api_key="test-key",
        post=post,
    ).decide(slots=slots)

    assert selections == {"tower": "TOWER_1"}
    assert diagnostics["generation_strategies"] == {"tower": "internal_project_generated"}
    assert diagnostics["semantic_strategies"] == {"tower": "compose_assets"}
    prompt_slots = json.loads(captured["messages"][1]["content"])["slots"]
    assert prompt_slots[0]["candidates"][0]["score"]["total_score"] == 92.0
    schema = captured["response_format"]["json_schema"]["schema"]
    tower_schema = schema["properties"]["selections"]["properties"]["tower"]
    assert tower_schema["properties"]["choice_id"]["enum"] == ["choice_0001"]
    assert set(tower_schema["required"]) == {"choice_id", "reason"}


def test_asset_selection_choice_schema_represents_only_exact_candidate_tuples() -> None:
    slots = [
        {
            "role_id": "tower",
            "candidates": [
                {
                    "asset_id": "TOWER_EXACT",
                    "allowed_generation_strategies": ["imported_glb_exact"],
                    "allowed_semantic_strategies": [
                        "reuse_component",
                        "adapt_component",
                    ],
                },
                {
                    "asset_id": "TOWER_PARAMETRIC",
                    "allowed_generation_strategies": ["internal_project_generated"],
                    "allowed_semantic_strategies": [
                        "compose_assets",
                        "adapt_component",
                    ],
                },
            ],
        }
    ]

    payload = GroqAssetSelectionClient(api_key="test-key")._payload(slots)
    schema = payload["response_format"]["json_schema"]["schema"]
    prompt = json.loads(payload["messages"][1]["content"])

    def exact_tuple(choice: dict) -> tuple[str, str, str, str]:
        return (
            choice["role_id"],
            choice["asset_id"],
            choice["generation_strategy"],
            choice["semantic_strategy"],
        )

    represented = {exact_tuple(choice) for choice in prompt["allowed_choices"]}
    assert represented == {
        ("tower", "TOWER_EXACT", "imported_glb_exact", "reuse_component"),
        ("tower", "TOWER_EXACT", "imported_glb_exact", "adapt_component"),
        (
            "tower",
            "TOWER_PARAMETRIC",
            "internal_project_generated",
            "compose_assets",
        ),
        (
            "tower",
            "TOWER_PARAMETRIC",
            "internal_project_generated",
            "adapt_component",
        ),
    }
    assert (
        "tower",
        "TOWER_EXACT",
        "internal_project_generated",
        "compose_assets",
    ) not in represented
    assert (
        "tower",
        "TOWER_PARAMETRIC",
        "imported_glb_exact",
        "reuse_component",
    ) not in represented
    selections_schema = schema["properties"]["selections"]
    assert selections_schema["additionalProperties"] is False
    assert selections_schema["required"] == ["tower"]
    tower_schema = selections_schema["properties"]["tower"]
    assert tower_schema["additionalProperties"] is False
    assert set(tower_schema["required"]) == {"choice_id", "reason"}
    assert tower_schema["properties"]["choice_id"]["enum"] == [
        choice["choice_id"] for choice in prompt["allowed_choices"]
    ]


def test_asset_selector_keeps_local_choice_role_validation() -> None:
    def post(url, headers, json, timeout):
        del headers, json, timeout
        request = httpx.Request("POST", url)
        content = {
            "selections": {
                "tower": {
                    "choice_id": "choice_0002",
                    "reason": "Choice belongs to another role.",
                },
                "antenna": {
                    "choice_id": "choice_0002",
                    "reason": "Valid choice for this role.",
                },
            }
        }
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": json_module(content)}}]},
        )

    slots = [
        {
            "role_id": "tower",
            "candidates": [
                {
                    "asset_id": "TOWER_EXACT",
                    "allowed_generation_strategies": ["imported_glb_exact"],
                    "allowed_semantic_strategies": ["reuse_component"],
                },
                {
                    "asset_id": "TOWER_PARAMETRIC",
                    "allowed_generation_strategies": ["internal_project_generated"],
                    "allowed_semantic_strategies": ["compose_assets"],
                },
            ],
        },
        {
            "role_id": "antenna",
            "candidates": [
                {
                    "asset_id": "ANTENNA_EXACT",
                    "allowed_generation_strategies": ["imported_glb_exact"],
                    "allowed_semantic_strategies": ["reuse_component"],
                }
            ],
        },
    ]

    selections, diagnostics = GroqAssetSelectionClient(
        api_key="test-key",
        post=post,
    ).decide(slots=slots)

    assert selections == {}
    assert diagnostics["fallback_reason"] == "model_output_rejected"


def json_module(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"))
