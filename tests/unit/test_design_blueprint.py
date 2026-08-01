import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agents.blueprint_composer import BlueprintComposer, design_blueprint_hash
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.scene_planner import ScenePlanner
from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.design_blueprint import ConnectionIntent, DesignBlueprint
from core.contracts.geometry_program import GeometryProgram
from core.contracts.requirements import GeometryRequest
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
    decisions = {decision.domain: decision for decision in blueprint.specialist_decisions}
    assert decisions["asset_composition"].execution_wave == 0
    assert decisions["asset_composition"].depends_on == []
    assert decisions["rf_layout"].execution_wave == 1
    assert decisions["rf_layout"].depends_on == ["asset_composition"]
    assert decisions["structural_support"].execution_wave == 1
    assert decisions["structural_support"].depends_on == ["asset_composition"]
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


def test_blueprint_uses_manifest_backed_cable_without_a_duplicate_derived_intent() -> None:
    requirements, assets, scene = _inputs()
    registry = AssetRegistry(Path("assets/manifests"))
    cable_asset = registry.get("CABLE_TRAY_001")

    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=[*assets, cable_asset],
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )

    cable_intents = [
        intent for intent in blueprint.component_intents if intent.asset_type == "cable"
    ]
    assert requirements.include_cables is True
    assert [intent.intent_id for intent in cable_intents] == ["component:cable:1"]
    assert cable_intents[0].resolved_asset_id == cable_asset.asset_id
    assert cable_intents[0].instance_strategy_id == "per_sector"
    assert cable_intents[0].quantity == requirements.sector_count
    assert len({intent.intent_id for intent in blueprint.component_intents}) == len(
        blueprint.component_intents
    )


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


def test_blueprint_routes_arbitrary_geometry_through_typed_specialist() -> None:
    requirements, assets, scene = _inputs()
    request = GeometryRequest(
        request_id="maintenance_stair",
        semantic_role="maintenance_stair",
        description="Escalier métallique extérieur pour accéder à une plateforme technique.",
        quantity=1,
        placement_context="À côté du shelter, sans collision avec le pylône.",
        maximum_dimensions_m={"x": 4.0, "y": 2.0, "z": 4.0},
    )
    requirements = requirements.model_copy(update={"geometry_requests": [request]})
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=assets,
        tower_validation=TowerEngineerAgent().validate(requirements, assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )

    assert "geometry_generation" in blueprint.required_specialist_domains
    decision = next(
        item for item in blueprint.specialist_decisions if item.domain == "geometry_generation"
    )
    assert decision.depends_on == ["asset_composition"]
    assert decision.execution_wave == 1
    assert blueprint.composition_mode == "validated_catalog_with_llm_geometry_program"
    assert evaluate_blueprint_requirement_coverage(requirements, blueprint).passed is True
    missing = evaluate_blueprint_scene_coverage(blueprint, scene)
    assert "scene.geometry_program_roles" in missing.critical_errors

    program = GeometryProgram.model_validate(
        {
            "program_id": "maintenance_stair.llm_v1",
            "semantic_role": "maintenance_stair",
            "requested_quantity": 1,
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": "openai/gpt-oss-120b",
            "structured_output_mode": "strict_json_schema",
            "source_prompt_sha256": hashlib.sha256(request.description.encode()).hexdigest(),
            "nodes": [
                {
                    "kind": "primitive",
                    "node_id": "stair_root",
                    "primitive": "box",
                    "size_m": {"x": 3.0, "y": 1.2, "z": 0.2},
                    "semantic_role": "maintenance_stair",
                },
                {
                    "kind": "primitive",
                    "node_id": "stair_step",
                    "primitive": "box",
                    "size_m": {"x": 0.4, "y": 1.2, "z": 0.15},
                },
                {
                    "kind": "curve",
                    "node_id": "stair_guardrail",
                    "points_m": [
                        {"x": -1.5, "y": -0.6, "z": 0.2},
                        {"x": 1.5, "y": -0.6, "z": 1.8},
                    ],
                    "bevel_depth_m": 0.03,
                },
            ],
        }
    )
    compiled_scene = scene.model_copy(update={"geometry_programs": [program]})

    assert evaluate_blueprint_scene_coverage(blueprint, compiled_scene).passed is True


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
