from __future__ import annotations

from core.agents.cognitive_design_planner import (
    CognitiveDesignPlanner,
    GroqCognitivePlanningClient,
)
from core.agents.cognitive_supervisor import CognitiveSupervisor, GroqSpecialistRouteClient
from core.contracts.cognitive_design import SpecialistDescriptor
from core.llm.groq import GroqStructuredClient
from core.services.asset_registry import AssetRegistry
from core.services.cognitive_asset_reuse import asset_admission_registry
from core.services.geometry_capabilities import geometry_capability_registry
from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever
from core.validation.library_first import project_geometry_roles


def build_cognitive_design_planner(
    client: GroqStructuredClient,
    asset_registry: AssetRegistry,
    *,
    enable_project_geometry: bool = False,
) -> CognitiveDesignPlanner:
    capability_registry = asset_admission_registry(asset_registry)
    if enable_project_geometry:
        capability_registry = capability_registry.merged(geometry_capability_registry())
    capability_ids = [item.capability_id for item in capability_registry.discover()]
    descriptors = [
        SpecialistDescriptor(
            specialist_id="qualified_asset_reuse_specialist",
            description=(
                "Selects only admitted catalog assets and preserves their source evidence."
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
            depends_on=["qualified_asset_reuse_specialist"],
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
        candidate_retriever=QualifiedAssetCandidateRetriever(
            asset_registry, external_sources_only=True
        ),
        supervisor=CognitiveSupervisor(
            descriptors,
            GroqSpecialistRouteClient(client),
        ),
        capabilities=capability_registry.discover(),
        project_specific_roles=project_geometry_roles() if enable_project_geometry else frozenset(),
    )
