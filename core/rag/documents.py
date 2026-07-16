import json
import re
from pathlib import Path

from core.rag.models import RagDocument

KNOWLEDGE_COLLECTIONS = {
    "telecom_rules.md": "telecom_rules",
    "scene_templates.md": "scene_templates",
    "validation_cases.md": "validation_cases",
    "design_patterns.md": "design_patterns",
    "blender_generation_guides.md": "blender_generation_guides",
}

PLANNING_HINT_KEYS = {
    "antenna_install_height_m",
    "beamwidth_deg",
    "include_cables",
    "include_sector_beams",
    "include_labels",
    "include_power_cabinet",
    "include_gps_antenna",
    "include_rru",
    "foundation_type",
    "mechanical_tilt_deg",
    "electrical_tilt_deg",
}
PLANNING_HINT_ALIASES = {
    "include_beams": "include_sector_beams",
    "hba_m": "antenna_install_height_m",
    "antenna_hba_m": "antenna_install_height_m",
    "sector_beamwidth_deg": "beamwidth_deg",
    "include_gps": "include_gps_antenna",
    "include_cabinet": "include_power_cabinet",
    "include_power_box": "include_power_cabinet",
    "include_foundation": "foundation_type",
    "mechanical_tilt": "mechanical_tilt_deg",
    "electrical_tilt": "electrical_tilt_deg",
}


def load_rag_documents(project_root: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    documents.extend(_load_knowledge_documents(project_root, project_root / "data" / "knowledge"))
    documents.extend(
        _load_asset_manifest_documents(project_root, project_root / "assets" / "manifests")
    )
    return documents


def _load_knowledge_documents(project_root: Path, knowledge_dir: Path) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for filename, collection in KNOWLEDGE_COLLECTIONS.items():
        path = knowledge_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for index, chunk in enumerate(_markdown_chunks(text), start=1):
            documents.append(
                RagDocument(
                    doc_id=f"knowledge:{path.stem}:{index}",
                    collection=collection,
                    text=chunk,
                    payload={
                        "type": "knowledge_doc",
                        "doc_type": "knowledge_doc",
                        "source_path": _relative_source(project_root, path),
                        "filename": filename,
                        "chunk_index": index,
                        "network_type": _infer_network_type(chunk),
                        "tower_type": _infer_tower_type(chunk),
                        "planning_hints": _extract_planning_hints(chunk),
                    },
                )
            )
    return documents


def _load_asset_manifest_documents(project_root: Path, manifests_dir: Path) -> list[RagDocument]:
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
                    "source_path": _relative_source(project_root, path),
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


def _markdown_chunks(text: str) -> list[str]:
    """Split markdown by headings to avoid indexing giant, noisy documents."""
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and current:
            chunk = "\n".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = [line]
            continue
        current.append(line)
    chunk = "\n".join(current).strip()
    if chunk:
        chunks.append(chunk)
    return chunks or [text]


def _extract_planning_hints(text: str) -> dict:
    hints: dict[str, object] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*[-*]\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)\s*$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        key = PLANNING_HINT_ALIASES.get(key, key)
        if key not in PLANNING_HINT_KEYS:
            continue
        hints[key] = _parse_hint_value(raw_value)
    return hints


def _parse_hint_value(value: str) -> object:
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "oui"}:
        return True
    if lowered in {"false", "no", "non"}:
        return False
    numeric = lowered.replace(",", ".")
    try:
        return float(numeric)
    except ValueError:
        return value.strip()


def _relative_source(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return path.name


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
