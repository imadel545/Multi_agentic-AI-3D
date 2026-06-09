from core.contracts.assets import AssetManifest
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport


def _mount_zones_valid(scene: SceneSpec, assets_by_id: dict[str, AssetManifest]) -> bool:
    tower_asset = assets_by_id.get(scene.tower.asset_id)
    if tower_asset and tower_asset.mount_zones:
        for sector in scene.sectors:
            if not any(
                zone.min_height_m <= sector.install_height_m <= zone.max_height_m
                for zone in tower_asset.mount_zones
            ):
                return False
    for sector in scene.sectors:
        antenna_asset = assets_by_id.get(sector.antenna_asset_id)
        if antenna_asset and antenna_asset.mount_zones:
            if not any(
                zone.min_height_m <= sector.install_height_m <= zone.max_height_m
                for zone in antenna_asset.mount_zones
            ):
                return False
    return True


def _has_accessory(scene: SceneSpec, asset_type: str) -> bool:
    return any(accessory.asset_type == asset_type for accessory in scene.accessory_assets)


def validate_scene_spec(scene: SceneSpec, assets: list[AssetManifest]) -> ValidationReport:
    assets_by_id = {asset.asset_id: asset for asset in assets}
    checks = {
        "tower_asset_valid": scene.tower.asset_id in assets_by_id
        and assets_by_id[scene.tower.asset_id].is_validated,
        "tower_height_valid": scene.tower.height_m > 0,
        "tower_characteristics_valid": bool(scene.tower.characteristics.structure),
        "sector_count_valid": len(scene.sectors) > 0,
        "antenna_height_valid": all(
            sector.install_height_m <= scene.tower.height_m for sector in scene.sectors
        ),
        "azimuths_valid": all(0 <= sector.azimuth_deg < 360 for sector in scene.sectors),
        "sector_asset_valid": all(
            sector.antenna_asset_id in assets_by_id for sector in scene.sectors
        ),
        "radio_asset_valid": all(
            sector.radio_asset_id is None or sector.radio_asset_id in assets_by_id
            for sector in scene.sectors
        ),
        "accessory_assets_valid": all(
            accessory.asset_id in assets_by_id
            and assets_by_id[accessory.asset_id].is_validated
            and assets_by_id[accessory.asset_id].type == accessory.asset_type
            for accessory in scene.accessory_assets
        ),
        "gps_asset_present_when_requested": (
            not scene.visual_elements.include_gps_antenna or _has_accessory(scene, "gps")
        ),
        "power_cabinet_asset_present_when_requested": (
            not scene.visual_elements.include_power_cabinet or _has_accessory(scene, "cabinet")
        ),
        "cable_option_consistent": all(sector.include_cable for sector in scene.sectors)
        or not any(sector.include_cable for sector in scene.sectors),
        "mount_zones_valid": _mount_zones_valid(scene, assets_by_id),
        "units_meters": scene.units == "meters",
    }
    errors = [
        ValidationIssue(
            code=code.upper(), message=f"SceneSpec check failed: {code}", severity="error"
        )
        for code, passed in checks.items()
        if not passed
    ]
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return ValidationReport(
        design_id=scene.scene_id,
        status="passed" if not errors else "failed",
        score=score,
        checks=checks,
        warnings=[],
        errors=errors,
    )
