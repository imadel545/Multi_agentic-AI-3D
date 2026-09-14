"""Strict bounded provider schemas for cognitive planning decisions."""

from typing import Any


def _llm_asset_decisions_schema(
    *,
    candidate_ids: list[str],
    parameter_ids: list[str],
    capability_ids: list[str],
    strategies: list[str],
) -> dict[str, Any]:
    def bounded_string(values: list[str]) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "string"}
        if values:
            schema["enum"] = values
        return schema

    vector = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "x": {"type": "number"},
            "y": {"type": "number"},
            "z": {"type": "number"},
        },
        "required": ["x", "y", "z"],
    }
    placement = {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "translation_m": vector,
                    "rotation_deg": vector,
                    "scale": vector,
                },
                "required": ["translation_m", "rotation_deg", "scale"],
            },
            {"type": "null"},
        ]
    }
    decision = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "strategy": {"type": "string", "enum": strategies},
            "selected_candidate_ids": {
                "type": "array",
                "maxItems": min(16, len(candidate_ids)),
                "items": bounded_string(candidate_ids),
            },
            "selected_parameters": {
                "type": "array",
                "maxItems": min(64, len(parameter_ids)),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "parameter_id": bounded_string(parameter_ids),
                        "value": {"type": "number"},
                    },
                    "required": ["parameter_id", "value"],
                },
            },
            "placement": placement,
            "required_capability_ids": {
                "type": "array",
                "maxItems": min(64, len(capability_ids)),
                "items": bounded_string(capability_ids),
            },
            "rationale": {"type": "string", "minLength": 8, "maxLength": 1000},
        },
        "required": [
            "strategy",
            "selected_candidate_ids",
            "selected_parameters",
            "placement",
            "required_capability_ids",
            "rationale",
        ],
    }
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": 1,
        "items": decision,
    }


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
