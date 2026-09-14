from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.contracts.assembly import AssetCandidateScore
from core.contracts.assets import AssetDecisionPacket, AssetManifest
from core.contracts.cognitive_design import AssetCandidateEvidence
from core.services.asset_registry import AssetRegistry


@dataclass(frozen=True)
class QualifiedAssetCandidate:
    manifest: AssetManifest
    score: AssetCandidateScore
    packet: AssetDecisionPacket


class QualifiedAssetCandidateRetriever:
    """One fail-closed candidate boundary for telecom and cognitive planners.

    The registry remains the canonical manifest store. This service only derives
    bounded packets and evidence; it never promotes raw library catalog records.
    Generic reuse is exposed only when a manifest explicitly enables it and
    declares compatible semantic roles.
    """

    def __init__(
        self,
        registry: AssetRegistry,
        *,
        external_sources_only: bool = False,
    ) -> None:
        self.external_sources_only = external_sources_only
        self.registry = registry
        self.evidence_verifier = registry.evidence_verifier

    def _source_allowed(self, manifest: AssetManifest) -> bool:
        from core.validation.library_first import has_external_geometry_source

        return not self.external_sources_only or has_external_geometry_source(manifest)

    def available_semantic_roles(self) -> list[str]:
        """Expose only roles backed by an admitted cognitive-reuse manifest."""

        return sorted(
            {
                role.strip().lower()
                for manifest in self.registry.list_assets()
                if manifest.cognitive_reuse_enabled
                and self.registry.is_generation_admitted(manifest)
                and self._source_allowed(manifest)
                for role in manifest.compatibility_rules.compatible_roles
                if role.strip()
            }
        )

    def rank_telecom(
        self,
        *,
        asset_type: str,
        network_type: str,
        tower_type: str | None = None,
        min_height_m: float | None = None,
        role_id: str | None = None,
        required_connectors: dict[str, str] | None = None,
    ) -> list[QualifiedAssetCandidate]:
        ranked = self.registry.rank_candidates(
            asset_type=asset_type,
            network_type=network_type,
            tower_type=tower_type,
            min_height_m=min_height_m,
        )
        compatible = [
            (manifest, score)
            for manifest, score in ranked
            if _supports_telecom_role(
                manifest,
                role_id=role_id,
                required_connectors=required_connectors or {},
            )
        ]
        if not compatible:
            requested_role = role_id or asset_type
            raise LookupError(
                f"no qualified {asset_type} asset satisfies telecom role {requested_role}"
            )
        return [
            QualifiedAssetCandidate(
                manifest=manifest,
                score=score,
                packet=self.packet_for(manifest, rejection_risks=[]),
            )
            for manifest, score in compatible
        ]

    def search(self, component: dict[str, Any]) -> list[AssetCandidateEvidence]:
        role = str(component.get("semantic_role") or "").strip().lower()
        if not role:
            return []
        target_dimensions = component.get("target_dimensions_m")
        query_tokens = _component_tokens(component)
        evidence: list[AssetCandidateEvidence] = []
        for manifest in self.registry.list_assets():
            if not self._source_allowed(manifest):
                continue
            if not manifest.cognitive_reuse_enabled or not self.registry.is_generation_admitted(
                manifest
            ):
                continue
            compatible_roles = {
                item.strip().lower() for item in manifest.compatibility_rules.compatible_roles
            }
            if role not in compatible_roles:
                continue
            packet = self.packet_for(manifest, rejection_risks=[])
            function_score = _lexical_function_score(query_tokens, manifest)
            dimension_score = _dimension_score(target_dimensions, manifest)
            material_score = _material_score(component, manifest)
            provenance_score = _provenance_score(manifest)
            compatibility_score = 100.0
            qa_risk = _qa_risk(manifest)
            estimated_cost = _estimated_cost(manifest)
            evidence.append(
                AssetCandidateEvidence(
                    candidate_id=manifest.asset_id,
                    source_kind="component",
                    qualified=True,
                    compatibility_score=compatibility_score,
                    function_score=function_score,
                    dimension_score=dimension_score,
                    material_score=material_score,
                    provenance_score=provenance_score,
                    estimated_cost=estimated_cost,
                    qa_risk=qa_risk,
                    allowed_strategies=_cognitive_strategies(manifest),
                    allowed_parameter_ids=[
                        parameter.parameter_id for parameter in manifest.allowed_parameters
                    ],
                    limitations=(
                        packet.rejection_risks
                        + [
                            "Reuse supports one rigid component with explicit placement. "
                            "Compose supports one "
                            "required aligned_with driver with offset_world_m "
                            "and matched orientation; "
                            "it does not certify contact, collision or fastening."
                        ]
                    )[:32],
                    decision_packet=packet,
                )
            )
        return sorted(
            evidence,
            key=lambda item: (
                -_evidence_total(item),
                item.candidate_id,
            ),
        )

    def packet_for(
        self,
        manifest: AssetManifest,
        *,
        rejection_risks: list[str] | None = None,
    ) -> AssetDecisionPacket:
        risks = list(manifest.qualification.limitations)
        risks.extend(manifest.qa_evidence.limitations)
        if not manifest.preview_set:
            risks.append("No qualified per-asset preview set is published.")
        if manifest.qa_evidence.status != "passed":
            risks.append("Professional asset QA has not passed.")
        evidence = self.evidence_verifier.verify(manifest)
        admission = self.evidence_verifier.verify_effective_generation_admission(manifest)
        risks.extend(admission.failures)
        risks.extend(evidence.failures)
        risks.extend(rejection_risks or [])
        risks = list(dict.fromkeys(risks))[:32]
        return AssetDecisionPacket(
            asset_id=manifest.asset_id,
            asset_type=manifest.type,
            family=manifest.resolved_family,
            subtype=manifest.subtype,
            manufacturer=manifest.manufacturer,
            reference=manifest.reference,
            source_provenance=(
                manifest.source_provenance
                or manifest.attribution
                or manifest.original_url
                or manifest.source
            ),
            license=manifest.license,
            usage_rights=manifest.usage_rights,
            source_format=manifest.resolved_source_format,
            source_file_sha256=manifest.source_file_sha256,
            geometry_status=manifest.resolved_geometry_status,
            conversion_method=manifest.conversion_method,
            geometry_fidelity=manifest.geometry_fidelity,
            qualification_status=manifest.qualification.status,
            generation_eligible=admission.eligible,
            milestone_evidence_eligible=evidence.eligible,
            dimensions_m=manifest.dimensions_m,
            bounding_box_m=manifest.bounding_box_m,
            master_representation=manifest.master_representation,
            viewer_representation=manifest.viewer_representation,
            previews=manifest.preview_set,
            lods=manifest.lods,
            anchors=manifest.anchors,
            connectors=manifest.connectors,
            editable_parameters=manifest.allowed_parameters,
            transform_permissions=manifest.transform_permissions,
            compatibility=manifest.compatibility_rules,
            builder_capability_id=manifest.builder_profile_id,
            adapter_capability_id=manifest.adapter_capability_id,
            qa=manifest.qa_evidence,
            qualification_version=manifest.qualification_version,
            allowed_generation_modes=(
                manifest.qualification.allowed_generation_modes if admission.eligible else []
            ),
            allowed_strategies=_decision_packet_strategies(
                manifest,
                generation_admitted=admission.eligible,
            ),
            estimated_blender_cost=_cost_class(manifest),
            rejection_risks=risks,
        )


