from __future__ import annotations

import json
from typing import Any, Protocol

from core.contracts.cognitive_design import (
    ComponentGraph,
    DesignIntent,
    SpecialistDescriptor,
    SpecialistRoutePlan,
)
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqRequestPolicy


class SpecialistRouteClient(Protocol):
    provider_name: str
    model_name: str

    def decide_route(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class GroqSpecialistRouteClient:
    """GPT-OSS route selection constrained to a supplied specialist registry."""

    provider_name = "groq"

    def __init__(self, client: GroqStructuredClient) -> None:
        self.client = client
        self.model_name = client.model
        self.policy = GroqRequestPolicy(
            capability="specialist_route_selection",
            reasoning_effort="medium",
            max_completion_tokens=4096,
        )

    def decide_route(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.request_json(
            {
                "model": self.model_name,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the bounded supervisor of a verified cognitive 3D system. "
                            "Select only specialist_id values supplied in the registry. Select "
                            "the smallest sufficient team. Preserve every declared dependency "
                            "and place dependencies in earlier execution waves. Do not invent "
                            "tools, agents, assets, component IDs or Blender code. Return one "
                            "JSON object only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            policy=self.policy,
        )
        if not isinstance(response, dict):
            raise ValueError("specialist supervisor returned a non-object response")
        return response


class CognitiveSupervisor:
    """Validate a dynamic LLM route against a closed typed specialist registry."""

    def __init__(
        self,
        descriptors: list[SpecialistDescriptor],
        route_client: SpecialistRouteClient,
    ) -> None:
        identifiers = [item.specialist_id for item in descriptors]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("specialist descriptor IDs must be unique")
        known = set(identifiers)
        for descriptor in descriptors:
            unknown = set(descriptor.depends_on) - known
            if unknown:
                raise ValueError(
                    f"specialist {descriptor.specialist_id!r} has unknown dependencies: "
                    f"{sorted(unknown)}"
                )
        self.descriptors = list(descriptors)
        self.route_client = route_client

    def route(self, intent: DesignIntent, graph: ComponentGraph) -> SpecialistRoutePlan:
        compatible = [
            descriptor
            for descriptor in self.descriptors
            if intent.domain in descriptor.compatible_domains
            or "generic" in descriptor.compatible_domains
        ]
        if not compatible:
            raise ValueError(f"no registered specialist supports domain {intent.domain!r}")
        raw = self.route_client.decide_route(
            {
                "contract": "specialist_route_plan@1.0.0",
                "required_route_id": f"{intent.intent_id}:specialists:v1",
                "domain": intent.domain,
                "design_functions": [item.model_dump(mode="json") for item in intent.functions],
                "components": [
                    {
                        "component_id": item.component_id,
                        "semantic_role": item.semantic_role,
                        "functions": item.functions,
                        "required": item.required,
                    }
                    for item in graph.components
                ],
                "specialist_registry": [item.model_dump(mode="json") for item in compatible],
                "output_shape": {
                    "route_id": "string",
                    "domain": intent.domain,
                    "steps": [
                        {
                            "specialist_id": "registered id",
                            "objective": "bounded objective",
                            "input_component_ids": ["known component id"],
                            "depends_on": ["registered dependency selected in this route"],
                            "execution_wave": 0,
                        }
                    ],
                    "rationale": "why this is the smallest sufficient route",
                },
            }
        )
        raw.update(
            {
                "schema_version": "1.0.0",
                "route_id": f"{intent.intent_id}:specialists:v1",
                "domain": intent.domain,
                "llm_provider": self.route_client.provider_name,
                "llm_model": self.route_client.model_name,
            }
        )
        route = SpecialistRoutePlan.model_validate(raw)
        route.validate_against_registry(
            compatible,
            {item.component_id for item in graph.components},
        )
        return route
