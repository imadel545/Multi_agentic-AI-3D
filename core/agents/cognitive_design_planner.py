from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Protocol

import httpx

from core.agents.cognitive_supervisor import CognitiveSupervisor
from core.contracts.capabilities import CapabilityDefinition
from core.contracts.cognitive_design import (
    AssetCandidateEvidence,
    AssetDecisionPlan,
    CognitiveDesignPlan,
    ComponentAssetDecision,
    ComponentGraph,
    DesignIntent,
)
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqRequestPolicy
from core.llm.transport import GroqTransportError, groq_error_status_code


class CognitivePlanningClient(Protocol):
    provider_name: str
    model_name: str

    def decompose(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def decide_assets(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class ComponentCandidateRetriever(Protocol):
    def search(self, component: dict[str, Any]) -> list[AssetCandidateEvidence]: ...


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
                "record safe derivations and non-blocking engineering unknowns as assumptions."
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
                "response_key": "components",
                "response_schema": graph_schema["properties"]["components"],
            },
            policy=self.decomposition_policy,
            system=(
                "Decompose the supplied DesignIntent into the smallest sufficient set of 3 to "
                "24 functional 3D components and subassemblies. Return exactly one JSON object "
                "with one top-level key components. Follow the supplied response_schema. Include "
                "dimensions, functions, material intent, parent relationships and honest detail "
                "needs. Do not emit Blender code, asset IDs, capability IDs or prose."
            ),
        )
        relationships = self._request(
            {
                "contract": payload["contract"],
                "domain": raw_intent.get("domain"),
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
                "asset, capability, Blender code or prose outside JSON."
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
        return self._request(
            payload,
            policy=self.asset_policy,
            system=(
                "Choose a bounded creation strategy for every supplied component. Candidate data "
                "and capability IDs are authoritative. Select only supplied qualified candidate "
                "IDs, allowed strategies, allowed parameters and supplied capability IDs. Prefer "
                "reuse or safe adaptation when quality and QA risk justify it; otherwise choose "
                "compose, compose_and_generate or procedural_generate. Return exactly one JSON "
                "object with top-level key decisions and no prose outside JSON. "
                "For reuse provide placement with translation_m and rotation_deg as x/y/z objects "
                "in meters Z-up and degrees, and scale {x:1,y:1,z:1}. "
                "Never stretch a reused asset. "
                "Reuse currently supports one independent component only; required relationships "
                "need clarification until executable assembly is available."
            ),
        )

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


class CognitiveDesignPlanner:
    """Compile LLM decisions into a governed domain-neutral cognitive plan."""

    def __init__(
        self,
        planning_client: CognitivePlanningClient,
        candidate_retriever: ComponentCandidateRetriever,
        supervisor: CognitiveSupervisor,
        capabilities: list[CapabilityDefinition],
    ) -> None:
        capability_ids = [item.capability_id for item in capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("planner capability IDs must be unique")
        self.planning_client = planning_client
        self.candidate_retriever = candidate_retriever
        self.supervisor = supervisor
        self.capabilities = list(capabilities)

    def plan(self, *, workflow_id: str, request: str) -> CognitiveDesignPlan:
        normalized_request = request.strip()
        if len(normalized_request) < 3:
            raise ValueError("generic design request is too short")
        if len(normalized_request) > 12_000:
            raise ValueError("generic design request exceeds 12000 characters")
        prompt_hash = hashlib.sha256(normalized_request.encode("utf-8")).hexdigest()
        intent_id = f"{workflow_id}:intent:v1"
        decomposition = self.planning_client.decompose(
            {
                "contract": "design_intent_component_graph@1.0.0",
                "required_intent_id": intent_id,
                "required_graph_id": f"{workflow_id}:components:v1",
                "source_request": normalized_request,
                "coordinate_frame": "meters_z_up",
                "rules": {
                    "clarification_truth_must_match_missing_information": True,
                    "all_components_require_functions": True,
                    "all_relationship_references_must_resolve": True,
                    "no_assets_or_blender_code": True,
                },
                "design_intent_schema": _llm_design_intent_schema(),
                # The LLM receives the semantic subset it owns. Runtime-only defaults,
                # port frames and free-form relationship parameters are validated and
                # enriched downstream instead of making constrained decoding brittle.
                "component_graph_schema": _llm_component_graph_schema(),
            }
        )
        raw_intent = dict(decomposition.get("design_intent") or {})
        raw_intent.update(
            {
                "schema_version": "1.0.0",
                "intent_id": intent_id,
                "source_request": normalized_request,
                "coordinate_frame": "meters_z_up",
                "llm_provider": self.planning_client.provider_name,
                "llm_model": self.planning_client.model_name,
                "source_prompt_sha256": prompt_hash,
            }
        )
        intent = DesignIntent.model_validate(raw_intent)
        raw_graph = dict(decomposition.get("component_graph") or {})
        raw_graph.update(
            {
                "schema_version": "1.0.0",
                "graph_id": f"{workflow_id}:components:v1",
                "intent_id": intent.intent_id,
            }
        )
        graph = ComponentGraph.model_validate(raw_graph)

        candidates_by_component = {
            component.component_id: self.candidate_retriever.search(
                component.model_dump(mode="json")
            )
            for component in graph.components
        }
        capability_payload = [
            {
                "capability_id": capability.capability_id,
                "description": capability.description,
                "compatible_domains": capability.compatible_domains,
                "capability_tags": capability.capability_tags,
                "cost": capability.cost.model_dump(mode="json"),
                "limits": capability.limits.model_dump(mode="json"),
                "permissions": capability.permissions,
                "possible_errors": capability.possible_errors,
                "generated_proofs": capability.generated_proofs,
            }
            for capability in self.capabilities
            if intent.domain in capability.compatible_domains
            or "generic" in capability.compatible_domains
        ]

        def decide_one(component_index: int) -> tuple[int, dict[str, Any]]:
            component = graph.components[component_index]
            raw_decisions = self.planning_client.decide_assets(
                {
                    "contract": "component_asset_decision@1.0.0",
                    "intent": {
                        "domain": intent.domain,
                        "title": intent.title,
                        "requested_fidelity": intent.requested_fidelity,
                    },
                    "component": component.model_dump(mode="json"),
                    "relationships": [
                        item.model_dump(mode="json")
                        for item in graph.relationships
                        if component.component_id
                        in {item.source_component_id, item.target_component_id}
                    ],
                    "candidates": [
                        item.model_dump(mode="json")
                        for item in candidates_by_component[component.component_id]
                    ],
                    "capabilities": capability_payload,
                    "required_component_id": component.component_id,
                    "required_strategies": [
                        "reuse",
                        "adapt",
                        "compose",
                        "compose_and_generate",
                        "procedural_generate",
                        "clarify",
                        "unsupported",
                    ],
                }
            )
            returned = [
                item for item in raw_decisions.get("decisions", []) if isinstance(item, dict)
            ]
            if len(returned) != 1:
                raise ValueError(
                    "LLM asset decision must return exactly one decision for "
                    f"{component.component_id!r}"
                )
            # The deterministic caller owns identity. The model decides only the
            # bounded strategy, candidate subset, parameters and capabilities.
            returned[0]["component_id"] = component.component_id
            return component_index, returned[0]

        worker_count = min(3, len(graph.components))
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="cognitive-asset-decision",
        ) as pool:
            indexed_decisions = list(pool.map(decide_one, range(len(graph.components))))
        raw_by_component = {
            graph.components[index].component_id: raw for index, raw in sorted(indexed_decisions)
        }
        known_capabilities = {item["capability_id"] for item in capability_payload}
        decisions: list[ComponentAssetDecision] = []
        for component in graph.components:
            raw = raw_by_component.get(component.component_id)
            if raw is None:
                raise ValueError(f"LLM asset plan omitted component {component.component_id!r}")
            pinned = dict(raw)
            pinned["component_id"] = component.component_id
            pinned["candidates"] = [
                item.model_dump(mode="json")
                for item in candidates_by_component[component.component_id]
            ]
            decision = ComponentAssetDecision.model_validate(pinned)
            unknown_capabilities = set(decision.required_capability_ids) - known_capabilities
            if unknown_capabilities:
                raise ValueError(
                    f"LLM asset plan selected unknown capabilities: {sorted(unknown_capabilities)}"
                )
            decisions.append(decision)
        decision_plan = AssetDecisionPlan(
            plan_id=f"{workflow_id}:asset-decisions:v1",
            graph_id=graph.graph_id,
            decisions=decisions,
            llm_provider=self.planning_client.provider_name,
            llm_model=self.planning_client.model_name,
        )
        route = self.supervisor.route(intent, graph)
        return CognitiveDesignPlan(
            design_intent=intent,
            component_graph=graph,
            asset_decision_plan=decision_plan,
            specialist_route=route,
        )


def _llm_component_graph_schema() -> dict[str, Any]:
    identifier = {
        "type": "string",
        "pattern": "^[a-z][a-z0-9._-]*$",
        "maxLength": 120,
    }
    nullable_identifier = {"anyOf": [identifier, {"type": "null"}]}
    dimensions = {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                },
                "required": ["x", "y", "z"],
            },
            {"type": "null"},
        ]
    }
    component = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "component_id": identifier,
            "semantic_role": identifier,
            "parent_component_id": nullable_identifier,
            "description": {"type": "string", "minLength": 4, "maxLength": 800},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 512},
            "functions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 32,
                "items": {"type": "string"},
            },
            "target_dimensions_m": dimensions,
            "material_intent": {
                "type": "array",
                "maxItems": 16,
                "items": {"type": "string"},
            },
            "required": {"type": "boolean"},
            "minimum_detail_parts": {"type": "integer", "minimum": 1, "maximum": 512},
        },
        "required": [
            "component_id",
            "semantic_role",
            "parent_component_id",
            "description",
            "quantity",
            "functions",
            "target_dimensions_m",
            "material_intent",
            "required",
            "minimum_detail_parts",
        ],
    }
    relationship = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "relationship_id": identifier,
            "kind": {
                "type": "string",
                "enum": [
                    "parent_child",
                    "connected",
                    "supported_by",
                    "aligned_with",
                    "distributed_on",
                    "inside",
                    "adjacent",
                    "clearance",
                ],
            },
            "source_component_id": identifier,
            "target_component_id": identifier,
            "required": {"type": "boolean"},
        },
        "required": [
            "relationship_id",
            "kind",
            "source_component_id",
            "target_component_id",
            "required",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "components": {
                "type": "array",
                "minItems": 1,
                "maxItems": 24,
                "items": component,
            },
            "relationships": {
                "type": "array",
                "maxItems": 256,
                "items": relationship,
            },
        },
        "required": ["components", "relationships"],
    }


