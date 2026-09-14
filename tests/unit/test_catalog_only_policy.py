from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from apps.api.telecom_studio_api.workflow import _tower_characteristics_summary
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.services.asset_registry import AssetRegistry
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler
from core.validation.library_first import library_first_scene_violations
from tests.unit.test_cognitive_asset_reuse import reuse_plan
from tests.unit.test_quality_gates import _valid_scene_inputs


def test_catalog_only_policy_accepts_only_exact_asset_programs() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    _, raw = reuse_plan()
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_catalog_policy_001",
        plan=CognitiveDesignPlan.model_validate(raw),
        geometry_programs=[],
    )

    assert library_first_scene_violations(scene) == []
    assert _tower_characteristics_summary(SimpleNamespace(scene=scene)) is None


def test_catalog_only_policy_rejects_legacy_component_construction() -> None:
    _, valid_scene, _ = _valid_scene_inputs()
    assert library_first_scene_violations(valid_scene) == [
        "scene.schema_version:legacy_component_construction"
    ]


def test_product_retrieval_excludes_internal_synthetic_sources() -> None:
    from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever

    registry = AssetRegistry(Path("assets/manifests"))
    retriever = QualifiedAssetCandidateRetriever(registry, external_sources_only=True)
    assert retriever.search({"semantic_role": "antenna"}) == []
    assert "equipped_tower" in retriever.available_semantic_roles()
    assert "antenna" not in retriever.available_semantic_roles()


def test_product_runner_rejects_internal_mesh_before_starting_blender(tmp_path) -> None:
    from core.services.blender_runner import BlenderRunner

    registry, raw = reuse_plan()
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_internal_source",
        plan=CognitiveDesignPlan.model_validate(raw),
        geometry_programs=[],
    )
    result = BlenderRunner(Path.cwd(), library_first_registry=registry).generate(scene, tmp_path)
    assert result.status == "failed"
    assert result.error == "LIBRARY_SOURCE_REQUIRED"
    assert result.artifacts == {}
    assert list(tmp_path.iterdir()) == []


def test_product_planner_and_compiler_share_executable_admission_capability() -> None:
    from core.services.cognitive_asset_reuse import asset_admission_registry
    from tests.e2e.test_generic_exact_asset_reuse import EquippedTowerReusePlanner

    registry = AssetRegistry(Path("assets/manifests"))
    plan = EquippedTowerReusePlanner(registry).plan(workflow_id="wf_catalog", request="site")
    plan.asset_decision_plan.decisions[0].required_capability_ids = [
        "catalog.validate_exact_source@1.0.0"
    ]
    compilation = CognitiveSceneCompiler(
        asset_admission_registry(registry), registry=registry
    ).compile_with_observations(workflow_id="wf_catalog", plan=plan, geometry_programs=[])
    assert library_first_scene_violations(compilation.scene, registry=registry) == []
    assert compilation.capability_observations[0].status == "completed"


def test_library_first_allows_project_geometry_but_not_generated_radio() -> None:
    from core.contracts.geometry_program import GeometryProgram
    from core.validation.library_first import project_geometry_roles
    from tests.e2e.test_generic_exact_asset_reuse import EquippedTowerReusePlanner
    from tests.unit.test_cognitive_runtime_integration import FakeGeometryPlanner

    registry = AssetRegistry(Path("assets/manifests"))
    plan = EquippedTowerReusePlanner(registry).plan(workflow_id="wf_mix", request="tower")
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_mix", plan=plan, geometry_programs=[]
    )
    raw = FakeGeometryPlanner().plan(schema_version="2.0.0").model_dump(mode="json")
    raw["semantic_role"] = "project_support"
    raw["nodes"][0]["semantic_role"] = "project_support"
    generated = GeometryProgram.model_validate(raw)
    mixed = scene.model_copy(update={"geometry_programs": [*scene.geometry_programs, generated]})
    assert (
        library_first_scene_violations(
            mixed, registry=registry, generated_roles=project_geometry_roles()
        )
        == []
    )
    invalid = generated.model_copy(update={"semantic_role": "radio"})
    assert library_first_scene_violations(
        scene.model_copy(update={"geometry_programs": [invalid]}),
        registry=registry,
        generated_roles=project_geometry_roles(),
    )
    # Even an overly broad caller policy cannot bypass an existing reusable source.
    replacement = generated.model_copy(update={"semantic_role": "equipped_tower"})
    assert any(
        "reusable_source_exists" in issue
        for issue in library_first_scene_violations(
            scene.model_copy(update={"geometry_programs": [replacement]}),
            registry=registry,
            generated_roles=frozenset({"equipped_tower"}),
        )
    )


def test_equipped_tower_does_not_claim_complete_site_or_rf_compatibility() -> None:
    from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever

    registry = AssetRegistry(Path("assets/manifests"))
    retriever = QualifiedAssetCandidateRetriever(registry, external_sources_only=True)
    assert retriever.search({"semantic_role": "telecom_site"}) == []
    candidates = retriever.search({"semantic_role": "equipped_tower"})
    assert len(candidates) == 1
    manifest = registry.get(candidates[0].candidate_id)
    assert manifest.family == "equipped_tower_assembly"
    assert manifest.compatible_networks == []
    assert not manifest.connectors


def test_exact_scene_pose_diff_without_v1_tower() -> None:
    from core.services.diff_engine import DiffEngine
    from tests.e2e.test_generic_exact_asset_reuse import EquippedTowerReusePlanner

    registry = AssetRegistry(Path("assets/manifests"))
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_pose_diff",
        geometry_programs=[],
        plan=EquippedTowerReusePlanner(registry).plan(workflow_id="wf_pose_diff", request="tower"),
    )
    patched = scene.model_copy(deep=True)
    patched.geometry_programs[0].nodes[0].transform.translation_m.x = 2
    diff = DiffEngine.diff_scenes(scene, patched)
    assert diff["tower_changed"] is False
    assert diff["geometry_programs_changed"] is True
    assert len(diff["geometry_program_changes"]) == 1
    assert DiffEngine.diff_scenes(scene, scene)["geometry_programs_changed"] is False
