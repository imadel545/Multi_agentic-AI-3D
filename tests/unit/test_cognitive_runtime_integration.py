from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.agents.cognitive_domain_router import ConservativeDesignDomainRouter
from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.cognitive_design import CognitiveDesignPlan, DesignRouteDecision
from core.contracts.geometry_program import GeometryProgram
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler


class GenericRoute:
    def route(self, request: str) -> DesignRouteDecision:
        return DesignRouteDecision(
            route="generic_cognitive_v1",
            inferred_domain="architecture",
            rationale="The request is a physical architectural access structure.",
            provider="groq",
            model="openai/gpt-oss-120b",
        )


class FakeCognitivePlanner:
    def plan(self, *, workflow_id: str, request: str) -> CognitiveDesignPlan:
        return CognitiveDesignPlan.model_validate(
            {
                "design_intent": {
                    "intent_id": f"{workflow_id}:intent:v1",
                    "domain": "architecture",
                    "title": "Technical access structure",
                    "source_request": request,
                    "functions": [
                        {
                            "function_id": "safe_access",
                            "description": "Provide stable access between two levels.",
                            "priority": "required",
                        }
                    ],
                    "requested_fidelity": "technical_generic",
                    "llm_provider": "groq",
                    "llm_model": "openai/gpt-oss-120b",
                    "source_prompt_sha256": hashlib.sha256(request.encode()).hexdigest(),
                },
                "component_graph": {
                    "graph_id": f"{workflow_id}:components:v1",
                    "intent_id": f"{workflow_id}:intent:v1",
                    "components": [
                        {
                            "component_id": "access_structure",
                            "semantic_role": "access_structure",
                            "description": "Steel access platform with two supports.",
                            "quantity": 1,
                            "functions": ["safe_access"],
                            "target_dimensions_m": {"x": 4.0, "y": 3.0, "z": 3.0},
                            "material_intent": ["steel"],
                            "minimum_detail_parts": 3,
                        }
                    ],
                },
                "asset_decision_plan": {
                    "plan_id": f"{workflow_id}:asset-decisions:v1",
                    "graph_id": f"{workflow_id}:components:v1",
                    "decisions": [
                        {
                            "component_id": "access_structure",
                            "strategy": "procedural_generate",
                            "required_capability_ids": ["geometry.primitive@1.0.0"],
                            "rationale": "No qualified reusable component is available.",
                        }
                    ],
                    "llm_provider": "groq",
                    "llm_model": "openai/gpt-oss-120b",
                },
                "specialist_route": {
                    "route_id": f"{workflow_id}:intent:v1:specialists:v1",
                    "domain": "architecture",
                    "steps": [
                        {
                            "specialist_id": "geometry_program_specialist",
                            "objective": "Create bounded declarative access geometry.",
                            "input_component_ids": ["access_structure"],
                            "execution_wave": 0,
                        }
                    ],
                    "rationale": "One geometry specialist is sufficient for this component.",
                    "llm_provider": "groq",
                    "llm_model": "openai/gpt-oss-120b",
                },
            }
        )


class FakeGeometryPlanner:
    def plan(self, **kwargs) -> GeometryProgram:
        assert kwargs["schema_version"] == "2.0.0"
        return GeometryProgram.model_validate(
            {
                "schema_version": "2.0.0",
                "program_id": "access_structure.llm_v2",
                "semantic_role": "access_structure",
                "requested_quantity": 1,
                "authorship": "llm_generated",
                "generator_provider": "groq",
                "generator_model": "openai/gpt-oss-120b",
                "structured_output_mode": "strict_json_schema",
                "source_prompt_sha256": hashlib.sha256(b"access structure").hexdigest(),
                "source_description": "Governed technical access structure.",
                "materials": [
                    {
                        "material_id": "steel",
                        "base_color_rgba": {"r": 0.25, "g": 0.3, "b": 0.35, "a": 1.0},
                        "metallic": 0.7,
                        "roughness": 0.3,
                    }
                ],
                "nodes": [
                    {
                        "kind": "primitive",
                        "node_id": "platform",
                        "primitive": "box",
                        "size_m": {"x": 2.8, "y": 1.8, "z": 0.18},
                        "material_id": "steel",
                        "semantic_role": "access_structure",
                        "transform": {"translation_m": {"x": 0.0, "y": 0.0, "z": 2.0}},
                    },
                    {
                        "kind": "primitive",
                        "node_id": "support_left",
                        "primitive": "box",
                        "size_m": {"x": 0.18, "y": 0.18, "z": 2.0},
                        "material_id": "steel",
                        "transform": {"translation_m": {"x": -1.0, "y": 0.0, "z": 1.0}},
                    },
                    {
                        "kind": "primitive",
                        "node_id": "support_right",
                        "primitive": "box",
                        "size_m": {"x": 0.18, "y": 0.18, "z": 2.0},
                        "material_id": "steel",
                        "transform": {"translation_m": {"x": 1.0, "y": 0.0, "z": 1.0}},
                    },
                ],
                "limitations": ["No structural engineering certification."],
            }
        )


