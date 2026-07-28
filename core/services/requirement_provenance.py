from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.contracts.common import WarningItem
from core.contracts.requirements import (
    RequirementCandidateEvidence,
    RequirementConflict,
    RequirementFieldEvidence,
)

NUMBER_WORDS = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
NUMBER_TOKEN = rf"(?:\d+|{'|'.join(sorted(NUMBER_WORDS, key=len, reverse=True))})"
TOWER_TERMS = (
    r"pyl[oô]ne|tower|tour|m[aâ]t|monopole|treillis|lattice|"
    r"rooftop(?:\s+mast)?|small[- ]cell(?:\s+pole)?"
)
CORRECTION_CUES = (
    "correction",
    "corriger",
    "corrigé",
    "corrige",
    "finalement",
    "valeur finale",
    "final value",
    "actually",
    "instead",
    "remplacer",
    "replace",
)
DEFAULT_WARNING_BY_FIELD = {
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
DIRECT_TEXT_FIELDS = {
    "network_type",
    "tower_type",
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
}


@dataclass(frozen=True)
class CriticalRequirementResolution:
    values: dict[str, Any]
    explicit: dict[str, bool]
    field_evidence: dict[str, RequirementFieldEvidence]
    conflicts: list[RequirementConflict]
    assumptions: list[str]
    confirmation_fields: list[str]

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.confirmation_fields)


def resolve_critical_requirements(text: str) -> CriticalRequirementResolution:
    normalized = text.lower()
    tower_candidates = _tower_height_candidates(text, normalized)
    tower_value, tower_evidence, tower_conflicts = _resolve_candidates(
        "tower_height_m",
        tower_candidates,
        default=30.0,
        default_rationale="Aucune hauteur de pylône explicite; valeur de planification 30 m.",
    )
    sector_candidates = _sector_count_candidates(text, normalized)
    sector_value, sector_evidence, sector_conflicts = _resolve_candidates(
        "sector_count",
        sector_candidates,
        default=3,
        default_rationale="Aucun nombre de secteurs explicite; valeur de planification 3.",
    )
    install_candidates = _install_height_candidates(text, normalized)
    install_default = min(24.0, float(tower_value))
    install_value, install_evidence, install_conflicts = _resolve_candidates(
        "antenna_install_height_m",
        install_candidates,
        default=install_default,
        default_rationale=(
            "Aucune hauteur d'installation explicite; valeur de planification "
            f"{install_default:g} m."
        ),
    )
    azimuth_candidates = _azimuth_candidates(text, normalized)
    azimuth_default = _default_azimuths(int(sector_value))
    azimuth_value, azimuth_evidence, azimuth_conflicts = _resolve_candidates(
        "azimuths_deg",
        azimuth_candidates,
        default=azimuth_default,
        default_rationale=(
            "Aucune liste d'azimuts explicite; répartition uniforme utilisée pour la planification."
        ),
    )

    conflicts = [
        *tower_conflicts,
        *sector_conflicts,
        *install_conflicts,
        *azimuth_conflicts,
    ]
    confirmation_fields = [conflict.field for conflict in conflicts if not conflict.resolved]

    if len(azimuth_value) != int(sector_value):
        mismatch = RequirementConflict(
            field="sector_count/azimuths_deg",
            candidate_values=[sector_value, azimuth_value],
            source_texts=[
                candidate.source_text
                for candidate in [*sector_candidates, *azimuth_candidates]
                if candidate.source_text
            ],
            reason=(
                "Le nombre de secteurs explicite ne correspond pas au nombre d'azimuts explicites."
            ),
            resolved=False,
        )
        conflicts.append(mismatch)
        confirmation_fields.extend(["sector_count", "azimuths_deg"])
        azimuth_value = azimuth_default
        azimuth_evidence = azimuth_evidence.model_copy(
            update={
                "selected_value": azimuth_value,
                "selected_source": "repair",
                "confidence": 0.0,
                "conflict": True,
                "requires_confirmation": True,
                "rationale": (
                    "Liste temporairement normalisée pour conserver un RequirementSpec valide; "
                    "confirmation utilisateur obligatoire."
                ),
            }
        )

    if float(install_value) > float(tower_value):
        conflicts.append(
            RequirementConflict(
                field="antenna_install_height_m",
                candidate_values=[install_value, tower_value],
                source_texts=[
                    candidate.source_text
                    for candidate in [*install_candidates, *tower_candidates]
                    if candidate.source_text
                ],
                reason="La hauteur d'installation dépasse la hauteur du pylône.",
                resolved=False,
            )
        )
        confirmation_fields.append("antenna_install_height_m")
        install_evidence = install_evidence.model_copy(
            update={
                "conflict": True,
                "requires_confirmation": True,
                "rationale": (
                    "La valeur explicite est géométriquement impossible et doit être confirmée "
                    "ou corrigée avant génération."
                ),
            }
        )

    confirmation_fields = list(dict.fromkeys(confirmation_fields))
    field_evidence = {
        "tower_height_m": _mark_confirmation(tower_evidence, confirmation_fields),
        "sector_count": _mark_confirmation(sector_evidence, confirmation_fields),
        "antenna_install_height_m": _mark_confirmation(install_evidence, confirmation_fields),
        "azimuths_deg": _mark_confirmation(azimuth_evidence, confirmation_fields),
    }
    assumptions = [evidence.rationale for evidence in field_evidence.values() if evidence.defaulted]
    return CriticalRequirementResolution(
        values={
            "tower_height_m": float(tower_value),
            "sector_count": int(sector_value),
            "antenna_install_height_m": float(install_value),
            "azimuths_deg": [float(value) for value in azimuth_value],
        },
        explicit={field: evidence.explicit for field, evidence in field_evidence.items()},
        field_evidence=field_evidence,
        conflicts=conflicts,
        assumptions=assumptions,
        confirmation_fields=confirmation_fields,
    )


