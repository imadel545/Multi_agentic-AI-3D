from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.contracts.assembly import AssemblyComponentSelection, AssemblyConnection, AssemblyPlan
from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.services.asset_registry import AssetRegistry
from core.services.builder_registry import BuilderRegistry
from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever


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
        self,
        registry: AssetRegistry,
        decision_client: BoundedAssemblyDecisionClient | None = None,
        builder_registry: BuilderRegistry | None = None,
        candidate_retriever: QualifiedAssetCandidateRetriever | None = None,
    ) -> None:
        self.registry = registry
        self.decision_client = decision_client
        self.candidate_retriever = candidate_retriever or QualifiedAssetCandidateRetriever(registry)
        self.builder_registry = builder_registry or BuilderRegistry(
            registry.manifests_dir.parent / "capabilities" / "builder_profiles.json"
        )

    def plan(self, *, workflow_id: str, requirements: RequirementSpec) -> AssemblyPlanningResult:
        slots = self._required_slots(requirements)
        ranked: dict[str, list[tuple[AssetManifest, object]]] = {}
        for role_id, asset_type, _required in slots:
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
            qualified_candidates = self.candidate_retriever.rank_telecom(
                asset_type=asset_type,
                network_type=requirements.network_type,
                tower_type=requirements.tower_type,
                min_height_m=requirements.tower_height_m if asset_type == "tower" else None,
                role_id=role_id,
                required_connectors=_required_candidate_connectors(role_id, requirements),
            )
            ranked[role_id] = [
                (candidate.manifest, candidate.score) for candidate in qualified_candidates
            ]
        selected_ids, decision = self._bounded_decision(ranked)
        components: list[AssemblyComponentSelection] = []
        assets_by_role: dict[str, AssetManifest] = {}
        for role_id, asset_type, required in slots:
            options = ranked[role_id]
            selected_id = selected_ids.get(role_id, options[0][0].asset_id)
            asset = next(
                (candidate for candidate, _score in options if candidate.asset_id == selected_id),
                options[0][0],
            )
            assets_by_role[role_id] = asset
            strategy = (decision.get("generation_strategies") or {}).get(role_id)
            if strategy is None:
                strategy = _deterministic_generation_strategy(asset)
            if strategy not in _allowed_assembly_strategies(asset):
                raise ValueError(
                    f"ASSET_GENERATION_STRATEGY_NOT_ALLOWED:{asset.asset_id}:{strategy}"
                )
            semantic_strategy = (decision.get("semantic_strategies") or {}).get(role_id)
            if semantic_strategy is None:
                semantic_strategy = _deterministic_semantic_strategy(asset, strategy)
            if semantic_strategy not in _allowed_semantic_strategies(asset, strategy):
                raise ValueError(
                    "ASSET_SEMANTIC_STRATEGY_NOT_ALLOWED:"
                    f"{asset.asset_id}:{strategy}:{semantic_strategy}"
                )
            manifest_generation_mode = (
                "imported_glb_exact" if strategy == "imported_glb_exact" else "parametric_generated"
            )
            if asset.builder_profile_id is None:
                raise ValueError(f"ASSET_BUILDER_PROFILE_MISSING:{asset.asset_id}")
            builder_profile = self.builder_registry.resolve(asset.builder_profile_id)
            if asset.type not in builder_profile.asset_types:
                raise ValueError(
                    f"BUILDER_ASSET_TYPE_INCOMPATIBLE:{asset.builder_profile_id}:{asset.type}"
                )
            if manifest_generation_mode not in builder_profile.allowed_generation_modes:
                raise ValueError(
                    "BUILDER_GENERATION_MODE_INCOMPATIBLE:"
                    f"{asset.builder_profile_id}:{manifest_generation_mode}"
                )
            manifest_parameters = {item.parameter_id for item in asset.allowed_parameters}
            if not manifest_parameters.issubset(builder_profile.allowed_parameter_ids):
                raise ValueError(f"BUILDER_PARAMETER_ALLOWLIST_MISMATCH:{asset.builder_profile_id}")
            selected_packet = self.candidate_retriever.packet_for(asset)
            components.append(
                AssemblyComponentSelection(
                    role_id=role_id,
                    asset_type=asset_type,
                    required=required,
                    candidate_scores=[score for _candidate, score in options],
                    selected_asset_id=asset.asset_id,
                    builder_profile_id=asset.builder_profile_id,
                    generation_strategy=strategy,
                    semantic_strategy=semantic_strategy,
                    allowed_parameter_ids=[item.parameter_id for item in asset.allowed_parameters],
                    parameter_values=_parameter_values(asset, requirements),
                    manifest_snapshot=self.registry.manifest_snapshot(
                        asset.asset_id,
                        generation_mode=manifest_generation_mode,
                    ),
                    builder_profile=builder_profile,
                    requirement_links=_requirement_links(role_id),
                    blueprint_links=[f"component:{asset.type}:1"],
                    selection_risks=selected_packet.rejection_risks,
                    selection_reason=_selection_reason(role_id, asset, options, decision),
                )
            )
        plan = AssemblyPlan(
            schema_version="1.1.0",
            workflow_id=workflow_id,
            components=components,
            connections=_connections(components),
            selection_authority=decision["authority"],
            selection_provider=decision.get("provider"),
            selection_model=decision.get("model_name"),
            llm_fallback_used=decision["fallback_used"],
            llm_fallback_reason=decision.get("fallback_reason"),
            compilation_status="declared",
            manifest_catalog_sha256=self.registry.manifest_hash,
        )
        return AssemblyPlanningResult(plan=plan, assets_by_role=assets_by_role)

    def _required_slots(self, requirements: RequirementSpec) -> list[tuple[str, str, bool]]:
        slots = [
            ("support_structure", "tower", True),
            ("sector_antenna", "antenna", True),
            ("antenna_mount", "bracket", True),
        ]
        if requirements.include_cables:
            slots.append(("sector_cable_route", "cable", True))
        if requirements.include_rru:
            slots.append(("remote_radio", "radio", True))
        if requirements.include_power_cabinet:
            slots.append(("ground_equipment", "cabinet", True))
        if requirements.include_gps_antenna:
            slots.append(("timing_antenna", "gps", True))
        return slots

    def _bounded_decision(
        self, ranked: dict[str, list[tuple[AssetManifest, object]]]
    ) -> tuple[dict[str, str], dict]:
        if self.decision_client is None:
            return {}, {
                "authority": "deterministic_fallback",
                "provider": "deterministic",
                "model_name": None,
                "fallback_used": True,
                "fallback_reason": "llm_asset_selector_unavailable",
            }
        slots = [
            {
                "role_id": role_id,
                "candidate_asset_ids": [asset.asset_id for asset, _score in options],
                "candidates": [
                    {
                        "asset_id": asset.asset_id,
                        "asset_type": asset.type,
                        "score": score.model_dump(mode="json"),
                        "dimensions_m": (
                            asset.dimensions_m.model_dump(mode="json")
                            if asset.dimensions_m is not None
                            else None
                        ),
                        "compatible_networks": asset.compatible_networks,
                        "compatible_tower_types": asset.compatible_tower_types,
                        "geometry_fidelity": asset.geometry_fidelity,
                        "allowed_generation_strategies": _allowed_assembly_strategies(asset),
                        "allowed_semantic_strategies": _allowed_semantic_strategies(asset),
                        "allowed_parameter_ids": [
                            parameter.parameter_id for parameter in asset.allowed_parameters
                        ],
                        "builder_profile_id": asset.builder_profile_id,
                        "qualification_limitations": asset.qualification.limitations,
                        "asset_decision_packet": self.candidate_retriever.packet_for(
                            asset
                        ).model_dump(mode="json"),
                    }
                    for asset, score in options
                ],
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
                "provider": diagnostics.get("provider", "deterministic"),
                "model_name": diagnostics.get("model_name"),
                "fallback_used": True,
                "fallback_reason": diagnostics.get("fallback_reason")
                or "llm_asset_selector_output_rejected",
            }
        generation_strategies = diagnostics.get("generation_strategies") or {}
        semantic_strategies = diagnostics.get("semantic_strategies") or {}
        selected_assets = {
            role_id: next(asset for asset, _score in ranked[role_id] if asset.asset_id == asset_id)
            for role_id, asset_id in safe.items()
        }
        if set(generation_strategies) != set(allowed) or any(
            generation_strategies[role_id] not in _allowed_assembly_strategies(asset)
            for role_id, asset in selected_assets.items()
        ):
            return {}, {
                "authority": "deterministic_fallback",
                "provider": diagnostics.get("provider", "deterministic"),
                "model_name": diagnostics.get("model_name"),
                "fallback_used": True,
                "fallback_reason": "llm_asset_strategy_output_rejected",
            }
        if set(semantic_strategies) != set(allowed) or any(
            semantic_strategies[role_id]
            not in _allowed_semantic_strategies(
                asset,
                generation_strategies.get(role_id),
            )
            for role_id, asset in selected_assets.items()
        ):
            return {}, {
                "authority": "deterministic_fallback",
                "provider": diagnostics.get("provider", "deterministic"),
                "model_name": diagnostics.get("model_name"),
                "fallback_used": True,
                "fallback_reason": "llm_asset_semantic_strategy_output_rejected",
            }
        return safe, {
            "authority": "llm_bounded",
            "fallback_used": False,
            "fallback_reason": None,
            **diagnostics,
        }


def _selection_reason(
    role_id: str,
    asset: AssetManifest,
    options: list[tuple[AssetManifest, object]],
    decision: dict,
) -> str:
    rank = next(
        index
        for index, (candidate, _score) in enumerate(options, start=1)
        if candidate.asset_id == asset.asset_id
    )
    source = (
        "Le LLM borné" if decision["authority"] == "llm_bounded" else "Le fallback déterministe"
    )
    model_reason = (decision.get("selection_reasons_by_role") or {}).get(role_id)
    if model_reason is None:
        model_reason = (decision.get("selection_reasons") or {}).get(asset.asset_id)
    if model_reason and decision["authority"] == "llm_bounded":
        return f"{source} a retenu le candidat classé #{rank} ; motif structuré : {model_reason}"
    return f"{source} a retenu le candidat classé #{rank} ; compatibilité et permissions vérifiées."


def _allowed_assembly_strategies(asset: AssetManifest) -> list[str]:
    strategies = []
    if asset.allows_generation_mode("imported_glb_exact"):
        strategies.append("imported_glb_exact")
    if asset.allows_generation_mode("parametric_generated"):
        strategies.append("internal_project_generated")
    if not strategies:
        raise ValueError(f"ASSET_HAS_NO_EXECUTABLE_GENERATION_STRATEGY:{asset.asset_id}")
    return strategies


def _deterministic_generation_strategy(asset: AssetManifest) -> str:
    strategies = _allowed_assembly_strategies(asset)
    return "imported_glb_exact" if "imported_glb_exact" in strategies else strategies[0]


def _allowed_semantic_strategies(
    asset: AssetManifest,
    generation_strategy: str | None = None,
) -> list[str]:
    generation_strategies = (
        [generation_strategy]
        if generation_strategy is not None
        else _allowed_assembly_strategies(asset)
    )
    semantics: list[str] = []
    if "imported_glb_exact" in generation_strategies:
        semantics.append("reuse_component")
    if "internal_project_generated" in generation_strategies:
        semantics.append("compose_assets")
    if asset.allowed_parameters or asset.adapter_capability_id:
        semantics.append("adapt_component")
    return list(dict.fromkeys(semantics))


def _deterministic_semantic_strategy(
    asset: AssetManifest,
    generation_strategy: str,
) -> str:
    strategies = _allowed_semantic_strategies(asset, generation_strategy)
    preferred = (
        "reuse_component" if generation_strategy == "imported_glb_exact" else "compose_assets"
    )
    return preferred if preferred in strategies else strategies[0]


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
                connection_id="radio-to-mount",
                kind="mechanical",
                source_role_id="remote_radio",
                source_connector_id="rear_mount",
                target_role_id="antenna_mount",
                target_connector_id="radio_rail",
                required=True,
            )
        )
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