def _decision_packet_strategies(
    manifest: AssetManifest,
    *,
    generation_admitted: bool,
) -> list[str]:
    if not generation_admitted:
        return []
    strategies = []
    if manifest.allows_generation_mode("imported_glb_exact"):
        strategies.append("reuse_component")
    if manifest.allows_generation_mode("parametric_generated"):
        strategies.append("compose_assets")
    if manifest.allowed_parameters or manifest.adapter_capability_id:
        strategies.append("adapt_component")
    return strategies


def _supports_telecom_role(
    manifest: AssetManifest,
    *,
    role_id: str | None,
    required_connectors: dict[str, str],
) -> bool:
    """Reject candidates whose declared interfaces cannot satisfy a planner slot.

    Legacy parametric assets may omit compatible_roles because their geometry is
    generated by a bounded builder. Exact imports must opt into the requested
    semantic role explicitly; geometric fidelity alone cannot establish that a
    mesh is a usable telecom component.
    """

    if role_id:
        compatible_roles = {
            item.strip().lower()
            for item in manifest.compatibility_rules.compatible_roles
            if item.strip()
        }
        normalized_role = role_id.strip().lower()
        if compatible_roles and normalized_role not in compatible_roles:
            return False
        # remote_radio currently carries the strictest functional contract: an
        # exact mesh must declare that it is a radio, not merely resemble an
        # enclosure. Other legacy exact roles will adopt this rule as their
        # manifests gain explicit role declarations.
        if (
            normalized_role == "remote_radio"
            and manifest.allows_generation_mode("imported_glb_exact")
            and normalized_role not in compatible_roles
        ):
            return False

    connectors = {connector.connector_id: connector.kind for connector in manifest.connectors}
    return all(
        connectors.get(connector_id) == connector_kind
        for connector_id, connector_kind in required_connectors.items()
    )


