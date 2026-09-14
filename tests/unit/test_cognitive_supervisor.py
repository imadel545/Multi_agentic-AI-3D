from __future__ import annotations

import hashlib

import pytest

from core.agents.cognitive_supervisor import CognitiveSupervisor, GroqSpecialistRouteClient
from core.contracts.cognitive_design import (
    ComponentGraph,
    ComponentNode,
    DesignFunction,
    DesignIntent,
    SpecialistDescriptor,
)


class RouteClient:
    provider_name = "groq"
    model_name = "openai/gpt-oss-120b"

    def __init__(self, steps: list[dict]) -> None:
        self.steps = steps
        self.last_payload: dict | None = None

    def decide_route(self, payload: dict) -> dict:
        self.last_payload = payload
        return {
            "steps": self.steps,
            "rationale": "Select only the specialists needed to synthesize and inspect geometry.",
        }


def _intent_and_graph() -> tuple[DesignIntent, ComponentGraph]:
    request = "Créer une structure paramétrique avec ses appuis et ses matériaux."
    intent = DesignIntent(
        intent_id="design.generic.1",
        domain="generic",
        title="Structure paramétrique",
        source_request=request,
        functions=[
            DesignFunction(
                function_id="safe_access",
                description="Provide safe physical access to the elevated surface.",
            )
        ],
        requested_fidelity="technical_generic",
        llm_provider="groq",
        llm_model="openai/gpt-oss-120b",
        source_prompt_sha256=hashlib.sha256(request.encode()).hexdigest(),
    )
    graph = ComponentGraph(
        graph_id="design.generic.1:components:v1",
        intent_id=intent.intent_id,
        components=[
            ComponentNode(
                component_id="access_structure",
                semantic_role="access_structure",
                description="Primary parametric access structure.",
                functions=["safe_access"],
            )
        ],
    )
    return intent, graph


def _descriptors() -> list[SpecialistDescriptor]:
    return [
        SpecialistDescriptor(
            specialist_id="geometry_synthesis",
            description="Synthesize governed declarative geometry programs.",
            compatible_domains=["generic"],
            capability_ids=["geometry.extrude_profile@2.0.0"],
            required_gate=True,
        ),
        SpecialistDescriptor(
            specialist_id="geometry_critic",
            description="Inspect geometry evidence and identify bounded repairs.",
            compatible_domains=["generic"],
            capability_ids=["qa.geometry_contract@1.0.0"],
            depends_on=["geometry_synthesis"],
            required_gate=True,
        ),
    ]


def test_llm_supervisor_route_is_dynamic_but_registry_governed() -> None:
    intent, graph = _intent_and_graph()
    client = RouteClient(
        [
            {
                "specialist_id": "geometry_synthesis",
                "objective": "Generate the required access structure from governed operations.",
                "input_component_ids": ["access_structure"],
                "depends_on": [],
                "execution_wave": 0,
            },
            {
                "specialist_id": "geometry_critic",
                "objective": "Inspect proportions, connections and unsupported geometry.",
                "input_component_ids": ["access_structure"],
                "depends_on": ["geometry_synthesis"],
                "execution_wave": 1,
            },
        ]
    )

    route = CognitiveSupervisor(_descriptors(), client).route(intent, graph)

    assert [step.specialist_id for step in route.steps] == [
        "geometry_synthesis",
        "geometry_critic",
    ]
    assert route.llm_model == "openai/gpt-oss-120b"
    assert client.last_payload is not None
    assert {item["specialist_id"] for item in client.last_payload["specialist_registry"]} == {
        "geometry_synthesis",
        "geometry_critic",
    }


def test_llm_supervisor_rejects_invented_specialist_and_pins_dependencies() -> None:
    intent, graph = _intent_and_graph()
    invented = RouteClient(
        [
            {
                "specialist_id": "free_python_agent",
                "objective": "Run unrestricted generated Blender code for the requested design.",
                "input_component_ids": ["access_structure"],
                "depends_on": [],
                "execution_wave": 0,
            }
        ]
    )
    with pytest.raises(ValueError, match="unknown specialist"):
        CognitiveSupervisor(_descriptors(), invented).route(intent, graph)

    bypass = RouteClient(
        [
            {
                "specialist_id": "geometry_synthesis",
                "objective": "Generate the required access structure from governed operations.",
                "input_component_ids": ["access_structure"],
                "depends_on": [],
                "execution_wave": 0,
            },
            {
                "specialist_id": "geometry_critic",
                "objective": "Inspect the generated access structure after synthesis.",
                "input_component_ids": ["access_structure"],
                "depends_on": [],
                "execution_wave": 1,
            },
        ]
    )
    route = CognitiveSupervisor(_descriptors(), bypass).route(intent, graph)
    critic = next(step for step in route.steps if step.specialist_id == "geometry_critic")
    assert critic.depends_on == ["geometry_synthesis"]
    assert critic.execution_wave == 1


def test_supervisor_completes_required_gates_and_dependencies_from_registry() -> None:
    intent, graph = _intent_and_graph()
    client = RouteClient(
        [
            {
                "specialist_id": "geometry_synthesis",
                "objective": "Prepare the admitted component for deterministic compilation.",
                "input_component_ids": ["access_structure"],
                "depends_on": [],
                "execution_wave": 0,
            }
        ]
    )

    route = CognitiveSupervisor(_descriptors(), client).route(intent, graph)

    assert [step.specialist_id for step in route.steps] == [
        "geometry_synthesis",
        "geometry_critic",
    ]
    added_gate = route.steps[1]
    assert added_gate.objective == _descriptors()[1].description
    assert added_gate.input_component_ids == ["access_structure"]
    assert added_gate.depends_on == ["geometry_synthesis"]
    assert added_gate.execution_wave == 1


def test_groq_supervisor_uses_a_strict_registry_bounded_response_schema() -> None:
    class StructuredClient:
        model = "openai/gpt-oss-120b"

        def request_json(self, request, *, policy):
            assert policy.capability == "specialist_route_selection"
            response_format = request["response_format"]
            assert response_format["type"] == "json_schema"
            schema = response_format["json_schema"]["schema"]
            assert schema["required"] == ["steps", "rationale"]
            specialist_enum = schema["properties"]["steps"]["items"]["properties"]["specialist_id"][
                "enum"
            ]
            assert specialist_enum == ["geometry_synthesis"]
            return {
                "steps": [
                    {
                        "specialist_id": "geometry_synthesis",
                        "objective": "Compile the selected admitted component into the scene.",
                        "input_component_ids": ["complete_site"],
                        "depends_on": [],
                        "execution_wave": 0,
                    }
                ],
                "rationale": "One registered compiler is sufficient for exact reuse.",
            }

    client = GroqSpecialistRouteClient(StructuredClient())  # type: ignore[arg-type]
    result = client.decide_route(
        {
            "components": [{"component_id": "complete_site"}],
            "specialist_registry": [{"specialist_id": "geometry_synthesis"}],
        }
    )

    assert result["rationale"] == "One registered compiler is sufficient for exact reuse."
