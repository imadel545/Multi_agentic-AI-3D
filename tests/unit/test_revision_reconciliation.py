from pathlib import Path

import pytest

from core.agents.blueprint_composer import BlueprintComposer
from core.agents.scene_planner import ScenePlanner
from core.contracts.requirements import RequirementSpec
from core.contracts.rf_validation import RfValidationReport
from core.contracts.tower_validation import TowerValidationReport
from core.orchestration.langgraph_orchestrator import (
    _requirements_from_scene,
    _scene_with_revision_dependencies,
)
from core.services.assembly_compiler import resolve_scene_assembly
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.validation.design_blueprint import evaluate_blueprint_scene_coverage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = PROJECT_ROOT / "assets" / "manifests"


def test_revision_removing_power_cabinet_reconciles_blueprint_assets() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    planner = AssetAssemblyPlanner(registry)
    original_requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30.0,
        sector_count=1,
        antenna_type="panel_5g",
        antenna_install_height_m=24.0,
        azimuths_deg=[0.0],
        include_rru=False,
        include_cables=False,
        include_power_cabinet=True,
        include_gps_antenna=False,
    )
    planning = planner.plan(
        workflow_id="wf_remove_power_cabinet",
        requirements=original_requirements,
    )
    llm_plan = planning.plan.model_copy(
        update={
            "selection_authority": "llm_bounded",
            "selection_provider": "groq",
            "selection_model": "selection-model",
            "llm_fallback_used": False,
            "llm_fallback_reason": None,
        }
    )
    original_scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_remove_power_cabinet",
        requirements=original_requirements,
        tower=planning.assets_by_role["support_structure"],
        antenna=planning.assets_by_role["sector_antenna"],
        radio=None,
        accessory_assets=[planning.assets_by_role["ground_equipment"]],
        assembly_plan=llm_plan,
    )

    edited_scene = original_scene.model_copy(
        update={
            "visual_elements": original_scene.visual_elements.model_copy(
                update={"include_power_cabinet": False}
            )
        }
    )
    normalized_scene = _scene_with_revision_dependencies(edited_scene, registry)
    assert normalized_scene.accessory_assets == []
    assert normalized_scene.assembly_plan is not None

    tower = registry.get(normalized_scene.tower.asset_id)
    antenna = registry.get(normalized_scene.sectors[0].antenna_asset_id)
    revision_requirements = _requirements_from_scene(
        normalized_scene,
        tower,
        antenna,
        None,
        "high",
    )
    stale_assets = [
        registry.get(component.selected_asset_id)
        for component in normalized_scene.assembly_plan.components
        if component.selected_asset_id
    ]
    stale_blueprint = BlueprintComposer().compose(
        workflow_id=normalized_scene.scene_id,
        requirements=revision_requirements,
        selected_assets=stale_assets,
        tower_validation=TowerValidationReport(),
        rf_validation=RfValidationReport(),
        planning_resolution=None,
        assembly_plan=normalized_scene.assembly_plan,
    )
    stale_coverage = evaluate_blueprint_scene_coverage(stale_blueprint, normalized_scene)
    assert "scene.accessory_asset_ids" in stale_coverage.critical_errors

    reconciled = planner.reconcile_with_scene(
        normalized_scene.assembly_plan,
        scene=normalized_scene,
        requirements=revision_requirements,
    )
    assert "ground_equipment" not in {component.role_id for component in reconciled.components}
    assert all(
        "ground_equipment" not in {connection.source_role_id, connection.target_role_id}
        for connection in reconciled.connections
    )
    assert reconciled.selection_authority == "llm_bounded"
    assert reconciled.selection_provider == "groq"
    assert reconciled.selection_model == "selection-model"
    assert reconciled.llm_fallback_used is False
    assert reconciled.llm_fallback_reason is None

    reconciled_scene = normalized_scene.model_copy(update={"assembly_plan": reconciled})
    resolved = resolve_scene_assembly(reconciled_scene)
    assert resolved is not None
    reconciled_scene = reconciled_scene.model_copy(update={"assembly_plan": resolved})
    selected_assets = [
        registry.get(component.selected_asset_id)
        for component in resolved.components
        if component.selected_asset_id
    ]
    blueprint = BlueprintComposer().compose(
        workflow_id=reconciled_scene.scene_id,
        requirements=revision_requirements,
        selected_assets=selected_assets,
        tower_validation=TowerValidationReport(),
        rf_validation=RfValidationReport(),
        planning_resolution=None,
        assembly_plan=resolved,
    )

    coverage = evaluate_blueprint_scene_coverage(blueprint, reconciled_scene)
    assert coverage.passed is True
    assert not any(intent.asset_type == "cabinet" for intent in blueprint.component_intents)


