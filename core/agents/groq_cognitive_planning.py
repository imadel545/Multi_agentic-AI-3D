"""Bounded Groq transport and shape validation for cognitive planning."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx

from core.agents.cognitive_planning_schemas import _llm_asset_decisions_schema
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqRequestPolicy
from core.llm.transport import GroqTransportError, groq_error_status_code


class GroqCognitivePlanningClient:
    """Two bounded GPT-OSS decisions: decomposition, then reuse/adapt/generate."""

    provider_name = "groq"

    def __init__(self, client: GroqStructuredClient) -> None:
        self.client = client
        self.model_name = client.model
        self.decomposition_policy = GroqRequestPolicy(
            capability="generic_design_decomposition",
            reasoning_effort="medium",
            max_completion_tokens=8192,
        )
        self.asset_policy = GroqRequestPolicy(
            capability="generic_asset_strategy",
            reasoning_effort="medium",
            max_completion_tokens=8192,
        )

    def decompose(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = self._request(
            {
                "contract": payload["contract"],
                "required_intent_id": payload["required_intent_id"],
                "source_request": payload["source_request"],
                "coordinate_frame": payload["coordinate_frame"],
                "rules": payload["rules"],
                "design_intent_schema": payload["design_intent_schema"],
            },
            policy=self.decomposition_policy,
            system=(
                "Interpret a general 3D design request into one domain-neutral DesignIntent. "
                "Return exactly one JSON object with one top-level key design_intent. Follow the "
                "supplied schema. Do not emit Blender code, asset IDs or capability IDs. Do not "
                "add scenario-specific shortcuts or prose outside JSON. Mark clarification as "
                "required only when a missing fact prevents a bounded technical-generic design; "
                "record safe derivations and non-blocking engineering unknowns as assumptions. "
                "The downstream qualified retriever owns candidate ranking. A request for the "
                "best or most suitable available catalog design does not require user "
                "clarification; record deterministic downstream ranking as an assumption."
            ),
        )
        graph_schema = payload["component_graph_schema"]
        raw_intent = intent.get("design_intent") or {}
        decomposition_context = {
            key: raw_intent.get(key)
            for key in (
                "domain",
                "title",
                "functions",
                "constraints",
                "requested_fidelity",
            )
        }
        components = self._request(
            {
                "contract": payload["contract"],
                "design_intent": decomposition_context,
                "available_catalog_roles": payload["available_catalog_roles"],
                "project_specific_roles": payload.get("project_specific_roles", []),
                "response_key": "components",
                "response_schema": graph_schema["properties"]["components"],
            },
            policy=self.decomposition_policy,
            system=(
                "Decompose the supplied DesignIntent into the smallest sufficient set of 1 to "
                "24 functional 3D components and subassemblies. Return exactly one JSON object "
                "with one top-level key components. Follow the supplied response_schema. Include "
                "dimensions, functions, material intent, parent relationships and honest detail "
                "needs. For genuinely project-specific geometry use its matching "
                "project_specific_roles "
                "entry; never label standard equipment as a custom support or terrain. "
                "Keep reusable equipment and new connecting geometry as separate components. "
                "Do not emit Blender code, asset IDs, capability IDs or prose."
                " When the source request explicitly asks to reuse a complete catalog design and "
                "one available_catalog_roles value names that same functional whole, use that "
                "exact role. These roles describe searchable interfaces, not proof that a matching "
                "asset exists."
            ),
        )
        relationships = self._request(
            {
                "contract": payload["contract"],
                "domain": raw_intent.get("domain"),
                "design_intent": decomposition_context,
                "components": [
                    {
                        "component_id": item.get("component_id"),
                        "semantic_role": item.get("semantic_role"),
                        "parent_component_id": item.get("parent_component_id"),
                        "functions": item.get("functions"),
                    }
                    for item in components.get("components", [])
                    if isinstance(item, dict)
                ],
                "response_key": "relationships",
                "response_schema": graph_schema["properties"]["relationships"],
            },
            policy=self.decomposition_policy,
            system=(
                "Describe only the required spatial and functional relationships among the "
                "supplied component IDs. Return exactly one JSON object with one top-level key "
                "relationships. Follow the supplied response_schema. Never invent a component, "
                "asset, capability, Blender code or prose outside JSON. "
                "For an explicitly requested rigid alignment use kind aligned_with, source and "
                "target component IDs, and parameters:{offset_world_m:{x,y,z}} in metres Z-up. "
                "This copies orientation and offsets origins in world coordinates; it does not "
                "mean surface contact, clearance or fastening. Do not invent missing distances."
            ),
        )
        return {
            "design_intent": intent.get("design_intent"),
            "component_graph": {
                "components": components.get("components"),
                "relationships": relationships.get("relationships"),
            },
        }

    def decide_assets(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate_ids = [
            item["candidate_id"]
            for item in payload.get("candidates", [])
            if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
        ]
        parameter_ids = sorted(
            {
                parameter_id
                for item in payload.get("candidates", [])
                if isinstance(item, dict)
                for parameter_id in item.get("allowed_parameter_ids", [])
                if isinstance(parameter_id, str)
            }
        )
        capability_ids = [
            item["capability_id"]
            for item in payload.get("capabilities", [])
            if isinstance(item, dict) and isinstance(item.get("capability_id"), str)
        ]
        response = self._request(
            {
                **payload,
                "response_key": "decisions",
                "response_schema": _llm_asset_decisions_schema(
                    candidate_ids=candidate_ids,
                    parameter_ids=parameter_ids,
                    capability_ids=capability_ids,
                    strategies=[str(item) for item in payload["required_strategies"]],
                ),
            },
            policy=self.asset_policy,
            system=(
                "Choose a bounded catalog strategy for every supplied component. Candidate data "
                "and capability IDs are authoritative. Select only supplied qualified candidate "
                "IDs, allowed strategies, allowed parameters and supplied capability IDs. Prefer "
                "reuse or rigid catalog composition when quality and QA risk justify it. If no "
                "supplied candidate can satisfy standard equipment, choose unsupported or clarify. "
                "Only when required_strategies explicitly allows procedural_generate, construct "
                "genuinely missing project-specific geometry, with an explicit rationale. "
                "Never recreate manufacturer equipment or override catalog geometry. "
                "Return exactly one JSON "
                "object with top-level key decisions and no prose outside JSON. Return exactly "
                "one decision. Put parameter choices in selected_parameters as "
                "{parameter_id,value} entries; never invent an ID. "
                "For reuse provide placement with translation_m and rotation_deg as x/y/z objects "
                "in meters Z-up and degrees, and scale {x:1,y:1,z:1}. "
                "Never stretch a reused asset. "
                "Catalog compose is limited to singleton rigid components with one required "
                "aligned_with relationship per composed source, targeting a reused or composed "
                "catalog component. Parameters must contain only offset_world_m:{x,y,z}; "
                "the compiler derives world position and copies target orientation. Omit placement "
                "for compose. Ports, parent hierarchy, contact and fastening are unsupported. "
                "A reused singleton can anchor composed components. Other required relationships "
                "need clarification until their execution is supported."
            ),
        )
        for decision in response.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            selected_parameters = decision.pop("selected_parameters", [])
            parameter_values: dict[str, float] = {}
            for item in selected_parameters:
                if not isinstance(item, dict):
                    raise ValueError("selected parameter entry must be an object")
                parameter_id = item.get("parameter_id")
                if not isinstance(parameter_id, str) or parameter_id in parameter_values:
                    raise ValueError("selected parameter IDs must be unique strings")
                value = item.get("value")
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError("selected parameter values must be numeric")
                parameter_values[parameter_id] = float(value)
            decision["selected_parameter_values"] = parameter_values
        return response

    def _request(
        self,
        payload: dict[str, Any],
        *,
        policy: GroqRequestPolicy,
        system: str,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ]
        explicit_schema = payload.get("response_schema")
        explicit_key = payload.get("response_key")
        schema_item = (
            (str(explicit_key), explicit_schema)
            if isinstance(explicit_key, str) and isinstance(explicit_schema, dict)
            else next(
                (
                    (key.removesuffix("_schema"), value)
                    for key, value in payload.items()
                    if key in {"design_intent_schema", "component_graph_schema"}
                    and isinstance(value, dict)
                ),
                None,
            )
        )
        response_format: dict[str, Any] = {"type": "json_object"}
        if schema_item is not None:
            output_key, output_schema = schema_item
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_key,
                    "schema": _strict_envelope_schema(output_key, output_schema),
                    "strict": True,
                },
            }
        request = {
            "model": self.model_name,
            "temperature": 0,
            "messages": messages,
            "response_format": response_format,
        }
        try:
            response = self.client.request_json(request, policy=policy)
        except (httpx.HTTPStatusError, GroqTransportError) as exc:
            if schema_item is None or groq_error_status_code(exc) != 400:
                raise
            last_error = exc
            for attempt in range(1, 3):
                try:
                    response = self.client.request_json(
                        {
                            **request,
                            "messages": [
                                *messages,
                                {
                                    "role": "system",
                                    "content": (
                                        "The constrained decoder rejected the prior attempt. "
                                        f"Repair attempt {attempt}/2: return the one requested "
                                        "JSON object only, keep it compact, close every array and "
                                        "object, and emit no analysis. Local Pydantic validation "
                                        "remains fail-closed."
                                    ),
                                },
                            ],
                            "response_format": {"type": "json_object"},
                        },
                        policy=policy,
                    )
                    break
                except (httpx.HTTPStatusError, GroqTransportError) as retry_error:
                    if groq_error_status_code(retry_error) != 400:
                        raise
                    last_error = retry_error
            else:
                raise last_error
        if not isinstance(response, dict):
            raise ValueError("cognitive planning response must be a JSON object")
        if schema_item is not None:
            output_key, output_schema = schema_item
            envelope_schema = {
                "type": "object",
                "properties": {output_key: output_schema},
                "required": [output_key],
            }
            for repair_attempt in range(1, 3):
                shape_errors = _schema_shape_errors(response, envelope_schema)
                if not shape_errors:
                    break
                response = self.client.request_json(
                    {
                        "model": self.model_name,
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Repair one bounded JSON response. Preserve valid semantic "
                                    "decisions, add or correct every required field reported by "
                                    "the local validator, follow the supplied schema, and return "
                                    "JSON only. Do not add prose or code."
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "repair_attempt": repair_attempt,
                                        "validation_errors": shape_errors[:32],
                                        "required_schema": envelope_schema,
                                        "invalid_response": response,
                                    },
                                    ensure_ascii=False,
                                    sort_keys=True,
                                ),
                            },
                        ],
                        "response_format": {"type": "json_object"},
                    },
                    policy=policy,
                )
                if not isinstance(response, dict):
                    raise ValueError("cognitive repair returned a non-object response")
            remaining_errors = _schema_shape_errors(response, envelope_schema)
            if remaining_errors:
                raise ValueError(
                    "cognitive planning response failed local schema validation: "
                    + "; ".join(remaining_errors[:8])
                )
        return response


def _strict_envelope_schema(output_key: str, output_schema: dict[str, Any]) -> dict[str, Any]:
    """Build Groq's fail-closed strict envelope from the authoritative Pydantic schema."""

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {output_key: deepcopy(output_schema)},
        "required": [output_key],
    }

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                properties = value.get("properties", {})
                value["additionalProperties"] = False
                value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


def _schema_shape_errors(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate the bounded JSON shape locally before Pydantic owns semantics."""

    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        alternative_errors = [
            _schema_shape_errors(value, item, path)
            for item in alternatives
            if isinstance(item, dict)
        ]
        if any(not errors for errors in alternative_errors):
            return []
        return [f"{path}: value matches no allowed shape"]
    expected_type = schema.get("type")
    if expected_type == "null":
        return [] if value is None else [f"{path}: expected null"]
    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        errors = [
            f"{path}.{key}: required field missing"
            for key in schema.get("required", [])
            if key not in value
        ]
        properties = schema.get("properties", {})
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(_schema_shape_errors(item, child_schema, f"{path}.{key}"))
        return errors
    if expected_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        errors: list[str] = []
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{path}: array shorter than minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: array longer than maxItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_schema_shape_errors(item, item_schema, f"{path}[{index}]"))
        return errors
    type_valid = {
        "string": isinstance(value, str),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(expected_type, True)
    if not type_valid:
        return [f"{path}: expected {expected_type}"]
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        return [f"{path}: value is outside enum"]
    return []


