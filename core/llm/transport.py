from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx

from core.contracts.vision import VisionCapabilityHealth
from core.llm.groq_policy import normalize_groq_base_url

GroqFailureReason = Literal[
    "provider_timeout",
    "provider_authentication_failed",
    "provider_rate_limited",
    "provider_unavailable",
    "provider_transport_error",
    "provider_circuit_open",
    "model_output_rejected",
]


class GroqTransportError(RuntimeError):
    """Sanitized provider error; it never contains request headers or the API key."""

    def __init__(
        self,
        reason: GroqFailureReason,
        *,
        attempts: int,
        retryable: bool,
        status_code: int | None = None,
        retry_after_s: float | None = None,
        provider_error_code: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after_s = retry_after_s
        self.provider_error_code = provider_error_code


@dataclass(frozen=True)
class GroqTransportResponse:
    body: dict[str, Any]
    attempts: int
    latency_ms: int


@dataclass
class _CapabilityState:
    consecutive_failures: int = 0
    circuit_open_until_monotonic: float | None = None
    last_error: str | None = None
    last_success_at: datetime | None = None
    operational: bool = False


class GroqTransport:
    """Persistent, injectable transport shared by bounded Groq capabilities.

    HTTP retries are limited to transient transport/provider failures. Schema or
    business validation remains owned by each capability client.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        client: httpx.Client | None = None,
        max_transient_retries: int = 2,
        circuit_failure_threshold: int = 3,
        circuit_reset_s: float = 30.0,
        backoff_base_s: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("api_key must not be empty")
        if not 0 <= max_transient_retries <= 5:
            raise ValueError("max_transient_retries must be between 0 and 5")
        if not 1 <= circuit_failure_threshold <= 20:
            raise ValueError("circuit_failure_threshold must be between 1 and 20")
        if not 1 <= circuit_reset_s <= 600:
            raise ValueError("circuit_reset_s must be between 1 and 600")
        if not 0 < backoff_base_s <= 10:
            raise ValueError("backoff_base_s must be between 0 and 10")
        self.base_url = normalize_groq_base_url(base_url)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            headers={
                "Authorization": f"Bearer {normalized_key}",
                "Content-Type": "application/json",
            }
        )
        self._api_key = normalized_key
        self._max_transient_retries = max_transient_retries
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_reset_s = circuit_reset_s
        self._backoff_base_s = backoff_base_s
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._jitter = jitter
        self._states: dict[str, _CapabilityState] = {}
        self._lock = threading.RLock()
        self._closed = False

    def request_chat_completion(
        self,
        *,
        capability: str,
        payload: dict[str, Any],
        timeout_s: float,
    ) -> GroqTransportResponse:
        if not capability.strip():
            raise ValueError("capability must not be empty")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._ensure_open()
        started = self._monotonic()
        self._reject_if_circuit_open(capability)
        last_error: GroqTransportError | None = None

        for attempt in range(1, self._max_transient_retries + 2):
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_s,
                )
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise TypeError("provider response envelope must be a JSON object")
                return GroqTransportResponse(
                    body=body,
                    attempts=attempt,
                    latency_ms=_elapsed_ms(started, self._monotonic()),
                )
            except Exception as exc:
                classified = _classify_error(exc, attempt)
                last_error = classified
                if classified.retryable and attempt <= self._max_transient_retries:
                    self._sleeper(
                        _retry_delay(
                            classified,
                            attempt=attempt,
                            base_s=self._backoff_base_s,
                            jitter=self._jitter(),
                        )
                    )
                    continue
                self.mark_failed(
                    capability,
                    classified.reason,
                    contributes_to_circuit=classified.retryable,
                )
                raise classified from None

        # The loop always returns or raises. This guard protects future edits.
        assert last_error is not None
        raise last_error

    def mark_operational(self, capability: str) -> None:
        with self._lock:
            state = self._states.setdefault(capability, _CapabilityState())
            state.consecutive_failures = 0
            state.circuit_open_until_monotonic = None
            state.last_error = None
            state.last_success_at = datetime.now(UTC)
            state.operational = True

    def mark_failed(
        self,
        capability: str,
        reason: str,
        *,
        contributes_to_circuit: bool = False,
    ) -> None:
        clean_reason = reason[:160]
        with self._lock:
            state = self._states.setdefault(capability, _CapabilityState())
            state.last_error = clean_reason
            if contributes_to_circuit:
                state.consecutive_failures += 1
                if state.consecutive_failures >= self._circuit_failure_threshold:
                    state.circuit_open_until_monotonic = self._monotonic() + self._circuit_reset_s
            else:
                state.consecutive_failures = max(1, state.consecutive_failures)
            state.operational = False

    def health(
        self,
        capability: str,
        *,
        enabled: bool = True,
        advisory_only: bool = True,
    ) -> VisionCapabilityHealth:
        # VisionCapabilityHealth intentionally accepts only declared vision
        # capability IDs; text health remains an internal transport concern.
        with self._lock:
            state = self._states.setdefault(capability, _CapabilityState())
            now = self._monotonic()
            if state.circuit_open_until_monotonic is not None:
                if state.circuit_open_until_monotonic <= now:
                    state.circuit_open_until_monotonic = None
                else:
                    remaining = state.circuit_open_until_monotonic - now
                    circuit_until = datetime.now(UTC) + timedelta(seconds=remaining)
                    return VisionCapabilityHealth(
                        capability=capability,
                        status="failed" if enabled else "disabled",
                        advisory_only=advisory_only,
                        consecutive_failures=state.consecutive_failures,
                        circuit_open_until=circuit_until,
                        last_error=state.last_error or "provider_circuit_open",
                        last_success_at=state.last_success_at,
                    )
            if not enabled:
                status = "disabled"
            elif state.operational:
                status = "operational"
            elif state.last_error:
                status = "failed"
            else:
                status = "configured_unverified"
            return VisionCapabilityHealth(
                capability=capability,
                status=status,
                advisory_only=advisory_only,
                consecutive_failures=state.consecutive_failures,
                last_error=state.last_error,
                last_success_at=state.last_success_at,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self._owns_client:
            self._client.close()

    def _ensure_open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("GroqTransport is closed")

    def _reject_if_circuit_open(self, capability: str) -> None:
        with self._lock:
            state = self._states.setdefault(capability, _CapabilityState())
            open_until = state.circuit_open_until_monotonic
            if open_until is None:
                return
            now = self._monotonic()
            if open_until <= now:
                state.circuit_open_until_monotonic = None
                state.consecutive_failures = 0
                return
            raise GroqTransportError(
                "provider_circuit_open",
                attempts=0,
                retryable=False,
                retry_after_s=open_until - now,
            )


def chat_message_content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TypeError("provider response does not contain message content") from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise TypeError("provider message content must be a string")
    return content


def chat_message_json(body: dict[str, Any]) -> dict[str, Any]:
    parsed = json.loads(chat_message_content(body))
    if not isinstance(parsed, dict):
        raise TypeError("provider message content must be a JSON object")
    return parsed


def _classify_error(exc: Exception, attempt: int) -> GroqTransportError:
    if isinstance(exc, GroqTransportError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return GroqTransportError(
            "provider_timeout",
            attempts=attempt,
            retryable=True,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        retry_after = _retry_after_seconds(exc.response.headers.get("Retry-After"))
        if status in {401, 403}:
            reason: GroqFailureReason = "provider_authentication_failed"
            retryable = False
        elif status == 429:
            reason = "provider_rate_limited"
            retryable = True
        elif status >= 500:
            reason = "provider_unavailable"
            retryable = True
        else:
            reason = "model_output_rejected"
            retryable = False
        return GroqTransportError(
            reason,
            attempts=attempt,
            retryable=retryable,
            status_code=status,
            retry_after_s=retry_after,
            provider_error_code=_provider_error_code(exc.response),
        )
    if isinstance(exc, httpx.RequestError):
        return GroqTransportError(
            "provider_transport_error",
            attempts=attempt,
            retryable=True,
        )
    return GroqTransportError(
        "model_output_rejected",
        attempts=attempt,
        retryable=False,
    )


def _retry_delay(
    error: GroqTransportError,
    *,
    attempt: int,
    base_s: float,
    jitter: float,
) -> float:
    if error.retry_after_s is not None:
        return max(0.0, error.retry_after_s)
    bounded_jitter = min(1.0, max(0.0, jitter))
    return base_s * (2 ** (attempt - 1)) + bounded_jitter * base_s


def _provider_error_code(response: httpx.Response) -> str | None:
    """Keep only a bounded machine code; never retain provider messages or payloads."""

    try:
        error = response.json().get("error", {})
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    if not isinstance(error, dict):
        return None
    value = error.get("code")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 96:
        return None
    if any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in normalized
    ):
        return None
    return normalized


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def _elapsed_ms(started: float, completed: float) -> int:
    return max(0, round((completed - started) * 1000))
