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
        missing = [entry for entry in entries if not entry["asset_file_exists"]]
        import_ready = [entry for entry in entries if entry["asset_import_mode"] == "imported_glb"]
        fallback = [
            entry
            for entry in entries
            if entry["effective_generation_mode"] == "procedural_fallback"
        ]
        by_type: dict[str, int] = {}
        for entry in entries:
            by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
        status = "ready_for_import"
        if missing and import_ready:
            status = "partial_import_ready"
        elif missing:
            status = "manifest_only"
        return {
            "status": status,
            "asset_count": len(entries),
            "asset_count_by_type": by_type,
            "missing_file_count": len(missing),
            "real_glb_asset_count": len(import_ready),
            "import_ready_asset_count": len(import_ready),
            "procedural_fallback_count": len(fallback),
            "procedural_generation_required": bool(missing),
            "entries": entries,
            "missing_files": missing,
        }


def _entry(project_root: Path, asset: AssetManifest) -> dict:
    path = project_root / asset.file
    file_exists = path.exists()
    dimensions_checked = asset.dimensions_m is not None
    warnings = []
    if not file_exists:
        warnings.append("ASSET_FILE_MISSING")
    if asset.source == "internal_test_minimal":
        warnings.append("INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE")
    if asset.source == "internal_cleaned":
        warnings.append("INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE")
    if asset.source == "internal_project_generated":
        warnings.append("INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE")
    if asset.attribution_required:
        warnings.append("ATTRIBUTION_REQUIRED")
    if asset.source == "cc_by":
        warnings.append("CC_BY_ASSET_NOT_VENDOR_GRADE")
    asset_import_mode = "imported_glb" if file_exists else "missing_file"
    effective_generation_mode = (
        "imported_glb"
        if file_exists
        else "procedural_fallback"
        if asset.import_fallback_allowed
        else "missing_file"
    )
    return {
        "asset_id": asset.asset_id,
        "type": asset.type,
        "file": asset.file,
        "file_exists": file_exists,
        "asset_file_exists": file_exists,
        "asset_import_mode": asset_import_mode,
        "asset_import_success": None,
        "effective_generation_mode": effective_generation_mode,
        "import_fallback_allowed": asset.import_fallback_allowed,
        "source": asset.source,
        "license": asset.license,
        "attribution_required": asset.attribution_required,
        "attribution": asset.attribution,
        "original_url": asset.original_url,
        "original_author": asset.original_author,
        "normalized_by": asset.normalized_by,
        "pivot_policy": asset.pivot_policy,
        "front_axis": asset.front_axis,
        "adaptation_profile_id": asset.adaptation_profile_id,
        "status": asset.status,
        "compatible_networks": asset.compatible_networks,
        "compatible_tower_types": asset.compatible_tower_types,
        "dimensions_m": asset.dimensions_m.model_dump() if asset.dimensions_m else None,
        "asset_dimensions_checked": dimensions_checked,
        "mount_zones": [zone.model_dump() for zone in asset.mount_zones],
        "warnings": warnings,
    }
