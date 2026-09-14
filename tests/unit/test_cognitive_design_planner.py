from __future__ import annotations

import hashlib

from core.agents.cognitive_design_planner import (
    CognitiveDesignPlanner,
    GroqCognitivePlanningClient,
    _llm_component_graph_schema,
)
from core.agents.cognitive_supervisor import CognitiveSupervisor
from core.contracts.capabilities import CapabilityCost, CapabilityDefinition
from core.contracts.cognitive_design import AssetCandidateEvidence, SpecialistDescriptor
from core.contracts.geometry_program import GeometryProgram
from core.llm.groq_policy import GroqRequestPolicy
from core.llm.transport import GroqTransportError
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
    def available_semantic_roles(self) -> list[str]:
        return []

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
        allow_generated_geometry=True,
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


def test_catalog_only_planner_does_not_offer_generated_geometry() -> None:
    class CatalogPolicyClient(PlanningClient):
        def decide_assets(self, payload: dict) -> dict:
            assert payload["required_strategies"] == [
                "reuse",
                "compose",
                "clarify",
                "unsupported",
            ]
            return {
                "decisions": [
                    {
                        "strategy": "unsupported",
                        "selected_candidate_ids": [],
                        "selected_parameter_values": {},
                        "required_capability_ids": [],
                        "rationale": "No admitted catalog asset can satisfy this component.",
                    }
                ]
            }

    plan = CognitiveDesignPlanner(
        CatalogPolicyClient(),
        CandidateRetriever(),
        _supervisor(),
        [_capability()],
    ).plan(
        workflow_id="wf_catalog_only_001",
        request="Créer un accès qui n'existe pas encore dans le catalogue.",
    )

    assert plan.asset_decision_plan.decisions[0].strategy == "unsupported"


def test_llm_and_runtime_share_the_same_component_fanout_bound() -> None:
    schema = _llm_component_graph_schema()

    assert schema["properties"]["components"]["maxItems"] == 24


def test_asset_decision_uses_strict_owned_shape_and_normalizes_parameters() -> None:
    class StructuredAssetClient:
        model = "openai/gpt-oss-120b"

        def request_json(self, payload, *, policy):
            assert policy.capability == "generic_asset_strategy"
            assert payload["response_format"]["type"] == "json_schema"
            decision = payload["response_format"]["json_schema"]["schema"]["properties"][
                "decisions"
            ]["items"]
            assert set(decision["required"]) == {
                "strategy",
                "selected_candidate_ids",
                "selected_parameters",
                "placement",
                "required_capability_ids",
                "rationale",
            }
            return {
                "decisions": [
                    {
                        "strategy": "adapt",
                        "selected_candidate_ids": ["tower_candidate"],
                        "selected_parameters": [{"parameter_id": "height_m", "value": 32}],
                        "placement": None,
                        "required_capability_ids": [],
                        "rationale": "Use the qualified candidate at the requested height.",
                    }
                ]
            }

    client = GroqCognitivePlanningClient(StructuredAssetClient())  # type: ignore[arg-type]
    result = client.decide_assets(
        {
            "required_strategies": ["reuse", "adapt", "procedural_generate"],
            "candidates": [
                {
                    "candidate_id": "tower_candidate",
                    "allowed_parameter_ids": ["height_m"],
                }
            ],
            "capabilities": [],
        }
    )

    assert result["decisions"][0]["selected_parameter_values"] == {"height_m": 32.0}
    assert "selected_parameters" not in result["decisions"][0]


def test_cognitive_strict_400_from_shared_transport_reaches_json_object_fallback() -> None:
    class TransportBackedClient:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.calls = 0

        def request_json(self, payload, *, policy):
            self.calls += 1
            if self.calls == 1:
                raise GroqTransportError(
                    "model_output_rejected",
                    attempts=1,
                    retryable=False,
                    status_code=400,
                )
            assert payload["response_format"] == {"type": "json_object"}
            return {"result": {"name": "validated"}}

    structured = TransportBackedClient()
    client = GroqCognitivePlanningClient(structured)  # type: ignore[arg-type]

    result = client._request(
        {
            "response_key": "result",
            "response_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
        policy=GroqRequestPolicy(
            capability="generic_design_decomposition",
            reasoning_effort="medium",
            max_completion_tokens=1024,
        ),
        system="Return the bounded result.",
    )

    assert result == {"result": {"name": "validated"}}
    assert structured.calls == 2


def test_project_specific_generation_requires_empty_retrieval_and_allowed_role() -> None:
    import pytest

    class ProjectClient(PlanningClient):
        def decompose(self, payload):
            result = super().decompose(payload)
            result["component_graph"]["components"][0]["semantic_role"] = "project_support"
            return result

        def decide_assets(self, payload):
            assert "procedural_generate" in payload["required_strategies"]
            return super().decide_assets(payload)

    planner = CognitiveDesignPlanner(
        ProjectClient(),
        CandidateRetriever(),
        _supervisor(),
        [_capability()],
        project_specific_roles=frozenset({"project_support"}),
    )
    assert (
        planner.plan(workflow_id="wf_custom", request="custom support")
        .asset_decision_plan.decisions[0]
        .strategy
        == "procedural_generate"
    )
    # A standard equipment role is denied even if a provider returns generation.
    planner.planning_client = PlanningClient()
    with pytest.raises(ValueError, match="POLICY_REJECTED_GENERATED_GEOMETRY"):
        planner.plan(workflow_id="wf_standard", request="standard access equipment")