def align_evidence_with_repaired_values(
    field_evidence: dict[str, RequirementFieldEvidence],
    repaired: dict[str, Any],
) -> dict[str, RequirementFieldEvidence]:
    aligned = dict(field_evidence)
    for field, evidence in field_evidence.items():
        if field not in repaired or repaired[field] == evidence.selected_value:
            continue
        candidates = [
            candidate.model_copy(update={"selected": False}) for candidate in evidence.candidates
        ]
        candidates.append(
            RequirementCandidateEvidence(
                value=repaired[field],
                source="repair",
                mechanism="contract_repair",
                confidence=0.5,
                selected=True,
                rationale="Valeur réparée pour satisfaire les invariants géométriques.",
            )
        )
        aligned[field] = evidence.model_copy(
            update={
                "selected_value": repaired[field],
                "selected_source": "repair",
                "confidence": 0.5,
                "candidates": candidates,
                "rationale": (
                    "Valeur réparée pour conserver un contrat valide; la provenance "
                    "explicite d'origine reste disponible."
                ),
            }
        )
    return aligned


def complete_requirement_evidence(
    *,
    selected_values: dict[str, Any],
    warnings: list[WarningItem],
    existing: dict[str, RequirementFieldEvidence],
) -> dict[str, RequirementFieldEvidence]:
    completed = dict(existing)
    warning_codes = {warning.code for warning in warnings}
    excluded = {
        "warnings",
        "repair_events",
        "field_evidence",
        "conflicts",
        "assumptions",
        "requires_confirmation",
        "confirmation_fields",
    }
    for field, value in selected_values.items():
        if field in excluded or field in completed:
            continue
        defaulted = DEFAULT_WARNING_BY_FIELD.get(field) in warning_codes
        if defaulted:
            source = "default"
            confidence = 0.35
            mechanism = "deterministic_default"
            rationale = "Valeur de planification utilisée faute de valeur explicite."
            source_text = None
        elif field in DIRECT_TEXT_FIELDS:
            source = "user_text"
            confidence = 0.85
            mechanism = "deterministic_text_extraction"
            rationale = "Valeur extraite ou booléen déduit directement du texte utilisateur."
            source_text = None
        else:
            source = "deterministic"
            confidence = 0.7
            mechanism = "deterministic_derivation"
            rationale = "Valeur dérivée par les règles déterministes du contrat."
            source_text = None
        completed[field] = RequirementFieldEvidence(
            field=field,
            selected_value=value,
            selected_source=source,
            confidence=confidence,
            explicit=source == "user_text",
            defaulted=defaulted,
            candidates=[
                RequirementCandidateEvidence(
                    value=value,
                    source=source,
                    source_text=source_text,
                    mechanism=mechanism,
                    confidence=confidence,
                    selected=True,
                    rationale=rationale,
                )
            ],
            rationale=rationale,
        )
    return completed


