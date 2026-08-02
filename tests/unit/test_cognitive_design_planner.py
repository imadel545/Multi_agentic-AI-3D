from __future__ import annotations

import hashlib

from core.agents.cognitive_design_planner import CognitiveDesignPlanner
from core.agents.cognitive_supervisor import CognitiveSupervisor
from core.contracts.capabilities import CapabilityCost, CapabilityDefinition
from core.contracts.cognitive_design import AssetCandidateEvidence, SpecialistDescriptor
from core.contracts.geometry_program import GeometryProgram
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler


class PlanningClient:
    provider_name = "groq"
    model_name = "openai/gpt-oss-120b"

    def decompose(self, payload: dict) -> dict:
        return {
            "design_intent": {
                "domain": "generic",
                "title": "Accès technique paramétrique",
                "functions": [
                    {
                        "function_id": "safe_access",
                        "description": "Provide safe access between two levels.",
                        "priority": "required",
                    }
                ],
                "constraints": [],
                "requested_fidelity": "technical_generic",
                "assumptions": [],
                "missing_information": [],
                "clarification_required": False,
            },
            "component_graph": {
                "components": [
                    {
                        "component_id": "access_structure",
                        "semantic_role": "access_structure",
                        "description": "Parametric structure connecting two levels.",
                        "quantity": 1,
                        "functions": ["safe_access"],
                        "material_intent": ["steel"],
                        "ports": [],
                        "required": True,
                        "minimum_detail_parts": 8,
                    }
                ],
                "relationships": [],
            },
        }

    def decide_assets(self, payload: dict) -> dict:
        return {
            "decisions": [
                {
                    "component_id": "access_structure",
                    "strategy": "procedural_generate",
                    "selected_candidate_ids": [],
                    "selected_parameter_values": {},
                    "required_capability_ids": ["geometry.extrude_profile@2.0.0"],
                    "rationale": "No qualified reusable asset exists; use governed extrusion.",
                    "decision_authority": "llm_bounded",
                }
            ]
        }


class CandidateRetriever:
    def search(self, component: dict) -> list[AssetCandidateEvidence]:
        assert component["component_id"] == "access_structure"
        return []


class RouteClient:
    provider_name = "groq"
    model_name = "openai/gpt-oss-120b"

    def decide_route(self, payload: dict) -> dict:
        return {
            "steps": [
                {
                    "specialist_id": "geometry_synthesis",
                    "objective": "Synthesize governed geometry for every generated component.",
                    "input_component_ids": ["access_structure"],
                    "depends_on": [],
                    "execution_wave": 0,
                }
            ],
            "rationale": "Geometry synthesis is the smallest sufficient registered route.",
        }


def _capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="geometry.extrude_profile@2.0.0",
        description="Extrude a bounded planar profile into deterministic mesh geometry.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        compatible_domains=["generic"],
        capability_tags=["geometry_program"],
        cost=CapabilityCost(
            class_name="low",
            estimated_seconds=0.1,
            estimated_memory_mb=16,
        ),
        permissions=["mutate_scene_spec"],
        timeout_s=5.0,
        possible_errors=["PROFILE_INVALID"],
        version="2.0.0",
        generated_proofs=["geometry_program_node"],
    )


def _supervisor() -> CognitiveSupervisor:
    return CognitiveSupervisor(
        [
            SpecialistDescriptor(
                specialist_id="geometry_synthesis",
                description="Synthesize governed declarative geometry programs.",
                compatible_domains=["generic"],
                capability_ids=["geometry.extrude_profile@2.0.0"],
                required_gate=True,
            )
        ],
        RouteClient(),
    )


def test_planner_pins_llm_decomposition_assets_capabilities_and_route() -> None:
    plan = CognitiveDesignPlanner(
        PlanningClient(),
        CandidateRetriever(),
        _supervisor(),
        [_capability()],
    ).plan(
        workflow_id="wf_123456789abc",
        request="Créer un accès paramétrique entre deux niveaux.",
    )

    assert plan.design_intent.domain == "generic"
    assert plan.component_graph.components[0].component_id == "access_structure"
    decision = plan.asset_decision_plan.decisions[0]
    assert decision.strategy == "procedural_generate"
    assert decision.required_capability_ids == ["geometry.extrude_profile@2.0.0"]
    assert plan.specialist_route.steps[0].specialist_id == "geometry_synthesis"

    program = GeometryProgram.model_validate(
        {
            "program_id": "access_structure.llm_v1",
            "semantic_role": "access_structure",
            "requested_quantity": 1,
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": "openai/gpt-oss-120b",
            "structured_output_mode": "strict_json_schema",
            "source_prompt_sha256": hashlib.sha256(b"access structure").hexdigest(),
            "nodes": [
                {
                    "kind": "primitive",
                    "node_id": "access_root",
                    "primitive": "box",
                    "size_m": {"x": 2.0, "y": 1.2, "z": 0.2},
                    "semantic_role": "access_structure",
                },
                {
                    "kind": "primitive",
                    "node_id": "support_left",
                    "primitive": "box",
                    "size_m": {"x": 0.2, "y": 0.2, "z": 2.0},
                },
                {
                    "kind": "primitive",
                    "node_id": "support_right",
                    "primitive": "box",
                    "size_m": {"x": 0.2, "y": 0.2, "z": 2.0},
                },
            ],
        }
    )
    scene = CognitiveSceneCompiler().compile(
        workflow_id="wf_123456789abc",
        plan=plan,
        geometry_programs=[program],
    )

    assert scene.schema_version == "2.0.0"
    assert scene.design_domain == "generic"
    assert scene.tower is None
    assert scene.sectors == []
    assert scene.cognitive_plan_sha256 is not None
