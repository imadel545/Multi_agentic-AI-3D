from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from core.contracts.assembly import AssemblyPlan
from core.contracts.assets import AssetManifest
from core.contracts.design_blueprint import (
    BlueprintAssetQuery,
    BlueprintConstraint,
    BlueprintIssue,
    BlueprintSpecialistDecision,
    ComponentIntent,
    ConnectionIntent,
    DesignBlueprint,
)
from core.contracts.requirements import RequirementSpec
from core.contracts.rf_validation import RfValidationReport
from core.contracts.tower_validation import TowerValidationReport
from core.performance import requirements_hash


@dataclass(frozen=True)
class BlueprintContext:
    requirements: RequirementSpec
    selected_assets: tuple[AssetManifest, ...]
    tower_validation: TowerValidationReport
    rf_validation: RfValidationReport


SpecialistCallable = Callable[[BlueprintContext], BlueprintSpecialistDecision]


class BlueprintComposer:
    """Compose a typed planning blueprint through a routed specialist registry.

    The registry is intentionally deterministic today.  A future LLM may choose
    among already validated blueprint candidates, but cannot create asset IDs,
    geometry families, placement strategies or Blender code.
    """

    def __init__(
        self,
        specialists: dict[str, SpecialistCallable] | None = None,
    ) -> None:
        self._specialists = specialists or {
            "asset_composition": _asset_composition_specialist,
            "rf_layout": _rf_specialist,
            "structural_support": _structural_specialist,
        }

    def compose(
        self,
        *,
        workflow_id: str,
        requirements: RequirementSpec,
        selected_assets: list[AssetManifest],
        tower_validation: TowerValidationReport,
        rf_validation: RfValidationReport,
        planning_resolution: dict | None,
        assembly_plan: AssemblyPlan | None = None,
    ) -> DesignBlueprint:
        context = BlueprintContext(
            requirements=requirements,
            selected_assets=tuple(selected_assets),
            tower_validation=tower_validation,
            rf_validation=rf_validation,
        )
        required_domains = _required_specialist_domains(context)
        missing = [domain for domain in required_domains if domain not in self._specialists]
        if missing:
            raise ValueError(f"blueprint specialist registry is missing domains: {missing}")
        decisions = [self._specialists[domain](context) for domain in required_domains]
        components = _component_intents(requirements, selected_assets, assembly_plan)
        applied_fields = sorted(
            {
                str(decision.get("field"))
                for decision in (planning_resolution or {}).get("decisions", [])
                if isinstance(decision, dict) and decision.get("status") == "applied"
            }
        )
        issues = _open_issues(components, requirements)
        return DesignBlueprint(
            blueprint_id=f"{workflow_id}:blueprint:v1",
            workflow_id=workflow_id,
            requirements_sha256=requirements_hash(requirements),
            planning_resolution_sha256=_payload_hash(planning_resolution or {}),
            network_type=requirements.network_type,
            detail_level=requirements.detail_level,
            component_intents=components,
            connection_intents=_connection_intents(assembly_plan),
            constraints=_constraints(requirements, planning_resolution),
            required_specialist_domains=required_domains,
            specialist_decisions=decisions,
            planning_fields_applied=applied_fields,
            open_issues=issues,
        )


def design_blueprint_hash(blueprint: DesignBlueprint) -> str:
    return _payload_hash(blueprint.model_dump(mode="json"))


def _required_specialist_domains(context: BlueprintContext) -> list[str]:
    asset_types = {asset.type for asset in context.selected_assets}
    domains = ["asset_composition"]
    if "antenna" in asset_types:
        domains.append("rf_layout")
    if "tower" in asset_types:
        domains.append("structural_support")
    return sorted(domains)


