import re
from collections import defaultdict
from dataclasses import dataclass

from core.contracts.document_pack import DocumentReference, ExtractedField, SourceEvidence
from core.document_pack.coordinates import coordinate_conversion_candidates
from core.document_pack.text_extractor import TextPage


@dataclass(frozen=True)
class FieldCandidate:
    field: str
    value: str | float | int | bool | list[float] | list[str]
    confidence: float
    source: SourceEvidence


def extract_field_candidates(
    document: DocumentReference,
    pages: list[TextPage],
) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    for page in pages:
        text = _compact(page.text)
        if not text:
            continue
        candidates.extend(_site_candidates(document, page, text))
        candidates.extend(_tower_candidates(document, page, text))
        candidates.extend(_radio_candidates(document, page, text))
        candidates.extend(_technical_candidates(document, page, text))
    return candidates


def consolidate_candidates(
    pack_id: str,
    documents: list[DocumentReference],
    candidates: list[FieldCandidate],
    processing_capabilities: dict[str, str] | None = None,
    processing_warnings: list[str] | None = None,
    groq_rejected_fields: list[dict] | None = None,
    llm_provider: str | None = None,
    llm_fallback_used: bool | None = None,
) -> dict:
    fields: dict[str, list[FieldCandidate]] = defaultdict(list)
    for candidate in candidates:
        fields[candidate.field].append(candidate)

    resolved = {field: _resolve_field(field, values) for field, values in fields.items()}
    coordinate_candidates = _coordinate_candidates(resolved)
    for candidate in coordinate_candidates:
        fields[candidate.field].append(candidate)
    if coordinate_candidates:
        resolved = {field: _resolve_field(field, values) for field, values in fields.items()}
    missing = _missing_fields(resolved)
    conflicts = [value for value in resolved.values() if value.status == "conflict"]
    radio_sectors = _radio_sectors(resolved)
    provenance_map = {field: value.sources for field, value in resolved.items() if value.sources}
    confirmed_count = sum(1 for value in resolved.values() if value.status == "confirmed")
    confidence = (
        round(
            sum(value.confidence for value in resolved.values()) / max(len(resolved), 1),
            3,
        )
        if resolved
        else 0.0
    )
    return {
        "pack_id": pack_id,
        "site_info": _prefix_fields(resolved, "site."),
        "coordinate_info": _prefix_fields(resolved, "coordinates."),
        "tower_spec": _prefix_fields(resolved, "tower."),
        "foundation_spec": _prefix_fields(resolved, "foundation."),
        "radio_sectors": radio_sectors,
        "antenna_inventory": [],
        "rru_inventory": _rru_inventory(resolved),
        "cabinet_inventory": _cabinet_inventory(resolved),
        "cabling_spec": _prefix_fields(resolved, "cabling."),
        "grounding_spec": _prefix_fields(resolved, "grounding."),
        "compound_spec": _prefix_fields(resolved, "compound."),
        "document_references": documents,
        "missing_fields": missing,
        "conflicts": conflicts,
        "assumptions": [],
        "confidence_summary": {
            "field_count": len(resolved),
            "confirmed_field_count": confirmed_count,
            "missing_field_count": len(missing),
            "conflict_count": len(conflicts),
            "average_confidence": confidence,
        },
        "provenance_map": provenance_map,
        "source_mode": _source_mode(candidates),
        "llm_provider": llm_provider,
        "llm_fallback_used": llm_fallback_used,
        "groq_rejected_fields": groq_rejected_fields or [],
        "processing_capabilities": processing_capabilities or {},
        "processing_warnings": processing_warnings or [],
    }


