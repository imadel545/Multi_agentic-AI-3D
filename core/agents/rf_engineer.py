from core.contracts.requirements import RequirementSpec
from core.contracts.rf_validation import RfValidationReport
from core.contracts.validation import ValidationIssue


class RfEngineerAgent:
    """RF engineering agent for antenna parameter validation."""

    MIN_AZIMUTH_SPACING_DEG: float = 30.0
    MAX_MECHANICAL_TILT_DEG: float = 15.0

    def validate(self, requirements: RequirementSpec) -> RfValidationReport:
        checks: dict[str, bool] = {}
        warnings: list[ValidationIssue] = []
        errors: list[ValidationIssue] = []
        overlap_sectors: list[tuple[str, str]] = []

        azimuths = sorted(requirements.azimuths_deg)
        sector_count = len(azimuths)

        # Azimuth spacing
        spacings = []
        for i in range(sector_count):
            a1 = azimuths[i]
            a2 = azimuths[(i + 1) % sector_count]
            delta = abs((a2 - a1) % 360)
            if delta > 180:
                delta = 360 - delta
            spacings.append(delta)

        checks["azimuth_spacing_adequate"] = all(
            s >= self.MIN_AZIMUTH_SPACING_DEG for s in spacings
        )
        if not checks["azimuth_spacing_adequate"]:
            min_space = min(spacings)
            warnings.append(
                ValidationIssue(
                    code="RF_AZIMUTH_SPACING_LOW",
                    message=(
                        f"Minimum azimuth spacing is {min_space:.1f}°, "
                        f"recommended >= {self.MIN_AZIMUTH_SPACING_DEG}° "
                        "to reduce inter-sector interference."
                    ),
                    severity="warning",
                )
            )

        # Detect overlapping sectors (same azimuth or < 10°)
        for i in range(sector_count):
            for j in range(i + 1, sector_count):
                delta = abs((azimuths[j] - azimuths[i]) % 360)
                if delta > 180:
                    delta = 360 - delta
                if delta < 10.0:
                    overlap_sectors.append((f"S{i + 1}", f"S{j + 1}"))

        checks["no_overlap"] = not overlap_sectors
        if overlap_sectors:
            errors.append(
                ValidationIssue(
                    code="RF_SECTOR_OVERLAP",
                    message=(
                        "Sector overlap detected: "
                        + ", ".join(f"{a}-{b}" for a, b in overlap_sectors)
                    ),
                    severity="error",
                )
            )

        # Tilt reasonableness
        checks["tilt_reasonable"] = True
        if abs(requirements.mechanical_tilt_deg) > self.MAX_MECHANICAL_TILT_DEG:
            checks["tilt_reasonable"] = False
            warnings.append(
                ValidationIssue(
                    code="RF_TILT_HIGH",
                    message=(
                        f"Mechanical tilt {requirements.mechanical_tilt_deg}° exceeds "
                        f"typical maximum {self.MAX_MECHANICAL_TILT_DEG}°."
                    ),
                    severity="warning",
                )
            )

        # Beamwidth vs sector count
        checks["beamwidth_sector_compatible"] = True
        expected_beamwidth = 360.0 / sector_count
        if requirements.beamwidth_deg < expected_beamwidth * 0.7:
            warnings.append(
                ValidationIssue(
                    code="RF_BEAMWIDTH_NARROW",
                    message=(
                        f"Beamwidth {requirements.beamwidth_deg}° may be too narrow "
                        f"for {sector_count} sectors (expected ~{expected_beamwidth:.0f}°)."
                    ),
                    severity="warning",
                )
            )

        # Height vs tilt consistency
        checks["height_tilt_consistent"] = True
        if requirements.antenna_install_height_m < requirements.tower_height_m * 0.3:
            if abs(requirements.mechanical_tilt_deg) < 2.0:
                warnings.append(
                    ValidationIssue(
                        code="RF_LOW_HEIGHT_LOW_TILT",
                        message=(
                            "Low mount height with near-zero tilt may cause "
                            "near-field coverage issues."
                        ),
                        severity="warning",
                    )
                )

        passed = not errors
        score = sum(1 for v in checks.values() if v) / len(checks) if checks else 1.0
        return RfValidationReport(
            status="passed" if passed else "failed",
            checks=checks,
            warnings=warnings,
            errors=errors,
            azimuth_spacing_deg=[round(s, 2) for s in spacings],
            min_spacing_deg=round(min(spacings), 2) if spacings else 0.0,
            overlap_sectors=overlap_sectors,
            rf_score=round(score, 4),
        )