def _resolve_candidates(
    field: str,
    candidates: list[RequirementCandidateEvidence],
    *,
    default: Any,
    default_rationale: str,
) -> tuple[Any, RequirementFieldEvidence, list[RequirementConflict]]:
    if not candidates:
        evidence = RequirementFieldEvidence(
            field=field,
            selected_value=default,
            selected_source="default",
            confidence=0.35,
            explicit=False,
            defaulted=True,
            candidates=[
                RequirementCandidateEvidence(
                    value=default,
                    source="default",
                    mechanism="deterministic_default",
                    confidence=0.35,
                    selected=True,
                    rationale=default_rationale,
                )
            ],
            rationale=default_rationale,
        )
        return default, evidence, []

    distinct = _distinct_values(candidates)
    selected_index = 0
    conflicts: list[RequirementConflict] = []
    resolved = False
    resolution: str | None = None
    if len(distinct) > 1:
        corrected = [
            index
            for index, candidate in enumerate(candidates)
            if candidate.rationale == "explicit_late_correction"
        ]
        if corrected:
            selected_index = corrected[-1]
            resolved = True
            resolution = "La dernière valeur est explicitement marquée comme correction."
        else:
            resolution = "Plusieurs valeurs explicites incompatibles nécessitent confirmation."
        conflicts.append(
            RequirementConflict(
                field=field,
                candidate_values=distinct,
                source_texts=[
                    candidate.source_text for candidate in candidates if candidate.source_text
                ],
                reason="Plusieurs valeurs explicites incompatibles ont été détectées.",
                resolved=resolved,
                resolution=resolution,
            )
        )

    selected = candidates[selected_index]
    selected_candidates = [
        candidate.model_copy(update={"selected": index == selected_index})
        for index, candidate in enumerate(candidates)
    ]
    unresolved = len(distinct) > 1 and not resolved
    evidence = RequirementFieldEvidence(
        field=field,
        selected_value=selected.value,
        selected_source=selected.source,
        confidence=selected.confidence if not unresolved else min(selected.confidence, 0.5),
        explicit=True,
        defaulted=False,
        candidates=selected_candidates,
        conflict=len(distinct) > 1,
        requires_confirmation=unresolved,
        rationale=resolution or "Valeur explicite extraite du texte utilisateur.",
    )
    return selected.value, evidence, conflicts


def _candidate(
    text: str,
    match: re.Match[str],
    value: Any,
    mechanism: str,
) -> RequirementCandidateEvidence:
    start, end = match.span()
    correction = _has_correction_cue(text.lower(), start)
    return RequirementCandidateEvidence(
        value=value,
        source="user_text",
        source_text=text[start:end],
        mechanism=mechanism,
        confidence=0.99 if correction else 0.96,
        span_start=start,
        span_end=end,
        rationale="explicit_late_correction" if correction else "explicit_text_match",
    )


def _tower_height_candidates(text: str, normalized: str) -> list[RequirementCandidateEvidence]:
    patterns = (
        (
            rf"(?:hauteur\s+(?:du\s+)?(?:{TOWER_TERMS})|tower\s+height)"
            rf"\s*(?:de|=|:|is)?\s*(\d+(?:[.,]\d+)?)\s*m\b",
            "named_tower_height",
            1,
        ),
        (
            rf"(\d+(?:[.,]\d+)?)\s*m\b[^\d.!?]{{0,32}}?(?:{TOWER_TERMS})",
            "height_before_tower",
            1,
        ),
        (
            rf"(?:{TOWER_TERMS})[^\d.!?]{{0,32}}?(\d+(?:[.,]\d+)?)\s*m\b",
            "tower_before_height",
            1,
        ),
        (
            r"(?:correction|finalement|valeur\s+finale|final\s+value|actually)"
            r"[^\d.!?]{0,48}?(?:hauteur|height)?\s*(\d+(?:[.,]\d+)?)\s*m\b",
            "corrected_height",
            1,
        ),
    )
    candidates: list[RequirementCandidateEvidence] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern, mechanism, group in patterns:
        for match in re.finditer(pattern, normalized):
            number_span = match.span(group)
            context = normalized[max(0, match.start() - 20) : match.end() + 10]
            if mechanism == "corrected_height" and re.search(
                r"\b(?:hba|antenn\w*|secteurs?|sectors?)\b", match.group(0)
            ):
                continue
            if mechanism == "height_before_tower" and re.search(
                r"(?:hba|antenn\w*|secteurs?|sectors?)\b[^\d]{0,20}\d", context
            ):
                continue
            if mechanism == "tower_before_height" and re.search(
                r"(?:hba|antenn\w*|secteurs?|sectors?)\b[^\d]{0,20}\d", context
            ):
                continue
            if number_span in seen_spans:
                continue
            seen_spans.add(number_span)
            value = float(match.group(group).replace(",", "."))
            candidates.append(_candidate(text, match, value, mechanism))
    return sorted(candidates, key=lambda item: item.span_start or 0)