def _site_candidates(
    document: DocumentReference,
    page: TextPage,
    text: str,
) -> list[FieldCandidate]:
    patterns = {
        "site.site_code": r"\b(?:code\s*site|site\s*code|code)\s*[:\-]\s*([A-Z0-9_-]{3,})",
        "site.site_name": r"\b(?:nom\s*site|site\s*name|site)\s*[:\-]\s*([A-Z0-9 _'-]{3,})",
        "site.address": r"\b(?:adresse|address)\s*[:\-]\s*([^;\n]{5,120})",
        "site.commune": r"\b(?:commune|ville)\s*[:\-]\s*([A-ZÀ-ÿ' -]{3,80})",
        "coordinates.coordinate_system": (
            r"\b(?:systeme|système|coord(?:inate)? system|projection)\s*[:\-]\s*([^;\n]{3,80})"
        ),
        "coordinates.altitude_m": r"\b(?:altitude|ngf)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m?",
        "coordinates.x": r"\b(?:x|coordonnée\s*x|coordonnees\s*x)\s*[:=]\s*(\d+(?:[.,]\d+)?)",
        "coordinates.y": r"\b(?:y|coordonnée\s*y|coordonnees\s*y)\s*[:=]\s*(\d+(?:[.,]\d+)?)",
        "coordinates.z": r"\b(?:z|coordonnée\s*z|coordonnees\s*z)\s*[:=]\s*(\d+(?:[.,]\d+)?)",
        "coordinates.latitude": r"\b(?:latitude|lat)\s*[:=]\s*(-?\d+(?:[.,]\d+)?)",
        "coordinates.longitude": r"\b(?:longitude|lon|lng)\s*[:=]\s*(-?\d+(?:[.,]\d+)?)",
    }
    candidates = _pattern_candidates(document, page, text, patterns)
    lower = text.lower()
    for system in ["lambert ii", "lambert 93", "wgs84", "wgs 84"]:
        if system in lower:
            candidates.append(
                FieldCandidate(
                    "coordinates.coordinate_system",
                    system.upper().replace(" ", "_"),
                    0.78,
                    _source(document, page, _evidence_for(text, system)),
                )
            )
    return candidates


def _coordinate_candidates(resolved: dict[str, ExtractedField]) -> list[FieldCandidate]:
    return [
        FieldCandidate(
            field=candidate.field,
            value=candidate.value,
            confidence=candidate.confidence,
            source=candidate.source,
        )
        for candidate in coordinate_conversion_candidates(resolved)
    ]


def _tower_candidates(
    document: DocumentReference,
    page: TextPage,
    text: str,
) -> list[FieldCandidate]:
    candidates = _pattern_candidates(
        document,
        page,
        text,
        {
            "tower.tower_height_m": (
                r"\b(?:hauteur\s*(?:pylone|pylône|tour|totale)|h\s*(?:pylone|pylône)?|pylone|pylône)"
                r"\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*m"
            ),
            "tower.color_ral": r"\b(RAL\s*[0-9]{3,4})\b",
            "foundation.foundation_type": r"\b(?:fondation|massif)\s*[:\-]\s*([^;\n]{3,80})",
        },
    )
    tower_type = _tower_type(text)
    if tower_type:
        candidates.append(
            FieldCandidate(
                "tower.tower_type",
                tower_type[0],
                0.9,
                _source(document, page, tower_type[1]),
            )
        )
    for field in ["tower.has_lightning_rod", "tower.has_aviation_light", "tower.has_ladder"]:
        value, evidence = _boolean_tower_field(field, text)
        if value is not None:
            candidates.append(FieldCandidate(field, value, 0.78, _source(document, page, evidence)))
    return candidates


