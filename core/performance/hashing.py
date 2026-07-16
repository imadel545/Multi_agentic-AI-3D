import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def requirements_hash(requirements: Any) -> str:
    return _hash_payload(_model_payload(requirements, exclude={"warnings", "repair_events"}))


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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
