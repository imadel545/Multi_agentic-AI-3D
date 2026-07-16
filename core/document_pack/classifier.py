import hashlib
import re
from pathlib import Path

from core.contracts.document_pack import (
    CadStatus,
    DocumentCategory,
    DocumentPriority,
    DocumentPurpose,
    DocumentReference,
    Extractability,
)

HIGH_PRIORITY = {
    "apd_plan",
    "antenna_plan",
    "elevation_plan",
    "site_plan",
    "mass_plan",
    "technical_sheet",
    "equipment_list",
}
MEDIUM_PRIORITY = {"grounding_plan", "cable_route_plan", "adduction_plan", "cad_dwg", "cad_dxf"}


def classify_document(
    path: str, content: bytes, duplicate_of: str | None = None
) -> DocumentReference:
    filename = Path(path).name
    extension = Path(filename).suffix.lower().lstrip(".") or "none"
    preview = _text_preview(content, extension)
    normalized = _normalize(f"{path}\n{preview}")
    category, reason = _category_for(
        normalized,
        extension,
        semantic_text_available=bool(preview.strip()),
    )
    extractability = _extractability_for(extension)
    priority = _priority_for(category, duplicate_of)
    purpose = _purpose_for(category, extractability, duplicate_of)
    relevance_score = _relevance_for(priority, category, duplicate_of)
    confidence = _confidence_for(category, extractability, normalized, duplicate_of)
    cad_status = _cad_status_for(extension)
    used_for_design = priority in {"high", "medium"} and not duplicate_of
    why_used_or_ignored = _why_used_or_ignored(category, purpose, duplicate_of)
    return DocumentReference(
        document_id=_document_id(path, content),
        path=path,
        filename=filename,
        extension=extension,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        category=category,
        document_type=category,
        relevance_score=relevance_score,
        confidence=confidence,
        reason=reason if not duplicate_of else f"Duplicate of {duplicate_of}; {reason}",
        extractability=extractability,
        priority=priority,
        purpose=purpose,
        used_for_design=used_for_design,
        why_used_or_ignored=why_used_or_ignored,
        cad_status=cad_status,
        duplicate_of=duplicate_of,
    )


def reclassify_document(
    document: DocumentReference,
    extracted_text: str,
) -> DocumentReference:
    """Re-evaluate relevance after PDF/OCR/CAD tools produced readable text."""

    normalized = _normalize(f"{document.path}\n{extracted_text[:50000]}")
    category, reason = _category_for(
        normalized,
        document.extension,
        semantic_text_available=bool(extracted_text.strip()),
    )
    priority = _priority_for(category, document.duplicate_of)
    purpose = _purpose_for(category, document.extractability, document.duplicate_of)
    return document.model_copy(
        update={
            "category": category,
            "document_type": category,
            "relevance_score": _relevance_for(priority, category, document.duplicate_of),
            "confidence": _confidence_for(
                category,
                document.extractability,
                normalized,
                document.duplicate_of,
            ),
            "reason": reason,
            "priority": priority,
            "purpose": purpose,
            "used_for_design": priority in {"high", "medium"} and not document.duplicate_of,
            "why_used_or_ignored": _why_used_or_ignored(
                category,
                purpose,
                document.duplicate_of,
            ),
        }
    )


def _document_id(path: str, content: bytes) -> str:
    digest = hashlib.sha256(path.encode("utf-8") + b"\0" + content[:4096]).hexdigest()
    return f"doc_{digest[:12]}"


def _normalize(value: str) -> str:
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "à": "a",
        "â": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "û": "u",
        "ù": "u",
        "ç": "c",
    }
    lowered = value.lower()
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    return lowered


def _text_preview(content: bytes, extension: str) -> str:
    if extension not in {"txt", "md", "csv", "json"}:
        return ""
    try:
        decoded = content[:12000].decode("utf-8")
    except UnicodeDecodeError:
        decoded = content[:12000].decode("latin-1", errors="ignore")
    return decoded


