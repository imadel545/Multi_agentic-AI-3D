from __future__ import annotations

import math
from typing import Any

from core.contracts.completion import RequirementCoverageCheck, RequirementCoverageReport
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec


def evaluate_requirement_coverage(
    requirements: RequirementSpec,
    scene: SceneSpec,
    planning_resolution: dict[str, Any] | None = None,
) -> RequirementCoverageReport:
    """Prove that every represented requirement survives into the SceneSpec."""

    resolution = planning_resolution or {}
    applied_decisions = {
        str(decision.get("field")): decision
        for decision in resolution.get("decisions", [])
        if isinstance(decision, dict) and decision.get("status") == "applied"
    }
    controlled = {
        "antenna_install_height_m": requirements.antenna_install_height_m,
        "beamwidth_deg": requirements.beamwidth_deg,
        "include_cables": requirements.include_cables,
        "include_sector_beams": requirements.include_beams,
    }
    effective: dict[str, Any] = dict(controlled)
    approved_deviations: list[dict[str, Any]] = []
    override_evidence_checks: list[RequirementCoverageCheck] = []
    for field, original_value in controlled.items():
        candidate_value = resolution.get(field, original_value)
        if _same(candidate_value, original_value):
            continue
        decision = applied_decisions.get(field)
        evidenced = decision is not None and _same(decision.get("candidate_value"), candidate_value)
        override_evidence_checks.append(
            RequirementCoverageCheck(
                path=f"planning_resolution.{field}.evidence",
                expected=True,
                actual=evidenced,
                source="planning_resolution",
                passed=evidenced,
            )
        )
        if evidenced:
            effective[field] = candidate_value
            approved_deviations.append(
                {
                    "field": field,
                    "original_value": original_value,
                    "effective_value": candidate_value,
                    "reason": decision.get("reason"),
                    "provenance": decision.get("provenance"),
                }
            )

    checks = [
        _check("network_type", requirements.network_type, scene.network_type),
        _check("tower.height_m", requirements.tower_height_m, scene.tower.height_m),
        _check(
            "tower.characteristics.structure",
            requirements.tower_characteristics.structure,
            scene.tower.characteristics.structure,
        ),
        _check(
            "tower.characteristics.leg_count",
            requirements.tower_characteristics.leg_count,
            scene.tower.characteristics.leg_count,
        ),
        _check(
            "tower.characteristics.base_width_m",
            requirements.tower_characteristics.base_width_m,
            scene.tower.characteristics.base_width_m,
        ),
        _check(
            "tower.characteristics.top_width_m",
            requirements.tower_characteristics.top_width_m,
            scene.tower.characteristics.top_width_m,
        ),
        _check(
            "tower.characteristics.foundation_type",
            requirements.tower_characteristics.foundation_type,
            scene.tower.characteristics.foundation_type,
        ),
        _check(
            "tower.characteristics.material",
            requirements.tower_characteristics.material,
            scene.tower.characteristics.material,
        ),
        _check(
            "tower.characteristics.has_platform",
            requirements.tower_characteristics.has_platform,
            scene.tower.characteristics.has_platform,
        ),
        _check(
            "tower.characteristics.platform_count",
            requirements.tower_characteristics.platform_count,
            scene.tower.characteristics.platform_count,
        ),
        _check(
            "tower.characteristics.has_ladder",
            requirements.tower_characteristics.has_ladder,
            scene.tower.characteristics.has_ladder,
        ),
        _check(
            "tower.characteristics.has_lightning_rod",
            requirements.tower_characteristics.has_lightning_rod,
            scene.tower.characteristics.has_lightning_rod,
        ),
        _check(
            "tower.characteristics.has_aviation_light",
            requirements.tower_characteristics.has_aviation_light,
            scene.tower.characteristics.has_aviation_light,
        ),
        _check("sectors.count", requirements.sector_count, len(scene.sectors)),
        _check(
            "sectors.azimuth_deg",
            requirements.azimuths_deg,
            [sector.azimuth_deg for sector in scene.sectors],
        ),
        _check(
            "sectors.install_height_m",
            [effective["antenna_install_height_m"]] * requirements.sector_count,
            [sector.install_height_m for sector in scene.sectors],
            source=_source_for("antenna_install_height_m", applied_decisions),
        ),
        _check(
            "sectors.mechanical_tilt_deg",
            [requirements.mechanical_tilt_deg] * requirements.sector_count,
            [sector.mechanical_tilt_deg for sector in scene.sectors],
        ),
        _check(
            "sectors.electrical_tilt_deg",
            [requirements.electrical_tilt_deg] * requirements.sector_count,
            [sector.electrical_tilt_deg for sector in scene.sectors],
        ),
        _check(
            "sectors.beamwidth_deg",
            [effective["beamwidth_deg"]] * requirements.sector_count,
            [sector.beamwidth_deg for sector in scene.sectors],
            source=_source_for("beamwidth_deg", applied_decisions),
        ),
        _check(
            "sectors.radio_presence",
            [requirements.include_rru] * requirements.sector_count,
            [sector.radio_asset_id is not None for sector in scene.sectors],
        ),
        _check(
            "sectors.include_cable",
            [effective["include_cables"]] * requirements.sector_count,
            [sector.include_cable for sector in scene.sectors],
            source=_source_for("include_cables", applied_decisions),
        ),
        _check(
            "sectors.include_label",
            [requirements.include_labels] * requirements.sector_count,
            [sector.include_label for sector in scene.sectors],
        ),
        _check(
            "visual_elements.include_sector_beams",
            effective["include_sector_beams"],
            scene.visual_elements.include_sector_beams,
            source=_source_for("include_sector_beams", applied_decisions),
        ),
        _check(
            "visual_elements.include_labels",
            requirements.include_labels,
            scene.visual_elements.include_labels,
        ),
        _check(
            "visual_elements.include_power_cabinet",
            requirements.include_power_cabinet,
            scene.visual_elements.include_power_cabinet,
        ),
        _check(
            "visual_elements.include_gps_antenna",
            requirements.include_gps_antenna,
            scene.visual_elements.include_gps_antenna,
        ),
        *override_evidence_checks,
    ]
    failed = [check.path for check in checks if not check.passed]
    passed_count = sum(check.passed for check in checks)
    return RequirementCoverageReport(
        workflow_id=scene.scene_id,
        passed=not failed,
        coverage_ratio=passed_count / len(checks) if checks else 0.0,
        checks=checks,
        approved_deviations=approved_deviations,
        critical_errors=failed,
    )


def _source_for(field: str, applied_decisions: dict[str, dict[str, Any]]) -> str:
    return "planning_resolution" if field in applied_decisions else "requirements"


def _check(
    path: str,
    expected: Any,
    actual: Any,
    *,
    source: str = "requirements",
) -> RequirementCoverageCheck:
    return RequirementCoverageCheck(
        path=path,
        expected=expected,
        actual=actual,
        source=source,  # type: ignore[arg-type]
        passed=_same(expected, actual),
    )


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is bool and type(actual) is bool and expected is actual
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-6)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _same(left, right) for left, right in zip(expected, actual, strict=True)
        )
    return expected == actual
