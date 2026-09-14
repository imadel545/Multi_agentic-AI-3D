from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from apps.api.telecom_studio_api.workflow import _tower_characteristics_summary
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.services.asset_registry import AssetRegistry
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler
from core.validation.catalog_only import catalog_only_scene_violations
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

    assert catalog_only_scene_violations(scene) == []
    assert _tower_characteristics_summary(SimpleNamespace(scene=scene)) is None


def test_catalog_only_policy_rejects_legacy_component_construction() -> None:
    _, valid_scene, _ = _valid_scene_inputs()
    assert catalog_only_scene_violations(valid_scene) == [
        "scene.schema_version:legacy_component_construction"
    ]


def test_product_retrieval_excludes_internal_synthetic_sources() -> None:
    from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever

    registry = AssetRegistry(Path("assets/manifests"))
    retriever = QualifiedAssetCandidateRetriever(registry, external_sources_only=True)
    assert retriever.search({"semantic_role": "antenna"}) == []
    assert "telecom_site" in retriever.available_semantic_roles()
    assert "antenna" not in retriever.available_semantic_roles()


def test_product_runner_rejects_internal_mesh_before_starting_blender(tmp_path) -> None:
    from core.services.blender_runner import BlenderRunner

    registry, raw = reuse_plan()
    scene = CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_internal_source", plan=CognitiveDesignPlan.model_validate(raw),
        geometry_programs=[],
    )
    result = BlenderRunner(Path.cwd(), catalog_only_registry=registry).generate(scene, tmp_path)
    assert result.status == "failed"
    assert result.error == "CATALOG_ONLY_ASSET_REQUIRED"
    assert result.artifacts == {}
    assert list(tmp_path.iterdir()) == []


def test_product_planner_and_compiler_share_executable_admission_capability() -> None:
    from core.services.cognitive_asset_reuse import asset_admission_registry
    from tests.e2e.test_generic_exact_asset_reuse import CompleteTelecomSiteReusePlanner

    registry = AssetRegistry(Path("assets/manifests"))
    plan = CompleteTelecomSiteReusePlanner(registry).plan(workflow_id="wf_catalog", request="site")
    plan.asset_decision_plan.decisions[0].required_capability_ids = [
        "catalog.validate_exact_source@1.0.0"
    ]
    compilation = CognitiveSceneCompiler(
        asset_admission_registry(registry), registry=registry
    ).compile_with_observations(workflow_id="wf_catalog", plan=plan, geometry_programs=[])
    assert catalog_only_scene_violations(compilation.scene, registry=registry) == []
    assert compilation.capability_observations[0].status == "completed"
