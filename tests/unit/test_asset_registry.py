from pathlib import Path

from core.services.asset_registry import AssetRegistry


def test_registry_loads_and_selects_5g_assets() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    tower = registry.select_tower("lattice_tower", "5G", 30)
    antenna = registry.select_asset("antenna", "5G", "lattice_tower")
    radio = registry.select_asset("radio", "5G", "lattice_tower")

    assert tower.asset_id == "TOWER_LATTICE_30M"
    assert antenna.asset_id == "ANT_PANEL_5G_001"
    assert radio.asset_id == "RRU_SMALL_001"
