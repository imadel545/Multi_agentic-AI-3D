from __future__ import annotations

import json
import threading

import httpx
import pytest

from core.llm.asset_selection import GroqAssetSelectionClient
from core.llm.groq import GroqStructuredClient
from core.llm.transport import GroqTransport, GroqTransportError


def test_single_credential_rate_limit_never_blocks_the_worker() -> None:
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
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="asset_visual_review",
                payload={"model": "qwen/qwen3.6-27b"},
                timeout_s=3,
            )
        assert caught.value.reason == "provider_rate_limited"
        assert caught.value.attempts == 1
        assert calls == 1
        assert sleeps == []
        assert transport.credential_pool_status()["cooldown_credentials"] == 1
    finally:
        transport.close()
        client.close()


def test_transport_caps_untrusted_retry_after_without_hiding_provider_value() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "7200"}, request=request)
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    now = [100.0]
    transport = GroqTransport(
        api_key="secret-test-key",
        client=client,
        max_retry_after_s=30,
        sleeper=sleeps.append,
        monotonic=lambda: now[0],
        jitter=lambda: 0,
    )
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="planning_decision",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert caught.value.retry_after_s == 7200
        assert sleeps == []
        assert transport.credential_pool_status()["ready_credentials"] == 0
        now[0] += 30
        assert transport.credential_pool_status()["ready_credentials"] == 1
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


def test_pool_fails_over_immediately_when_one_credential_is_rate_limited() -> None:
    authorizations: list[str] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer account-a-key":
            return httpx.Response(429, headers={"Retry-After": "20"}, request=request)
        return _chat_response(request, {"served_by": "account-b"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["account-a-key", "account-b-key"],
        client=client,
        sleeper=sleeps.append,
        jitter=lambda: 0,
    )
    try:
        result = transport.request_chat_completion(
            capability="planning_decision",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )

        assert result.attempts == 2
        assert authorizations == ["Bearer account-a-key", "Bearer account-b-key"]
        assert sleeps == []
        snapshot = transport.credential_pool_status()
        assert snapshot["configured_credentials"] == 2
        assert snapshot["cooldown_credentials"] == 1
        assert snapshot["credentials_with_provider_response"] == 1
    finally:
        transport.close()
        client.close()


def test_groq_413_rate_limit_code_cools_account_and_fails_over() -> None:
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer lower-tpm-account":
            return httpx.Response(
                413,
                request=request,
                json={"error": {"code": "rate_limit_exceeded"}},
            )
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["lower-tpm-account", "higher-tpm-account"],
        client=client,
        rate_limit_default_cooldown_s=60,
    )
    try:
        result = transport.request_chat_completion(
            capability="asset_selection",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )

        assert result.attempts == 2
        assert authorizations == [
            "Bearer lower-tpm-account",
            "Bearer higher-tpm-account",
        ]
        assert transport.credential_pool_status()["cooldown_credentials"] == 1
    finally:
        transport.close()
        client.close()


def test_pool_quarantines_bad_auth_without_exposing_or_blocking_healthy_account() -> None:
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer revoked-secret":
            return httpx.Response(401, request=request, json={"error": "denied"})
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["revoked-secret", "healthy-secret"],
        client=client,
        sleeper=lambda _s: None,
    )
    try:
        first = transport.request_chat_completion(
            capability="asset_selection",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )
        second = transport.request_chat_completion(
            capability="asset_selection",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )

        assert first.attempts == 2
        assert second.attempts == 1
        assert authorizations == [
            "Bearer revoked-secret",
            "Bearer healthy-secret",
            "Bearer healthy-secret",
        ]
        snapshot = transport.credential_pool_status()
        assert snapshot["disabled_credentials"] == 1
        assert snapshot["ready_credentials"] == 1
        assert "revoked-secret" not in repr(snapshot)
        assert "healthy-secret" not in repr(snapshot)
    finally:
        transport.close()
        client.close()


def test_forbidden_model_scope_does_not_disable_other_capabilities() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        model = json.loads(request.content)["model"]
        calls.append((authorization, model))
        if authorization == "Bearer account-a" and model == "vision-model":
            return httpx.Response(403, request=request)
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=client)
    try:
        vision = transport.request_chat_completion(
            capability="multimodal_interpretation",
            payload={"model": "vision-model"},
            timeout_s=3,
        )
        text = transport.request_chat_completion(
            capability="requirement_extraction",
            payload={"model": "text-model"},
            timeout_s=3,
        )

        assert vision.attempts == 2
        assert text.attempts == 1
        assert calls == [
            ("Bearer account-a", "vision-model"),
            ("Bearer account-b", "vision-model"),
            ("Bearer account-a", "text-model"),
        ]
        snapshot = transport.credential_pool_status()
        assert snapshot["disabled_credentials"] == 0
        assert snapshot["capability_restricted_credentials"] == 1
    finally:
        transport.close()
        client.close()


def test_all_rate_limited_accounts_fail_fast_without_sleeping() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "60"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["account-a", "account-b"],
        client=client,
        sleeper=sleeps.append,
    )
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="planning_decision",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert caught.value.reason == "provider_rate_limited"
        assert caught.value.attempts == 2
        assert calls == 2
        assert sleeps == []
        assert transport.credential_pool_status()["cooldown_credentials"] == 2
    finally:
        transport.close()
        client.close()