def _llm_design_intent_schema() -> dict[str, Any]:
    identifier = {
        "type": "string",
        "pattern": "^[a-z][a-z0-9._-]*$",
        "maxLength": 96,
    }
    design_function = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "function_id": identifier,
            "description": {"type": "string", "minLength": 4, "maxLength": 500},
            "priority": {
                "type": "string",
                "enum": ["required", "preferred", "optional"],
            },
        },
        "required": ["function_id", "description", "priority"],
    }
    constraint = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "constraint_id": identifier,
            "subject_role": {"type": "string", "minLength": 1, "maxLength": 96},
            "property_path": {"type": "string", "minLength": 1, "maxLength": 180},
            "operator": {
                "type": "string",
                "enum": [
                    "equals",
                    "minimum",
                    "maximum",
                    "between",
                    "contains",
                    "connected_to",
                    "clearance",
                ],
            },
            "value": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "array", "items": {"type": "number"}},
                ]
            },
            "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "tolerance": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "source": {
                "type": "string",
                "enum": ["user", "document", "llm_inference", "domain_pack", "derived"],
            },
            "requires_confirmation": {"type": "boolean"},
        },
        "required": [
            "constraint_id",
            "subject_role",
            "property_path",
            "operator",
            "value",
            "unit",
            "tolerance",
            "source",
            "requires_confirmation",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "domain": identifier,
            "title": {"type": "string", "minLength": 3, "maxLength": 180},
            "functions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "items": design_function,
            },
            "constraints": {
                "type": "array",
                "maxItems": 256,
                "items": constraint,
            },
            "requested_fidelity": {
                "type": "string",
                "enum": ["schematic", "technical_generic", "reference_qualified"],
            },
            "assumptions": {
                "type": "array",
                "maxItems": 32,
                "items": {"type": "string"},
            },
            "missing_information": {
                "type": "array",
                "maxItems": 32,
                "items": {"type": "string"},
            },
            "clarification_required": {"type": "boolean"},
        },
        "required": [
            "domain",
            "title",
            "functions",
            "constraints",
            "requested_fidelity",
            "assumptions",
            "missing_information",
            "clarification_required",
        ],
    }
