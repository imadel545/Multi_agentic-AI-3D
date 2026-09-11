import hashlib
import hmac
import json
import math
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.contracts.requirement_analysis import RequirementAnalysisReceipt

# A confirmation is valid only for the API process that issued it. Restarting
# the local runtime intentionally requires the client to parse the request again.
_REQUIREMENTS_CONFIRMATION_SECRET = secrets.token_bytes(32)


def requirements_hash(requirements: Any) -> str:
    return _hash_payload(_model_payload(requirements, exclude={"warnings", "repair_events"}))


def requirements_confirmation_hash(
    requirements: Any,
    *,
    requirements_text: str,
    detail_level: str,
    analysis_receipt: RequirementAnalysisReceipt | None = None,
) -> str:
    """Return a process-bound, JavaScript-safe token for a confirmed requirement.

    Untyped evidence can contain ``30.0`` which JavaScript serializes as ``30``.
    Canonicalizing integral floats keeps a genuine JSON round trip stable without
    dropping conflicts, confirmation state, assumptions, or evidence from the
    integrity boundary.
    """

    payload = {
        "confirmation_contract_version": "3.0" if analysis_receipt is not None else "2.0",
        "requirements_text": requirements_text,
        "detail_level": detail_level,
        "requirements": _canonicalize_json_numbers(_model_payload(requirements)),
    }
    if analysis_receipt is not None:
        payload["analysis_receipt"] = _canonicalize_json_numbers(
            analysis_receipt.model_dump(mode="json")
        )
    return hmac.new(
        _REQUIREMENTS_CONFIRMATION_SECRET,
        _encode_payload(payload),
        digestmod=hashlib.sha256,
    ).hexdigest()


def confirmation_tokens_match(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected, actual)


def requirements_text_sha256(requirements_text: str) -> str:
    return _hash_payload(requirements_text)


def confirmed_requirements_sha256(requirements: Any) -> str:
    """Hash the complete browser-confirmed RequirementSpec payload.

    ``requirements_hash`` intentionally omits advisory warnings and repair
    history because it keys downstream semantic work.  A confirmation receipt
    must instead describe the complete reviewed payload; the HMAC remains the
    final integrity boundary for that payload.
    """

    return _hash_payload(_canonicalize_json_numbers(_model_payload(requirements)))


def issue_requirement_analysis_receipt(
    requirements: Any,
    *,
    requirements_text: str,
    detail_level: str,
    provider: str,
    extraction_provider: str,
    fallback_used: bool,
    fallback_reason: str | None,
) -> RequirementAnalysisReceipt:
    """Build one server-side analysis receipt before a user confirms input."""

    model = provider.split(":", 1)[1] if provider.startswith("groq:") else None
    return RequirementAnalysisReceipt(
        receipt_id=f"ira_{uuid.uuid4().hex}",
        issued_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        confirmed_prompt_sha256=requirements_text_sha256(requirements_text),
        confirmed_requirements_sha256=confirmed_requirements_sha256(requirements),
        detail_level=detail_level,
        provider=provider,
        model=model,
        extraction_provider=extraction_provider,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


def analysis_receipt_matches_confirmation(
    receipt: RequirementAnalysisReceipt,
    requirements: Any,
    *,
    requirements_text: str,
    detail_level: str,
) -> bool:
    """Check that an opaque returned receipt still describes this confirmation."""

    return (
        receipt.confirmed_prompt_sha256 == requirements_text_sha256(requirements_text)
        and receipt.confirmed_requirements_sha256 == confirmed_requirements_sha256(requirements)
        and receipt.detail_level == detail_level
    )


def scene_spec_hash(scene: Any) -> str:
    return _hash_payload(_model_payload(scene))


def asset_manifest_hash(manifests_dir: Path) -> str:
    entries = []
    for path in sorted(manifests_dir.glob("*.json")):
        entries.append(
            {
                "filename": path.name,
                "content": json.loads(path.read_text(encoding="utf-8")),
            }
        )
    return _hash_payload(entries)


def qualified_asset_library_hash(catalog_path: Path) -> str:
    if not catalog_path.is_file():
        return _hash_payload([])
    qualified = []
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if (
            payload.get("generation_eligible") is True
            and payload.get("qualification_status") == "validated"
        ):
            qualified.append(payload)
    return _hash_payload(qualified)


def knowledge_index_hash(project_root: Path) -> str:
    entries = []
    root = project_root / "data" / "knowledge"
    for path in sorted(root.glob("*.md")):
        entries.append(
            {
                "path": str(path.relative_to(project_root)),
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return _hash_payload(entries)


def rag_query_hash(
    query: str,
    limit: int,
    collection: str | None,
    filters: dict | None,
    embedding_provider_name: str,
    index_hash: str,
) -> str:
    return _hash_payload(
        {
            "query": query,
            "limit": limit,
            "collection": collection,
            "filters": filters or {},
            "embedding_provider": embedding_provider_name,
            "knowledge_index_hash": index_hash,
        }
    )


def _model_payload(value: Any, exclude: set[str] | None = None) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude=exclude or set())
    return value


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_encode_payload(payload)).hexdigest()


def _encode_payload(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonicalize_json_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_json_numbers(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("confirmation payload contains a non-finite number")
        if value.is_integer():
            return int(value)
    return value
