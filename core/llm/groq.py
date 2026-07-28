import json
from typing import Any

import httpx
from pydantic import ValidationError

from core.contracts.common import WarningItem
from core.contracts.requirements import (
    RequirementCandidateEvidence,
    RequirementSpec,
)
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
            # GPT-OSS may serialize a malformed azimuth token even under constrained
            # decoding. The local RequirementSpec validator repairs non-numeric items
            # from the deterministic baseline and records LLM_FIELD_REPAIRED.
            "items": {"anyOf": [{"type": "number"}, {"type": "string"}]},
        },
        "mechanical_tilt_deg": {"type": "number", "minimum": -15, "maximum": 30},
        "electrical_tilt_deg": {"type": "number", "minimum": -15, "maximum": 30},
        "beamwidth_deg": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
        "include_rru": {"type": "boolean"},
        "include_cables": {"type": "boolean"},
        "include_beams": {"type": "boolean"},
        "include_labels": {"type": "boolean"},
        "include_power_cabinet": {"type": "boolean"},
        "include_gps_antenna": {"type": "boolean"},
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
        "include_power_cabinet",
        "include_gps_antenna",
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
                    "Extract supported visual equipment flags such as include_power_cabinet "
                    "and include_gps_antenna when the user asks for power boxes, energy "
                    "cabinets, GPS, or GNSS. "
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
            return self._post_and_validate(strict_payload, baseline, requirements_text)
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
        requirements = self._post_and_validate(
            json_object_payload,
            baseline,
            requirements_text,
        )
        return requirements.model_copy(
            update={
                "warnings": [
                    *requirements.warnings,
                    WarningItem(
                        code="LLM_JSON_OBJECT_FALLBACK",
                        message=(
                            "Groq strict JSON Schema generation was rejected; a JSON Object "
                            "response was accepted only after local RequirementSpec validation."
                        ),
                    ),
                ]
            }
        )

    def _post_and_validate(
        self,
        payload: dict[str, Any],
        baseline: RequirementSpec,
        requirements_text: str,
    ) -> RequirementSpec:
        raw = self._post_raw(payload)
        raw, repaired_fields = _normalize_known_aliases(raw)
        raw, missing_fields = _restore_missing_baseline_fields(raw, baseline)
        repaired_fields.extend(missing_fields)
        llm_candidate = dict(raw)
        raw, protected_fields = _protect_explicit_source_fields(
            raw,
            baseline,
            requirements_text,
        )
        try:
            requirements = RequirementSpec.model_validate(raw)
        except ValidationError:
            requirements = _repair_and_validate(
                raw,
                baseline,
                initial_repaired_fields=repaired_fields,
            )
        return _finalize_requirements(
            requirements,
            baseline,
            repaired_fields=repaired_fields,
            protected_fields=protected_fields,
            llm_candidate=llm_candidate,
        )

    def _post_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        return json.loads(content)


def _restore_missing_baseline_fields(
    raw: dict[str, Any],
    baseline: RequirementSpec,
) -> tuple[dict[str, Any], list[str]]:
    candidate = dict(raw)
    repaired_fields = []
    baseline_payload = baseline.model_dump(exclude={"repair_events"})
    for field in REQUIREMENT_SPEC_SCHEMA["required"]:
        if field not in candidate:
            candidate[field] = baseline_payload[field]
            repaired_fields.append(field)
    return candidate, repaired_fields


