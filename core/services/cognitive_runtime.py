from __future__ import annotations

from core.agents.cognitive_design_planner import (
    CognitiveDesignPlanner,
    GroqCognitivePlanningClient,
)
from core.agents.cognitive_supervisor import CognitiveSupervisor, GroqSpecialistRouteClient
from core.contracts.cognitive_design import AssetCandidateEvidence, SpecialistDescriptor
from core.llm.groq import GroqStructuredClient
from core.services.geometry_capabilities import geometry_capability_registry


class ProceduralOnlyCandidateRetriever:
    """Honest catalog boundary until generic assets gain executable assembly plans.

    Returning no candidate makes GPT-OSS select governed procedural generation.
    Telecom reuse remains implemented by the existing qualified asset planner.
    """

    def search(self, component: dict) -> list[AssetCandidateEvidence]:
        return []


def build_cognitive_design_planner(client: GroqStructuredClient) -> CognitiveDesignPlanner:
    registry = geometry_capability_registry()
    capability_ids = [item.capability_id for item in registry.discover()]
    descriptors = [
        SpecialistDescriptor(
            specialist_id="geometry_program_specialist",
            description=(
                "Authors bounded declarative geometry programs for components that are absent "
                "from the qualified catalog."
            ),
            compatible_domains=["generic"],
            capability_ids=capability_ids,
        ),
        SpecialistDescriptor(
            specialist_id="deterministic_scene_compiler",
            description=(
                "Compiles validated cognitive plans and geometry programs into SceneSpec V2."
            ),
            compatible_domains=["generic"],
            capability_ids=capability_ids,
            depends_on=["geometry_program_specialist"],
        ),
        SpecialistDescriptor(
            specialist_id="geometry_qa_gate",
            description=(
                "Verifies real GLB structure, semantic coverage, previews and bounded geometry."
            ),
            compatible_domains=["generic"],
            capability_ids=capability_ids,
            depends_on=["deterministic_scene_compiler"],
            required_gate=True,
        ),
    ]
    return CognitiveDesignPlanner(
        planning_client=GroqCognitivePlanningClient(client),
        candidate_retriever=ProceduralOnlyCandidateRetriever(),
        supervisor=CognitiveSupervisor(
            descriptors,
            GroqSpecialistRouteClient(client),
        ),
        capabilities=registry.discover(),
    )
