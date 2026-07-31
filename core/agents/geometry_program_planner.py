from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from core.contracts.geometry_program import (
    GeometryProgram,
    GeometryProgramVector3,
    geometry_program_dimensions,
)
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqReasoningEffort, GroqRequestPolicy


class GeometryProgramPlanner:
    """Ask GPT-OSS for typed geometry data, never executable Blender Python."""

    def __init__(
        self,
        groq_client: GroqStructuredClient,
        *,
        max_completion_tokens: int = 8192,
        reasoning_effort: GroqReasoningEffort = "medium",
    ) -> None:
        self.groq = groq_client
        self.policy = GroqRequestPolicy(
            capability="geometry_program_generation",
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens,
        )

    def plan(
        self,
        *,
        prompt: str,
        semantic_role: str,
        design_context: dict[str, Any],
        request_id: str | None = None,
        quantity: int = 1,
        source_description: str | None = None,
        source_description_origin: Literal[
            "user_requirement",
            "revision_preserved",
            "legacy_unavailable",
        ] = "user_requirement",
        placement_context: str | None = None,
        maximum_dimensions_m: GeometryProgramVector3 | None = None,
    ) -> GeometryProgram:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("geometry-program prompt must not be empty")
        normalized_role = _program_identifier(semantic_role)
        normalized_request_id = _program_identifier(request_id or normalized_role)
        program_id = f"{normalized_request_id}.llm_v1"
        if quantity < 1 or quantity > 32:
            raise ValueError("geometry-program quantity must be in [1, 32]")
        prompt_hash = hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest()
        normalized_source_description = (source_description or normalized_prompt).strip()
        if len(normalized_source_description) < 8:
            raise ValueError("geometry-program source description must contain 8 characters")
        if len(normalized_source_description) > 2400:
            raise ValueError("geometry-program source description exceeds 2400 characters")
        normalized_placement_context = (
            placement_context.strip() if placement_context is not None else None
        )
        if normalized_placement_context == "":
            normalized_placement_context = None
        if normalized_placement_context is not None and len(normalized_placement_context) > 600:
            raise ValueError("geometry-program placement context exceeds 600 characters")
        maximum_dimensions_payload = (
            maximum_dimensions_m.model_dump(mode="json")
            if maximum_dimensions_m is not None
            else None
        )
        context_json = json.dumps(
            design_context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(context_json) > 32_000:
            raise ValueError("geometry-program design context exceeds 32000 characters")

        schema = _strict_json_schema(GeometryProgram.model_json_schema())
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the geometry-program specialist of a verified 3D design system. "
                    "Write a declarative meter-based geometry program, not Python and not prose. "
                    "Use only the schema primitives, curves, instances, materials and transforms. "
                    "Create coherent multi-part technical geometry with stable semantic roles. "
                    "Do not reference files, URLs, Blender operators, scripts or "
                    "undeclared assets. "
                    "Stay within the declared dimensions and use assumptions/limitations honestly. "
                    "Every top-level component requires at least one node whose semantic_role "
                    "equals "
                    "the requested semantic role."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Required program_id: {program_id}\n"
                    f"Required semantic_role: {normalized_role}\n"
                    f"Required requested_quantity: {quantity}\n"
                    "Required maximum_dimensions_m: "
                    f"{json.dumps(maximum_dimensions_payload, separators=(',', ':'))}\n"
                    "Required units: meters\n"
                    "Required authorship: llm_generated\n"
                    "Required generator_provider: groq\n"
                    f"Required generator_model: {self.groq.model}\n"
                    "Required structured_output_mode: strict_json_schema\n"
                    f"Required source_prompt_sha256: {prompt_hash}\n\n"
                    "Required source_description: "
                    f"{json.dumps(normalized_source_description, ensure_ascii=False)}\n"
                    "Required source_description_origin: "
                    f"{source_description_origin}\n"
                    "Required placement_context: "
                    f"{json.dumps(normalized_placement_context, ensure_ascii=False)}\n\n"
                    f"Design context JSON:\n{context_json}\n\n"
                    f"User design request:\n{normalized_prompt}"
                ),
            },
        ]
        strict_payload = {
            "model": self.groq.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "GeometryProgram",
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        output_mode = "strict_json_schema"
        try:
            raw = self.groq.request_json(strict_payload, policy=self.policy)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            output_mode = "json_object_validated"
            raw = self.groq.request_json(
                {
                    "model": self.groq.model,
                    "temperature": 0,
                    "messages": [
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "The strict decoder rejected the first attempt. Return one JSON "
                                "object matching the requested GeometryProgram shape. Optional "
                                "fields may be omitted; local validation remains fail-closed.\n\n"
                                + _json_object_contract()
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                policy=self.policy,
            )
        pinned = {
            "program_id": program_id,
            "semantic_role": normalized_role,
            "requested_quantity": quantity,
            "units": "meters",
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": self.groq.model,
            "structured_output_mode": output_mode,
            "source_prompt_sha256": prompt_hash,
            "source_description": normalized_source_description,
            "source_description_origin": source_description_origin,
            "placement_context": normalized_placement_context,
            "maximum_dimensions_m": maximum_dimensions_payload,
            "deterministic_adjustments": [],
        }
        raw.update(pinned)
        candidate = raw
        for repair_attempt in range(3):
            _normalize_disclosures(candidate)
            try:
                return GeometryProgram.model_validate(candidate)
            except ValidationError as exc:
                if repair_attempt == 2:
                    fitted = _fit_to_maximum_dimensions(candidate)
                    if fitted is not None:
                        return GeometryProgram.model_validate(fitted)
                    raise
                candidate = self._repair_invalid_program(
                    raw=candidate,
                    validation_error=exc,
                    program_id=program_id,
                    semantic_role=normalized_role,
                    quantity=quantity,
                    prompt_hash=prompt_hash,
                    maximum_dimensions_m=maximum_dimensions_payload,
                )
                candidate.update(
                    {
                        **pinned,
                        "structured_output_mode": "json_object_repaired",
                    }
                )
        raise RuntimeError("unreachable geometry-program validation state")

    def _repair_invalid_program(
        self,
        *,
        raw: dict[str, Any],
        validation_error: ValidationError,
        program_id: str,
        semantic_role: str,
        quantity: int,
        prompt_hash: str,
        maximum_dimensions_m: dict[str, float] | None,
    ) -> dict[str, Any]:
        error_payload = validation_error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
        return self.groq.request_json(
            {
                "model": self.groq.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Repair one invalid GeometryProgram JSON object. Return JSON only. "
                            "Do not redesign it. Preserve valid geometry intent and correct every "
                            "reported schema error. Every vector must be an object with the "
                            "numeric keys x, y and z; every color must be an object with the "
                            "numeric keys r, g, b and a. " + _json_object_contract()
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Pinned program_id: {program_id}\n"
                            f"Pinned semantic_role: {semantic_role}\n"
                            f"Pinned requested_quantity: {quantity}\n"
                            "Pinned schema_version: 1.0.0\n"
                            "Pinned authorship: llm_generated\n"
                            "Pinned generator_provider: groq\n"
                            f"Pinned generator_model: {self.groq.model}\n"
                            f"Pinned source_prompt_sha256: {prompt_hash}\n\n"
                            "Pinned maximum_dimensions_m: "
                            f"{json.dumps(maximum_dimensions_m, separators=(',', ':'))}\n\n"
                            "Validation errors:\n"
                            + json.dumps(error_payload[:48], ensure_ascii=False)
                            + "\n\nInvalid JSON:\n"
                            + json.dumps(raw, ensure_ascii=False)[:32_000]
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            policy=self.policy,
        )


def _program_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "_", value.strip().lower()).strip("._-")
    if not normalized:
        raise ValueError("semantic role must contain an alphanumeric identifier")
    if not normalized[0].isalpha():
        normalized = f"component_{normalized}"
    return normalized[:80]


def _json_object_contract() -> str:
    return """
GeometryProgram compact contract:
- top-level keys: schema_version, program_id, semantic_role, units, authorship,
  requested_quantity, generator_provider, generator_model, structured_output_mode,
  source_prompt_sha256, source_description, source_description_origin, placement_context,
  maximum_dimensions_m, materials, nodes, assumptions, limitations,
  deterministic_adjustments.
- maximum_dimensions_m is null or an XYZ object. The complete transformed program
  envelope must remain within it.
- material: material_id, base_color_rgba as {"r":0..1,"g":0..1,
  "b":0..1,"a":0..1}, metallic, roughness.
- every node has kind, node_id and may have parent_id, material_id,
  semantic_role, transform.
- transform uses translation_m, rotation_deg and scale; every vector is an
  object {"x":number,"y":number,"z":number}.
- primitive node: kind="primitive", primitive is box/cylinder/cone/uv_sphere.
  A box requires size_m as an XYZ object. A cylinder requires radius_m and
  height_m. A cone requires radius_m, top_radius_m and height_m. A sphere
  requires radius_m.
  Optional vertices is 8..96 and bevel_m is 0..1.
- curve node: kind="curve", points_m has 2..128 XYZ objects, bevel_depth_m,
  cyclic.
- instance node: kind="instance", source_node_id references another node.
- node_id, material_id, parent_id and source_node_id use lowercase identifiers.
- at least one node semantic_role must equal the top-level semantic_role.
- exactly requested_quantity nodes must carry the top-level semantic_role; use
  instances for repeated equal components.
- assumptions and limitations are arrays of short JSON strings only, never objects.
- deterministic_adjustments is backend-owned and must be an empty array.

Example node list:
[
  {
    "kind":"primitive","node_id":"body","primitive":"box",
    "size_m":{"x":3.0,"y":2.0,"z":2.5},"material_id":"steel",
    "semantic_role":"equipment_shelter",
    "transform":{
      "translation_m":{"x":7.0,"y":0.0,"z":1.25},
      "rotation_deg":{"x":0.0,"y":0.0,"z":0.0},
      "scale":{"x":1.0,"y":1.0,"z":1.0}
    },"vertices":24,"bevel_m":0.04
  },
  {
    "kind":"instance","node_id":"door_right","source_node_id":"door_left",
    "transform":{
      "translation_m":{"x":7.4,"y":-1.04,"z":1.1},
      "rotation_deg":{"x":0.0,"y":0.0,"z":0.0},
      "scale":{"x":1.0,"y":1.0,"z":1.0}
    }
  }
]
"""


def _fit_to_maximum_dimensions(payload: dict[str, Any]) -> dict[str, Any] | None:
    maximum = payload.get("maximum_dimensions_m")
    if not isinstance(maximum, dict):
        return None
    unbounded_payload = deepcopy(payload)
    unbounded_payload["maximum_dimensions_m"] = None
    try:
        unbounded = GeometryProgram.model_validate(unbounded_payload)
    except ValidationError:
        return None
    actual = geometry_program_dimensions(unbounded)
    maximum_values = tuple(float(maximum[axis]) for axis in ("x", "y", "z"))
    ratios = [
        maximum_value / actual_value
        for maximum_value, actual_value in zip(maximum_values, actual, strict=True)
        if actual_value > 1e-9
    ]
    if not ratios:
        return None
    uniform_ratio = min(ratios)
    if uniform_ratio >= 1.0:
        return None

    fitted = unbounded.model_dump(mode="json")
    fitted["maximum_dimensions_m"] = maximum
    root_nodes = [node for node in fitted["nodes"] if node.get("parent_id") is None]
    if not root_nodes:
        return None
    pivot = {
        axis: sum(node["transform"]["translation_m"][axis] for node in root_nodes)
        / len(root_nodes)
        for axis in ("x", "y", "z")
    }
    for node in root_nodes:
        transform = node["transform"]
        for axis in ("x", "y", "z"):
            translation = transform["translation_m"][axis]
            transform["translation_m"][axis] = pivot[axis] + (
                translation - pivot[axis]
            ) * uniform_ratio
            transform["scale"][axis] *= uniform_ratio
    fitted["deterministic_adjustments"] = [
        *fitted.get("deterministic_adjustments", []),
        (
            "Uniform scale applied by the deterministic envelope adapter "
            f"(factor={uniform_ratio:.6f}) after bounded LLM repair attempts."
        ),
    ]
    return fitted


def _normalize_disclosures(payload: dict[str, Any]) -> None:
    """Bound non-executable disclosure metadata after an explicit LLM repair.

    Geometry remains fail-closed. Only assumptions/limitations accept this
    deterministic conversion because they are provenance text, not executable
    scene instructions.
    """

    for field_name in ("assumptions", "limitations"):
        value = payload.get(field_name)
        if not isinstance(value, list):
            continue
        payload[field_name] = [
            item
            if isinstance(item, str)
            else json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in value[:32]
        ]


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every object field required for Groq strict structured output."""

    strict = deepcopy(schema)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                value["additionalProperties"] = False
            if value.get("type") == "object" or "properties" in value:
                properties = value.get("properties", {})
                value["additionalProperties"] = False
                value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(strict)
    return strict
