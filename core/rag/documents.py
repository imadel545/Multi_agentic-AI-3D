import json
from pathlib import Path

from core.rag.models import RagDocument

KNOWLEDGE_COLLECTIONS = {
    "telecom_rules.md": "telecom_rules",
    "scene_templates.md": "scene_templates",
    "validation_cases.md": "validation_cases",
    "design_patterns.md": "design_patterns",
    "blender_generation_guides.md": "blender_generation_guides",
}


def load_rag_documents(project_root: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    documents.extend(_load_knowledge_documents(project_root / "data" / "knowledge"))
    documents.extend(_load_asset_manifest_documents(project_root / "assets" / "manifests"))
    documents.extend(_load_project_docs(project_root / "docs"))
    return documents


def _load_knowledge_documents(knowledge_dir: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for filename, collection in KNOWLEDGE_COLLECTIONS.items():
        path = knowledge_dir / filename
        if not path.exists():
            continue
        documents.append(
            RagDocument(
                doc_id=f"knowledge:{path.stem}",
                collection=collection,
                text=path.read_text(encoding="utf-8"),
                payload={
                    "type": "knowledge_doc",
                    "doc_type": "knowledge_doc",
                    "source_path": str(path),
                    "filename": filename,
                    "network_type": _infer_network_type(path.read_text(encoding="utf-8")),
                    "tower_type": _infer_tower_type(path.read_text(encoding="utf-8")),
                },
            )
        )
    return documents


def _load_asset_manifest_documents(manifests_dir: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for path in sorted(manifests_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        asset_text = _asset_text(payload)
        documents.append(
            RagDocument(
                doc_id=f"asset:{payload['asset_id']}",
                collection="asset_manifests",
                text=asset_text,
                payload={
                    "type": "asset_manifest",
                    "doc_type": "asset_manifest",
                    "source_path": str(path),
                    "asset_id": payload["asset_id"],
                    "asset_type": payload["type"],
                    "status": payload.get("status", "unknown"),
                    "version": payload.get("version", "unknown"),
                    "network_type": payload.get("compatible_networks", []),
                    "tower_type": payload.get("compatible_tower_types", []),
                    "compatible_networks": payload.get("compatible_networks", []),
                    "compatible_tower_types": payload.get("compatible_tower_types", []),
                },
            )
        )
    return documents


def _load_project_docs(docs_dir: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for path in sorted(docs_dir.glob("*.md")):
        documents.append(
            RagDocument(
                doc_id=f"doc:{path.stem}",
                collection="design_patterns",
                text=path.read_text(encoding="utf-8"),
                payload={
                    "type": "project_doc",
                    "doc_type": "project_doc",
                    "source_path": str(path),
                    "filename": path.name,
                    "network_type": _infer_network_type(path.read_text(encoding="utf-8")),
                    "tower_type": _infer_tower_type(path.read_text(encoding="utf-8")),
                },
            )
        )
    return documents


def _asset_text(payload: dict) -> str:
    return "\n".join(
        [
            f"asset_id: {payload['asset_id']}",
            f"type: {payload['type']}",
            f"file: {payload['file']}",
            f"height_m: {payload.get('height_m')}",
            f"compatible_networks: {', '.join(payload.get('compatible_networks', []))}",
            f"compatible_tower_types: {', '.join(payload.get('compatible_tower_types', []))}",
            f"status: {payload.get('status', 'unknown')}",
            f"version: {payload.get('version', 'unknown')}",
        ]
    )


def _infer_network_type(text: str) -> str | None:
    lowered = text.lower()
    if "5g" in lowered:
        return "5G"
    if "4g" in lowered:
        return "4G"
    if "microwave" in lowered or "mw" in lowered:
        return "MW"
    return None


def _infer_tower_type(text: str) -> str | None:
    lowered = text.lower()
    if "lattice" in lowered or "treillis" in lowered:
        return "lattice_tower"
    if "rooftop" in lowered:
        return "rooftop_mast"
    if "small_cell" in lowered or "small-cell" in lowered:
        return "small_cell_pole"
    if "monopole" in lowered:
        return "monopole"
    return None
