from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from core.agents.cognitive_planning_schemas import (
    _llm_component_graph_schema,
    _llm_design_intent_schema,
)
from core.agents.cognitive_supervisor import CognitiveSupervisor
from core.agents.groq_cognitive_planning import (
    GroqCognitivePlanningClient as GroqCognitivePlanningClient,
)
from core.contracts.capabilities import CapabilityDefinition
from core.contracts.cognitive_design import (
    AssetCandidateEvidence,
    AssetDecisionPlan,
    CognitiveDesignPlan,
    ComponentAssetDecision,
    ComponentGraph,
    DesignIntent,
)


class CognitivePlanningClient(Protocol):
    provider_name: str
    model_name: str

    def decompose(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def decide_assets(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class ComponentCandidateRetriever(Protocol):
    def available_semantic_roles(self) -> list[str]: ...

    def search(self, component: dict[str, Any]) -> list[AssetCandidateEvidence]: ...


class CognitiveDesignPlanner:
    """Compile LLM decisions into a governed domain-neutral cognitive plan."""

    def __init__(
        self,
        planning_client: CognitivePlanningClient,
        candidate_retriever: ComponentCandidateRetriever,
        supervisor: CognitiveSupervisor,
        capabilities: list[CapabilityDefinition],
        *,
        allow_generated_geometry: bool = False,
        project_specific_roles: frozenset[str] = frozenset(),
    ) -> None:
        capability_ids = [item.capability_id for item in capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("planner capability IDs must be unique")
        self.planning_client = planning_client
        self.candidate_retriever = candidate_retriever
        self.supervisor = supervisor
        self.capabilities = list(capabilities)
        self.allow_generated_geometry = allow_generated_geometry
        self.project_specific_roles = project_specific_roles

    def plan(self, *, workflow_id: str, request: str) -> CognitiveDesignPlan:
        normalized_request = request.strip()
        if len(normalized_request) < 3:
            raise ValueError("generic design request is too short")
        if len(normalized_request) > 12_000:
            raise ValueError("generic design request exceeds 12000 characters")
        prompt_hash = hashlib.sha256(normalized_request.encode("utf-8")).hexdigest()
        intent_id = f"{workflow_id}:intent:v1"
        decomposition = self.planning_client.decompose(
            {
                "contract": "design_intent_component_graph@1.0.0",
                "required_intent_id": intent_id,
                "required_graph_id": f"{workflow_id}:components:v1",
                "source_request": normalized_request,
                "coordinate_frame": "meters_z_up",
                "rules": {
                    "clarification_truth_must_match_missing_information": True,
                    "all_components_require_functions": True,
                    "all_relationship_references_must_resolve": True,
                    "no_assets_or_blender_code": True,
                    "qualified_candidate_ranking_is_downstream_authority": True,
                },
                "project_specific_roles": sorted(self.project_specific_roles),
                "available_catalog_roles": self.candidate_retriever.available_semantic_roles(),
                "design_intent_schema": _llm_design_intent_schema(),
                # The LLM receives the semantic subset it owns. Runtime-only defaults,
                # port frames and free-form relationship parameters are validated and
                # enriched downstream instead of making constrained decoding brittle.
                "component_graph_schema": _llm_component_graph_schema(),
            }
        )
        raw_intent = dict(decomposition.get("design_intent") or {})
        raw_intent.update(
            {
                "schema_version": "1.0.0",
                "intent_id": intent_id,
                "source_request": normalized_request,
                "coordinate_frame": "meters_z_up",
                "llm_provider": self.planning_client.provider_name,
                "llm_model": self.planning_client.model_name,
                "source_prompt_sha256": prompt_hash,
            }
        )
        intent = DesignIntent.model_validate(raw_intent)
        raw_graph = dict(decomposition.get("component_graph") or {})
        raw_graph.update(
            {
                "schema_version": "1.0.0",
                "graph_id": f"{workflow_id}:components:v1",
                "intent_id": intent.intent_id,
            }
        )
        graph = ComponentGraph.model_validate(raw_graph)

        candidates_by_component = {
            component.component_id: self.candidate_retriever.search(
                component.model_dump(mode="json")
            )
            for component in graph.components
        }
        capability_payload = [
            {
                "capability_id": capability.capability_id,
                "description": capability.description,
                "compatible_domains": capability.compatible_domains,
                "capability_tags": capability.capability_tags,
                "cost": capability.cost.model_dump(mode="json"),
                "limits": capability.limits.model_dump(mode="json"),
                "permissions": capability.permissions,
                "possible_errors": capability.possible_errors,
                "generated_proofs": capability.generated_proofs,
            }
            for capability in self.capabilities
            if intent.domain in capability.compatible_domains
            or "generic" in capability.compatible_domains
        ]

        def decide_one(component_index: int) -> tuple[int, dict[str, Any]]:
            component = graph.components[component_index]
            raw_decisions = self.planning_client.decide_assets(
                {
                    "contract": "component_asset_decision@1.0.0",
                    "intent": {
                        "domain": intent.domain,
                        "title": intent.title,
                        "requested_fidelity": intent.requested_fidelity,
                    },
                    "component": component.model_dump(mode="json"),
                    "relationships": [
                        item.model_dump(mode="json")
                        for item in graph.relationships
                        if component.component_id
                        in {item.source_component_id, item.target_component_id}
                    ],
                    "candidates": [
                        item.model_dump(mode="json")
                        for item in candidates_by_component[component.component_id]
                    ],
                    "capabilities": capability_payload,
                    "required_component_id": component.component_id,
                    "required_strategies": (
                        [
                            "reuse",
                            "adapt",
                            "compose",
                            "compose_and_generate",
                            "procedural_generate",
                            "clarify",
                            "unsupported",
                        ]
                        if self.allow_generated_geometry
                        else ["reuse", "compose", "procedural_generate", "clarify", "unsupported"]
                        if component.semantic_role in self.project_specific_roles
                        and not candidates_by_component[component.component_id]
                        else ["reuse", "compose", "clarify", "unsupported"]
                    ),
                }
            )
            returned = [
                item for item in raw_decisions.get("decisions", []) if isinstance(item, dict)
            ]
            if len(returned) != 1:
                raise ValueError(
                    "LLM asset decision must return exactly one decision for "
                    f"{component.component_id!r}"
                )
            # The deterministic caller owns identity. The model decides only the
            # bounded strategy, candidate subset, parameters and capabilities.
            returned[0]["component_id"] = component.component_id
            return component_index, returned[0]

        worker_count = min(3, len(graph.components))
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="cognitive-asset-decision",
        ) as pool:
            indexed_decisions = list(pool.map(decide_one, range(len(graph.components))))
        raw_by_component = {
            graph.components[index].component_id: raw for index, raw in sorted(indexed_decisions)
        }
        known_capabilities = {item["capability_id"] for item in capability_payload}
        decisions: list[ComponentAssetDecision] = []
        for component in graph.components:
            raw = raw_by_component.get(component.component_id)
            if raw is None:
                raise ValueError(f"LLM asset plan omitted component {component.component_id!r}")
            pinned = dict(raw)
            pinned["component_id"] = component.component_id
            pinned["candidates"] = [
                item.model_dump(mode="json")
                for item in candidates_by_component[component.component_id]
            ]
            decision = ComponentAssetDecision.model_validate(pinned)
            if (
                not self.allow_generated_geometry
                and not (
                    decision.strategy == "procedural_generate"
                    and component.semantic_role in self.project_specific_roles
                    and not candidates_by_component[component.component_id]
                )
                and decision.strategy
                not in {
                    "reuse",
                    "compose",
                    "clarify",
                    "unsupported",
                }
            ):
                raise ValueError(
                    "CATALOG_ONLY_POLICY_REJECTED_GENERATED_GEOMETRY:"
                    f"{component.component_id}:{decision.strategy}"
                )
            unknown_capabilities = set(decision.required_capability_ids) - known_capabilities
            if unknown_capabilities:
                raise ValueError(
                    f"LLM asset plan selected unknown capabilities: {sorted(unknown_capabilities)}"
                )
            decisions.append(decision)
        decision_plan = AssetDecisionPlan(
            plan_id=f"{workflow_id}:asset-decisions:v1",
            graph_id=graph.graph_id,
            decisions=decisions,
            llm_provider=self.planning_client.provider_name,
            llm_model=self.planning_client.model_name,
        )
        route = self.supervisor.route(intent, graph)
        return CognitiveDesignPlan(
            design_intent=intent,
            component_graph=graph,
            asset_decision_plan=decision_plan,
            specialist_route=route,
        )
