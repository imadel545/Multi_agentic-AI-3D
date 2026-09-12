from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.contracts.assets import (
    AssetAnchor,
    AssetBoundingBoxM,
    AssetCompatibilityRules,
    AssetConnector,
    AssetManifest,
    AssetPreview,
    AssetQaEvidence,
    AssetQualification,
    AssetRepresentation,
    AssetTransformPermissions,
    DimensionsM,
)
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_evidence import ProfessionalAssetVerifier
from core.services.asset_registry import AssetRegistry
from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever
from core.services.requirement_parser import parse_requirements_text

MANIFESTS_DIR = Path("assets/manifests")


def test_legacy_manifests_load_and_emit_truthful_decision_packets() -> None:
    registry = AssetRegistry(MANIFESTS_DIR)
    retriever = QualifiedAssetCandidateRetriever(registry)

    candidates = retriever.rank_telecom(
        asset_type="antenna",
        network_type="5G",
        tower_type="lattice_tower",
    )

    assert [candidate.manifest.asset_id for candidate in candidates] == [
        "ANT_PANEL_5G_001",
        "ANT_PANEL_5G_DUALBAND_V1",
    ]
    minimal = candidates[0].packet
    qualified = candidates[1].packet
    assert minimal.geometry_status == "reconstructed_parametric"
    assert minimal.milestone_evidence_eligible is False
    assert qualified.generation_eligible is True
    assert qualified.milestone_evidence_eligible is False
    assert qualified.allowed_strategies == [
        "compose_assets",
        "adapt_component",
    ]
    assert "No qualified per-asset preview set is published." in qualified.rejection_risks
    assert "Master and viewer representations are not both published." in (
        qualified.rejection_risks
    )


def test_raw_dwg_acis_cannot_be_promoted_to_generation() -> None:
    with pytest.raises(ValidationError, match="non-executable asset geometry"):
        AssetManifest(
            asset_id="RAW_ACIS_TOWER",
            type="tower",
            file="assets/library/raw_tower.dwg",
            source_format="dwg",
            source_contains_acis_3d_solids=True,
            geometry_status="source_only",
            compatible_networks=["5G"],
            compatible_tower_types=["lattice_tower"],
            builder_profile_id="tower_structure_v1",
            qualification=AssetQualification(
                status="qualified_for_generation",
                allowed_generation_modes=["parametric_generated"],
            ),
        )


def test_neutral_acis_route_requires_brep_master_and_hashed_viewer_lineage() -> None:
    master = AssetRepresentation(
        representation_id="master_step",
        role="master",
        format="step",
        file="assets/qualified/tower.step",
        sha256="a" * 64,
        units="millimeters",
    )
    viewer = AssetRepresentation(
        representation_id="viewer_glb",
        role="viewer",
        format="glb",
        file="assets/qualified/tower.glb",
        sha256="b" * 64,
        units="meters",
        derived_from_representation_id="master_step",
        tessellation_tolerance_m=0.001,
    )
    manifest = AssetManifest(
        asset_id="NEUTRAL_ACIS_TOWER",
        type="tower",
        file=viewer.file,
        family="telecom_structure",
        manufacturer="Authorized manufacturer",
        reference="TOWER-36M",
        source_provenance="Authorized DWG plus STEP AP242 export.",
        source_format="dwg",
        source_file_sha256="c" * 64,
        source_contains_acis_3d_solids=True,
        geometry_status="neutral_format_conversion",
        conversion_method="FreeCAD/OpenCascade controlled STEP tessellation",
        master_representation=master,
        viewer_representation=viewer,
        compatible_networks=["4G", "5G"],
        compatible_tower_types=["lattice_tower"],
        builder_profile_id="tower_structure_v1",
        transform_permissions=AssetTransformPermissions(),
        import_fallback_allowed=False,
        qualification=AssetQualification(
            status="qualified_for_generation",
            allowed_generation_modes=["imported_glb_exact"],
            verified_file_sha256="b" * 64,
            mesh_integrity_verified=True,
            dimensions_verified=True,
            pivot_verified=True,
            orientation_verified=True,
        ),
    )

    packet = QualifiedAssetCandidateRetriever(AssetRegistry(MANIFESTS_DIR)).packet_for(manifest)

    assert packet.geometry_status == "neutral_format_conversion"
    assert packet.master_representation is not None
    assert packet.viewer_representation is not None
    assert packet.viewer_representation.derived_from_representation_id == "master_step"
    assert packet.milestone_evidence_eligible is False


