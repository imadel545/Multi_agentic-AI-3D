import hashlib
import json
from pathlib import Path

import pytest

from core.contracts.cognitive_design import CognitiveDesignPlan
from core.contracts.geometry_program import GeometryProgram
from core.services.adaptation_capabilities import AdaptationCapabilityService
from core.services.asset_registry import AssetRegistry
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler, cognitive_plan_hash
from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever
from tests.unit.test_cognitive_runtime_integration import FakeCognitivePlanner


def reuse_plan():
    registry = AssetRegistry(Path("assets/manifests"))
    raw = (
        FakeCognitivePlanner()
        .plan(workflow_id="wf_reuse", request="Inspect a reusable panel antenna")
        .model_dump(mode="json")
    )
    component = raw["component_graph"]["components"][0]
    component.update(
        semantic_role="antenna",
        description="Inspect one existing antenna panel.",
        target_dimensions_m={"x": 2, "y": 2, "z": 2},
    )
    candidates = QualifiedAssetCandidateRetriever(registry).search(component)
    assert any(item.candidate_id == "ANT_PANEL_4G_001" for item in candidates)
    raw["asset_decision_plan"]["decisions"][0].update(
        strategy="reuse",
        candidates=[item.model_dump(mode="json") for item in candidates],
        selected_candidate_ids=["ANT_PANEL_4G_001"],
        required_capability_ids=[],
        placement={
            "translation_m": {"x": 0, "y": 0, "z": 1},
            "rotation_deg": {"x": 0, "y": 0, "z": 0},
        },
    )
    return registry, raw


def test_reuse_compiles_pinned_source_without_geometry_planner():
    registry, raw = reuse_plan()
    plan = CognitiveDesignPlan.model_validate(raw)
    compiler = CognitiveSceneCompiler(registry=registry)
    scene = compiler.compile(workflow_id="wf_reuse", plan=plan, geometry_programs=[])
    node = scene.geometry_programs[0].nodes[0]
    assert node.kind == "exact_asset"
    assert node.asset_sha256 == hashlib.sha256(Path(node.asset_file).read_bytes()).hexdigest()
    assert node.transform.translation_m.z == 1
    assert (
        compiler.compile(
            workflow_id="wf_reuse", plan=plan, geometry_programs=scene.geometry_programs
        )
        == scene
    )
    changed = scene.geometry_programs[0].model_dump(mode="json")
    changed["nodes"][0]["transform"]["translation_m"]["z"] = 2
    with pytest.raises(ValueError, match="DIFFERS_FROM_CATALOG"):
        compiler.compile(
            workflow_id="wf_reuse",
            plan=plan,
            geometry_programs=[GeometryProgram.model_validate(changed)],
        )


def test_reuse_admission_is_file_validation_and_does_not_offer_procedural_rebuild():
    registry, raw = reuse_plan()
    compilation = CognitiveSceneCompiler(registry=registry).compile_with_observations(
        workflow_id="wf_reuse", plan=CognitiveDesignPlan.model_validate(raw), geometry_programs=[]
    )
    observation, = compilation.capability_observations
    assert observation.capability_id == "catalog.validate_exact_source@1.0.0"
    assert observation.status == "completed"
    assert observation.output["source_hashes_verified"] is True
    assert observation.output["blender_executed"] is False
    capabilities = AdaptationCapabilityService(Path.cwd(), registry).resolve(compilation.scene)
    assert all(
        capability.execution_tool != "geometry_program_rebuild"
        for capability in capabilities.capabilities
    )
    assert capabilities.unsupported_operations


def test_optional_reuse_placement_preserves_existing_plan_hash():
    plan = FakeCognitivePlanner().plan(workflow_id="wf_old", request="Create an object")
    historical = plan.model_dump(mode="json")
    for decision in historical["asset_decision_plan"]["decisions"]:
        decision.pop("placement", None)
    expected = hashlib.sha256(json.dumps(
        historical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()
    assert cognitive_plan_hash(CognitiveDesignPlan.model_validate(historical)) == expected


def test_generic_revision_retains_exact_asset_metadata():
    from core.agents.requirement_extractor import RequirementExtractor
    from core.orchestration import DesignOrchestrator
    from core.services.blender_runner import BlenderRunner

    registry, raw = reuse_plan()
    plan = CognitiveDesignPlan.model_validate(raw)
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_reuse", plan=plan, geometry_programs=[]
    )
    orchestrator = DesignOrchestrator(
        registry=registry, extractor=RequirementExtractor(enabled=False), rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
    )
    command = orchestrator._prepare_scene_revision({
        "workflow_id": "wf_reuse", "scene": scene, "cognitive_plan": plan, "trace": []
    })
    assert command.goto == "validate_cognitive_scene"
    assert [asset.asset_id for asset in command.update["selected_assets"]] == ["ANT_PANEL_4G_001"]


@pytest.mark.parametrize(
    "change,error",
    [
        ("placement", "EXPLICIT_PLACEMENT"),
        ("scale", "scaled"),
        ("quantity", "SINGLE_COMPONENT"),
        ("rotation", "TRANSFORM_NOT_AUTHORIZED"),
        ("envelope", "exceeds maximum"),
    ],
)
def test_reuse_refuses_unexecutable_changes(change, error):
    registry, raw = reuse_plan()
    decision = raw["asset_decision_plan"]["decisions"][0]
    component = raw["component_graph"]["components"][0]
    if change == "placement":
        decision["placement"] = None
    if change == "scale":
        decision["placement"]["scale"] = {"x": 2, "y": 1, "z": 1}
    if change == "rotation":
        decision["placement"]["rotation_deg"]["y"] = 30
    if change == "quantity":
        component["quantity"] = 2
    if change == "envelope":
        component["target_dimensions_m"] = {"x": 0.1, "y": 0.1, "z": 0.1}
    with pytest.raises(ValueError, match=error):
        CognitiveSceneCompiler(registry=registry).compile(
            workflow_id="wf_reuse",
            plan=CognitiveDesignPlan.model_validate(raw),
            geometry_programs=[],
        )