def _asset_composition_specialist(context: BlueprintContext) -> BlueprintSpecialistDecision:
    assets = context.selected_assets
    checks = {
        "assets_selected": bool(assets),
        "asset_ids_unique": len({asset.asset_id for asset in assets}) == len(assets),
        "all_assets_validated": all(asset.is_validated for asset in assets),
        "all_assets_generation_eligible": all(asset.is_generation_eligible for asset in assets),
        "generation_mode_declared": all(
            bool(asset.qualification.allowed_generation_modes) for asset in assets
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return BlueprintSpecialistDecision(
        specialist_id="asset-composition-v1",
        domain="asset_composition",
        status="failed" if failures else "passed",
        actor_kind="deterministic_specialist",
        decision_authority="deterministic",
        checks=checks,
        error_codes=[f"BLUEPRINT_{name.upper()}" for name in failures],
    )


def _rf_specialist(context: BlueprintContext) -> BlueprintSpecialistDecision:
    report = context.rf_validation
    return BlueprintSpecialistDecision(
        specialist_id="rf-layout-v1",
        domain="rf_layout",
        status=report.status,
        actor_kind="deterministic_specialist",
        decision_authority="deterministic",
        checks=dict(report.checks),
        warning_codes=[warning.code for warning in report.warnings],
        error_codes=[error.code for error in report.errors],
    )


def _structural_specialist(context: BlueprintContext) -> BlueprintSpecialistDecision:
    report = context.tower_validation
    return BlueprintSpecialistDecision(
        specialist_id="structural-support-v1",
        domain="structural_support",
        status=report.status,
        actor_kind="deterministic_specialist",
        decision_authority="deterministic",
        checks=dict(report.checks),
        warning_codes=[warning.code for warning in report.warnings],
        error_codes=[error.code for error in report.errors],
    )


def _component_intents(
    requirements: RequirementSpec,
    selected_assets: list[AssetManifest],
    assembly_plan: AssemblyPlan | None,
) -> list[ComponentIntent]:
    intents: list[ComponentIntent] = []
    type_counts: dict[str, int] = {}
    role_by_asset = {
        component.selected_asset_id: component.role_id
        for component in (assembly_plan.components if assembly_plan else [])
        if component.selected_asset_id
    }
    profile_by_asset = {
        component.selected_asset_id: component.builder_profile_id
        for component in (assembly_plan.components if assembly_plan else [])
        if component.selected_asset_id
    }
    for asset in selected_assets:
        type_counts[asset.type] = type_counts.get(asset.type, 0) + 1
        suffix = type_counts[asset.type]
        per_sector = asset.type in {"antenna", "radio"}
        role_id = role_by_asset.get(
            asset.asset_id,
            {
                "tower": "support_structure",
                "antenna": "sector_antenna",
                "radio": "remote_radio",
            }.get(asset.type, asset.type),
        )
        intents.append(
            ComponentIntent(
                intent_id=f"component:{asset.type}:{suffix}",
                semantic_role_id=role_id,
                asset_type=asset.type,
                instance_strategy_id="per_sector" if per_sector else "single",
                quantity=requirements.sector_count if per_sector else 1,
                asset_query=BlueprintAssetQuery(
                    asset_type=asset.type,
                    network_type=requirements.network_type,
                    compatible_tower_type=requirements.tower_type,
                ),
                resolved_asset_id=asset.asset_id,
                generation_strategy=_generation_strategy(asset),
                geometry_profile_id=profile_by_asset.get(asset.asset_id)
                or _geometry_profile_id(asset),
                geometry_fidelity=asset.geometry_fidelity,
                placement_strategy_id=_placement_strategy(asset.type),
                provenance=[
                    "requirement_spec",
                    f"asset_manifest:{asset.asset_id}:{asset.version}",
                ],
            )
        )
    if requirements.include_cables:
        intents.append(
            ComponentIntent(
                intent_id="component:cable:1",
                semantic_role_id="sector_cable_route",
                asset_type="cable",
                instance_strategy_id="per_sector",
                quantity=requirements.sector_count,
                asset_query=BlueprintAssetQuery(
                    asset_type="cable",
                    network_type=requirements.network_type,
                    compatible_tower_type=requirements.tower_type,
                    required_capability_tags=["scene_spec_parametric_route"],
                ),
                resolved_asset_id="PARAMETRIC_SECTOR_CABLE",
                generation_strategy="parametric_generated",
                geometry_fidelity="technical_generic",
                placement_strategy_id="antenna_to_radio_or_tower_route",
                provenance=["requirement_spec", "derived_rule:cable_per_sector"],
            )
        )
    if requirements.include_beams:
        intents.append(
            ComponentIntent(
                intent_id="component:beam:1",
                semantic_role_id="sector_coverage_volume",
                asset_type="beam",
                instance_strategy_id="per_sector",
                quantity=requirements.sector_count,
                asset_query=BlueprintAssetQuery(
                    asset_type="beam",
                    network_type=requirements.network_type,
                    compatible_tower_type=requirements.tower_type,
                    required_capability_tags=["scene_spec_rf_visualization"],
                ),
                resolved_asset_id="PARAMETRIC_SECTOR_BEAM",
                generation_strategy="parametric_generated",
                geometry_fidelity="schematic",
                placement_strategy_id="sector_boresight_volume",
                provenance=["requirement_spec", "derived_rule:beam_per_sector"],
            )
        )
    return intents


def _connection_intents(assembly_plan: AssemblyPlan | None):
    if assembly_plan is None:
        return []
    return [
        ConnectionIntent(
            connection_id=connection.connection_id,
            kind=connection.kind,
            source_intent_id=_intent_id_for_role(connection.source_role_id, assembly_plan),
            target_intent_id=_intent_id_for_role(connection.target_role_id, assembly_plan),
            source_connector_role=connection.source_connector_id,
            target_connector_role=connection.target_connector_id,
            route_strategy_id="validated_connector_route",
            required=connection.required,
            provenance=["assembly_plan", "asset_manifest_connectors"],
        )
        for connection in assembly_plan.connections
        if _intent_id_for_role(connection.source_role_id, assembly_plan)
        and _intent_id_for_role(connection.target_role_id, assembly_plan)
    ]


def _intent_id_for_role(role_id: str, assembly_plan: AssemblyPlan) -> str | None:
    component = next((item for item in assembly_plan.components if item.role_id == role_id), None)
    if component is None:
        return None
    asset_type = component.asset_type
    return f"component:{asset_type}:1"


def _constraints(
    requirements: RequirementSpec,
    planning_resolution: dict | None,
) -> list[BlueprintConstraint]:
    resolution = planning_resolution or {}

    def effective(field: str, fallback):
        return resolution.get(field, fallback)

    values = [
        ("tower.height_m", "equals", requirements.tower_height_m, "requirement"),
        ("sectors.count", "equals", requirements.sector_count, "requirement"),
        ("sectors.azimuth_deg", "equals", tuple(requirements.azimuths_deg), "requirement"),
        (
            "sectors.install_height_m",
            "equals",
            effective("antenna_install_height_m", requirements.antenna_install_height_m),
            _source("antenna_install_height_m", resolution),
        ),
        (
            "sectors.beamwidth_deg",
            "equals",
            effective("beamwidth_deg", requirements.beamwidth_deg),
            _source("beamwidth_deg", resolution),
        ),
        (
            "sectors.mechanical_tilt_deg",
            "equals",
            effective("mechanical_tilt_deg", requirements.mechanical_tilt_deg),
            _source("mechanical_tilt_deg", resolution),
        ),
        (
            "sectors.electrical_tilt_deg",
            "equals",
            effective("electrical_tilt_deg", requirements.electrical_tilt_deg),
            _source("electrical_tilt_deg", resolution),
        ),
    ]
    return [
        BlueprintConstraint(
            constraint_id=f"constraint:{index + 1}",
            domain="geometry",
            field_path=path,
            operator=operator,
            value=value,
            source=source,
        )
        for index, (path, operator, value, source) in enumerate(values)
    ]


def _source(field: str, resolution: dict) -> str:
    for decision in resolution.get("decisions", []):
        if (
            isinstance(decision, dict)
            and decision.get("field") == field
            and decision.get("status") == "applied"
        ):
            return "planning_decision"
    return "requirement"


def _generation_strategy(asset: AssetManifest):
    if asset.allows_generation_mode("imported_glb_exact"):
        return "imported_glb_exact"
    if asset.allows_generation_mode("parametric_generated"):
        return "internal_project_generated"
    return "procedural_fallback"


def _geometry_profile_id(asset: AssetManifest) -> str | None:
    if asset.panel_geometry_profile is not None:
        return asset.panel_geometry_profile.family
    if asset.radio_geometry_profile is not None:
        return asset.radio_geometry_profile.family
    return None


def _placement_strategy(asset_type: str) -> str:
    return {
        "tower": "site_origin_support",
        "antenna": "sector_azimuth_mount",
        "radio": "sector_radio_mount",
        "cabinet": "ground_equipment_zone",
        "gps": "tower_top_accessory",
    }.get(asset_type, "manifest_controlled_placement")


def _open_issues(
    components: list[ComponentIntent],
    requirements: RequirementSpec,
) -> list[BlueprintIssue]:
    issues = [
        BlueprintIssue(
            code="CONNECTOR_CATALOG_NOT_OPERATIONAL",
            severity="warning",
            message=(
                "Mechanical, RF, fiber, power and grounding connector roles are not yet "
                "declared by the asset catalog; SceneSpec cable routing remains the active proof."
            ),
        )
    ]
    generic_roles = sorted(
        {
            intent.semantic_role_id
            for intent in components
            if intent.geometry_fidelity == "technical_generic"
        }
    )
    if generic_roles:
        issues.append(
            BlueprintIssue(
                code="TECHNICAL_GENERIC_NOT_VENDOR_QUALIFIED",
                severity="warning",
                message=(
                    "Generic technical geometry is used for roles: " + ", ".join(generic_roles)
                ),
            )
        )
    if requirements.network_type != "MW":
        issues.append(
            BlueprintIssue(
                code="RF_PROPAGATION_MODEL_NOT_OPERATIONAL",
                severity="warning",
                message=(
                    "Sector volumes are visual aids; no propagation, link-budget or terrain "
                    "simulation is certified by this blueprint."
                ),
            )
        )
    return issues


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