def test_revision_keeps_asset_choices_and_refreshes_parameters_without_rewiring() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    planner = AssetAssemblyPlanner(registry)
    original_requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30.0,
        tower_characteristics={"structure": "lattice", "base_width_m": 4.0},
        sector_count=1,
        antenna_type="panel_5g",
        antenna_install_height_m=24.0,
        azimuths_deg=[0.0],
        include_rru=False,
        include_cables=False,
    )
    planning = planner.plan(workflow_id="wf_refresh_parameters", requirements=original_requirements)
    llm_plan = planning.plan.model_copy(
        update={
            "selection_authority": "llm_bounded",
            "selection_provider": "groq",
            "selection_model": "selection-model",
            "llm_fallback_used": False,
            "llm_fallback_reason": None,
        }
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_refresh_parameters",
        requirements=original_requirements,
        tower=planning.assets_by_role["support_structure"],
        antenna=planning.assets_by_role["sector_antenna"],
        radio=None,
        assembly_plan=llm_plan,
    )
    assert scene.assembly_plan is not None
    revised_requirements = original_requirements.model_copy(
        update={
            "tower_height_m": 35.0,
            "tower_characteristics": original_requirements.tower_characteristics.model_copy(
                update={"base_width_m": 5.0}
            ),
        }
    )
    revised_scene = scene.model_copy(
        update={
            "tower": scene.tower.model_copy(
                update={
                    "height_m": 35.0,
                    "characteristics": scene.tower.characteristics.model_copy(
                        update={"base_width_m": 5.0}
                    ),
                }
            )
        }
    )
    original_asset_ids = {
        component.role_id: component.selected_asset_id
        for component in scene.assembly_plan.components
    }
    original_connections = list(scene.assembly_plan.connections)

    reconciled = planner.reconcile_with_scene(
        scene.assembly_plan,
        scene=revised_scene,
        requirements=revised_requirements,
    )

    assert {
        component.role_id: component.selected_asset_id for component in reconciled.components
    } == original_asset_ids
    tower_component = next(
        component for component in reconciled.components if component.role_id == "support_structure"
    )
    assert tower_component.parameter_values == {"height_m": 35.0, "base_width_m": 5.0}
    assert reconciled.connections == original_connections
    assert reconciled.compilation_status == "declared"
    assert reconciled.operations == []
    assert reconciled.selection_authority == "llm_bounded"
    assert reconciled.selection_provider == "groq"
    assert reconciled.selection_model == "selection-model"
    assert reconciled.llm_fallback_used is False
    assert reconciled.llm_fallback_reason is None


def test_revision_rejects_explicit_scene_asset_outside_admitted_candidates() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    planner = AssetAssemblyPlanner(registry)
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30.0,
        sector_count=1,
        antenna_type="panel_5g",
        antenna_install_height_m=24.0,
        azimuths_deg=[0.0],
        include_rru=False,
        include_cables=False,
    )
    planning = planner.plan(workflow_id="wf_reject_scene_asset", requirements=requirements)
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_reject_scene_asset",
        requirements=requirements,
        tower=planning.assets_by_role["support_structure"],
        antenna=planning.assets_by_role["sector_antenna"],
        radio=None,
        assembly_plan=planning.plan,
    )
    assert scene.assembly_plan is not None
    scene = scene.model_copy(
        update={
            "sectors": [
                scene.sectors[0].model_copy(update={"antenna_asset_id": "ANT_PANEL_4G_001"})
            ]
        }
    )

    with pytest.raises(
        LookupError,
        match="scene asset is not admitted for sector_antenna: ANT_PANEL_4G_001",
    ):
        planner.reconcile_with_scene(
            scene.assembly_plan,
            scene=scene,
            requirements=requirements,
        )


