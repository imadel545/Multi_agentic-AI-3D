from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role_id: str = Field(min_length=1, max_length=96)
    asset_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=200)


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    selections: list[_Selection] = Field(min_length=1, max_length=16)


PostCallable = Callable[..., httpx.Response]


class GroqAssetSelectionClient:
    """Bounded asset selector: it may only choose supplied manifest candidates."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_s: float = 15.0,
        *,
        post: PostCallable | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._post = post or httpx.post

    def decide(self, *, slots: list[dict]) -> tuple[dict[str, str], dict]:
        started = time.monotonic()
        try:
            response = self._post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._payload(slots),
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            decision = _Decision.model_validate(json.loads(content))
            selections = {item.role_id: item.asset_id for item in decision.selections}
            if len(selections) != len(slots) or set(selections) != {
                slot["role_id"] for slot in slots
            }:
                raise ValueError("model must select exactly one asset for every role")
            return selections, {
                "provider": "groq",
                "model_name": self.model,
                "latency_ms": _elapsed_ms(started),
            }
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            return {}, {
                "provider": "groq",
                "model_name": self.model,
                "latency_ms": _elapsed_ms(started),
                "fallback_reason": _fallback_reason(exc),
            }

    def _payload(self, slots: list[dict]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "selections": {
                    "type": "array",
                    "minItems": len(slots),
                    "maxItems": len(slots),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "role_id": {"type": "string"},
                            "asset_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["role_id", "asset_id", "reason"],
                    },
                }
            },
            "required": ["selections"],
        }
        return {
            "model": self.model,
            "temperature": 0,
            "reasoning_effort": "low",
            "max_completion_tokens": 1024,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose exactly one candidate asset_id for each supplied role. "
                        "You may only use supplied IDs. Do not create assets, transforms, "
                        "connector names, parameters, or Blender code. Return strict JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps({"slots": slots}, separators=(",", ":"))},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "BoundedAssetSelection", "schema": schema, "strict": True},
            },
        }


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "provider_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"provider_http_{exc.response.status_code}"
    if isinstance(exc, httpx.RequestError):
        return "provider_transport_error"
    return "model_output_rejected"
