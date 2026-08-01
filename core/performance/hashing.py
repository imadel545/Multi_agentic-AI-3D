import hashlib
import hmac
import json
import math
import secrets
from pathlib import Path
from typing import Any

from pydantic import BaseModel

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
) -> str:
    """Return a process-bound, JavaScript-safe token for a confirmed requirement.

    Untyped evidence can contain ``30.0`` which JavaScript serializes as ``30``.
    Canonicalizing integral floats keeps a genuine JSON round trip stable without
    dropping conflicts, confirmation state, assumptions, or evidence from the
    integrity boundary.
    """

    payload = {
        "confirmation_contract_version": "2.0",
        "requirements_text": requirements_text,
        "detail_level": detail_level,
        "requirements": _canonicalize_json_numbers(_model_payload(requirements)),
    }
    return hmac.new(
        _REQUIREMENTS_CONFIRMATION_SECRET,
        _encode_payload(payload),
        digestmod=hashlib.sha256,
    ).hexdigest()


def confirmation_tokens_match(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected, actual)


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
