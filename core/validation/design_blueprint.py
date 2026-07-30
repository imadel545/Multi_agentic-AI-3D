from __future__ import annotations

from typing import Any

from core.contracts.design_blueprint import (
    BlueprintCoverageCheck,
    BlueprintCoverageReport,
    DesignBlueprint,
)
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec


def evaluate_blueprint_requirement_coverage(
    requirements: RequirementSpec,
    blueprint: DesignBlueprint,
    planning_resolution: dict[str, Any] | None = None,
) -> BlueprintCoverageReport:
    """Prove that the blueprint preserves the currently effective requirements."""

    resolution = planning_resolution or {}
    intents = _intents_by_type(blueprint)
    effective = {
        "antenna_install_height_m": resolution.get(
            "antenna_install_height_m", requirements.antenna_install_height_m
        ),
        "beamwidth_deg": resolution.get("beamwidth_deg", requirements.beamwidth_deg),
        "mechanical_tilt_deg": resolution.get(
            "mechanical_tilt_deg", requirements.mechanical_tilt_deg
        ),
        "electrical_tilt_deg": resolution.get(
            "electrical_tilt_deg", requirements.electrical_tilt_deg
        ),
    }
    constraints = {constraint.field_path: constraint.value for constraint in blueprint.constraints}
    checks = [
        _check("network_type", requirements.network_type, blueprint.network_type),
        _check("detail_level", requirements.detail_level, blueprint.detail_level),
        _check("tower.quantity", 1, _quantity(intents, "tower")),
        _check("antenna.quantity", requirements.sector_count, _quantity(intents, "antenna")),
        _check(
            "radio.quantity",
            requirements.sector_count if requirements.include_rru else 0,
            _quantity(intents, "radio"),
        ),
        _check(
            "cable.quantity",
            requirements.sector_count if requirements.include_cables else 0,
            _quantity(intents, "cable"),
        ),
        _check(
            "beam.quantity",
            requirements.sector_count if requirements.include_beams else 0,
            _quantity(intents, "beam"),
        ),
        _check(
            "constraints.tower.height_m",
            requirements.tower_height_m,
            constraints.get("tower.height_m"),
        ),
        _check(
            "constraints.sectors.count", requirements.sector_count, constraints.get("sectors.count")
        ),
        _check(
            "constraints.sectors.azimuth_deg",
            tuple(requirements.azimuths_deg),
            constraints.get("sectors.azimuth_deg"),
        ),
        _check(
            "constraints.sectors.install_height_m",
            effective["antenna_install_height_m"],
            constraints.get("sectors.install_height_m"),
        ),
        _check(
            "constraints.sectors.beamwidth_deg",
            effective["beamwidth_deg"],
            constraints.get("sectors.beamwidth_deg"),
        ),
        _check(
            "constraints.sectors.mechanical_tilt_deg",
            effective["mechanical_tilt_deg"],
            constraints.get("sectors.mechanical_tilt_deg"),
        ),
        _check(
            "constraints.sectors.electrical_tilt_deg",
            effective["electrical_tilt_deg"],
            constraints.get("sectors.electrical_tilt_deg"),
        ),
    ]
    return _report(blueprint, "requirements_to_blueprint", checks)


def evaluate_blueprint_scene_coverage(
    blueprint: DesignBlueprint,
    scene: SceneSpec,
) -> BlueprintCoverageReport:
    """Prove that every current blueprint intent compiled into SceneSpec."""

    intents = _intents_by_type(blueprint)
    tower_ids = _resolved_ids(intents, "tower")
    antenna_ids = _resolved_ids(intents, "antenna")
    radio_ids = _resolved_ids(intents, "radio")
    accessory_ids = {accessory.asset_id for accessory in scene.accessory_assets}
    expected_accessories = {
        intent.resolved_asset_id
        for asset_type, values in intents.items()
        if asset_type in {"cabinet", "gps"}
        for intent in values
        if intent.resolved_asset_id
    }
    checks = [
        _check("scene.network_type", blueprint.network_type, scene.network_type),
        _check("scene.detail_level", blueprint.detail_level, scene.detail_level),
        _check("scene.tower.asset_id", tower_ids, {scene.tower.asset_id}),
        _check(
            "scene.sectors.quantity",
            _quantity(intents, "antenna"),
            len(scene.sectors),
        ),
        _check(
            "scene.sectors.antenna_asset_ids",
            antenna_ids,
            {sector.antenna_asset_id for sector in scene.sectors},
        ),
        _check(
            "scene.sectors.radio_asset_ids",
            radio_ids,
            {sector.radio_asset_id for sector in scene.sectors if sector.radio_asset_id},
        ),
        _check(
            "scene.sectors.cable_quantity",
            _quantity(intents, "cable"),
            sum(1 for sector in scene.sectors if sector.include_cable),
        ),
        _check(
            "scene.visual_elements.include_sector_beams",
            _quantity(intents, "beam") > 0,
            scene.visual_elements.include_sector_beams,
        ),
        _check("scene.accessory_asset_ids", expected_accessories, accessory_ids),
        _check(
            "scene.assembly_plan.asset_ids",
            {
                intent.resolved_asset_id
                for values in intents.values()
                for intent in values
                if intent.resolved_asset_id and intent.asset_type not in {"cable", "beam"}
            },
            {
                component.selected_asset_id
                for component in (scene.assembly_plan.components if scene.assembly_plan else [])
                if component.selected_asset_id
            },
        ),
    ]
    return _report(blueprint, "blueprint_to_scene", checks)


def _intents_by_type(blueprint: DesignBlueprint) -> dict[str, list]:
    values: dict[str, list] = {}
    for intent in blueprint.component_intents:
        values.setdefault(intent.asset_type, []).append(intent)
    return values


def _quantity(intents: dict[str, list], asset_type: str) -> int:
    return sum(intent.quantity for intent in intents.get(asset_type, []))


def _resolved_ids(intents: dict[str, list], asset_type: str) -> set[str]:
    return {
        intent.resolved_asset_id
        for intent in intents.get(asset_type, [])
        if intent.resolved_asset_id
    }


def _check(path: str, expected: object, actual: object) -> BlueprintCoverageCheck:
    return BlueprintCoverageCheck(
        path=path,
        expected=expected,
        actual=actual,
        passed=_same(expected, actual),
    )


def _same(expected: object, actual: object) -> bool:
    if isinstance(expected, float) and isinstance(actual, int | float):
        return abs(expected - float(actual)) <= 1e-9
    return expected == actual


def _report(
    blueprint: DesignBlueprint,
    stage: str,
    checks: list[BlueprintCoverageCheck],
) -> BlueprintCoverageReport:
    failures = [check.path for check in checks if not check.passed]
    passed_count = sum(check.passed for check in checks)
    return BlueprintCoverageReport(
        blueprint_id=blueprint.blueprint_id,
        stage=stage,  # type: ignore[arg-type]
        passed=not failures,
        coverage_ratio=passed_count / len(checks) if checks else 0.0,
        checks=checks,
        critical_errors=failures,
    )
