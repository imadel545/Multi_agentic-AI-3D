import json
from typing import Any

import httpx
from pydantic import ValidationError

from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec
from core.contracts.tower import TowerCharacteristics
from core.services.requirement_parser import parse_requirements_text

REQUIREMENT_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "network_type": {"type": "string", "enum": ["4G", "5G", "MW"]},
        "site_type": {"type": "string"},
        "tower_type": {
            "type": "string",
            "enum": ["lattice_tower", "monopole", "rooftop_mast", "small_cell_pole"],
        },
        "tower_height_m": {"type": "number", "exclusiveMinimum": 0, "maximum": 150},
        "tower_characteristics": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "structure": {
                    "type": "string",
                    "enum": ["lattice", "monopole", "rooftop_mast", "small_cell_pole"],
                },
                "leg_count": {"type": "integer", "minimum": 1, "maximum": 4},
                "base_width_m": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 30},
                "top_width_m": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 30},
                "foundation_type": {
                    "type": "string",
                    "enum": ["concrete_pad", "rooftop_anchored", "pole_base", "unknown"],
                },
                "has_platform": {"type": "boolean"},
                "platform_count": {"type": "integer", "minimum": 0, "maximum": 12},
                "has_ladder": {"type": "boolean"},
                "has_lightning_rod": {"type": "boolean"},
                "has_aviation_light": {"type": "boolean"},
                "material": {
                    "type": "string",
                    "enum": ["galvanized_steel", "painted_steel", "concrete", "unknown"],
                },
            },
            "required": [
                "structure",
                "leg_count",
                "base_width_m",
                "top_width_m",
                "foundation_type",
                "has_platform",
                "platform_count",
                "has_ladder",
                "has_lightning_rod",
                "has_aviation_light",
                "material",
            ],
        },
        "sector_count": {"type": "integer", "minimum": 1, "maximum": 12},
        "antenna_type": {"type": "string"},
        "antenna_install_height_m": {"type": "number", "exclusiveMinimum": 0, "maximum": 150},
        "azimuths_deg": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "number", "minimum": 0, "exclusiveMaximum": 360},
        },
        "mechanical_tilt_deg": {"type": "number", "minimum": -15, "maximum": 30},
        "electrical_tilt_deg": {"type": "number", "minimum": -15, "maximum": 30},
        "beamwidth_deg": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
        "include_rru": {"type": "boolean"},
        "include_cables": {"type": "boolean"},
        "include_beams": {"type": "boolean"},
        "include_labels": {"type": "boolean"},
        "detail_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "warnings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
            },
        },
    },
    "required": [
        "network_type",
        "site_type",
        "tower_type",
        "tower_height_m",
        "tower_characteristics",
        "sector_count",
        "antenna_type",
        "antenna_install_height_m",
        "azimuths_deg",
        "mechanical_tilt_deg",
        "electrical_tilt_deg",
        "beamwidth_deg",
        "include_rru",
        "include_cables",
        "include_beams",
        "include_labels",
        "detail_level",
        "warnings",
    ],
}


class GroqStructuredClient:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_s: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        baseline = parse_requirements_text(requirements_text, detail_level=detail_level)
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract telecom 3D design requirements into strict JSON. "
                    "Normalize French and English telecom vocabulary. "
                    "Never invent critical values silently; if a value is inferred, "
                    "add a warning with a stable code and concise message. "
                    "azimuths_deg must always be an array of separate JSON numbers, "
                    "for example [0, 120, 240], never a string and never concatenated. "
                    "Extract tower_characteristics from explicit pylon details such as "
                    "leg count, base/top width, foundation, platforms, ladder, lightning rod, "
                    "aviation light, and material. "
                    "Preserve the deterministic baseline values unless the user text "
                    "explicitly contradicts them. "
                    "Do not include explanatory text outside JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Preferred detail_level: {detail_level}\n\n"
                    "Deterministic baseline JSON:\n"
                    f"{baseline.model_dump_json(exclude={'repair_events'})}\n\n"
                    f"Requirements:\n{requirements_text}"
                ),
            },
        ]
        strict_payload = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "RequirementSpec",
                    "schema": REQUIREMENT_SPEC_SCHEMA,
                    "strict": True,
                },
            },
        }
        try:
            return self._post_and_validate(strict_payload, baseline)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise

        json_object_payload = {
            "model": self.model,
            "temperature": 0,
            "messages": messages
            + [
                {
                    "role": "system",
                    "content": (
                        "Retry in JSON Object Mode. Return the same object shape. "
                        "Use numeric JSON arrays exactly as in the deterministic baseline."
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
        }
        return self._post_and_validate(json_object_payload, baseline)

    def _post_and_validate(
        self, payload: dict[str, Any], baseline: RequirementSpec
    ) -> RequirementSpec:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        raw = json.loads(content)
        try:
            return RequirementSpec.model_validate(raw)
        except ValidationError:
            return _repair_and_validate(raw, baseline)


def _repair_and_validate(raw: dict[str, Any], baseline: RequirementSpec) -> RequirementSpec:
    candidate = baseline.model_dump()
    candidate.update(raw)
    repaired_fields: list[str] = []
    if not _is_number_list(candidate.get("azimuths_deg")):
        candidate["azimuths_deg"] = baseline.azimuths_deg
        repaired_fields.append("azimuths_deg")
    if len(candidate["azimuths_deg"]) != int(candidate.get("sector_count", 0)):
        candidate["sector_count"] = baseline.sector_count
        candidate["azimuths_deg"] = baseline.azimuths_deg
        repaired_fields.extend(["sector_count", "azimuths_deg"])
    if float(candidate.get("antenna_install_height_m", 0)) > float(
        candidate.get("tower_height_m", 0)
    ):
        candidate["antenna_install_height_m"] = baseline.antenna_install_height_m
        repaired_fields.append("antenna_install_height_m")
    try:
        tower_characteristics = TowerCharacteristics.model_validate(
            candidate.get("tower_characteristics")
        )
    except ValidationError:
        candidate["tower_characteristics"] = baseline.tower_characteristics.model_dump()
        repaired_fields.append("tower_characteristics")
    else:
        baseline_characteristics = baseline.tower_characteristics
        if tower_characteristics.material != baseline_characteristics.material:
            candidate["tower_characteristics"] = tower_characteristics.model_copy(
                update={"material": baseline_characteristics.material}
            ).model_dump()
            repaired_fields.append("tower_characteristics.material")
    warnings = [
        WarningItem.model_validate(warning).model_dump()
        for warning in candidate.get("warnings", [])
        if isinstance(warning, dict)
    ]
    if repaired_fields:
        warnings.append(
            WarningItem(
                code="LLM_FIELD_REPAIRED",
                message=(
                    "Invalid LLM fields repaired from deterministic baseline: "
                    f"{sorted(set(repaired_fields))}."
                ),
            ).model_dump()
        )
    candidate["warnings"] = warnings
    return RequirementSpec.model_validate(candidate)


def _is_number_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, int | float) for item in value)