def _sector_count_candidates(text: str, normalized: str) -> list[RequirementCandidateEvidence]:
    candidates = []
    for match in re.finditer(rf"\b({NUMBER_TOKEN})\s+sect(?:eurs?|ors?)\b", normalized):
        token = match.group(1)
        value = int(token) if token.isdigit() else NUMBER_WORDS[token]
        candidates.append(_candidate(text, match, value, "sector_count_phrase"))
    return candidates


def _install_height_candidates(text: str, normalized: str) -> list[RequirementCandidateEvidence]:
    patterns = (
        r"(?:hba|hauteur\s+(?:d['’]installation\s+)?(?:des\s+)?antennes?)"
        r"\s*(?:de|=|:|is)?\s*(\d+(?:[.,]\d+)?)\s*m\b",
        r"(?:secteurs?|sectors?)\s+(?:[aà]|at)\s*(\d+(?:[.,]\d+)?)\s*m\b",
        r"(?:antennes?|antennas?)\s+(?:[aà]|at)\s*(\d+(?:[.,]\d+)?)\s*m\b",
    )
    candidates = []
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            if match.span(1) in seen:
                continue
            seen.add(match.span(1))
            candidates.append(
                _candidate(
                    text,
                    match,
                    float(match.group(1).replace(",", ".")),
                    "antenna_install_height_phrase",
                )
            )
    return sorted(candidates, key=lambda item: item.span_start or 0)


def _azimuth_candidates(text: str, normalized: str) -> list[RequirementCandidateEvidence]:
    candidates = []
    for match in re.finditer(r"(?:azimuts?|azimuths?)\s*:?\s*", normalized):
        end = len(normalized)
        boundary = re.search(
            r"(?:[.!?\n]|\b(?:tilt|inclinaison|hba|hauteur|height|c[âa]bles?|"
            r"labels?|rru|cabinet|gps|secteurs?|sectors?|pyl[oô]ne|tower|tour|m[aâ]t|"
            r"monopole|treillis|lattice|rooftop|small[- ]cell)\b)",
            normalized[match.end() :],
        )
        if boundary:
            end = match.end() + boundary.start()
        block = normalized[match.end() : end]
        values = [float(value.replace(",", ".")) for value in re.findall(r"\d+(?:[.,]\d+)?", block)]
        if not values:
            continue
        absolute_match = _AbsoluteMatch(match.start(), end)
        candidates.append(_candidate(text, absolute_match, values, "azimuth_list"))
    return candidates


def _default_azimuths(sector_count: int) -> list[float]:
    step = 360 / sector_count
    return [round(step * index, 3) for index in range(sector_count)]


def _distinct_values(candidates: list[RequirementCandidateEvidence]) -> list[Any]:
    distinct: list[Any] = []
    keys: set[str] = set()
    for candidate in candidates:
        key = repr(candidate.value)
        if key in keys:
            continue
        keys.add(key)
        distinct.append(candidate.value)
    return distinct


def _has_correction_cue(text: str, start: int) -> bool:
    context = text[max(0, start - 80) : start]
    return any(cue in context for cue in CORRECTION_CUES)


def _mark_confirmation(
    evidence: RequirementFieldEvidence, confirmation_fields: list[str]
) -> RequirementFieldEvidence:
    if evidence.field not in confirmation_fields:
        return evidence
    return evidence.model_copy(update={"conflict": True, "requires_confirmation": True})


class _AbsoluteMatch:
    def __init__(self, start: int, end: int) -> None:
        self._span = (start, end)

    def span(self, group: int = 0) -> tuple[int, int]:
        return self._span