def _radio_candidates(
    document: DocumentReference,
    page: TextPage,
    text: str,
) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    azimuths = _extract_number_list(
        text,
        r"\b(?:azimuts?|azimuths?|az)\s*[:\-]\s*([0-9°,\s;/]+)",
        maximum=360,
    )
    if not azimuths:
        azimuths = _sector_value_list(text, ["az", "azimut", "azimuth"], maximum=360)
    if azimuths:
        candidates.append(
            FieldCandidate(
                "radio.azimuths_deg",
                azimuths,
                0.92,
                _source(document, page, _evidence_for(text, "azimut")),
            )
        )
        candidates.append(
            FieldCandidate(
                "radio.sector_count",
                len(azimuths),
                0.88,
                _source(document, page, _evidence_for(text, "azimut")),
            )
        )
    hba_values = _extract_number_list(
        text,
        r"\b(?:hba|hma|hauteur\s*bas\s*antenne|hauteur\s*antennes?)"
        r"\s*[:\-]\s*([0-9m,\s;/.,]+)",
        maximum=150,
    )
    if not hba_values:
        hba_values = _sector_value_list(text, ["hba", "hma", "hauteur"], maximum=150)
    if hba_values:
        candidates.append(
            FieldCandidate(
                "radio.hba_m",
                hba_values,
                0.9,
                _source(document, page, _evidence_for(text, "hba")),
            )
        )
    bands = sorted(
        set(re.findall(r"\b(?:NR700|NR3500|L800|L1800|L2100|L2600|5G|4G)\b", text, re.I))
    )
    if bands:
        normalized = [band.upper() for band in bands]
        candidates.append(
            FieldCandidate(
                "radio.bands",
                normalized,
                0.78,
                _source(document, page, _evidence_for(text, normalized[0])),
            )
        )
    tilt_values = _extract_number_list(
        text,
        r"\b(?:tilt|ret|mechanical tilt|tilt mecanique|tilt mécanique)\s*[:\-]\s*([0-9,\s;/.-]+)",
        maximum=30,
    )
    if tilt_values:
        candidates.append(
            FieldCandidate(
                "radio.mechanical_tilt_deg",
                tilt_values,
                0.68,
                _source(document, page, _evidence_for(text, "tilt")),
            )
        )
    for field, tokens in {
        "radio.include_rru": ["rru", "remote radio", "radio unit"],
        "cabling.include_cables": [
            "cable",
            "câble",
            "chemin de cable",
            "cheminement",
            "cdc",
        ],
    }.items():
        if any(token in text.lower() for token in tokens):
            candidates.append(
                FieldCandidate(
                    field, True, 0.72, _source(document, page, _evidence_for(text, tokens[0]))
                )
            )
    return candidates


def _technical_candidates(
    document: DocumentReference,
    page: TextPage,
    text: str,
) -> list[FieldCandidate]:
    candidates = []
    lower = text.lower()
    for field, tokens in {
        "compound.gps": ["gps"],
        "compound.power_cabinet": [
            "baie energie",
            "baie énergie",
            "coffret",
            "armoire",
            "cabinet",
            "48v",
        ],
        "grounding.grounding": ["terre", "tlti", "grounding", "mise à la terre"],
        "cabling.enedis": ["enedis"],
        "cabling.ft": ["ft", "orange", "fibre", "fo"],
    }.items():
        if any(token in lower for token in tokens):
            candidates.append(
                FieldCandidate(
                    field, True, 0.64, _source(document, page, _evidence_for(text, tokens[0]))
                )
            )
    return candidates


def _pattern_candidates(
    document: DocumentReference,
    page: TextPage,
    text: str,
    patterns: dict[str, str],
) -> list[FieldCandidate]:
    candidates = []
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        raw = match.group(1).strip(" .;")
        value = _numeric(raw) if _numeric_field(field) else raw.strip()
        candidates.append(
            FieldCandidate(field, value, 0.82, _source(document, page, match.group(0)))
        )
    return candidates


def _resolve_field(field: str, candidates: list[FieldCandidate]) -> ExtractedField:
    corrections = [
        candidate for candidate in candidates if candidate.source.document_id == "user_correction"
    ]
    if corrections:
        correction = corrections[-1]
        return ExtractedField(
            field=field,
            value=correction.value,
            status="confirmed",
            confidence=correction.confidence,
            sources=[correction.source],
            reason="Manual correction selected over extracted candidates.",
        )
    unique: list[str | float | int | bool | list[float] | list[str]] = []
    for candidate in candidates:
        if not any(_same_value(candidate.value, existing) for existing in unique):
            unique.append(candidate.value)
    sources = [candidate.source for candidate in candidates]
    if len(unique) == 1:
        confidence = round(max(candidate.confidence for candidate in candidates), 3)
        return ExtractedField(
            field=field,
            value=unique[0],
            status="confirmed",
            confidence=confidence,
            sources=sources,
        )
    return ExtractedField(
        field=field,
        value=None,
        status="conflict",
        confidence=0.2,
        sources=sources,
        values=unique,
        resolution="needs_user_review",
        reason="Multiple non-equivalent values found across the pack.",
    )


