import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from core.contracts.document_pack import DocumentReference, SourceEvidence
from core.document_pack.extractor import FieldCandidate
from core.document_pack.text_extractor import TextPage

MAX_GROQ_CHUNKS = 12
MAX_CHUNK_CHARS = 2500
MAX_TOTAL_CHARS = 20000

ALLOWED_FIELD_PREFIXES = (
    "site.",
    "coordinates.",
    "tower.",
    "foundation.",
    "radio.",
    "cabling.",
    "grounding.",
    "compound.",
)

BOOLEAN_EVIDENCE_TERMS: dict[str, tuple[str, ...]] = {
    "radio.include_rru": ("rru", "radio"),
    "cabling.include_cables": ("câble", "cable"),
    "compound.gps": ("gps", "gnss"),
    "compound.power_cabinet": ("cabinet", "armoire", "alimentation"),
    "tower.has_aviation_light": ("balisage", "aviation"),
    "tower.has_ladder": ("échelle", "echelle", "ladder"),
    "tower.has_lightning_rod": ("paratonnerre", "lightning rod"),
    "grounding.grounding": ("terre", "grounding", "mise à la terre"),
}

DOCUMENT_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string"},
                    "value": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "number"},
                            {"type": "boolean"},
                            {"type": "array", "items": {"type": ["string", "number"]}},
                        ]
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "document_id": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "evidence": {"type": "string"},
                },
                "required": ["field", "value", "confidence", "document_id", "page", "evidence"],
            },
        },
    },
    "required": ["fields"],
}


