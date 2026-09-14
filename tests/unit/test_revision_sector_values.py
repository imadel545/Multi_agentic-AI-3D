from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agents.blueprint_composer import BlueprintComposer
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.scene_planner import ScenePlanner
from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.requirements import RequirementSpec
from core.orchestration.langgraph_orchestrator import (
    _requirements_from_scene,
    _scene_with_revision_dependencies,
)
from core.services.assembly_compiler import resolve_scene_assembly
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text
from core.validation.design_blueprint import (
    evaluate_blueprint_requirement_coverage,
    evaluate_blueprint_scene_coverage,
)
from core.validation.requirement_coverage import evaluate_requirement_coverage
from core.validation.scene_validator import validate_scene_spec


def _inputs():
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Site 5G pylône treillis 30m, 3 secteurs à 24m, azimuts 0, 120, 240.", "high"
    )
    planning = AssetAssemblyPlanner(registry).plan(
        workflow_id="wf_sector_revision", requirements=requirements
    )
    assets = planning.assets_by_role
    scene = ScenePlanner().build_scene_spec(
        "wf_sector_revision",
        requirements,
        assets["support_structure"],
        assets["sector_antenna"],
        assets.get("remote_radio"),
        [a for a in assets.values() if a.type in {"gps", "cabinet"}],
        assembly_plan=planning.plan,
    )
    return requirements, assets, scene


def test_nonuniform_revision_values_survive_requirements_blueprint_and_recompilation():
    _, assets, scene = _inputs()
    scene.sectors[1].install_height_m = 26.0
    scene.sectors[1].mechanical_tilt_deg = 6.0
    scene.sectors[2].electrical_tilt_deg = 4.0
    scene.sectors[2].beamwidth_deg = 70.0
    scene.sectors[1].include_cable = False
    scene.sectors[2].include_label = False
    scene.visual_elements.include_labels = False
    scene.assembly_plan = resolve_scene_assembly(scene)
    requirements = _requirements_from_scene(
        scene,
        assets["support_structure"],
        assets["sector_antenna"],
        assets.get("remote_radio"),
        "high",
    )
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=list(assets.values()),
        tower_validation=TowerEngineerAgent().validate(requirements, assets["support_structure"]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
        assembly_plan=scene.assembly_plan,
    )
    assert evaluate_requirement_coverage(requirements, scene).passed
    assert evaluate_blueprint_requirement_coverage(requirements, blueprint).passed
    assert evaluate_blueprint_scene_coverage(blueprint, scene).passed
    assert validate_scene_spec(scene, list(assets.values())).status == "passed"
    rebuilt = ScenePlanner().build_scene_spec(
        scene.scene_id,
        requirements,
        assets["support_structure"],
        assets["sector_antenna"],
        assets.get("remote_radio"),
        [a for a in assets.values() if a.type in {"gps", "cabinet"}],
        assembly_plan=scene.assembly_plan,
    )
    for field in (
        "install_height_m",
        "mechanical_tilt_deg",
        "electrical_tilt_deg",
        "beamwidth_deg",
        "include_cable",
        "include_label",
    ):
        assert [getattr(s, field) for s in rebuilt.sectors] == [
            getattr(s, field) for s in scene.sectors
        ]
    cable_op = next(
        op for op in rebuilt.assembly_plan.operations if op.target_role_id == "sector_cable_route"
    )
    assert [i.instance_id for i in cable_op.instances] == ["S1", "S3"]
    rebuilt.sectors[1].install_height_m = 24.0
    assert not evaluate_requirement_coverage(requirements, rebuilt).passed


def test_absent_sector_overrides_preserve_historical_requirement_payload():
    requirements, _, _ = _inputs()
    payload = requirements.model_dump(mode="json")
    assert not any(key.startswith("sector_") and key != "sector_count" for key in payload)
    assert RequirementSpec.model_validate(payload).model_dump(mode="json") == payload


def test_accessory_edit_preserves_selected_tower_and_its_execution_strategy():
    _, _, scene = _inputs()
    scene.tower = scene.tower.model_copy(
        update={
            "generation_strategy": "imported_glb_exact",
            "geometry_source": "imported_glb_exact",
            "generation_reason": "Keep the selected source geometry.",
        }
    )
    scene.visual_elements.include_power_cabinet = False
    revised = _scene_with_revision_dependencies(scene, AssetRegistry(Path("assets/manifests")))
    assert revised.tower.asset_id == scene.tower.asset_id
    assert revised.tower.generation_strategy == "imported_glb_exact"
    assert revised.tower.geometry_source == "imported_glb_exact"
    assert revised.tower.generation_reason == scene.tower.generation_reason
    assert all(asset.asset_type != "cabinet" for asset in revised.accessory_assets)


@pytest.mark.parametrize(
    "field,values",
    [
        ("sector_install_heights_m", [24, 24]),
        ("sector_install_heights_m", [24, 24, 40]),
        ("sector_mechanical_tilts_deg", [0, float("nan"), 0]),
        ("sector_beamwidths_deg", [65, 0, 65]),
        ("sector_include_cables", [True, False]),
    ],
)
def test_invalid_sector_override_is_rejected(field, values):
    requirements, _, _ = _inputs()
    with pytest.raises(ValidationError):
        RequirementSpec.model_validate({**requirements.model_dump(), field: values})