def test_revision_new_role_records_deterministic_selection_provenance() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    planner = AssetAssemblyPlanner(registry)
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30.0,
        sector_count=1,
        antenna_type="panel_5g",
        antenna_install_height_m=24.0,
        azimuths_deg=[0.0],
        include_rru=False,
        include_cables=False,
        include_power_cabinet=False,
        include_gps_antenna=False,
    )
    planning = planner.plan(workflow_id="wf_revision_provenance", requirements=requirements)
    llm_plan = planning.plan.model_copy(
        update={
            "selection_authority": "llm_bounded",
            "selection_provider": "groq",
            "selection_model": "selection-model",
            "llm_fallback_used": False,
            "llm_fallback_reason": None,
        }
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_revision_provenance",
        requirements=requirements,
        tower=planning.assets_by_role["support_structure"],
        antenna=planning.assets_by_role["sector_antenna"],
        radio=None,
        assembly_plan=llm_plan,
    )
    scene = scene.model_copy(
        update={
            "visual_elements": scene.visual_elements.model_copy(
                update={"include_power_cabinet": True}
            )
        }
    )
    scene = _scene_with_revision_dependencies(scene, registry)
    revision_requirements = _requirements_from_scene(
        scene,
        registry.get(scene.tower.asset_id),
        registry.get(scene.sectors[0].antenna_asset_id),
        None,
        "high",
    )

    reconciled = planner.reconcile_with_scene(
        scene.assembly_plan,
        scene=scene,
        requirements=revision_requirements,
    )

    assert reconciled.selection_authority == "deterministic_fallback"
    assert reconciled.selection_provider == "deterministic"
    assert reconciled.selection_model is None
    assert reconciled.llm_fallback_used is True
    assert reconciled.llm_fallback_reason == (
        "scene_revision_role_reconciled_without_new_llm_selection"
    )
    assert any(component.role_id == "ground_equipment" for component in reconciled.components)


def test_legacy_revision_removes_stale_role_without_upgrading_or_snapshots() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    planner = AssetAssemblyPlanner(registry)
    original_requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30.0,
        sector_count=1,
        antenna_type="panel_5g",
        antenna_install_height_m=24.0,
        azimuths_deg=[0.0],
        include_rru=False,
        include_cables=False,
        include_power_cabinet=True,
        include_gps_antenna=False,
    )
    planning = planner.plan(
        workflow_id="wf_legacy_remove_power_cabinet",
        requirements=original_requirements,
    )
    legacy_components = [
        component.model_copy(update={"manifest_snapshot": None, "builder_profile": None})
        for component in planning.plan.components
    ]
    legacy_plan = planning.plan.model_copy(
        update={
            "schema_version": "1.0.0",
            "components": legacy_components,
            "operations": [],
            "compilation_status": "legacy_uncompiled",
        }
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_legacy_remove_power_cabinet",
        requirements=original_requirements,
        tower=planning.assets_by_role["support_structure"],
        antenna=planning.assets_by_role["sector_antenna"],
        radio=None,
        accessory_assets=[planning.assets_by_role["ground_equipment"]],
        assembly_plan=legacy_plan,
    )
    scene = scene.model_copy(
        update={
            "visual_elements": scene.visual_elements.model_copy(
                update={"include_power_cabinet": False}
            )
        }
    )
    scene = _scene_with_revision_dependencies(scene, registry)
    revision_requirements = _requirements_from_scene(
        scene,
        registry.get(scene.tower.asset_id),
        registry.get(scene.sectors[0].antenna_asset_id),
        None,
        "high",
    )

    reconciled = planner.reconcile_with_scene(
        scene.assembly_plan,
        scene=scene,
        requirements=revision_requirements,
    )

    assert reconciled.schema_version == "1.0.0"
    assert reconciled.compilation_status == "legacy_uncompiled"
    assert reconciled.operations == []
    assert "ground_equipment" not in {component.role_id for component in reconciled.components}
    assert all(component.manifest_snapshot is None for component in reconciled.components)
    assert all(component.builder_profile is None for component in reconciled.components)

    reconciled_scene = scene.model_copy(update={"assembly_plan": reconciled})
    selected_assets = [
        registry.get(component.selected_asset_id)
        for component in reconciled.components
        if component.selected_asset_id
    ]
    blueprint = BlueprintComposer().compose(
        workflow_id=reconciled_scene.scene_id,
        requirements=revision_requirements,
        selected_assets=selected_assets,
        tower_validation=TowerValidationReport(),
        rf_validation=RfValidationReport(),
        planning_resolution=None,
        assembly_plan=reconciled,
    )
    coverage = evaluate_blueprint_scene_coverage(blueprint, reconciled_scene)
    assert coverage.passed is True
    assert not any(intent.asset_type == "cabinet" for intent in blueprint.component_intents)