def _missing_fields(resolved: dict[str, ExtractedField]) -> list[ExtractedField]:
    required = {
        "tower.tower_type": "blocking",
        "tower.tower_height_m": "blocking",
        "radio.sector_count": "blocking",
        "radio.azimuths_deg": "blocking",
        "radio.hba_m": "blocking",
        "tower.color_ral": "optional",
        "coordinates.coordinate_system": "warning",
        "coordinates.altitude_m": "optional",
    }
    missing = []
    for field, severity in required.items():
        value = resolved.get(field)
        if value is None or value.status != "confirmed":
            missing.append(
                ExtractedField(
                    field=field,
                    status="missing",
                    confidence=0.0,
                    severity=severity,  # type: ignore[arg-type]
                    reason="No confirmed value with provenance found in document pack.",
                )
            )
    return missing


def _radio_sectors(resolved: dict[str, ExtractedField]) -> list[dict]:
    azimuth_field = resolved.get("radio.azimuths_deg")
    hba_field = resolved.get("radio.hba_m")
    mechanical_tilt_field = resolved.get("radio.mechanical_tilt_deg")
    if (
        not azimuth_field
        or azimuth_field.status != "confirmed"
        or not isinstance(azimuth_field.value, list)
    ):
        return []
    hba_values = hba_field.value if hba_field and isinstance(hba_field.value, list) else []
    sectors = []
    for index, azimuth in enumerate(azimuth_field.value):
        hba_value = (
            hba_values[index] if index < len(hba_values) else hba_values[0] if hba_values else None
        )
        hba = (
            ExtractedField(
                field=f"radio_sectors[{index}].hba_m",
                value=hba_value,
                status="confirmed",
                confidence=hba_field.confidence if hba_field else 0.0,
                sources=hba_field.sources if hba_field else [],
            )
            if hba_value is not None and hba_field
            else ExtractedField(
                field=f"radio_sectors[{index}].hba_m",
                status="missing",
                confidence=0,
                severity="blocking",
            )
        )
        mechanical_tilt = _sector_optional_numeric_field(
            mechanical_tilt_field,
            index,
            field=f"radio_sectors[{index}].mechanical_tilt_deg",
        )
        sectors.append(
            {
                "sector_id": f"S{index + 1}",
                "azimuth_deg": ExtractedField(
                    field=f"radio_sectors[{index}].azimuth_deg",
                    value=azimuth,
                    status="confirmed",
                    confidence=azimuth_field.confidence,
                    sources=azimuth_field.sources,
                ),
                "hba_m": hba,
                "bands": resolved.get("radio.bands"),
                "mechanical_tilt_deg": mechanical_tilt,
                "rru": resolved.get("radio.include_rru"),
            }
        )
    return sectors


def _sector_optional_numeric_field(
    source: ExtractedField | None,
    index: int,
    *,
    field: str,
) -> ExtractedField | None:
    if not source or source.status != "confirmed":
        return None
    if isinstance(source.value, list):
        if not source.value:
            return None
        raw_value = source.value[index] if index < len(source.value) else source.value[0]
    else:
        raw_value = source.value
    if not isinstance(raw_value, float | int):
        return None
    return ExtractedField(
        field=field,
        value=float(raw_value),
        status="confirmed",
        confidence=source.confidence,
        sources=source.sources,
    )


def _rru_inventory(resolved: dict[str, ExtractedField]) -> list[dict[str, ExtractedField]]:
    value = resolved.get("radio.include_rru")
    return [{"present": value}] if value and value.status == "confirmed" else []


def _cabinet_inventory(resolved: dict[str, ExtractedField]) -> list[dict[str, ExtractedField]]:
    value = resolved.get("compound.power_cabinet")
    return [{"present": value}] if value and value.status == "confirmed" else []


def _prefix_fields(resolved: dict[str, ExtractedField], prefix: str) -> dict[str, ExtractedField]:
    return {
        field.removeprefix(prefix): value
        for field, value in resolved.items()
        if field.startswith(prefix)
    }


