from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

GroqReasoningEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class GroqRequestPolicy:
    """One explicit policy for a bounded, non-streaming GPT-OSS decision."""

    capability: str
    reasoning_effort: GroqReasoningEffort
    max_completion_tokens: int

    def __post_init__(self) -> None:
        if not self.capability.strip():
            raise ValueError("capability must not be empty")
        if self.reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("reasoning_effort must be low, medium, or high")
        if not 128 <= self.max_completion_tokens <= 65_536:
            raise ValueError("max_completion_tokens must be between 128 and 65536")

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("stream") is True:
            raise ValueError("Groq Structured Outputs cannot be streamed")
        if payload.get("tools"):
            raise ValueError("Groq Structured Outputs cannot be combined with tool use")
        return {
            **payload,
            "reasoning_effort": self.reasoning_effort,
            "max_completion_tokens": self.max_completion_tokens,
            "stream": False,
        }


def normalize_groq_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("groq_base_url must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("groq_base_url must use HTTPS outside local development")
    return normalized


def groq_fallback_reason(exc: Exception) -> str:
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return "provider_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return "provider_authentication_failed"
        if status == 429:
            return "provider_rate_limited"
        if status >= 500:
            return "provider_unavailable"
        return f"provider_http_{status}"
    if isinstance(exc, httpx.RequestError):
        return "provider_transport_error"
    return "model_output_rejected"
