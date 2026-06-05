from pathlib import Path

from core.services.asset_inventory import AssetInventoryService
from core.services.asset_registry import AssetRegistry


def test_asset_inventory_reports_manifest_only_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    inventory = AssetInventoryService(Path.cwd(), registry).inspect()

    assert inventory["asset_count"] == 8
    assert inventory["status"] == "manifest_only"
    assert inventory["missing_file_count"] == 8
    assert inventory["real_glb_asset_count"] == 0
    assert inventory["procedural_generation_required"] is True
    assert all(not entry["file_exists"] for entry in inventory["entries"])