def test_professional_milestone_declaration_cannot_replace_runtime_evidence(
    tmp_path: Path,
) -> None:
    master = AssetRepresentation(
        representation_id="master_step",
        role="master",
        format="step",
        file="assets/qualified/panel.step",
        sha256="a" * 64,
        units="millimeters",
    )
    viewer = AssetRepresentation(
        representation_id="viewer_glb",
        role="viewer",
        format="glb",
        file="assets/qualified/panel.glb",
        sha256="b" * 64,
        units="meters",
        derived_from_representation_id="master_step",
        tessellation_tolerance_m=0.0005,
    )
    manifest = AssetManifest(
        asset_id="PROFESSIONAL_PANEL",
        type="antenna",
        file=viewer.file,
        family="sector_panel",
        manufacturer="Authorized manufacturer",
        reference="PANEL-001",
        source="vendor_supplied",
        source_provenance="Authorized STEP AP242 export from the source assembly.",
        source_format="step",
        source_file_sha256="a" * 64,
        geometry_status="neutral_format_conversion",
        conversion_method="FreeCAD/OpenCascade controlled tessellation",
        geometry_fidelity="vendor_qualified",
        license="Project-authorized engineering use",
        master_representation=master,
        viewer_representation=viewer,
        dimensions_m=DimensionsM(width=0.42, depth=0.18, height=1.4),
        bounding_box_m=AssetBoundingBoxM(
            minimum=(-0.21, -0.09, 0.0),
            maximum=(0.21, 0.09, 1.4),
        ),
        preview_set=[
            AssetPreview(
                view=view,
                file=f"assets/qualified/previews/panel-{view}.png",
                sha256=str(index) * 64,
                width_px=1024,
                height_px=1024,
                qa_status="passed",
            )
            for index, view in enumerate(
                ["front", "side", "top", "perspective", "closeup"],
                start=1,
            )
        ],
        compatible_networks=["4G", "5G"],
        compatible_tower_types=["lattice_tower", "monopole"],
        compatibility_rules=AssetCompatibilityRules(
            compatible_roles=["sector_antenna"],
            required_connector_kinds=["mechanical"],
        ),
        builder_profile_id="qualified_asset_import_v1",
        anchors=[
            AssetAnchor(
                anchor_id="rear_mount",
                position_m=(0.0, -0.09, 0.7),
                normal=(0.0, -1.0, 0.0),
                roles=["tower_mount"],
            )
        ],
        connectors=[
            AssetConnector(
                connector_id="rear_mount_mechanical",
                kind="mechanical",
                anchor_id="rear_mount",
                compatible_connector_kinds=["mechanical"],
            )
        ],
        transform_permissions=AssetTransformPermissions(
            translation_axes=["x", "y", "z"],
            rotation_axes=["z"],
            maximum_translation_m=100.0,
            maximum_rotation_deg=360.0,
        ),
        import_fallback_allowed=False,
        qa_evidence=AssetQaEvidence(
            status="passed",
            report_file="assets/qualified/panel-qa.json",
            report_sha256="d" * 64,
            checks=["mesh_integrity", "dimensions", "pivot", "orientation"],
        ),
        qualification_version="m1.1",
        qualification=AssetQualification(
            status="qualified_for_generation",
            allowed_generation_modes=["imported_glb_exact"],
            verified_file_sha256="b" * 64,
            mesh_integrity_verified=True,
            dimensions_verified=True,
            pivot_verified=True,
            orientation_verified=True,
        ),
    )

    assert manifest.milestone_evidence_declaration_failures == []
    packet = QualifiedAssetCandidateRetriever(
        AssetRegistry(
            MANIFESTS_DIR,
            evidence_verifier=ProfessionalAssetVerifier(tmp_path),
        )
    ).packet_for(manifest)
    assert packet.milestone_evidence_eligible is False
    assert "Master representation file is missing." in packet.rejection_risks
    assert packet.generation_eligible is False
    assert packet.allowed_generation_modes == []
    assert packet.allowed_strategies == []


def test_generic_retrieval_requires_explicit_cognitive_execution_authorization(
    tmp_path: Path,
) -> None:
    source_registry = AssetRegistry(MANIFESTS_DIR)
    base = source_registry.get("ANT_PANEL_4G_001")
    authorized = base.model_copy(
        update={
            "asset_id": "AUTHORIZED_GENERIC_PANEL",
            "family": "sector_panel",
            "source": "internal_project_generated",
            "cognitive_reuse_enabled": True,
            "compatibility_rules": AssetCompatibilityRules(
                compatible_roles=["sector_antenna"],
                required_connector_kinds=["mechanical", "rf"],
                maximum_adaptation_effort="low",
            ),
        }
    )
    (tmp_path / "AUTHORIZED_GENERIC_PANEL.json").write_text(
        authorized.model_dump_json(indent=2),
        encoding="utf-8",
    )
    retriever = QualifiedAssetCandidateRetriever(AssetRegistry(tmp_path))

    results = retriever.search(
        {
            "component_id": "sector_one",
            "semantic_role": "sector_antenna",
            "description": "Panel antenna for radio coverage",
            "functions": ["radio coverage"],
            "target_dimensions_m": {"x": 0.42, "y": 0.169, "z": 1.4},
            "material_intent": [],
        }
    )

    assert len(results) == 1
    assert results[0].candidate_id == "AUTHORIZED_GENERIC_PANEL"
    assert results[0].decision_packet is not None
    assert results[0].decision_packet.compatibility.compatible_roles == ["sector_antenna"]
    assert results[0].allowed_strategies == ["reuse", "compose"]
    assert any("one rigid" in limitation for limitation in results[0].limitations)


