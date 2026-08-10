from __future__ import annotations

import json

import httpx
import pytest

from core.llm.asset_selection import GroqAssetSelectionClient
from core.llm.groq import GroqStructuredClient
from core.llm.transport import GroqTransport, GroqTransportError, chat_message_json


def test_transport_honors_retry_after_and_becomes_operational_only_after_validation() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"}, request=request)
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_key="secret-test-key",
        client=client,
        sleeper=sleeps.append,
        jitter=lambda: 0,
    )
    try:
        assert transport.health("asset_visual_review").status == "configured_unverified"
        result = transport.request_chat_completion(
            capability="asset_visual_review",
            payload={"model": "qwen/qwen3.6-27b"},
            timeout_s=3,
        )
        assert chat_message_json(result.body) == {"ok": True}
        assert result.attempts == 2
        assert sleeps == [1.5]
        assert transport.health("asset_visual_review").status == "configured_unverified"

        transport.mark_operational("asset_visual_review")
        health = transport.health("asset_visual_review")
        assert health.status == "operational"
        assert health.last_success_at is not None
    finally:
        transport.close()
        client.close()


def test_authentication_failure_is_not_retried_or_leaked() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, request=request, json={"error": "denied"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_key="must-not-leak", client=client, sleeper=lambda _s: None)
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="asset_visual_review",
                payload={"model": "qwen/qwen3.6-27b"},
                timeout_s=3,
            )
        assert caught.value.reason == "provider_authentication_failed"
        assert caught.value.attempts == 1
        assert calls == 1
        assert "must-not-leak" not in str(caught.value)
        assert transport.health("asset_visual_review").status == "failed"
    finally:
        transport.close()
        client.close()


def test_transport_retains_only_bounded_provider_error_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "code": "json_validate_failed",
                    "message": "Failed generation contains provider-only details.",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_key="must-not-leak", client=client)
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="asset_visual_review",
                payload={"model": "qwen/qwen3.6-27b"},
                timeout_s=3,
            )
        assert caught.value.provider_error_code == "json_validate_failed"
        assert "provider-only details" not in str(caught.value)
    finally:
        transport.close()
        client.close()


def test_repeated_transient_failures_open_capability_circuit() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_key="test-key",
        client=client,
        max_transient_retries=0,
        circuit_failure_threshold=2,
        sleeper=lambda _s: None,
    )
    try:
        for _ in range(2):
            with pytest.raises(GroqTransportError, match="provider_unavailable"):
                transport.request_chat_completion(
                    capability="multimodal_interpretation",
                    payload={"model": "qwen/qwen3.6-27b"},
                    timeout_s=3,
                )
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="multimodal_interpretation",
                payload={"model": "qwen/qwen3.6-27b"},
                timeout_s=3,
            )
        assert caught.value.reason == "provider_circuit_open"
        assert caught.value.attempts == 0
        assert calls == 2
        health = transport.health("multimodal_interpretation")
        assert health.status == "failed"
        assert health.circuit_open_until is not None
    finally:
        transport.close()
        client.close()


def test_disabled_capability_is_not_reported_as_configured() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: _chat_response(request, {}))
    )
    transport = GroqTransport(api_key="test-key", client=client)
    try:
        health = transport.health("visual_design_critic", enabled=False)
        assert health.status == "disabled"
        assert health.advisory_only is True
    finally:
        transport.close()
        client.close()


def test_one_persistent_transport_is_injectable_into_existing_clients() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        schema_name = payload.get("response_format", {}).get("json_schema", {}).get("name")
        if schema_name == "BoundedAssetSelection":
            return _chat_response(
                request,
                {
                    "selections": [
                        {
                            "role_id": "tower",
                            "asset_id": "TOWER_1",
                            "generation_strategy": "internal_project_generated",
                            "semantic_strategy": "compose_assets",
                            "reason": "Only qualified candidate.",
                        }
                    ]
                },
            )
        return _chat_response(request, {"accepted": True})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_key="test-key", client=http_client)
    structured = GroqStructuredClient(api_key="test-key", transport=transport)
    selector = GroqAssetSelectionClient(api_key="test-key", transport=transport)
    slots = [
        {
            "role_id": "tower",
            "candidates": [
                {
                    "asset_id": "TOWER_1",
                    "allowed_generation_strategies": ["internal_project_generated"],
                    "allowed_semantic_strategies": ["compose_assets"],
                }
            ],
        }
    ]
    try:
        assert structured.request_json(
            {
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "Return JSON."}],
                "response_format": {"type": "json_object"},
            }
        ) == {"accepted": True}
        selections, diagnostics = selector.decide(slots=slots)
        assert selections == {"tower": "TOWER_1"}
        assert diagnostics["attempts"] == 1
        assert calls == 2
    finally:
        transport.close()
        http_client.close()


def _chat_response(request: httpx.Request, content: dict) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={"choices": [{"message": {"content": json.dumps(content)}}]},
    )
