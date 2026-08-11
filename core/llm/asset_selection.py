from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.llm.groq_policy import (
    GroqReasoningEffort,
    GroqRequestPolicy,
    groq_fallback_reason,
    normalize_groq_base_url,
)
from core.llm.transport import GroqTransport, GroqTransportError


class _Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role_id: str = Field(min_length=1, max_length=96)
    asset_id: str = Field(min_length=1, max_length=120)
    generation_strategy: Literal["imported_glb_exact", "internal_project_generated"]
    semantic_strategy: Literal[
        "reuse_component",
        "adapt_component",
        "compose_assets",
    ]
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
        transport: GroqTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key.strip()
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
        if post is not None and transport is not None:
            raise ValueError("post and transport are mutually exclusive")
        self._transport = transport
        self._post = post or (None if transport is not None else httpx.post)

    def decide(self, *, slots: list[dict]) -> tuple[dict[str, str], dict]:
        started = time.monotonic()
        attempts = 1
        try:
            if self._transport is not None:
                result = self._transport.request_chat_completion(
                    capability="asset_selection",
                    payload=self._payload(slots),
                    timeout_s=self.timeout_s,
                )
                body = result.body
                attempts = result.attempts
            else:
                assert self._post is not None
                response = self._post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=self._payload(slots),
                    timeout=self.timeout_s,
                )
                response.raise_for_status()
                body = response.json()
            decision = _Decision.model_validate(_response_content(body))
            selections = {item.role_id: item.asset_id for item in decision.selections}
            allowed = {
                slot["role_id"]: {
                    (candidate["asset_id"], strategy, semantic_strategy)
                    for candidate in slot["candidates"]
                    for strategy in candidate["allowed_generation_strategies"]
                    for semantic_strategy in candidate["allowed_semantic_strategies"]
                    if _semantic_matches_generation(strategy, semantic_strategy)
                }
                for slot in slots
            }
            if (
                len(selections) != len(slots)
                or set(selections) != set(allowed)
                or any(
                    (item.asset_id, item.generation_strategy, item.semantic_strategy)
                    not in allowed[item.role_id]
                    for item in decision.selections
                )
            ):
                raise ValueError(
                    "model must select exactly one allowed asset and strategy for every role"
                )
            if self._transport is not None:
                self._transport.mark_operational("asset_selection")
            return selections, {
                "provider": "groq",
                "model_name": self.model,
                "latency_ms": _elapsed_ms(started),
                "attempts": attempts,
                "selection_reasons": {item.asset_id: item.reason for item in decision.selections},
                "selection_reasons_by_role": {
                    item.role_id: item.reason for item in decision.selections
                },
                "generation_strategies": {
                    item.role_id: item.generation_strategy for item in decision.selections
                },
                "semantic_strategies": {
                    item.role_id: item.semantic_strategy for item in decision.selections
                },
            }
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
            GroqTransportError,
        ) as exc:
            if self._transport is not None and not isinstance(exc, GroqTransportError):
                self._transport.mark_failed("asset_selection", "model_output_rejected")
            return {}, {
                "provider": "groq",
                "model_name": self.model,
                "latency_ms": _elapsed_ms(started),
                "attempts": getattr(exc, "attempts", attempts),
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
                            "generation_strategy": {
                                "type": "string",
                                "enum": ["imported_glb_exact", "internal_project_generated"],
                            },
                            "semantic_strategy": {
                                "type": "string",
                                "enum": [
                                    "reuse_component",
                                    "adapt_component",
                                    "compose_assets",
                                ],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "role_id",
                            "asset_id",
                            "generation_strategy",
                            "semantic_strategy",
                            "reason",
                        ],
                    },
                }
            },
            "required": ["selections"],
        }
        return self._policy.apply(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Choose exactly one candidate asset_id and one of that candidate's "
                            "allowed_generation_strategies and allowed_semantic_strategies for "
                            "each supplied role. Compare the "
                            "provided scores, dimensions, compatibility, permissions, and "
                            "qualification limitations. You may only use supplied values. Do not "
                            "create assets, transforms, connector names, parameters, strategies, "
                            "or Blender code. Return strict JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"slots": slots}, separators=(",", ":")),
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "BoundedAssetSelection",
                        "schema": schema,
                        "strict": True,
                    },
                },
            }
        )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _semantic_matches_generation(generation_strategy: str, semantic_strategy: str) -> bool:
    return semantic_strategy in {
        "imported_glb_exact": {"reuse_component", "adapt_component"},
        "internal_project_generated": {"compose_assets", "adapt_component"},
    }.get(generation_strategy, set())


def _response_content(body: dict[str, Any]) -> dict[str, Any]:
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise TypeError("provider message content must be a JSON string")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("provider decision must be a JSON object")
    return parsed
