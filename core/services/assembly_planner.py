from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.contracts.assembly import AssemblyComponentSelection, AssemblyConnection, AssemblyPlan
from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.services.asset_registry import AssetRegistry


class BoundedAssemblyDecisionClient(Protocol):
    def decide(self, *, slots: list[dict]) -> tuple[dict[str, str], dict]: ...


@dataclass(frozen=True)
class AssemblyPlanningResult:
    plan: AssemblyPlan
    assets_by_role: dict[str, AssetManifest]


class AssetAssemblyPlanner:
    """Compile a request into a bounded catalog assembly plan.

    Role families and builder profiles are stable engine capabilities. Concrete
    asset IDs, dimensions, connectors and permitted adaptations come only from
    the small qualified manifest sample.
    """

    def __init__(
        self, registry: AssetRegistry, decision_client: BoundedAssemblyDecisionClient | None = None
    ) -> None:
        self.registry = registry
        self.decision_client = decision_client

    def plan(self, *, workflow_id: str, requirements: RequirementSpec) -> AssemblyPlanningResult:
        slots = self._required_slots(requirements)
        ranked: dict[str, list[tuple[AssetManifest, object]]] = {}
        for role_id, asset_type, _required, _profile, _strategy in slots:
            if asset_type == "cable":
                continue
            # Preserve registry policy overrides (including a controlled
            # "asset unavailable" outcome) before exposing the full ranking.
            if asset_type == "tower":
                self.registry.select_tower(
                    requirements.tower_type,
                    requirements.network_type,
                    requirements.tower_height_m,
                )
            else:
                selected = self.registry.select_asset(
                    asset_type,
                    requirements.network_type,
                    requirements.tower_type,
                )
                if selected is None:
                    raise LookupError(
                        f"no validated {asset_type} asset for {requirements.network_type}"
                    )
            ranked[role_id] = self.registry.rank_candidates(
                asset_type=asset_type,
                network_type=requirements.network_type,
                tower_type=requirements.tower_type,
                min_height_m=requirements.tower_height_m if asset_type == "tower" else None,
            )
        selected_ids, decision = self._bounded_decision(ranked)
        components: list[AssemblyComponentSelection] = []
        assets_by_role: dict[str, AssetManifest] = {}
        for role_id, asset_type, required, default_profile, _default_strategy in slots:
            if asset_type == "cable":
                components.append(
                    AssemblyComponentSelection(
                        role_id=role_id,
                        asset_type=asset_type,
                        required=required,
                        candidate_scores=[],
                        selected_asset_id=None,
                        builder_profile_id="cable_route_v1",
                        generation_strategy="procedural_fallback",
                        allowed_parameter_ids=["route_clearance_m", "cable_diameter_m"],
                        selection_reason=(
                            "Aucun chemin de câble qualifié dans l’échantillon ; "
                            "route procédurale contrôlée."
                        ),
                    )
                )
                continue
            options = ranked[role_id]
            selected_id = selected_ids.get(role_id, options[0][0].asset_id)
            asset = next(
                (candidate for candidate, _score in options if candidate.asset_id == selected_id),
                options[0][0],
            )
            assets_by_role[role_id] = asset
            strategy = (
                "imported_glb_exact"
                if asset.allows_generation_mode("imported_glb_exact")
                else "internal_project_generated"
            )
            components.append(
                AssemblyComponentSelection(
                    role_id=role_id,
                    asset_type=asset_type,
                    required=required,
                    candidate_scores=[score for _candidate, score in options],
                    selected_asset_id=asset.asset_id,
                    builder_profile_id=asset.builder_profile_id or default_profile,
                    generation_strategy=strategy,
                    allowed_parameter_ids=[item.parameter_id for item in asset.allowed_parameters],
                    selection_reason=_selection_reason(asset, options, decision),
                )
            )
        plan = AssemblyPlan(
            workflow_id=workflow_id,
            components=components,
            connections=_connections(components),
            selection_authority=decision["authority"],
            llm_fallback_used=decision["fallback_used"],
            llm_fallback_reason=decision.get("fallback_reason"),
        )
        return AssemblyPlanningResult(plan=plan, assets_by_role=assets_by_role)

    def _required_slots(
        self, requirements: RequirementSpec
    ) -> list[tuple[str, str, bool, str, str]]:
        slots = [
            (
                "support_structure",
                "tower",
                True,
                "tower_structure_v1",
                "internal_project_generated",
            ),
            ("sector_antenna", "antenna", True, "sector_panel_v1", "internal_project_generated"),
            ("antenna_mount", "bracket", True, "mount_bracket_v1", "internal_project_generated"),
            (
                "sector_cable_route",
                "cable",
                bool(requirements.include_cables),
                "cable_route_v1",
                "procedural_fallback",
            ),
        ]
        if requirements.include_rru:
            slots.append(
                ("remote_radio", "radio", True, "rru_enclosure_v1", "internal_project_generated")
            )
        if requirements.include_power_cabinet:
            slots.append(
                ("ground_equipment", "cabinet", True, "ground_cabinet_v1", "imported_glb_exact")
            )
        if requirements.include_gps_antenna:
            slots.append(("timing_antenna", "gps", True, "gps_radome_v1", "imported_glb_exact"))
        return slots

    def _bounded_decision(
        self, ranked: dict[str, list[tuple[AssetManifest, object]]]
    ) -> tuple[dict[str, str], dict]:
        if self.decision_client is None:
            return {}, {
                "authority": "deterministic_fallback",
                "fallback_used": True,
                "fallback_reason": "llm_asset_selector_unavailable",
            }
        slots = [
            {
                "role_id": role_id,
                "candidate_asset_ids": [asset.asset_id for asset, _score in options],
            }
            for role_id, options in ranked.items()
        ]
        selections, diagnostics = self.decision_client.decide(slots=slots)
        allowed = {
            role_id: {asset.asset_id for asset, _score in options}
            for role_id, options in ranked.items()
        }
        safe = {
            role: asset_id
            for role, asset_id in selections.items()
            if asset_id in allowed.get(role, set())
        }
        if len(safe) != len(allowed):
            return {}, {
                "authority": "deterministic_fallback",
                "fallback_used": True,
                "fallback_reason": "llm_asset_selector_output_rejected",
            }
        return safe, {
            "authority": "llm_bounded",
            "fallback_used": False,
            "fallback_reason": None,
            **diagnostics,
        }