def test_credential_failover_checks_fourth_account_without_multiplying_transient_retries() -> None:
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        authorizations.append(authorization)
        if authorization != "Bearer account-d":
            return httpx.Response(401, request=request)
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["account-a", "account-b", "account-c", "account-d"],
        client=client,
    )
    try:
        result = transport.request_chat_completion(
            capability="requirement_extraction",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )

        assert result.attempts == 4
        assert authorizations[-1] == "Bearer account-d"
        assert transport.credential_pool_status()["disabled_credentials"] == 3
    finally:
        transport.close()
        client.close()


def test_pool_rejects_more_credentials_than_its_supported_bound() -> None:
    with pytest.raises(ValueError, match="at most eight"):
        GroqTransport(api_keys=[f"account-{index}" for index in range(9)])


def test_pool_balances_serial_requests_across_healthy_accounts() -> None:
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers["Authorization"])
        return _chat_response(request, {"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=client)
    try:
        for _ in range(4):
            transport.request_chat_completion(
                capability="extraction",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert authorizations == [
            "Bearer account-a",
            "Bearer account-b",
            "Bearer account-a",
            "Bearer account-b",
        ]
    finally:
        transport.close()
        client.close()


def test_pool_prefers_idle_credential_for_concurrent_requests() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    authorizations: list[str] = []
    results: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["Authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer account-a":
            first_entered.set()
            assert release_first.wait(timeout=2)
        return _chat_response(request, {"authorization": authorization})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=client)

    def call() -> None:
        response = transport.request_chat_completion(
            capability="extraction",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )
        results.append(response.body)

    first_thread = threading.Thread(target=call)
    second_thread = threading.Thread(target=call)
    try:
        first_thread.start()
        assert first_entered.wait(timeout=2)
        second_thread.start()
        second_thread.join(timeout=2)
        release_first.set()
        first_thread.join(timeout=2)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()
        assert sorted(authorizations) == ["Bearer account-a", "Bearer account-b"]
        assert len(results) == 2
        assert transport.credential_pool_status()["in_flight_requests"] == 0
    finally:
        release_first.set()
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)
        transport.close()
        client.close()


def test_pool_queues_above_per_account_concurrency_and_releases_slot() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    calls = 0
    results: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        return _chat_response(request, {"call": calls})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_key="one-account",
        client=client,
        max_in_flight_per_credential=1,
        pool_acquire_timeout_s=2,
    )

    def call() -> None:
        response = transport.request_chat_completion(
            capability="asset_selection",
            payload={"model": "openai/gpt-oss-120b"},
            timeout_s=3,
        )
        results.append(response.body)

    first_thread = threading.Thread(target=call)
    second_thread = threading.Thread(target=call)
    try:
        first_thread.start()
        assert first_entered.wait(timeout=2)
        second_thread.start()
        assert transport.credential_pool_status()["saturated_credentials"] == 1
        release_first.set()
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()
        assert calls == 2
        assert len(results) == 2
        assert transport.credential_pool_status()["in_flight_requests"] == 0
    finally:
        release_first.set()
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)
        transport.close()
        client.close()


def test_transient_failures_keep_one_global_network_attempt_budget() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(
        api_keys=["account-a", "account-b", "account-c", "account-d"],
        client=client,
        max_transient_retries=2,
        sleeper=lambda _s: None,
    )
    try:
        with pytest.raises(GroqTransportError):
            transport.request_chat_completion(
                capability="requirement_extraction",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert calls == 3
    finally:
        transport.close()
        client.close()


def test_non_retryable_payload_error_is_not_hidden_by_another_credential() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            request=request,
            json={"error": {"code": "json_validate_failed"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=client)
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="geometry_program",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert caught.value.reason == "model_output_rejected"
        assert caught.value.attempts == 1
        assert calls == 1
    finally:
        transport.close()
        client.close()


def test_asset_selection_retries_one_provider_json_validation_rejection() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                400,
                request=request,
                json={"error": {"code": "json_validate_failed"}},
            )
        return _chat_response(request, {"selections": {"tower": "choice_0001"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=http_client)
    selector = GroqAssetSelectionClient(api_key="account-a", transport=transport)
    try:
        selections, diagnostics = selector.decide(
            slots=[
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
        )

        assert calls == 2
        assert selections == {"tower": "TOWER_1"}
        assert diagnostics["attempts"] == 2
        assert "fallback_reason" not in diagnostics
    finally:
        transport.close()
        http_client.close()


@pytest.mark.parametrize(
    "error_type",
    [httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError],
)
def test_ambiguous_or_local_timeout_is_never_replayed_on_another_account(
    error_type: type[httpx.RequestError],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise error_type("ambiguous", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = GroqTransport(api_keys=["account-a", "account-b"], client=client)
    try:
        with pytest.raises(GroqTransportError) as caught:
            transport.request_chat_completion(
                capability="geometry_program",
                payload={"model": "openai/gpt-oss-120b"},
                timeout_s=3,
            )

        assert caught.value.reason == "provider_timeout"
        assert caught.value.retryable is False
        assert caught.value.attempts == 1
        assert calls == 1
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
                {"selections": {"tower": "choice_0001"}},
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
