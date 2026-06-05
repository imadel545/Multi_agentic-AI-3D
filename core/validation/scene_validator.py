from core.contracts.assets import AssetManifest
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport


def validate_scene_spec(scene: SceneSpec, assets: list[AssetManifest]) -> ValidationReport:
    assets_by_id = {asset.asset_id: asset for asset in assets}
    checks = {
        "tower_asset_valid": scene.tower.asset_id in assets_by_id
        and assets_by_id[scene.tower.asset_id].is_validated,
        "tower_height_valid": scene.tower.height_m > 0,
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
        "cable_option_consistent": all(sector.include_cable for sector in scene.sectors)
        or not any(sector.include_cable for sector in scene.sectors),
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
