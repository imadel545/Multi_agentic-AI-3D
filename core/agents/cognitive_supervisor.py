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
        response_schema = _specialist_route_response_schema(payload)
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
                            "JSON object with exactly the keys steps and rationale only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "specialist_route",
                        "schema": response_schema,
                        "strict": True,
                    },
                },
            },
            policy=self.policy,
        )
        if not isinstance(response, dict):
            raise ValueError("specialist supervisor returned a non-object response")
        return response


def _specialist_route_response_schema(payload: dict[str, Any]) -> dict[str, Any]:
    specialist_ids = [
        item["specialist_id"]
        for item in payload.get("specialist_registry", [])
        if isinstance(item, dict) and isinstance(item.get("specialist_id"), str)
    ]
    component_ids = [
        item["component_id"]
        for item in payload.get("components", [])
        if isinstance(item, dict) and isinstance(item.get("component_id"), str)
    ]
    step = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "specialist_id": {"type": "string", "enum": specialist_ids},
            "objective": {"type": "string", "minLength": 8, "maxLength": 600},
            "input_component_ids": {
                "type": "array",
                "maxItems": min(128, len(component_ids)),
                "items": {"type": "string", "enum": component_ids},
            },
            "depends_on": {
                "type": "array",
                "maxItems": min(16, len(specialist_ids)),
                "items": {"type": "string", "enum": specialist_ids},
            },
            "execution_wave": {"type": "integer", "minimum": 0, "maximum": 31},
        },
        "required": [
            "specialist_id",
            "objective",
            "input_component_ids",
            "depends_on",
            "execution_wave",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": min(32, len(specialist_ids)),
                "items": step,
            },
            "rationale": {"type": "string", "minLength": 8, "maxLength": 1000},
        },
        "required": ["steps", "rationale"],
    }


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
        raw["steps"] = _complete_required_route(
            raw.get("steps"),
            descriptors=compatible,
            component_ids={item.component_id for item in graph.components},
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


def _complete_required_route(
    raw_steps: Any,
    *,
    descriptors: list[SpecialistDescriptor],
    component_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_steps, list):
        raise ValueError("specialist route steps must be a list")
    registry = {item.specialist_id: item for item in descriptors}
    raw_by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_steps:
        if not isinstance(raw, dict) or not isinstance(raw.get("specialist_id"), str):
            raise ValueError("specialist route step must declare a specialist ID")
        specialist_id = raw["specialist_id"]
        if specialist_id in raw_by_id:
            raise ValueError("specialist route contains duplicate specialists")
        if specialist_id not in registry:
            raise ValueError(f"specialist route contains unknown specialist {specialist_id!r}")
        raw_by_id[specialist_id] = raw

    selected = set(raw_by_id)
    selected.update(item.specialist_id for item in descriptors if item.required_gate)
    pending = list(selected)
    while pending:
        specialist_id = pending.pop()
        for dependency in registry[specialist_id].depends_on:
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)

    waves: dict[str, int] = {}
    visiting: set[str] = set()

    def wave_for(specialist_id: str) -> int:
        if specialist_id in waves:
            return waves[specialist_id]
        if specialist_id in visiting:
            raise ValueError("specialist registry dependency graph contains a cycle")
        visiting.add(specialist_id)
        dependencies = registry[specialist_id].depends_on
        waves[specialist_id] = (
            max(wave_for(dependency) for dependency in dependencies) + 1 if dependencies else 0
        )
        visiting.remove(specialist_id)
        return waves[specialist_id]

    completed = []
    for specialist_id in sorted(selected, key=lambda item: (wave_for(item), item)):
        descriptor = registry[specialist_id]
        raw = raw_by_id.get(specialist_id, {})
        completed.append(
            {
                "specialist_id": specialist_id,
                "objective": raw.get("objective") or descriptor.description,
                "input_component_ids": raw.get("input_component_ids") or sorted(component_ids),
                "depends_on": list(descriptor.depends_on),
                "execution_wave": wave_for(specialist_id),
            }
        )
    return completed