def _required_candidate_connectors(
    role_id: str,
    requirements: RequirementSpec,
) -> dict[str, str]:
    if role_id != "remote_radio":
        return {}
    connectors = {
        "rear_mount": "mechanical",
        "rf_port": "rf",
    }
    if requirements.include_cables:
        connectors["cable_exit"] = "routing"
    return connectors


def _parameter_values(asset: AssetManifest, requirements: RequirementSpec) -> dict:
    allowed = {item.parameter_id for item in asset.allowed_parameters}
    values: dict[str, float | int | bool | str] = {}
    if "height_m" in allowed:
        values["height_m"] = float(requirements.tower_height_m)
    if "base_width_m" in allowed and requirements.tower_characteristics.base_width_m is not None:
        values["base_width_m"] = float(requirements.tower_characteristics.base_width_m)
    if "vertical_offset_m" in allowed and asset.radio_geometry_profile is not None:
        values["vertical_offset_m"] = float(asset.radio_geometry_profile.vertical_offset_m)
    if "radial_inset_m" in allowed and asset.radio_geometry_profile is not None:
        values["radial_inset_m"] = float(asset.radio_geometry_profile.radial_inset_m)
    return values


def _requirement_links(role_id: str) -> list[str]:
    mapping = {
        "support_structure": ["tower_type", "tower_height_m", "tower_characteristics"],
        "sector_antenna": ["network_type", "sector_count", "azimuths_deg"],
        "antenna_mount": ["tower_type", "antenna_install_height_m"],
        "remote_radio": ["include_rru", "sector_count"],
        "sector_cable_route": ["include_cables", "sector_count"],
        "ground_equipment": ["include_power_cabinet"],
        "timing_antenna": ["include_gps_antenna"],
    }
    return mapping.get(role_id, [role_id])
