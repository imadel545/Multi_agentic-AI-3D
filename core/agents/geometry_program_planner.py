from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from core.contracts.geometry_program import (
    GeometryProgram,
    GeometryProgramVector3,
    geometry_program_dimensions,
    geometry_program_visible_root_bounds,
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
        schema_version: Literal["1.0.0", "2.0.0"] = "2.0.0",
    ) -> GeometryProgram:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("geometry-program prompt must not be empty")
        normalized_role = _program_identifier(semantic_role)
        normalized_request_id = _program_identifier(request_id or normalized_role)
        program_id = f"{normalized_request_id}.llm_v{schema_version.split('.', 1)[0]}"
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
                    "Use only operations present in the supplied GeometryProgram schema. "
                    "For V2 prefer profiles, extrusion, sweep, arrays, exact booleans, bounded "
                    "modifiers, terrain, anchors, connectors and semantic groups when they improve "
                    "functional construction. "
                    "Create coherent multi-part technical geometry with stable semantic roles. "
                    "An LLM-authored program must contain at least three nodes, including "
                    "supporting/detail geometry in addition to its primary semantic node. "
                    "Put the requested semantic_role only on visible mesh-producing nodes; "
                    "never put a primary semantic node in construction_node_ids. "
                    "Never emit ellipsis tokens (... or …), placeholder objects or abbreviated "
                    "point lists; write every coordinate explicitly. "
                    "The program frame is meter-based and Z-up. Primitive and extrusion depth "
                    "are centered on their local origin. Every independent visible root of a "
                    "ground-contact component must have a minimum world Z of exactly 0; translate "
                    "centered geometry by its half-height instead of leaving it below ground. "
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
                    f"Required schema_version: {schema_version}\n"
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
                                + _json_object_contract(schema_version)
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                policy=self.policy,
            )
        pinned = {
            "schema_version": schema_version,
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
            _normalize_explicit_point_placeholders(candidate)
            _normalize_profile_definitions(candidate)
            _normalize_ground_contact(candidate)
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
                    schema_version=schema_version,
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
        schema_version: Literal["1.0.0", "2.0.0"],
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
                            "numeric keys r, g, b and a. " + _json_object_contract(schema_version)
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Pinned program_id: {program_id}\n"
                            f"Pinned semantic_role: {semantic_role}\n"
                            f"Pinned requested_quantity: {quantity}\n"
                            f"Pinned schema_version: {schema_version}\n"
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


def _json_object_contract(schema_version: str = "2.0.0") -> str:
    v2_contract = """
- V2 profile node: kind="profile", points_m are XY objects and closed declares a reusable
  transform-free profile.
- V2 mesh operations: extrude(profile_node_id, depth_m),
  revolve(profile_node_id, angle_deg, segments), sweep(profile_node_id, path_points_m),
  array(source_node_id, count, offset_m), boolean(left_node_id, right_node_id,
  operation=union/difference/intersection, solver=exact), modifier(source_node_id,
  modifier=bevel/solidify/mirror), and terrain(width_m, depth_m, columns, rows, heights_m).
- V2 may declare anchors, connectors, semantic_groups and construction_node_ids. References
  must resolve and the dependency graph must be acyclic. Use construction_node_ids for profiles,
  cutters and intermediate sources that must not appear as final visible geometry. A profile
  has no semantic_role; the visible extrude/revolve/sweep result carries the role instead.
"""
    version_contract = (
        v2_contract
        if schema_version == "2.0.0"
        else "- V1 permits only primitive, curve and instance nodes."
    )
    return (
        """
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
- points_m and path_points_m must contain every coordinate explicitly. Never emit
  ellipsis tokens ("..." or "…"), placeholder objects or abbreviated point lists.
- instance node: kind="instance", source_node_id references another node.
- node_id, material_id, parent_id and source_node_id use lowercase identifiers.
- at least one node semantic_role must equal the top-level semantic_role.
- every LLM-authored program contains at least three nodes in total; add real
  supporting/detail geometry instead of padding with duplicate empty parts.
- exactly requested_quantity visible mesh-producing nodes must carry the
  top-level semantic_role; use instances for repeated equal components. Those
  primary nodes must never appear in construction_node_ids.
- assumptions and limitations are arrays of short JSON strings only, never objects.
- deterministic_adjustments is backend-owned and must be an empty array.
"""
        + version_contract
        + """
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
    )


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
    construction_node_ids = set(fitted.get("construction_node_ids", []))
    root_nodes = [
        node
        for node in fitted["nodes"]
        if node.get("parent_id") is None and node.get("node_id") not in construction_node_ids
    ]
    if not root_nodes:
        return None
    pivot = {
        axis: sum(node["transform"]["translation_m"][axis] for node in root_nodes) / len(root_nodes)
        for axis in ("x", "y", "z")
    }
    for node in root_nodes:
        transform = node["transform"]
        for axis in ("x", "y", "z"):
            translation = transform["translation_m"][axis]
            transform["translation_m"][axis] = (
                pivot[axis] + (translation - pivot[axis]) * uniform_ratio
            )
            transform["scale"][axis] *= uniform_ratio
    fitted["deterministic_adjustments"] = [
        *fitted.get("deterministic_adjustments", []),
        (
            "Uniform scale applied by the deterministic envelope adapter "
            f"(factor={uniform_ratio:.6f}) after bounded LLM repair attempts."
        ),
    ]
    return fitted


_GROUND_CONTACT_ROLES = {
    "barrier",
    "cabinet",
    "equipment_enclosure",
    "equipment_shelter",
    "fence",
    "gate",
    "ground_enclosure",
    "ground_equipment",
    "kiosk",
    "perimeter_fence",
    "site_shelter",
    "solar_canopy",
}
_GROUND_CONTACT_SIGNALS = (
    "at ground level",
    "ground contact",
    "ground level",
    "on ground",
    "on the ground",
    "pose au sol",
    "pose sur le sol",
    "au niveau du sol",
    "sur le terrain",
)
_ELEVATED_PLACEMENT_SIGNALS = (
    "above ground",
    "at height",
    "elevated",
    "mounted on tower",
    "mounted on the tower",
    "on platform",
    "rooftop",
    "suspended",
    "en hauteur",
    "monte sur le pylone",
    "sur plateforme",
    "suspendu",
)


def _normalize_ground_contact(payload: dict[str, Any]) -> None:
    """Align validated ground-contact outputs without inventing geometry.

    GPT-OSS chooses the component and its typed geometry. The deterministic
    adapter enforces only the declared spatial policy: a ground-contact output
    may not cross below Z=0. Each independent visible root is lifted by its
    measured envelope, which also handles centered primitives and asymmetric
    sweep profiles consistently.
    """

    if not _requires_ground_contact(payload):
        return
    candidate = deepcopy(payload)
    candidate["maximum_dimensions_m"] = None
    try:
        program = GeometryProgram.model_validate(candidate)
    except ValidationError:
        return
    root_bounds = geometry_program_visible_root_bounds(program)
    offsets = {
        node_id: -minimum[2] for node_id, (minimum, _) in root_bounds.items() if minimum[2] < -1e-6
    }
    if not offsets:
        return

    adjustments = payload.get("deterministic_adjustments")
    if adjustments is None:
        adjustments = []
        payload["deterministic_adjustments"] = adjustments
    if not isinstance(adjustments, list) or len(adjustments) >= 16:
        return
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return
    nodes_by_id = {
        node.get("node_id"): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    if any(node_id not in nodes_by_id for node_id in offsets):
        return

    for node_id, offset in offsets.items():
        node = nodes_by_id[node_id]
        transform = node.setdefault("transform", _identity_transform_payload())
        translation = transform.setdefault("translation_m", _xyz_payload(0.0, 0.0, 0.0))
        translation["z"] = float(translation.get("z", 0.0)) + offset
    detail = ", ".join(f"{node_id}:+{offset:.6f}m" for node_id, offset in sorted(offsets.items()))
    adjustments.append(
        "Aligned ground-contact visible root envelope(s) to Z=0 "
        f"({detail}); geometry and XY placement were unchanged."
    )


def _requires_ground_contact(payload: dict[str, Any]) -> bool:
    role = _normalized_text(str(payload.get("semantic_role") or "")).replace(" ", "_")
    context = _normalized_text(
        " ".join(
            str(payload.get(field) or "") for field in ("placement_context", "source_description")
        )
    )
    if any(signal in context for signal in _ELEVATED_PLACEMENT_SIGNALS):
        return False
    if any(signal in context for signal in _GROUND_CONTACT_SIGNALS):
        return True
    return role in _GROUND_CONTACT_ROLES


def _normalized_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


def _xyz_payload(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


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


def _normalize_explicit_point_placeholders(payload: dict[str, Any]) -> None:
    """Remove only explicit ellipsis sentinels from bounded point lists.

    Some JSON-object completions abbreviate an otherwise complete list with an
    entry such as ``{"...": "..."}``. That is neither geometry nor a value we
    can repair semantically. It is safe to remove only when the remaining list
    still satisfies the operation's contract minimum. Any other malformed
    point, or a list made too short by removal, is left unchanged so Pydantic
    validation fails closed.
    """

    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return

    repairs: list[tuple[dict[str, Any], str, list[Any], str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = node.get("kind")
        if kind in {"curve", "profile"}:
            field_name = "points_m"
            minimum = 3 if kind == "profile" and node.get("closed", True) else 2
        elif kind == "sweep":
            field_name = "path_points_m"
            minimum = 3 if node.get("cyclic", False) else 2
        else:
            continue
        points = node.get(field_name)
        if not isinstance(points, list):
            continue
        filtered = [point for point in points if not _is_explicit_ellipsis(point)]
        removed_count = len(points) - len(filtered)
        if removed_count == 0 or len(filtered) < minimum:
            continue
        node_id = node.get("node_id")
        label = node_id if isinstance(node_id, str) else "unknown_node"
        repairs.append((node, field_name, filtered, f"{label}.{field_name}:{removed_count}"))

    if not repairs:
        return
    adjustments = payload.get("deterministic_adjustments")
    if adjustments is None:
        adjustments = []
        payload["deterministic_adjustments"] = adjustments
    if not isinstance(adjustments, list) or len(adjustments) >= 16:
        return

    for node, field_name, filtered, _ in repairs:
        node[field_name] = filtered
    labels = [repair[3] for repair in repairs]
    shown = ", ".join(labels[:8])
    suffix = "" if len(labels) <= 8 else f", +{len(labels) - 8} more"
    adjustments.append(
        "Removed explicit non-geometric ellipsis placeholder(s) from point lists "
        f"({shown}{suffix}); all remaining coordinates still satisfy contract minima."
    )


def _is_explicit_ellipsis(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() in {"...", "…"}
    if not isinstance(value, dict) or not value:
        return False
    return all(_is_explicit_ellipsis(item) for item in value.values())


def _normalize_profile_definitions(payload: dict[str, Any]) -> None:
    """Canonicalize V2 profiles before fail-closed graph validation.

    Groq strict structured output requires every property declared by an
    object schema. Because profile nodes inherit the common node fields, the
    decoder must emit ``transform`` even though profiles are local 2D
    definitions and the GeometryProgram contract forbids profile transforms.
    Model repair can therefore repeat the same invalid shape indefinitely.

    This normalization never invents geometry: it removes metadata and
    transforms that have no executable meaning on a profile and makes profile
    construction-only status explicit. Placement and materials remain owned by
    the consuming extrude/revolve/sweep mesh node. Any semantic change is
    recorded in deterministic provenance.
    """

    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return

    profile_ids: list[str] = []
    normalized_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("kind") != "profile":
            continue
        node_id = node.get("node_id")
        if isinstance(node_id, str):
            profile_ids.append(node_id)

        changed = False
        for field_name in ("parent_id", "material_id", "semantic_role"):
            if node.get(field_name) is not None:
                node.pop(field_name, None)
                changed = True

        transform = node.pop("transform", None)
        if transform is not None and transform != _identity_transform_payload():
            changed = True
        if changed and isinstance(node_id, str):
            normalized_ids.append(node_id)

    construction_ids = payload.get("construction_node_ids")
    if construction_ids is None:
        construction_ids = []
        payload["construction_node_ids"] = construction_ids
    if isinstance(construction_ids, list):
        for profile_id in profile_ids:
            if profile_id not in construction_ids:
                construction_ids.append(profile_id)
                if profile_id not in normalized_ids:
                    normalized_ids.append(profile_id)

    if not normalized_ids:
        return
    adjustments = payload.get("deterministic_adjustments")
    if not isinstance(adjustments, list) or len(adjustments) >= 16:
        return
    shown = ", ".join(normalized_ids[:8])
    suffix = "" if len(normalized_ids) <= 8 else f", +{len(normalized_ids) - 8} more"
    adjustments.append(
        "Canonicalized transform-free geometry profile definition(s) "
        f"({shown}{suffix}); placement and material remain on consuming mesh nodes."
    )


def _identity_transform_payload() -> dict[str, dict[str, float]]:
    return {
        "translation_m": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation_deg": {"x": 0.0, "y": 0.0, "z": 0.0},
        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
    }


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize Pydantic JSON Schema to Groq's strict supported subset."""

    strict = deepcopy(schema)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            # Groq strict structured output documents ``anyOf`` as the supported
            # union construct. Pydantic emits discriminated unions as
            # ``oneOf`` plus a discriminator, which the API rejects with 400.
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            value.pop("discriminator", None)

            # A reference is already closed by its target definition. Siblings
            # added next to ``$ref`` are neither needed nor part of the subset
            # shown by Groq, and can make an otherwise valid strict schema fail.
            if "$ref" in value:
                reference = value["$ref"]
                value.clear()
                value["$ref"] = reference
                return
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