def _cognitive_strategies(manifest: AssetManifest) -> list[str]:
    return (
        list(manifest.cognitive_reuse_strategies or ["reuse", "compose"])
        if manifest.cognitive_reuse_enabled
        and manifest.is_generation_eligible
        and manifest.allows_generation_mode("imported_glb_exact")
        else []
    )


def _component_tokens(component: dict[str, Any]) -> set[str]:
    values: list[str] = [
        str(component.get("semantic_role") or ""),
        str(component.get("description") or ""),
    ]
    values.extend(str(value) for value in component.get("functions") or [])
    return _tokens(" ".join(values))


def _manifest_tokens(manifest: AssetManifest) -> set[str]:
    values = [
        manifest.asset_id,
        manifest.type,
        manifest.resolved_family,
        manifest.subtype or "",
        manifest.manufacturer or "",
        manifest.reference or "",
        " ".join(manifest.capability_tags),
        " ".join(manifest.compatibility_rules.compatible_roles),
    ]
    return _tokens(" ".join(values))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 2}


def _lexical_function_score(query_tokens: set[str], manifest: AssetManifest) -> float:
    if not query_tokens:
        return 50.0
    overlap = len(query_tokens & _manifest_tokens(manifest))
    return round(min(100.0, 40.0 + 60.0 * overlap / max(1, len(query_tokens))), 2)


def _dimension_score(target: Any, manifest: AssetManifest) -> float:
    if not isinstance(target, dict) or manifest.dimensions_m is None:
        return 50.0
    requested = [target.get(axis) for axis in ("x", "y", "z")]
    if any(not isinstance(value, (int, float)) or value <= 0 for value in requested):
        return 50.0
    actual = [
        manifest.dimensions_m.width,
        manifest.dimensions_m.depth,
        manifest.dimensions_m.height,
    ]
    relative_errors = [
        abs(float(expected) - value) / float(expected)
        for expected, value in zip(requested, actual, strict=True)
    ]
    return round(max(0.0, 100.0 * (1.0 - sum(relative_errors) / len(relative_errors))), 2)


def _material_score(component: dict[str, Any], manifest: AssetManifest) -> float:
    requested = _tokens(" ".join(str(value) for value in component.get("material_intent") or []))
    if not requested:
        return 50.0
    declared = _tokens(" ".join(manifest.material_names))
    if not declared:
        return 25.0
    return round(100.0 * len(requested & declared) / len(requested), 2)


def _provenance_score(manifest: AssetManifest) -> float:
    score = 20.0
    if manifest.license:
        score += 25.0
    if manifest.source_file_sha256 or manifest.qualification.verified_file_sha256:
        score += 25.0
    if manifest.manufacturer and manifest.reference:
        score += 15.0
    if manifest.master_representation and manifest.viewer_representation:
        score += 15.0
    return min(100.0, score)


def _qa_risk(manifest: AssetManifest) -> float:
    return {
        "passed": 10.0,
        "limited": 45.0,
        "not_run": 70.0,
        "failed": 100.0,
    }[manifest.qa_evidence.status]


def _cost_class(manifest: AssetManifest) -> str:
    if manifest.allows_generation_mode("imported_glb_exact"):
        return "low"
    if manifest.allows_generation_mode("parametric_generated"):
        return "medium"
    return "high"


def _estimated_cost(manifest: AssetManifest) -> float:
    return {"low": 20.0, "medium": 50.0, "high": 90.0}[_cost_class(manifest)]


def _evidence_total(candidate: AssetCandidateEvidence) -> float:
    return (
        candidate.compatibility_score * 0.3
        + candidate.function_score * 0.2
        + candidate.dimension_score * 0.15
        + candidate.material_score * 0.1
        + candidate.provenance_score * 0.15
        + (100.0 - candidate.qa_risk) * 0.1
    )