def _normalize_known_aliases(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    candidate = dict(raw)
    repaired_fields: list[str] = []
    network = candidate.get("network_type")
    normalized_network = {
        "LTE": "4G",
        "LTE/4G": "4G",
        "NR": "5G",
        "5G NR": "5G",
        "MICROWAVE": "MW",
    }.get(str(network).strip().upper())
    if normalized_network and normalized_network != network:
        candidate["network_type"] = normalized_network
        repaired_fields.append("network_type")
    tower = candidate.get("tower_type")
    normalized_tower = {
        "LATTICE": "lattice_tower",
        "LATTICE TOWER": "lattice_tower",
        "ROOFTOP": "rooftop_mast",
        "SMALL CELL": "small_cell_pole",
        "SMALL-CELL": "small_cell_pole",
    }.get(str(tower).strip().upper())
    if normalized_tower and normalized_tower != tower:
        candidate["tower_type"] = normalized_tower
        repaired_fields.append("tower_type")
    return candidate, repaired_fields


def _protect_explicit_source_fields(
    raw: dict[str, Any],
    baseline: RequirementSpec,
    requirements_text: str,
) -> tuple[dict[str, Any], list[str]]:
    candidate = dict(raw)
    warning_codes = {warning.code for warning in baseline.warnings}
    protected = {"detail_level"}
    for field, default_warning in _DEFAULT_WARNING_BY_FIELD.items():
        if default_warning not in warning_codes:
            protected.add(field)

    normalized_text = requirements_text.lower()
    for field, terms in _EXPLICIT_TEXT_TERMS_BY_FIELD.items():
        if any(term in normalized_text for term in terms):
            protected.add(field)
    for field, evidence in baseline.field_evidence.items():
        if evidence.explicit and not evidence.requires_confirmation:
            protected.add(field)
        elif evidence.defaulted:
            protected.discard(field)
    if "network_type" in protected:
        protected.add("antenna_type")
    if "tower_type" in protected:
        protected.add("tower_characteristics")

    baseline_payload = baseline.model_dump(exclude={"repair_events"})
    restored: list[str] = []
    for field in sorted(protected):
        if field not in candidate or field not in baseline_payload:
            continue
        if candidate[field] == baseline_payload[field]:
            continue
        candidate[field] = baseline_payload[field]
        restored.append(field)
    return candidate, restored


def _repair_and_validate(
    raw: dict[str, Any],
    baseline: RequirementSpec,
    initial_repaired_fields: list[str] | None = None,
) -> RequirementSpec:
    candidate = baseline.model_dump()
    candidate.update(raw)
    repaired_fields = initial_repaired_fields if initial_repaired_fields is not None else []
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
    warnings = []
    for warning in candidate.get("warnings", []):
        if not isinstance(warning, dict):
            repaired_fields.append("warnings")
            continue
        try:
            warnings.append(WarningItem.model_validate(warning).model_dump())
        except ValidationError:
            repaired_fields.append("warnings")
    candidate["warnings"] = warnings
    for _ in range(3):
        try:
            return RequirementSpec.model_validate(candidate)
        except ValidationError as exc:
            repaired = False
            baseline_payload = baseline.model_dump()
            for error in exc.errors():
                location = error.get("loc") or ()
                field = location[0] if location else None
                if not isinstance(field, str) or field not in baseline_payload:
                    continue
                candidate[field] = baseline_payload[field]
                repaired_fields.append(".".join(str(part) for part in location))
                repaired = True
            if not repaired:
                raise
    return RequirementSpec.model_validate(candidate)


def _finalize_requirements(
    requirements: RequirementSpec,
    baseline: RequirementSpec,
    *,
    repaired_fields: list[str],
    protected_fields: list[str],
    llm_candidate: dict[str, Any],
) -> RequirementSpec:
    # LLM-authored warning text is neither an authority signal nor a safe
    # product message. Only deterministic baseline warnings and locally emitted
    # LLM safeguard codes may cross the public contract.
    warnings: list[WarningItem] = []
    for warning in baseline.warnings:
        fields = _BASELINE_WARNING_FIELDS.get(warning.code, ())
        if fields and not all(
            getattr(requirements, field) == getattr(baseline, field) for field in fields
        ):
            continue
        warnings.append(warning)
    if repaired_fields:
        warnings.append(_repaired_warning(repaired_fields))
    if protected_fields:
        warnings.append(_protected_warning(protected_fields))
    unique = []
    seen = set()
    for warning in warnings:
        identity = (warning.code, warning.message)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(warning)
    return _merge_llm_provenance(
        requirements.model_copy(update={"warnings": unique}),
        baseline,
        llm_candidate,
    )


def _merge_llm_provenance(
    requirements: RequirementSpec,
    baseline: RequirementSpec,
    llm_candidate: dict[str, Any],
) -> RequirementSpec:
    field_evidence = dict(baseline.field_evidence)
    for field, evidence in baseline.field_evidence.items():
        if field not in llm_candidate or not hasattr(requirements, field):
            continue
        llm_value = llm_candidate[field]
        selected_value = getattr(requirements, field)
        if hasattr(selected_value, "model_dump"):
            selected_value = selected_value.model_dump()
        selected = llm_value == selected_value
        candidates = [
            candidate.model_copy(update={"selected": False if selected else candidate.selected})
            for candidate in evidence.candidates
        ]
        candidates.append(
            RequirementCandidateEvidence(
                value=llm_value,
                source="llm",
                mechanism="groq_structured_extraction",
                confidence=0.78,
                selected=selected,
                rationale=(
                    "Valeur structurée proposée par Groq."
                    if selected
                    else "Proposition Groq rejetée par la provenance explicite ou la validation."
                ),
            )
        )
        if selected and llm_value != evidence.selected_value:
            field_evidence[field] = evidence.model_copy(
                update={
                    "selected_value": llm_value,
                    "selected_source": "llm",
                    "confidence": 0.78,
                    "explicit": False,
                    "defaulted": False,
                    "candidates": candidates,
                    "rationale": (
                        "Valeur Groq retenue car le texte ne contenait pas de valeur "
                        "explicite contradictoire."
                    ),
                }
            )
        else:
            field_evidence[field] = evidence.model_copy(update={"candidates": candidates})
    return requirements.model_copy(
        update={
            "field_evidence": field_evidence,
            "conflicts": baseline.conflicts,
            "assumptions": baseline.assumptions,
            "requires_confirmation": baseline.requires_confirmation,
            "confirmation_fields": baseline.confirmation_fields,
        }
    )


def _repaired_warning(repaired_fields: list[str]) -> WarningItem:
    return WarningItem(
        code="LLM_FIELD_REPAIRED",
        message=(
            "Invalid or missing LLM fields repaired from deterministic baseline: "
            f"{sorted(set(repaired_fields))}."
        ),
    )


def _protected_warning(protected_fields: list[str]) -> WarningItem:
    return WarningItem(
        code="LLM_SOURCE_FIELD_PROTECTED",
        message=(
            "LLM values conflicting with explicit source requirements were ignored: "
            f"{sorted(set(protected_fields))}."
        ),
    )


def _is_number_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, int | float) for item in value)


