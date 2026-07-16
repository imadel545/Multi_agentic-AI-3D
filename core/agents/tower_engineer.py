from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.contracts.tower_validation import TowerValidationReport
from core.contracts.validation import ValidationIssue


class TowerEngineerAgent:
    """Structural / civil engineering agent for tower validation."""

    def validate(
        self,
        requirements: RequirementSpec,
        tower: AssetManifest,
    ) -> TowerValidationReport:
        checks: dict[str, bool] = {}
        warnings: list[ValidationIssue] = []
        errors: list[ValidationIssue] = []
        recommended: dict[str, bool] = {}

        characteristics = requirements.tower_characteristics
        height = requirements.tower_height_m
        base_width, top_width = _resolved_tower_widths(requirements, tower)

        # Leg count rules
        checks["leg_count_appropriate"] = True
        if characteristics.structure == "lattice":
            checks["leg_count_appropriate"] = characteristics.leg_count >= 3
            if not checks["leg_count_appropriate"]:
                errors.append(
                    ValidationIssue(
                        code="TOWER_LATTICE_MIN_3_LEGS",
                        message="Lattice tower requires at least 3 legs.",
                        severity="error",
                    )
                )

        # Taper validation
        checks["taper_valid"] = top_width <= base_width
        if not checks["taper_valid"]:
            errors.append(
                ValidationIssue(
                    code="TOWER_TAPER_INVALID",
                    message="Tower top width must not exceed base width.",
                    severity="error",
                )
            )

        # Foundation appropriateness
        allowed_foundations = {
            "lattice": {"concrete_pad"},
            "monopole": {"concrete_pad", "pole_base"},
            "rooftop_mast": {"rooftop_anchored"},
            "small_cell_pole": {"concrete_pad", "pole_base"},
        }
        foundation_type = characteristics.foundation_type
        checks["foundation_appropriate"] = (
            foundation_type in allowed_foundations[characteristics.structure]
        )
        if not checks["foundation_appropriate"]:
            errors.append(
                ValidationIssue(
                    code="TOWER_FOUNDATION_UNSUPPORTED",
                    message=(
                        f"Foundation {foundation_type!r} is not supported for "
                        f"{characteristics.structure}; supported values are "
                        f"{sorted(allowed_foundations[characteristics.structure])}."
                    ),
                    severity="error",
                )
            )

        # Accessory recommendations based on height
        recommended["has_platform"] = height >= 20
        recommended["has_ladder"] = height >= 6
        recommended["has_lightning_rod"] = height >= 10
        recommended["has_aviation_light"] = height >= 45

        checks["accessories_recommended"] = True
        if height >= 20 and not characteristics.has_platform:
            warnings.append(
                ValidationIssue(
                    code="TOWER_PLATFORM_RECOMMENDED",
                    message="Platforms recommended for towers >= 20m for worker safety.",
                    severity="warning",
                )
            )
        if height >= 45 and not characteristics.has_aviation_light:
            warnings.append(
                ValidationIssue(
                    code="TOWER_AVIATION_LIGHT_RECOMMENDED",
                    message="Aviation light required for towers >= 45m per ICAO.",
                    severity="warning",
                )
            )

        # Material suitability
        checks["material_suitable"] = True
        if (
            characteristics.structure == "small_cell_pole"
            and characteristics.material == "concrete"
        ):
            checks["material_suitable"] = False
            warnings.append(
                ValidationIssue(
                    code="TOWER_MATERIAL_RECOMMENDATION",
                    message="Small cell poles are typically galvanized or painted steel.",
                    severity="warning",
                )
            )

        passed = not errors
        score = sum(1 for v in checks.values() if v) / len(checks) if checks else 1.0
        return TowerValidationReport(
            status="passed" if passed else "failed",
            checks=checks,
            warnings=warnings,
            errors=errors,
            recommended_accessories=recommended,
            structural_score=round(score, 4),
        )


def _resolved_tower_widths(
    requirements: RequirementSpec,
    tower: AssetManifest,
) -> tuple[float, float]:
    characteristics = requirements.tower_characteristics
    manifest_width = tower.dimensions_m.width if tower.dimensions_m else None
    default_base = {
        "lattice": 4.0,
        "monopole": 0.8,
        "rooftop_mast": 0.35,
        "small_cell_pole": 0.3,
    }[characteristics.structure]
    base_width = float(characteristics.base_width_m or manifest_width or default_base)
    default_top_ratio = {
        "lattice": 0.25,
        "monopole": 0.35,
        "rooftop_mast": 0.4,
        "small_cell_pole": 0.6,
    }[characteristics.structure]
    top_width = float(characteristics.top_width_m or (base_width * default_top_ratio))
    return base_width, top_width
