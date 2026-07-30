from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agents.blueprint_composer import BlueprintComposer, design_blueprint_hash
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.scene_planner import ScenePlanner
from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.design_blueprint import ConnectionIntent, DesignBlueprint
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text
from core.validation.design_blueprint import (
    evaluate_blueprint_requirement_coverage,
    evaluate_blueprint_scene_coverage,
)


def test_blueprint_composer_routes_required_specialists_and_covers_scene() -> None:
    requirements, assets, scene = _inputs()
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=assets,
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )

    assert blueprint.required_specialist_domains == [
        "asset_composition",
        "rf_layout",
        "structural_support",
    ]
    assert {decision.domain for decision in blueprint.specialist_decisions} == set(
        blueprint.required_specialist_domains
    )
    assert all(decision.status != "failed" for decision in blueprint.specialist_decisions)
    assert evaluate_blueprint_requirement_coverage(requirements, blueprint).passed is True
    assert evaluate_blueprint_scene_coverage(blueprint, scene).passed is True
    assert len(design_blueprint_hash(blueprint)) == 64


def test_blueprint_scene_coverage_rejects_silent_asset_mutation() -> None:
    requirements, assets, scene = _inputs()
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=assets,
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )
    mutated_sector = scene.sectors[0].model_copy(update={"antenna_asset_id": "UNKNOWN_ASSET"})
    mutated_scene = scene.model_copy(update={"sectors": [mutated_sector, *scene.sectors[1:]]})

    report = evaluate_blueprint_scene_coverage(blueprint, mutated_scene)

    assert report.passed is False
    assert "scene.sectors.antenna_asset_ids" in report.critical_errors


def test_blueprint_rejects_unknown_connection_reference() -> None:
    requirements, assets, scene = _inputs()
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=assets,
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )
    payload = blueprint.model_dump()
    payload["connection_intents"] = [
        ConnectionIntent(
            connection_id="connection:1",
            kind="mechanical",
            source_intent_id="missing:intent",
            target_intent_id=blueprint.component_intents[0].intent_id,
            source_connector_role="mount",
            target_connector_role="support",
            route_strategy_id="direct_mount",
            provenance=["derived_rule:test"],
        ).model_dump()
    ]

    with pytest.raises(ValidationError, match="unknown component intent"):
        DesignBlueprint.model_validate(payload)


def test_blueprint_contract_rejects_path_provenance() -> None:
    requirements, assets, scene = _inputs()
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=assets,
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )
    payload = blueprint.model_dump()
    payload["component_intents"][0]["provenance"] = ["/tmp/injected.py"]

    with pytest.raises(ValidationError, match="not filesystem paths"):
        DesignBlueprint.model_validate(payload)


def _inputs():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset(
        "antenna",
        requirements.network_type,
        requirements.tower_type,
    )
    radio = registry.select_asset(
        "radio",
        requirements.network_type,
        requirements.tower_type,
    )
    scene = ScenePlanner().build_scene_spec(
        "wf_design_blueprint",
        requirements,
        tower,
        antenna,
        radio,
    )
    return requirements, [tower, antenna, radio], scene
