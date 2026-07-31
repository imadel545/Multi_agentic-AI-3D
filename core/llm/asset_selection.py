from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.llm.groq_policy import (
    GroqReasoningEffort,
    GroqRequestPolicy,
    groq_fallback_reason,
    normalize_groq_base_url,
)


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
        max_completion_tokens: int = 1024,
        reasoning_effort: GroqReasoningEffort = "medium",
        *,
        post: PostCallable | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self.api_key = api_key.strip()
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.model = model.strip()
        if not self.model:
            raise ValueError("model must not be empty")
        self.base_url = normalize_groq_base_url(base_url)
        self.timeout_s = timeout_s
        self._policy = GroqRequestPolicy(
            capability="asset_selection",
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens,
        )
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
            decision = _Decision.model_validate(_response_content(response.json()))
            selections = {item.role_id: item.asset_id for item in decision.selections}
            allowed = {
                slot["role_id"]: set(slot["candidate_asset_ids"])
                for slot in slots
            }
            if (
                len(selections) != len(slots)
                or set(selections) != set(allowed)
                or any(asset_id not in allowed[role] for role, asset_id in selections.items())
            ):
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
                "fallback_reason": groq_fallback_reason(exc),
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
        return self._policy.apply({
            "model": self.model,
            "temperature": 0,
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
        })


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _response_content(body: dict[str, Any]) -> dict[str, Any]:
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str):
        raise TypeError("provider message content must be a JSON string")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("provider decision must be a JSON object")
    return parsed
