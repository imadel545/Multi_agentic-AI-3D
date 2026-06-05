from pathlib import Path

from core.contracts.assets import AssetManifest
from core.services.asset_registry import AssetRegistry


class AssetInventoryService:
    def __init__(self, project_root: Path, registry: AssetRegistry) -> None:
        self.project_root = project_root
        self.registry = registry

    def inspect(self) -> dict:
        assets = self.registry.list_assets()
        entries = [_entry(self.project_root, asset) for asset in assets]
        missing = [entry for entry in entries if not entry["file_exists"]]
        by_type: dict[str, int] = {}
        for entry in entries:
            by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
        return {
            "status": "manifest_only" if missing else "ready_for_import",
            "asset_count": len(entries),
            "asset_count_by_type": by_type,
            "missing_file_count": len(missing),
            "real_glb_asset_count": len(entries) - len(missing),
            "procedural_generation_required": bool(missing),
            "entries": entries,
            "missing_files": missing,
        }


def _entry(project_root: Path, asset: AssetManifest) -> dict:
    path = project_root / asset.file
    return {
        "asset_id": asset.asset_id,
        "type": asset.type,
        "file": asset.file,
        "file_exists": path.exists(),
        "status": asset.status,
        "compatible_networks": asset.compatible_networks,
        "compatible_tower_types": asset.compatible_tower_types,
        "dimensions_m": asset.dimensions_m.model_dump() if asset.dimensions_m else None,
    }