_DEFAULT_WARNING_BY_FIELD = {
    "network_type": "DEFAULT_NETWORK_USED",
    "tower_type": "DEFAULT_TOWER_USED",
    "tower_height_m": "DEFAULT_TOWER_HEIGHT_USED",
    "tower_characteristics": "DEFAULT_TOWER_CHARACTERISTICS_USED",
    "sector_count": "DEFAULT_SECTOR_COUNT_USED",
    "antenna_install_height_m": "DEFAULT_INSTALL_HEIGHT_USED",
    "azimuths_deg": "DEFAULT_AZIMUTHS_USED",
    "mechanical_tilt_deg": "DEFAULT_MECHANICAL_TILT_USED",
    "electrical_tilt_deg": "DEFAULT_ELECTRICAL_TILT_USED",
    "beamwidth_deg": "DEFAULT_BEAMWIDTH_USED",
    "include_cables": "DEFAULT_CABLES_USED",
    "include_beams": "DEFAULT_BEAMS_USED",
    "include_labels": "DEFAULT_LABELS_USED",
}

_BASELINE_WARNING_FIELDS = {
    warning: (field,) for field, warning in _DEFAULT_WARNING_BY_FIELD.items()
}

_EXPLICIT_TEXT_TERMS_BY_FIELD = {
    "include_rru": ("rru", "radio"),
    "include_cables": ("cable", "câble"),
    "include_beams": ("faisceau", "beam"),
    "include_labels": ("label", "étiquette", "etiquette"),
    "include_power_cabinet": (
        "armoire énergie",
        "armoire energie",
        "boîte alimentation",
        "boite alimentation",
        "power cabinet",
        "power box",
        "cabinet",
    ),
    "include_gps_antenna": ("gps", "gnss"),
}
