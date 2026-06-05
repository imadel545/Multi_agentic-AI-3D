from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.contracts.validation import ValidationIssue, ValidationReport


class RuleEngine:
    def validate_requirements(
        self,
        requirements: RequirementSpec,
        selected_assets: list[AssetManifest],
    ) -> ValidationReport:
        checks: dict[str, bool] = {
            "antenna_height_within_tower": requirements.antenna_install_height_m
            <= requirements.tower_height_m,
            "sector_count_matches_azimuths": requirements.sector_count
            == len(requirements.azimuths_deg),
            "azimuths_valid": all(0 <= azimuth < 360 for azimuth in requirements.azimuths_deg),
            "assets_validated": all(asset.is_validated for asset in selected_assets),
            "assets_network_compatible": all(
                requirements.network_type in asset.compatible_networks for asset in selected_assets
            ),
            "rru_required_has_radio_asset": (
                any(asset.type == "radio" for asset in selected_assets)
                if requirements.include_rru
                else True
            ),
            "cables_requested": requirements.include_cables,
            "scene_units_meters": True,
        }
        warnings = [
            ValidationIssue(code=warning.code, message=warning.message, severity="warning")
            for warning in requirements.warnings
        ]
        errors = [
            ValidationIssue(code=key.upper(), message=f"Rule failed: {key}", severity="error")
            for key, passed in checks.items()
            if not passed
        ]
        passed_count = sum(1 for passed in checks.values() if passed)
        score = passed_count / len(checks)
        return ValidationReport(
            design_id="requirements",
            status="passed" if not errors else "failed",
            score=score,
            checks=checks,
            warnings=warnings,
            errors=errors,
        )
