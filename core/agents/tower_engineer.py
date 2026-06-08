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
        checks["taper_valid"] = characteristics.top_width_m <= characteristics.base_width_m
        if not checks["taper_valid"]:
            errors.append(
                ValidationIssue(
                    code="TOWER_TAPER_INVALID",
                    message="Tower top width must not exceed base width.",
                    severity="error",
                )
            )

        # Foundation appropriateness
        checks["foundation_appropriate"] = True
        if characteristics.structure in ("rooftop_mast", "small_cell_pole"):
            if characteristics.foundation_type == "concrete_pad":
                checks["foundation_appropriate"] = False
                warnings.append(
                    ValidationIssue(
                        code="TOWER_FOUNDATION_RECOMMENDATION",
                        message=(
                            f"{characteristics.structure} typically uses "
                            "rooftop_anchored or pole_base foundation."
                        ),
                        severity="warning",
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