class GroqDocumentProvider(Protocol):
    model: str

    def _post_raw(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DocumentTextChunk:
    document_id: str
    file: str
    page: int | None
    source_type: str
    layer: str | None
    text: str


@dataclass(frozen=True)
class GroqDocumentExtractionResult:
    candidates: list[FieldCandidate]
    rejected_fields: list[dict]
    provider: str | None
    fallback_used: bool
    warnings: list[str]
    chunks: list[DocumentTextChunk]


class GroqDocumentExtractor:
    def __init__(
        self,
        provider: GroqDocumentProvider | None,
        *,
        provider_name: str | None,
        enabled: bool,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.enabled = enabled and provider is not None

    def extract(
        self,
        documents: list[DocumentReference],
        pages_by_document: dict[str, list[TextPage]],
    ) -> GroqDocumentExtractionResult:
        chunks = select_bounded_chunks(documents, pages_by_document)
        if not self.enabled or self.provider is None:
            return GroqDocumentExtractionResult(
                candidates=[],
                rejected_fields=[],
                provider=self.provider_name,
                fallback_used=True,
                warnings=["Groq document extraction disabled or not configured."],
                chunks=chunks,
            )
        if not chunks:
            return GroqDocumentExtractionResult(
                candidates=[],
                rejected_fields=[],
                provider=self.provider_name,
                fallback_used=False,
                warnings=["No bounded document chunks selected for Groq extraction."],
                chunks=[],
            )
        messages = _messages(chunks)
        payload = {
            "model": self.provider.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "DocumentPackFields",
                    "schema": DOCUMENT_FIELD_SCHEMA,
                    "strict": True,
                },
            },
        }
        json_object_fallback_used = False
        try:
            raw = self.provider._post_raw(payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                return _groq_failed(
                    chunks,
                    self.provider_name,
                    f"Groq document extraction failed: HTTP {exc.response.status_code}.",
                )
            try:
                json_object_fallback_used = True
                raw = self.provider._post_raw(
                    {
                        "model": self.provider.model,
                        "temperature": 0,
                        "messages": messages
                        + [
                            {
                                "role": "system",
                                "content": (
                                    "Retry in JSON Object Mode. Return exactly an object with a "
                                    "fields array. Keep evidence copied from chunks."
                                ),
                            }
                        ],
                        "response_format": {"type": "json_object"},
                    }
                )
            except Exception as retry_exc:
                return _groq_failed(
                    chunks,
                    self.provider_name,
                    (
                        "Groq document extraction failed after JSON Object retry: "
                        f"{type(retry_exc).__name__}."
                    ),
                )
        except Exception as exc:
            return _groq_failed(
                chunks,
                self.provider_name,
                f"Groq document extraction failed: {type(exc).__name__}.",
            )
        candidates, rejected = _validate_raw_fields(raw, chunks)
        return GroqDocumentExtractionResult(
            candidates=candidates,
            rejected_fields=rejected,
            provider=self.provider_name,
            fallback_used=json_object_fallback_used,
            warnings=(
                [
                    "Groq strict JSON Schema generation was rejected; a validated JSON "
                    "Object fallback was used."
                ]
                if json_object_fallback_used
                else []
            ),
            chunks=chunks,
        )


def select_bounded_chunks(
    documents: list[DocumentReference],
    pages_by_document: dict[str, list[TextPage]],
) -> list[DocumentTextChunk]:
    documents_by_id = {document.document_id: document for document in documents}
    chunks: list[DocumentTextChunk] = []
    total_chars = 0
    for document in documents:
        if document.priority not in {"high", "medium"} or document.duplicate_of:
            continue
        for page in pages_by_document.get(document.document_id, []):
            if page.source_type not in {"text", "table", "ocr", "cad"}:
                continue
            text = page.text.strip()
            if not text:
                continue
            chunk_text = text[:MAX_CHUNK_CHARS]
            if total_chars + len(chunk_text) > MAX_TOTAL_CHARS:
                return chunks
            chunks.append(
                DocumentTextChunk(
                    document_id=document.document_id,
                    file=document.path,
                    page=page.page,
                    source_type=page.source_type,
                    layer=page.layer,
                    text=chunk_text,
                )
            )
            total_chars += len(chunk_text)
            if len(chunks) >= MAX_GROQ_CHUNKS:
                return chunks
    return [
        chunk
        for chunk in chunks
        if chunk.document_id in documents_by_id
        and documents_by_id[chunk.document_id].used_for_design
    ]


def _messages(chunks: list[DocumentTextChunk]) -> list[dict[str, str]]:
    chunk_text = "\n\n".join(
        [
            (
                f"[chunk {index}] document_id={chunk.document_id} "
                f"page={chunk.page} source_type={chunk.source_type} layer={chunk.layer}\n"
                f"{chunk.text}"
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
    )
    return [
        {
            "role": "system",
            "content": (
                "Extract only telecom design fields that are explicitly evidenced in the chunks. "
                "Use fields such as tower.tower_type, tower.tower_height_m, radio.azimuths_deg, "
                "radio.hba_m, radio.sector_count, radio.bands, radio.include_rru, "
                "cabling.include_cables, compound.gps, compound.power_cabinet. "
                "When evidence exists, extract tower.tower_type, tower.tower_height_m, "
                "radio.azimuths_deg, radio.hba_m, and radio.sector_count. "
                "Use field names exactly as listed. "
                "Do not invent values. Every field must include document_id, page, confidence, "
                "and a short evidence quote copied from the chunk. Return JSON only."
            ),
        },
        {"role": "user", "content": chunk_text},
    ]


def _validate_raw_fields(
    raw: dict[str, Any],
    chunks: list[DocumentTextChunk],
) -> tuple[list[FieldCandidate], list[dict]]:
    chunks_by_document = {chunk.document_id: chunk for chunk in chunks}
    candidates: list[FieldCandidate] = []
    rejected: list[dict] = []
    for field in raw.get("fields", []):
        reason = _field_rejection_reason(field, chunks_by_document)
        if reason:
            rejected.append({"field": field.get("field"), "reason": reason, "raw": field})
            continue
        chunk = chunks_by_document[str(field["document_id"])]
        evidence = str(field["evidence"]).strip()
        normalized_value = _normalize_groq_value(str(field["field"]), field["value"], evidence)
        candidates.append(
            FieldCandidate(
                field=str(field["field"]),
                value=normalized_value,
                confidence=float(field["confidence"]),
                source=SourceEvidence(
                    document_id=chunk.document_id,
                    file=chunk.file,
                    source_type="groq",
                    page=field.get("page"),
                    layer=chunk.layer,
                    confidence=float(field["confidence"]),
                    evidence=evidence[:1000],
                ),
            )
        )
    return candidates, rejected


def _field_rejection_reason(
    field: dict[str, Any],
    chunks_by_document: dict[str, DocumentTextChunk],
) -> str | None:
    field_name = str(field.get("field", ""))
    if not field_name.startswith(ALLOWED_FIELD_PREFIXES):
        return "unsupported_field"
    document_id = str(field.get("document_id", ""))
    if document_id not in chunks_by_document:
        return "invalid_document_id"
    evidence = str(field.get("evidence", "")).strip()
    if not evidence:
        return "missing_evidence"
    if evidence.lower() not in chunks_by_document[document_id].text.lower():
        return "evidence_not_found_in_chunk"
    confidence = field.get("confidence")
    if not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1:
        return "invalid_confidence"
    normalized_value = _normalize_groq_value(field_name, field.get("value"), evidence)
    if field_name in {"radio.azimuths_deg", "radio.hba_m"}:
        if not _valid_number_list_value(field_name, normalized_value):
            return "invalid_value_shape"
    if not _value_is_supported_by_evidence(field_name, normalized_value, evidence):
        return "value_not_supported_by_evidence"
    return None


def _normalize_groq_value(field: str, value: Any, evidence: str = "") -> Any:
    if field == "tower.tower_type" and isinstance(value, str):
        normalized = value.lower().replace("ô", "o").replace("é", "e").replace("è", "e")
        if "treillis" in normalized or "lattice" in normalized:
            return "lattice_tower"
        if "monopole" in normalized or "monotube" in normalized:
            return "monopole"
        if "rooftop" in normalized or "toiture" in normalized:
            return "rooftop_mast"
        if "small cell" in normalized:
            return "small_cell_pole"
    if field in {"radio.azimuths_deg", "radio.hba_m"}:
        numbers = _number_list(value)
        if not _valid_number_list_value(field, numbers) and evidence:
            numbers = _number_list(evidence)
        return numbers
    if field == "radio.bands" and isinstance(value, str):
        return _band_list(value) or _band_list(evidence) or value
    if field == "radio.sector_count" and isinstance(value, float | int | str):
        try:
            return int(float(str(value).replace(",", ".")))
        except ValueError:
            return value
    if field.endswith("_m") and isinstance(value, str):
        try:
            return float(value.replace(",", ".").replace("m", "").strip())
        except ValueError:
            return value
    return value


def _value_is_supported_by_evidence(field: str, value: Any, evidence: str) -> bool:
    if field in {"radio.azimuths_deg", "radio.hba_m"}:
        expected = _number_list(evidence)
        return _same_numbers(value, expected)
    if field == "tower.tower_type":
        evidence_value = _normalize_groq_value(field, evidence)
        return evidence_value == value
    if (
        field == "radio.sector_count"
        or field.endswith(("_m", "_deg"))
        or field
        in {
            "coordinates.latitude",
            "coordinates.longitude",
            "coordinates.x",
            "coordinates.y",
            "coordinates.z",
        }
    ):
        if isinstance(value, bool) or not isinstance(value, int | float):
            return False
        numbers = _number_list(evidence)
        if not isinstance(numbers, list):
            return False
        return any(abs(float(number) - float(value)) <= 0.01 for number in numbers)
    if isinstance(value, bool) and field in BOOLEAN_EVIDENCE_TERMS:
        expected_boolean = _boolean_from_evidence(field, evidence)
        return expected_boolean is not None and value is expected_boolean
    return True


def _same_numbers(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    try:
        return all(abs(float(a) - float(b)) <= 0.01 for a, b in zip(left, right, strict=True))
    except (TypeError, ValueError):
        return False


def _boolean_from_evidence(field: str, evidence: str) -> bool | None:
    terms = BOOLEAN_EVIDENCE_TERMS.get(field)
    if not terms:
        return None
    lowered = evidence.lower()
    if not any(term in lowered for term in terms):
        return None
    negated = any(
        marker in lowered
        for marker in ("sans ", "aucun", "absence", "non prévu", "non prevu", "no ")
    )
    return not negated


def _number_list(value: Any) -> Any:
    if isinstance(value, list):
        numbers = []
        for item in value:
            try:
                numbers.append(float(str(item).replace(",", ".").replace("m", "")))
            except ValueError:
                return value
        return numbers
    if isinstance(value, str):
        numbers = [float(raw) for raw in _list_numbers(value)]
        return numbers or value
    return value


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


def _valid_number_list_value(field: str, value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    try:
        numbers = [float(item) for item in value]
    except (TypeError, ValueError):
        return False
    maximum = 360 if field == "radio.azimuths_deg" else 150
    if any(number < 0 or number > maximum for number in numbers):
        return False
    if field == "radio.azimuths_deg" and len(numbers) > 6:
        return False
    if field == "radio.hba_m" and len(numbers) > 6:
        return False
    return True


def _band_list(value: str) -> list[str]:
    bands = set()
    for raw in re.findall(r"\b(?:NR\d{3,4}|L\d{3,4}|[45]G|LTE|MW)\b", value.upper()):
        bands.add(raw)
    return sorted(bands)


def _groq_failed(
    chunks: list[DocumentTextChunk],
    provider_name: str | None,
    warning: str,
) -> GroqDocumentExtractionResult:
    return GroqDocumentExtractionResult(
        candidates=[],
        rejected_fields=[],
        provider=provider_name,
        fallback_used=True,
        warnings=[warning],
        chunks=chunks,
    )