def test_conservative_router_preserves_only_explicit_telecom() -> None:
    router = ConservativeDesignDomainRouter()

    assert router.route("Créer un site 5G avec trois antennes").route == "telecom_v1"
    assert router.route("Tour 5000m avec 100 secteurs").route == "telecom_v1"
    assert router.route("Tower 30m with 3 sectors").route == "telecom_v1"
    blocked = router.route("Créer un escalier et un jardin")
    assert blocked.route == "blocked"
    assert blocked.fallback_used is True
    assert router.route("Créer une tour résidentielle de 20 étages").route == "blocked"


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    not Path("/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender").exists(),
    reason="validated Blender LTS is not available",
)
def test_generic_request_runs_through_existing_graph_real_blender_and_certificate(
    tmp_path: Path,
) -> None:
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
        design_domain_router=GenericRoute(),
        cognitive_design_planner=FakeCognitivePlanner(),  # type: ignore[arg-type]
        geometry_program_planner=FakeGeometryPlanner(),  # type: ignore[arg-type]
    )

    result = orchestrator.run(
        workflow_id="wf_123456789abc",
        requirements_text="Créer une plateforme technique entre deux niveaux.",
        detail_level="medium",
        output_dir=tmp_path,
        use_llm=True,
    )

    assert result.status == "completed", result.report.errors
    assert result.scene is not None and result.scene.schema_version == "2.0.0"
    assert result.scene.tower is None
    assert result.generation is not None and result.generation.mode == "real_blender"
    assert result.qa_report is not None and result.qa_report.status == "passed"
    assert result.completion_certificate is not None
    assert result.completion_certificate.schema_version == "1.3.0"
    assert result.completion_certificate.status == "issued"
    assert result.cognitive_plan is not None
    assert result.capability_observations
    metadata = json.loads((tmp_path / "scene_metadata.json").read_text(encoding="utf-8"))
    assert metadata["geometry_program_ids"] == ["access_structure.llm_v2"]
    assert [item["node"] for item in result.trace[:5]] == [
        "infer_design_domain",
        "plan_cognitive_design",
        "plan_cognitive_geometry",
        "compile_cognitive_scene",
        "validate_cognitive_scene",
    ]


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    not Path("/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender").exists(),
    reason="validated Blender LTS is not available",
)
def test_generic_scene_revision_preserves_cognitive_plan_and_recertifies(
    tmp_path: Path,
) -> None:
    workflow_id = "wf_revision_123456"
    request = "Créer une plateforme technique entre deux niveaux."
    plan = FakeCognitivePlanner().plan(workflow_id=workflow_id, request=request)
    program = FakeGeometryPlanner().plan(schema_version="2.0.0")
    scene = CognitiveSceneCompiler().compile(
        workflow_id=workflow_id,
        plan=plan,
        geometry_programs=[program],
        detail_level="medium",
    )
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
    )

    result = orchestrator.run_scene_revision(
        workflow_id=workflow_id,
        scene=scene,
        output_dir=tmp_path,
        detail_level="medium",
        revision_id="v2",
        cognitive_plan=plan,
    )

    assert result.status == "completed", result.report.errors
    assert result.completion_certificate is not None
    assert result.completion_certificate.schema_version == "1.3.0"
    assert result.completion_certificate.status == "issued"
    assert result.trace[0]["node"] == "edit_prepare_revision"
