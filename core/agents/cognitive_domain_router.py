from __future__ import annotations

import json
from typing import Any, Protocol

from core.contracts.cognitive_design import DesignRouteDecision
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqRequestPolicy


class DesignDomainRouteClient(Protocol):
    def route(self, request: str) -> DesignRouteDecision: ...


class GroqDesignDomainRouter:
    """Route one prompt to the established telecom graph or the generic graph.

    The model decides the semantic domain. Local validation owns the closed route
    vocabulary, and a failed generic classification never falls through to a fake
    telecom extraction.
    """

    def __init__(self, client: GroqStructuredClient) -> None:
        self.client = client
        self.policy = GroqRequestPolicy(
            capability="design_domain_routing",
            reasoning_effort="low",
            max_completion_tokens=768,
        )

    def route(self, request: str) -> DesignRouteDecision:
        normalized = request.strip()
        if len(normalized) < 3:
            raise ValueError("design request is too short for domain routing")
        response = self.client.request_json(
            {
                "model": self.client.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Classify one 3D design request. Choose telecom_v1 only when the "
                            "requested primary product is a telecom radio site, tower, mast or "
                            "cellular/RF installation. Choose generic_cognitive_v1 for all other "
                            "physical designs, including architecture, stairs, furniture, terrain, "
                            "landscape and mixed environments. Choose blocked only when the "
                            "request is not a physical 3D design or is too ambiguous to model "
                            "safely. Infer "
                            "a short lowercase domain. Return JSON only; never emit code or tools."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "request": normalized,
                                "allowed_routes": [
                                    "telecom_v1",
                                    "generic_cognitive_v1",
                                    "blocked",
                                ],
                                "output": {
                                    "route": "allowed route",
                                    "inferred_domain": "lowercase domain identifier",
                                    "rationale": "concise reason",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            policy=self.policy,
        )
        if not isinstance(response, dict):
            raise ValueError("design domain router returned a non-object response")
        pinned: dict[str, Any] = dict(response)
        pinned.update(
            {
                "provider": "groq",
                "model": self.client.model,
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        return DesignRouteDecision.model_validate(pinned)


class ConservativeDesignDomainRouter:
    """Explicit degraded policy used only when the remote router is unavailable."""

    _TELECOM_MARKERS = frozenset(
        {
            "telecom",
            "4g",
            "5g",
            "rru",
            "antenna",
            "radio",
            "pylone",
            "pylône",
            "monopole",
            "cellulaire",
            "cellular",
            "microwave",
        }
    )

    def route(self, request: str) -> DesignRouteDecision:
        words = {word.strip(".,;:!?()[]{}\"'").lower() for word in request.split()}
        if words & self._TELECOM_MARKERS:
            return DesignRouteDecision(
                route="telecom_v1",
                inferred_domain="telecom",
                rationale=(
                    "Explicit telecom vocabulary permits the established deterministic route."
                ),
                provider="deterministic_conservative",
                model="none",
                fallback_used=True,
                fallback_reason="LLM domain router unavailable; only explicit telecom is accepted.",
            )
        return DesignRouteDecision(
            route="blocked",
            inferred_domain="generic",
            rationale="A non-telecom request requires the configured bounded LLM domain router.",
            provider="deterministic_conservative",
            model="none",
            fallback_used=True,
            fallback_reason="LLM domain router unavailable; generic generation is fail-closed.",
        )