def _tower_type(text: str) -> tuple[str, str] | None:
    lower = text.lower()
    if any(token in lower for token in ["pylône treillis", "pylone treillis", "lattice"]):
        return "lattice_tower", _evidence_for(text, "treillis")
    if any(token in lower for token in ["monopole", "monotube", "totem"]):
        return "monopole", _evidence_for(text, "monopole")
    if any(token in lower for token in ["rooftop", "toiture", "mat toiture", "mât rooftop"]):
        return "rooftop_mast", _evidence_for(text, "toiture")
    if any(token in lower for token in ["small cell", "support existant", "mât", "mat"]):
        return "small_cell_pole", _evidence_for(text, "small cell")
    return None


def _boolean_tower_field(field: str, text: str) -> tuple[bool | None, str]:
    tokens = {
        "tower.has_lightning_rod": ["paratonnerre"],
        "tower.has_aviation_light": ["balisage", "feu aviation"],
        "tower.has_ladder": ["echelle", "échelle"],
    }[field]
    lower = text.lower()
    for token in tokens:
        if token in lower:
            return True, _evidence_for(text, token)
    return None, ""


def _extract_number_list(text: str, pattern: str, maximum: float) -> list[float]:
    match = re.search(pattern, text, re.I)
    if not match:
        return []
    values = []
    for raw in _list_numbers(match.group(1)):
        number = float(raw)
        if 0 <= number <= maximum:
            values.append(number)
    return values


def _list_numbers(raw: str) -> list[str]:
    value = raw.replace("°", " ").replace("m", " ")
    if ";" in value or "/" in value:
        return [
            token.replace(",", ".")
            for token in re.split(r"[;\s/]+", value)
            if re.fullmatch(r"\d+(?:[,.]\d+)?", token)
        ]
    if value.count(",") > 1 or re.search(r",\s+", value):
        value = value.replace(",", " ")
        return re.findall(r"\d+(?:\.\d+)?", value)
    return [token.replace(",", ".") for token in re.findall(r"\d+(?:[,.]\d+)?", value)]


def _sector_value_list(text: str, labels: list[str], maximum: float) -> list[float]:
    values_by_sector: dict[int, float] = {}
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = (
        rf"\bS(?:ecteur)?\s*([0-9]+)\b[^;\n]{{0,80}}\b(?:{label_pattern})"
        r"\s*[:=]?\s*(\d+(?:[.,]\d+)?)"
    )
    for match in re.finditer(pattern, text, re.I):
        sector = int(match.group(1))
        value = float(match.group(2).replace(",", "."))
        if 0 <= value <= maximum:
            values_by_sector[sector] = value
    return [values_by_sector[index] for index in sorted(values_by_sector)]


def _numeric(value: str) -> float:
    return float(value.replace(",", "."))


def _numeric_field(field: str) -> bool:
    return field.endswith("_m") or field in {
        "coordinates.x",
        "coordinates.y",
        "coordinates.z",
        "coordinates.latitude",
        "coordinates.longitude",
    }


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, float | int) and isinstance(right, float | int):
        return abs(float(left) - float(right)) < 0.05
    if isinstance(left, str) and isinstance(right, str):
        left_normalized = _normalize_value(left)
        right_normalized = _normalize_value(right)
        return (
            left_normalized == right_normalized
            or left_normalized in right_normalized
            or right_normalized in left_normalized
        )
    return left == right


def _normalize_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _source(document: DocumentReference, page: TextPage, evidence: str) -> SourceEvidence:
    return SourceEvidence(
        document_id=document.document_id,
        file=document.path,
        source_type=page.source_type,  # type: ignore[arg-type]
        page=page.page,
        layer=page.layer,
        confidence=page.confidence,
        evidence=evidence.strip()[:1000],
    )


def _source_mode(candidates: list[FieldCandidate]) -> str:
    has_groq = any(candidate.source.source_type == "groq" for candidate in candidates)
    has_deterministic = any(candidate.source.source_type != "groq" for candidate in candidates)
    if has_groq and has_deterministic:
        return "mixed"
    if has_groq:
        return "groq"
    return "deterministic"


def _evidence_for(text: str, token: str) -> str:
    index = text.lower().find(token.lower())
    if index < 0:
        return text[:160]
    start = max(0, index - 80)
    end = min(len(text), index + 160)
    return text[start:end]


def _compact(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r", "\n"))