def _category_for(
    text: str,
    extension: str,
    *,
    semantic_text_available: bool,
) -> tuple[DocumentCategory, str]:
    if extension == "dwg":
        return "cad_dwg", "DWG CAD candidate recorded for local conversion strategy."
    if extension == "dxf":
        return "cad_dxf", "DXF CAD candidate can be parsed by a future ezdxf adapter."
    if extension in {"jpg", "jpeg", "png", "heic", "webp"} and not semantic_text_available:
        if "photomontage" in text:
            return "photomontage", "Photomontage is visual context for frontend review."
        return "photo", "Photo/image is visual reference, not primary numeric evidence."
    if extension in {"psd", "ai"}:
        return "psd_or_design_source", "Design source file is recorded but unsupported."
    if any(token in text for token in ["bail", "lease", "convention", "contrat"]):
        return "lease_or_bail", "Administrative lease/reference document."
    if any(token in text for token in ["administratif", "cerfa", "autorisation"]):
        return "administrative", "Administrative document with low direct 3D relevance."
    if any(
        token in text
        for token in [
            "antenne",
            "antennes",
            "azimut",
            "azimuth",
            "hba",
            "hma",
            "rru",
            "ret",
        ]
    ) or (semantic_text_available and re.search(r"\baz\s*[:=\-]", text)):
        return "antenna_plan", "Antenna/radio terms indicate high-value extraction."
    if any(token in text for token in ["elevation", "facade", "coupe", "hauteur totale"]):
        return "elevation_plan", "Elevation/cut plan can contain heights."
    if any(token in text for token in ["plan masse", "masse", "implantation", "zone technique"]):
        return "mass_plan", "Mass/site plan can contain compound and tower location."
    if any(token in text for token in ["terre", "tlti", "grounding"]):
        return "grounding_plan", "Grounding plan is useful technical context."
    if any(token in text for token in ["cable", "cheminement", "chemin de cable", "cdc"]):
        return "cable_route_plan", "Cable routing plan can affect visible cabling."
    if any(token in text for token in ["adduction", "enedis", "ft", "fibre", "fo", "48v"]):
        return "adduction_plan", "Adduction/power/fiber plan is useful context."
    if any(
        token in text
        for token in ["equipement", "equipment", "materiel", "baie", "nomenclature", "fiche"]
    ):
        return "equipment_list", "Equipment list can provide antenna/RRU/cabinet inventory."
    if "apd" in text:
        return "apd_plan", "APD document can contain consolidated site design values."
    if any(
        token in text
        for token in [
            "fiche technique",
            "technical sheet",
            "datasheet",
            "specification pylone",
            "spécification pylône",
        ]
    ):
        return "technical_sheet", "Technical specification contains direct design evidence."
    if extension in {"jpg", "jpeg", "png", "heic", "webp"}:
        return "photo", "Image OCR contains no strong telecom design signal."
    if extension in {"txt", "md", "csv", "pdf"}:
        return "unknown", "Text is extractable but has no direct telecom design signal."
    return "unknown", "No strong telecom design signal detected."


def _extractability_for(extension: str) -> Extractability:
    if extension in {"txt", "md", "csv", "json"}:
        return "text"
    if extension == "pdf":
        return "text"
    if extension in {"jpg", "jpeg", "png", "heic", "webp"}:
        return "image"
    if extension in {"dwg", "dxf"}:
        return "cad"
    if extension in {"psd", "ai", "zip"}:
        return "binary"
    return "unsupported"


def _priority_for(category: DocumentCategory, duplicate_of: str | None) -> DocumentPriority:
    if duplicate_of:
        return "ignore"
    if category in HIGH_PRIORITY:
        return "high"
    if category in MEDIUM_PRIORITY:
        return "medium"
    if category in {"photo", "photomontage", "administrative", "lease_or_bail"}:
        return "low"
    return "ignore"


def _purpose_for(
    category: DocumentCategory,
    extractability: Extractability,
    duplicate_of: str | None,
) -> DocumentPurpose:
    if duplicate_of:
        return "irrelevant"
    if category in HIGH_PRIORITY:
        return "needed_for_design"
    if category in {"grounding_plan", "cable_route_plan", "adduction_plan", "cad_dwg", "cad_dxf"}:
        return "useful_context"
    if category in {"photo", "photomontage"}:
        return "visual_reference"
    if category in {"administrative", "lease_or_bail"}:
        return "administrative_reference"
    if extractability in {"binary", "unsupported", "cad"}:
        return "unsupported_but_recorded"
    return "irrelevant"


def _relevance_for(
    priority: DocumentPriority, category: DocumentCategory, duplicate_of: str | None
) -> float:
    if duplicate_of:
        return 0.0
    if priority == "high":
        return 0.9 if category in {"antenna_plan", "apd_plan"} else 0.82
    if priority == "medium":
        return 0.62
    if priority == "low":
        return 0.28
    return 0.05


def _confidence_for(
    category: DocumentCategory,
    extractability: Extractability,
    text: str,
    duplicate_of: str | None,
) -> float:
    if duplicate_of:
        return 0.99
    score = 0.45
    if category not in {"unknown", "irrelevant"}:
        score += 0.2
    if extractability in {"text", "cad", "image"}:
        score += 0.1
    signals = ["azimut", "azimuth", "hba", "pylone", "pylône", "rru", "antenne", "enedis"]
    score += min(0.2, 0.04 * sum(1 for signal in signals if signal in text))
    return round(min(score, 0.95), 3)


def _why_used_or_ignored(
    category: DocumentCategory, purpose: DocumentPurpose, duplicate_of: str | None
) -> str:
    if duplicate_of:
        return "Ignored for extraction because the file content duplicates another document."
    if purpose == "needed_for_design":
        return f"Used for design because {category} usually contains critical 3D/radio values."
    if purpose == "useful_context":
        return f"Recorded as useful context because {category} can affect technical details."
    if purpose == "visual_reference":
        return "Recorded for visual context; not used as numeric evidence in MVP."
    if purpose == "administrative_reference":
        return "Recorded as administrative reference; not used for 3D geometry."
    if purpose == "unsupported_but_recorded":
        return "Recorded but not parsed by the local MVP extractor."
    return "Ignored because no direct telecom design signal was detected."


def _cad_status_for(extension: str) -> CadStatus:
    if extension == "dxf":
        return "inventory_only"
    if extension == "dwg":
        return "unsupported"
    return "not_cad"