def _selection_reason(
    asset: AssetManifest, options: list[tuple[AssetManifest, object]], decision: dict
) -> str:
    rank = next(
        index
        for index, (candidate, _score) in enumerate(options, start=1)
        if candidate.asset_id == asset.asset_id
    )
    source = (
        "Le LLM borné" if decision["authority"] == "llm_bounded" else "Le fallback déterministe"
    )
    return f"{source} a retenu le candidat classé #{rank} ; compatibilité et permissions vérifiées."


def _connections(components: list[AssemblyComponentSelection]) -> list[AssemblyConnection]:
    roles = {component.role_id for component in components}
    connections = [
        AssemblyConnection(
            connection_id="mount-to-support",
            kind="mechanical",
            source_role_id="antenna_mount",
            source_connector_id="tower_clamp",
            target_role_id="support_structure",
            target_connector_id="mount_zone",
            required=True,
        ),
        AssemblyConnection(
            connection_id="antenna-to-mount",
            kind="mechanical",
            source_role_id="sector_antenna",
            source_connector_id="rear_mount",
            target_role_id="antenna_mount",
            target_connector_id="antenna_rail",
            required=True,
        ),
    ]
    if "remote_radio" in roles:
        connections.append(
            AssemblyConnection(
                connection_id="antenna-to-radio-rf",
                kind="rf",
                source_role_id="sector_antenna",
                source_connector_id="rf_port",
                target_role_id="remote_radio",
                target_connector_id="rf_port",
                required=True,
            )
        )
    if "sector_cable_route" in roles:
        connections.append(
            AssemblyConnection(
                connection_id="radio-to-base-route",
                kind="routing",
                source_role_id="remote_radio" if "remote_radio" in roles else "sector_antenna",
                source_connector_id="cable_exit",
                target_role_id="sector_cable_route",
                target_connector_id="route_start",
                required=False,
            )
        )
    return connections