def test_current_catalog_does_not_fake_generic_reuse_without_authorization() -> None:
    retriever = QualifiedAssetCandidateRetriever(AssetRegistry(MANIFESTS_DIR))

    assert (
        retriever.search(
            {
                "component_id": "access_structure",
                "semantic_role": "access_structure",
                "description": "Steel access platform",
                "functions": ["safe access"],
            }
        )
        == []
    )


class _RuntimeClientStub:
    model = "openai/gpt-oss-120b"


def test_cognitive_runtime_reuses_the_canonical_asset_registry() -> None:
    from core.services.cognitive_runtime import build_cognitive_design_planner

    asset_registry = AssetRegistry(MANIFESTS_DIR)

    planner = build_cognitive_design_planner(_RuntimeClientStub(), asset_registry)  # type: ignore[arg-type]

    assert isinstance(planner.candidate_retriever, QualifiedAssetCandidateRetriever)
    assert planner.candidate_retriever.registry is asset_registry


class _CapturingDecisionClient:
    def __init__(self) -> None:
        self.slots: list[dict] = []

    def decide(self, *, slots: list[dict]) -> tuple[dict[str, str], dict]:
        self.slots = slots
        selections = {slot["role_id"]: slot["candidates"][0]["asset_id"] for slot in slots}
        strategies = {
            slot["role_id"]: slot["candidates"][0]["allowed_generation_strategies"][0]
            for slot in slots
        }
        semantic_strategies = {
            slot["role_id"]: next(
                semantic
                for semantic in slot["candidates"][0]["allowed_semantic_strategies"]
                if semantic
                in (
                    {"reuse_component", "adapt_component"}
                    if strategies[slot["role_id"]] == "imported_glb_exact"
                    else {"compose_assets", "adapt_component"}
                )
            )
            for slot in slots
        }
        return selections, {
            "provider": "controlled_test",
            "model_name": "bounded-test-selector",
            "generation_strategies": strategies,
            "semantic_strategies": semantic_strategies,
            "selection_reasons_by_role": {
                slot["role_id"]: "Best bounded candidate." for slot in slots
            },
        }


def test_telecom_planner_supplies_full_packets_to_bounded_selector() -> None:
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, armoire énergie et antenne GPS."
    )
    client = _CapturingDecisionClient()

    result = AssetAssemblyPlanner(
        AssetRegistry(MANIFESTS_DIR),
        decision_client=client,
    ).plan(workflow_id="wf_packet_test", requirements=requirements)

    assert result.plan.selection_authority == "llm_bounded"
    assert all(component.semantic_strategy is not None for component in result.plan.components)
    assert all(component.selection_risks for component in result.plan.components)
    assert all(
        any(
            "professional" in risk.lower() or "qualification" in risk.lower()
            for risk in component.selection_risks
        )
        for component in result.plan.components
    )
    assert client.slots
    for slot in client.slots:
        for candidate in slot["candidates"]:
            packet = candidate["asset_decision_packet"]
            assert packet["asset_id"] == candidate["asset_id"]
            assert packet["qualification_status"] == "qualified_for_generation"
            assert packet["generation_eligible"] is True
            assert packet["source_provenance"]
            assert packet["allowed_strategies"]


class _InvalidSemanticDecisionClient(_CapturingDecisionClient):
    def decide(self, *, slots: list[dict]) -> tuple[dict[str, str], dict]:
        selections, diagnostics = super().decide(slots=slots)
        diagnostics["semantic_strategies"] = {slot["role_id"]: "reuse_component" for slot in slots}
        return selections, diagnostics


def test_telecom_planner_rejects_semantic_strategy_not_executable_by_selected_asset() -> None:
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, armoire énergie et antenne GPS."
    )

    result = AssetAssemblyPlanner(
        AssetRegistry(MANIFESTS_DIR),
        decision_client=_InvalidSemanticDecisionClient(),
    ).plan(workflow_id="wf_invalid_semantic", requirements=requirements)

    assert result.plan.selection_authority == "deterministic_fallback"
    assert result.plan.llm_fallback_reason == "llm_asset_semantic_strategy_output_rejected"
    for component in result.plan.components:
        expected = (
            "reuse_component"
            if component.generation_strategy == "imported_glb_exact"
            else "compose_assets"
        )
        assert component.semantic_strategy == expected


def test_packet_hash_fields_accept_only_sha256() -> None:
    with pytest.raises(ValidationError):
        AssetRepresentation(
            representation_id="master_step",
            role="master",
            format="step",
            file="asset.step",
            sha256=hashlib.sha1(b"not-sha256").hexdigest(),  # noqa: S324
            units="meters",
        )
