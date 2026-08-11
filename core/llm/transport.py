from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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


@dataclass
class _CredentialState:
    api_key: str = field(repr=False)
    in_flight: int = 0
    cooldown_until_monotonic: float | None = None
    authentication_disabled: bool = False
    successful_requests: int = 0
    last_error: str | None = None
    forbidden_capabilities: set[str] = field(default_factory=set)


class GroqTransport:
    """Persistent, injectable transport shared by bounded Groq capabilities.

    HTTP retries are limited to transient transport/provider failures. Schema or
    business validation remains owned by each capability client.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_keys: Sequence[str] | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        client: httpx.Client | None = None,
        max_transient_retries: int = 2,
        circuit_failure_threshold: int = 3,
        circuit_reset_s: float = 30.0,
        backoff_base_s: float = 0.25,
        max_retry_after_s: float = 3600.0,
        rate_limit_default_cooldown_s: float = 60.0,
        max_in_flight_per_credential: int = 2,
        pool_acquire_timeout_s: float = 10.0,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        normalized_keys = _normalize_api_keys(api_key=api_key, api_keys=api_keys)
        if not 0 <= max_transient_retries <= 5:
            raise ValueError("max_transient_retries must be between 0 and 5")
        if not 1 <= circuit_failure_threshold <= 20:
            raise ValueError("circuit_failure_threshold must be between 1 and 20")
        if not 1 <= circuit_reset_s <= 600:
            raise ValueError("circuit_reset_s must be between 1 and 600")
        if not 0 < backoff_base_s <= 10:
            raise ValueError("backoff_base_s must be between 0 and 10")
        if not 1 <= max_retry_after_s <= 86_400:
            raise ValueError("max_retry_after_s must be between 1 and 86400")
        if not 1 <= rate_limit_default_cooldown_s <= 3600:
            raise ValueError("rate_limit_default_cooldown_s must be between 1 and 3600")
        if not 1 <= max_in_flight_per_credential <= 16:
            raise ValueError("max_in_flight_per_credential must be between 1 and 16")
        if not 0.1 <= pool_acquire_timeout_s <= 60:
            raise ValueError("pool_acquire_timeout_s must be between 0.1 and 60")
        self.base_url = normalize_groq_base_url(base_url)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            headers={
                "Content-Type": "application/json",
            }
        )
        self._credentials = [_CredentialState(api_key=value) for value in normalized_keys]
        self._selection_cursor = 0
        self._max_transient_retries = max_transient_retries
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_reset_s = circuit_reset_s
        self._backoff_base_s = backoff_base_s
        self._max_retry_after_s = max_retry_after_s
        self._rate_limit_default_cooldown_s = rate_limit_default_cooldown_s
        self._max_in_flight_per_credential = max_in_flight_per_credential
        self._pool_acquire_timeout_s = pool_acquire_timeout_s
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._jitter = jitter
        self._states: dict[str, _CapabilityState] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
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
        attempted_credentials: set[int] = set()
        attempt_limit = max(self._max_transient_retries + 1, len(self._credentials))
        transient_attempts = 0
        attempt = 0

        while attempt < attempt_limit:
            credential_index = self._acquire_credential(
                capability=capability,
                exclude=attempted_credentials,
            )
            if credential_index is None:
                if self._all_credentials_unavailable_for_capability(capability):
                    break
                attempted_credentials.clear()
                credential_index = self._acquire_credential(
                    capability=capability,
                    exclude=attempted_credentials,
                )
                if credential_index is None:
                    retry_after_s = self._minimum_credential_cooldown_remaining()
                    if retry_after_s is not None:
                        last_error = GroqTransportError(
                            "provider_rate_limited",
                            attempts=attempt,
                            retryable=True,
                            status_code=429,
                            retry_after_s=retry_after_s,
                        )
                    elif self._wait_for_credential_slot(
                        capability=capability,
                        timeout_s=min(timeout_s, self._pool_acquire_timeout_s),
                    ):
                        continue
                    else:
                        last_error = GroqTransportError(
                            "provider_transport_error",
                            attempts=attempt,
                            retryable=False,
                        )
                    break
            attempt += 1
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": (f"Bearer {self._credentials[credential_index].api_key}"),
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_s,
                )
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise TypeError("provider response envelope must be a JSON object")
                self._mark_credential_success(credential_index)
                return GroqTransportResponse(
                    body=body,
                    attempts=attempt,
                    latency_ms=_elapsed_ms(started, self._monotonic()),
                )
            except Exception as exc:
                classified = _classify_error(exc, attempt)
                last_error = classified
                if classified.reason == "provider_authentication_failed":
                    self._disable_credential(
                        credential_index,
                        classified.reason,
                        capability=capability,
                        global_disable=classified.status_code == 401,
                    )
                    attempted_credentials.add(credential_index)
                    if attempt < attempt_limit and self._has_ready_credential(
                        capability=capability,
                        exclude=attempted_credentials,
                    ):
                        continue
                    break
                if classified.reason == "provider_rate_limited":
                    delay = min(
                        self._max_retry_after_s,
                        (
                            classified.retry_after_s
                            if classified.retry_after_s is not None
                            else self._rate_limit_default_cooldown_s
                        ),
                    )
                    self._cooldown_credential(credential_index, delay, classified.reason)
                    attempted_credentials.add(credential_index)
                    if attempt < attempt_limit:
                        if self._has_ready_credential(
                            capability=capability,
                            exclude=attempted_credentials,
                        ):
                            continue
                    break
                if classified.retryable:
                    transient_attempts += 1
                if (
                    classified.retryable
                    and transient_attempts < self._max_transient_retries + 1
                    and attempt < attempt_limit
                ):
                    self._sleeper(
                        _retry_delay(
                            classified,
                            attempt=attempt,
                            base_s=self._backoff_base_s,
                            max_retry_after_s=self._max_retry_after_s,
                            jitter=self._jitter(),
                        )
                    )
                    attempted_credentials.add(credential_index)
                    if len(attempted_credentials) >= len(self._credentials):
                        attempted_credentials.clear()
                    continue
                break
            finally:
                self._release_credential(credential_index)

        if last_error is None:
            last_error = GroqTransportError(
                "provider_authentication_failed",
                attempts=attempt,
                retryable=False,
            )
        self.mark_failed(
            capability,
            last_error.reason,
            contributes_to_circuit=last_error.retryable,
        )
        raise last_error from None

    def credential_pool_status(self) -> dict[str, int | str]:
        """Return aggregate runtime state without credential identity or secret material."""

        with self._lock:
            self._expire_credential_cooldowns_locked()
            configured = len(self._credentials)
            disabled = sum(item.authentication_disabled for item in self._credentials)
            restricted = sum(bool(item.forbidden_capabilities) for item in self._credentials)
            cooling = sum(item.cooldown_until_monotonic is not None for item in self._credentials)
            saturated = sum(
                not item.authentication_disabled
                and item.cooldown_until_monotonic is None
                and item.in_flight >= self._max_in_flight_per_credential
                for item in self._credentials
            )
            ready = configured - disabled - cooling
            responded = sum(item.successful_requests > 0 for item in self._credentials)
            if ready == 0:
                status = "unavailable"
            elif disabled or cooling or restricted or saturated or (0 < responded < configured):
                status = "degraded"
            elif responded == configured:
                status = "operational"
            else:
                status = "configured_unverified"
            return {
                "status": status,
                "configured_credentials": configured,
                "ready_credentials": ready,
                "cooldown_credentials": cooling,
                "disabled_credentials": disabled,
                "capability_restricted_credentials": restricted,
                "credentials_with_provider_response": responded,
                "in_flight_requests": sum(item.in_flight for item in self._credentials),
                "saturated_credentials": saturated,
            }

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
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()
        if self._owns_client:
            self._client.close()

    def _ensure_open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("GroqTransport is closed")

    def _acquire_credential(self, *, capability: str, exclude: set[int]) -> int | None:
        with self._lock:
            self._expire_credential_cooldowns_locked()
            eligible = [
                index
                for index, state in enumerate(self._credentials)
                if index not in exclude
                and not state.authentication_disabled
                and capability not in state.forbidden_capabilities
                and state.cooldown_until_monotonic is None
                and state.in_flight < self._max_in_flight_per_credential
            ]
            if not eligible:
                return None
            minimum_in_flight = min(self._credentials[index].in_flight for index in eligible)
            least_loaded = {
                index
                for index in eligible
                if self._credentials[index].in_flight == minimum_in_flight
            }
            count = len(self._credentials)
            selected = next(
                index
                for offset in range(count)
                if (index := (self._selection_cursor + offset) % count) in least_loaded
            )
            self._selection_cursor = (selected + 1) % count
            self._credentials[selected].in_flight += 1
            return selected

    def _release_credential(self, index: int) -> None:
        with self._condition:
            state = self._credentials[index]
            state.in_flight = max(0, state.in_flight - 1)
            self._condition.notify_all()

    def _has_ready_credential(self, *, capability: str, exclude: set[int]) -> bool:
        with self._lock:
            self._expire_credential_cooldowns_locked()
            return any(
                index not in exclude
                and not state.authentication_disabled
                and capability not in state.forbidden_capabilities
                and state.cooldown_until_monotonic is None
                and state.in_flight < self._max_in_flight_per_credential
                for index, state in enumerate(self._credentials)
            )

    def _wait_for_credential_slot(self, *, capability: str, timeout_s: float) -> bool:
        deadline = self._monotonic() + timeout_s
        with self._condition:
            while True:
                self._expire_credential_cooldowns_locked()
                if self._closed:
                    return False
                if any(
                    not state.authentication_disabled
                    and capability not in state.forbidden_capabilities
                    and state.cooldown_until_monotonic is None
                    and state.in_flight < self._max_in_flight_per_credential
                    for state in self._credentials
                ):
                    return True
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)

    def _all_credentials_unavailable_for_capability(self, capability: str) -> bool:
        with self._lock:
            return all(
                state.authentication_disabled or capability in state.forbidden_capabilities
                for state in self._credentials
            )

    def _disable_credential(
        self,
        index: int,
        reason: str,
        *,
        capability: str,
        global_disable: bool,
    ) -> None:
        with self._lock:
            state = self._credentials[index]
            if global_disable:
                state.authentication_disabled = True
                state.cooldown_until_monotonic = None
            else:
                state.forbidden_capabilities.add(capability)
            state.last_error = reason

    def _cooldown_credential(self, index: int, delay_s: float, reason: str) -> None:
        with self._lock:
            state = self._credentials[index]
            state.cooldown_until_monotonic = self._monotonic() + max(0.0, delay_s)
            state.last_error = reason

    def _mark_credential_success(self, index: int) -> None:
        with self._lock:
            state = self._credentials[index]
            state.successful_requests += 1
            state.cooldown_until_monotonic = None
            state.last_error = None

    def _expire_credential_cooldowns_locked(self) -> None:
        now = self._monotonic()
        for state in self._credentials:
            if state.cooldown_until_monotonic is not None and state.cooldown_until_monotonic <= now:
                state.cooldown_until_monotonic = None

    def _minimum_credential_cooldown_remaining(self) -> float | None:
        with self._lock:
            self._expire_credential_cooldowns_locked()
            now = self._monotonic()
            remaining = [
                max(0.0, state.cooldown_until_monotonic - now)
                for state in self._credentials
                if not state.authentication_disabled and state.cooldown_until_monotonic is not None
            ]
            return min(remaining) if remaining else None

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
    if isinstance(
        exc,
        (
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.ReadError,
            httpx.WriteError,
            httpx.RemoteProtocolError,
        ),
    ):
        return GroqTransportError(
            "provider_timeout",
            attempts=attempt,
            retryable=False,
        )
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
        return GroqTransportError(
            "provider_timeout",
            attempts=attempt,
            retryable=True,
        )
    if isinstance(exc, httpx.TimeoutException):
        return GroqTransportError(
            "provider_timeout",
            attempts=attempt,
            retryable=False,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        retry_after = _retry_after_seconds(exc.response.headers.get("Retry-After"))
        provider_error_code = _provider_error_code(exc.response)
        if status in {401, 403}:
            reason: GroqFailureReason = "provider_authentication_failed"
            retryable = False
        elif status == 429 or (status == 413 and provider_error_code == "rate_limit_exceeded"):
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
            provider_error_code=provider_error_code,
        )
    if isinstance(exc, httpx.RequestError):
        return GroqTransportError(
            "provider_transport_error",
            attempts=attempt,
            retryable=False,
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
    max_retry_after_s: float,
    jitter: float,
) -> float:
    if error.retry_after_s is not None:
        return min(max_retry_after_s, max(0.0, error.retry_after_s))
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


def groq_error_status_code(exc: Exception) -> int | None:
    if isinstance(exc, GroqTransportError):
        return exc.status_code
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _normalize_api_keys(
    *,
    api_key: str | None,
    api_keys: Sequence[str] | None,
) -> tuple[str, ...]:
    values = []
    if api_key is not None:
        values.append(api_key)
    if api_keys is not None:
        values.extend(api_keys)
    normalized = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
    if not normalized:
        raise ValueError("at least one non-empty Groq API key is required")
    if len(normalized) > 8:
        raise ValueError("at most eight Groq API keys may be configured")
    return normalized
