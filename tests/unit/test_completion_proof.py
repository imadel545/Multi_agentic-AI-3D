import hashlib
import json
from pathlib import Path

import pytest

from core.agents.blueprint_composer import BlueprintComposer
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.scene_planner import ScenePlanner
from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.assembly_evidence import canonical_evidence_sha256
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.parametric import MeshQAReport
from core.contracts.quality import QualityGateReport
from core.contracts.validation import ValidationReport
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import GenerationResult
from core.services.requirement_parser import parse_requirements_text
from core.services.scene_versioning import (
    _verify_constraint_evidence,
    verify_persisted_version,
    verify_persisted_version_detailed,
)
from core.validation.completion_certificate import (
    _constraint_evidence_verified,
    build_completion_certificate,
    verify_completion_certificate,
)
from core.validation.design_blueprint import (
    evaluate_blueprint_requirement_coverage,
    evaluate_blueprint_scene_coverage,
)
from core.validation.requirement_coverage import evaluate_requirement_coverage


def test_requirement_coverage_proves_scene_spec_mapping() -> None:
    requirements, scene = _requirements_and_scene()

    report = evaluate_requirement_coverage(requirements, scene)

    assert report.passed is True
    assert report.coverage_ratio == 1.0
    assert report.critical_errors == []
    assert len(report.checks) >= 25


def test_requirement_coverage_rejects_silent_scene_mutation() -> None:
    requirements, scene = _requirements_and_scene()
    mutated_sector = scene.sectors[0].model_copy(update={"azimuth_deg": 10.0})
    mutated_scene = scene.model_copy(update={"sectors": [mutated_sector, *scene.sectors[1:]]})

    report = evaluate_requirement_coverage(requirements, mutated_scene)

    assert report.passed is False
    assert "sectors.azimuth_deg" in report.critical_errors


def test_requirement_coverage_accepts_only_evidenced_planning_override() -> None:
    requirements, _ = _requirements_and_scene()
    resolution = {
        "antenna_install_height_m": 25.0,
        "beamwidth_deg": requirements.beamwidth_deg,
        "include_cables": requirements.include_cables,
        "include_sector_beams": requirements.include_beams,
        "decisions": [
            {
                "field": "antenna_install_height_m",
                "status": "applied",
                "candidate_value": 25.0,
                "reason": "approved engineering rule",
                "provenance": {"source_id": "rule-1"},
            }
        ],
    }
    scene = _scene_for(requirements, planning_resolution=resolution)

    evidenced = evaluate_requirement_coverage(requirements, scene, resolution)
    unevidenced = evaluate_requirement_coverage(
        requirements,
        scene,
        {**resolution, "decisions": []},
    )

    assert evidenced.passed is True
    assert evidenced.approved_deviations[0]["field"] == "antenna_install_height_m"
    assert unevidenced.passed is False
    assert "planning_resolution.antenna_install_height_m.evidence" in (unevidenced.critical_errors)


def test_completion_certificate_binds_artifact_hashes(tmp_path: Path) -> None:
    inputs = _completion_inputs(tmp_path)

    certificate = build_completion_certificate(**inputs)

    assert certificate.status == "issued"
    assert certificate.blockers == []
    assert verify_completion_certificate(
        certificate,
        requirements=inputs["requirements"],
        design_blueprint=inputs["design_blueprint"],
        scene=inputs["scene"],
        generation=inputs["generation"],
    )
    Path(inputs["generation"].artifacts["glb"]).write_bytes(b"tampered")
    assert not verify_completion_certificate(
        certificate,
        requirements=inputs["requirements"],
        design_blueprint=inputs["design_blueprint"],
        scene=inputs["scene"],
        generation=inputs["generation"],
    )


def test_completion_certificate_rejects_json_only_glb_claim(tmp_path: Path) -> None:
    inputs = _completion_inputs(tmp_path)
    inputs["glb_inspection"] = inputs["glb_inspection"].model_copy(
        update={
            "valid_primitive_count": 0,
            "binary_chunk_count": 0,
            "structural_qa_passed": False,
        }
    )

    certificate = build_completion_certificate(**inputs)

    assert certificate.status == "rejected"
    assert "glb_binary_integrity_passed" in certificate.blockers


def test_completion_certificate_uses_v1_4_and_constraint_hash_for_assembly_plan_1_1(
    tmp_path: Path,
    monkeypatch,
) -> None:
    inputs = _completion_inputs(tmp_path)
    scene = _assembly_scene(inputs["requirements"])
    evidence_path = tmp_path / "constraint_evidence.json"
    component_proof_path = tmp_path / "component_proofs.json"
    _write_constraint_evidence(
        evidence_path,
        scene,
        Path(inputs["generation"].artifacts["glb"]),
    )
    component_proof_path.write_text('{"passed":true}', encoding="utf-8")
    inputs["scene"] = scene
    inputs["generation"] = inputs["generation"].model_copy(
        update={
            "artifacts": {
                **inputs["generation"].artifacts,
                "component_proofs": str(component_proof_path),
                "constraint_evidence": str(evidence_path),
            }
        }
    )
    monkeypatch.setattr(
        "core.validation.completion_certificate._component_proof_verified",
        lambda *_: True,
    )

    certificate = build_completion_certificate(**inputs)

    assert certificate.schema_version == "1.4.0"
    assert certificate.status == "issued"
    assert (
        certificate.constraint_evidence_sha256
        == hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    )
    assert {item.logical_name for item in certificate.artifacts} == {
        "glb",
        "preview",
        "metadata",
        "component_proofs",
        "constraint_evidence",
        "build_lock",
    }

    evidence_path.unlink()
    rejected = build_completion_certificate(**inputs)
    assert rejected.status == "rejected"
    assert rejected.constraint_evidence_sha256 is None
    assert "assembly_constraint_evidence_verified" in rejected.blockers
    assert "required_artifacts_regular_files" in rejected.blockers


def test_constraint_evidence_verifier_rejects_rehashed_wrong_workflow(
    tmp_path: Path,
) -> None:
    requirements, _ = _requirements_and_scene()
    scene = _assembly_scene(requirements)
    glb_path = tmp_path / "design.glb"
    evidence_path = tmp_path / "constraint_evidence.json"
    glb_path.write_bytes(b"certified-post-export-glb")
    _write_constraint_evidence(evidence_path, scene, glb_path)
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts={"glb": str(glb_path), "constraint_evidence": str(evidence_path)},
    )

    assert _constraint_evidence_verified(generation, scene)
    _verify_constraint_evidence(evidence_path, scene=scene)

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["workflow_id"] = "wf_other_design"
    payload["evidence_sha256"] = canonical_evidence_sha256(
        {key: value for key, value in payload.items() if key != "evidence_sha256"}
    )
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    assert not _constraint_evidence_verified(generation, scene)
    with pytest.raises(
        ValueError,
        match="ACTIVE_VERSION_CONSTRAINT_EVIDENCE_WORKFLOW_MISMATCH",
    ):
        _verify_constraint_evidence(evidence_path, scene=scene)


def test_persisted_version_accepts_v1_4_set_and_rejects_constraint_tamper(
    tmp_path: Path,
    monkeypatch,
) -> None:
    inputs = _completion_inputs(tmp_path)
    scene = _assembly_scene(inputs["requirements"])
    evidence_path = tmp_path / "constraint_evidence.json"
    component_proof_path = tmp_path / "component_proofs.json"
    _write_constraint_evidence(
        evidence_path,
        scene,
        Path(inputs["generation"].artifacts["glb"]),
    )
    component_proof_path.write_text('{"passed":true}', encoding="utf-8")
    inputs["workflow_id"] = scene.scene_id
    inputs["scene"] = scene
    inputs["generation"] = inputs["generation"].model_copy(
        update={
            "artifacts": {
                **inputs["generation"].artifacts,
                "component_proofs": str(component_proof_path),
                "constraint_evidence": str(evidence_path),
            }
        }
    )
    monkeypatch.setattr(
        "core.validation.completion_certificate._component_proof_verified",
        lambda *_: True,
    )
    certificate = build_completion_certificate(**inputs)
    (tmp_path / "requirements_spec.json").write_text(
        json.dumps(inputs["requirements"].model_dump(mode="json")),
        encoding="utf-8",
    )
    (tmp_path / "design_blueprint.json").write_text(
        json.dumps(inputs["design_blueprint"].model_dump(mode="json")),
        encoding="utf-8",
    )
    (tmp_path / "scene_spec.json").write_text(
        json.dumps(scene.model_dump(mode="json")),
        encoding="utf-8",
    )
    (tmp_path / "completion_certificate.json").write_text(
        certificate.model_dump_json(),
        encoding="utf-8",
    )
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "workflow_id": scene.scene_id,
                "status": "completed",
                "generation_mode": "real_blender",
                "completion_certificate_status": "issued",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "core.services.scene_versioning._verify_build_lock",
        lambda *_args, **_kwargs: "1.2.0",
    )

    evidence = verify_persisted_version(
        tmp_path,
        workflow_id=scene.scene_id,
        expected_scene=scene,
        require_report_proof=False,
    )

    assert {item["logical_name"] for item in evidence} == {
        "glb",
        "preview",
        "metadata",
        "component_proofs",
        "constraint_evidence",
        "build_lock",
    }
    downgraded = certificate.model_dump(mode="json")
    downgraded["schema_version"] = "1.2.0"
    downgraded["constraint_evidence_sha256"] = None
    downgraded["checks"].pop("assembly_constraint_evidence_verified")
    downgraded["artifacts"] = [
        item for item in downgraded["artifacts"] if item["logical_name"] != "constraint_evidence"
    ]
    (tmp_path / "completion_certificate.json").write_text(
        json.dumps(downgraded),
        encoding="utf-8",
    )
    # Without the activation manifest, a 1.2 certificate is verified under its own
    # contract and the newer evidence family is reported as a coverage gap. The
    # manifest hash binding (SceneVersioningService) is what rejects a rewrite.
    downgraded_verification = verify_persisted_version_detailed(
        tmp_path,
        workflow_id=scene.scene_id,
        expected_scene=scene,
        require_report_proof=False,
    )
    assert downgraded_verification.certificate_contract_version == "1.2.0"
    assert "constraint_evidence" in downgraded_verification.coverage_gaps
    (tmp_path / "completion_certificate.json").write_text(
        certificate.model_dump_json(),
        encoding="utf-8",
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["limitations"][0] = "tampered but internally rehashed limitation"
    payload["evidence_sha256"] = canonical_evidence_sha256(
        {key: value for key, value in payload.items() if key != "evidence_sha256"}
    )
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        ValueError,
        match="ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:constraint_evidence",
    ):
        verify_persisted_version(
            tmp_path,
            workflow_id=scene.scene_id,
            expected_scene=scene,
            require_report_proof=False,
        )


def _requirements_and_scene():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    return requirements, _scene_for(requirements)


def _scene_for(requirements, planning_resolution=None):
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    return ScenePlanner().build_scene_spec(
        "wf_completion_proof",
        requirements,
        tower,
        antenna,
        radio,
        planning_resolution=planning_resolution,
    )


def _assembly_scene(requirements):
    registry = AssetRegistry(Path("assets/manifests"))
    planning = AssetAssemblyPlanner(registry).plan(
        workflow_id="wf_completion_assembly",
        requirements=requirements,
    )
    scene = ScenePlanner().build_scene_spec(
        planning.plan.workflow_id,
        requirements,
        planning.assets_by_role["support_structure"],
        planning.assets_by_role["sector_antenna"],
        planning.assets_by_role.get("remote_radio"),
        assembly_plan=planning.plan,
    )
    assert scene.assembly_plan is not None
    assert scene.assembly_plan.schema_version == "1.1.0"
    return scene


def _write_constraint_evidence(path: Path, scene, glb_path: Path) -> None:
    plan = scene.assembly_plan
    assert plan is not None
    measurements = []
    for operation in plan.operations:
        if operation.kind != "mechanical":
            continue
        for instance in operation.instances:
            measurements.append(
                {
                    "measurement_id": f"{operation.connection_id}:{instance.instance_id}",
                    "connection_id": operation.connection_id,
                    "operation_id": operation.operation_id,
                    "instance_id": instance.instance_id,
                    "source_role_id": operation.source_role_id,
                    "source_connector_id": operation.source_connector_id,
                    "source_anchor_id": operation.source_anchor.anchor_id,
                    "target_role_id": operation.target_role_id,
                    "target_connector_id": operation.target_connector_id,
                    "target_anchor_id": operation.target_anchor.anchor_id,
                    "source_frame": {
                        "coordinate_space": "scenespec_z_up_meters",
                        "position_m": [0.0, 0.0, 0.0],
                        "normal": [1.0, 0.0, 0.0],
                        "up": [0.0, 0.0, 1.0],
                        "source": "glb_fixed_anchor",
                        "gltf_node_index": len(measurements),
                        "gltf_node_name": f"assembly_root_{len(measurements)}",
                    },
                    "target_frame": {
                        "coordinate_space": "scenespec_z_up_meters",
                        "position_m": [0.0, 0.0, 0.0],
                        "normal": [-1.0, 0.0, 0.0],
                        "up": [0.0, 0.0, 1.0],
                        "source": "glb_resolved_anchor",
                        "gltf_node_index": len(measurements) + 10_000,
                        "gltf_node_name": f"target_anchor_{len(measurements)}",
                    },
                    "position_error_m": 0.0,
                    "position_tolerance_m": operation.tolerance_m,
                    "normal_opposition_error_deg": 0.0,
                    "up_alignment_error_deg": 0.0,
                    "angular_tolerance_deg": 1.0,
                    "position_passed": True,
                    "normal_opposition_passed": True,
                    "up_alignment_passed": True,
                    "passed": True,
                }
            )
    plan_payload = plan.model_dump(mode="json")
    payload = {
        "schema_version": "1.0.0",
        "assembly_plan_schema_version": "1.1.0",
        "workflow_id": plan.workflow_id,
        "status": "passed",
        "coordinate_space": "scenespec_z_up_meters",
        "glb_sha256": hashlib.sha256(glb_path.read_bytes()).hexdigest(),
        "assembly_plan_sha256": hashlib.sha256(
            json.dumps(
                plan_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
        "angular_tolerance_deg": 1.0,
        "expected_measurement_count": len(measurements),
        "measured_constraint_count": len(measurements),
        "failed_constraint_count": 0,
        "measurements": measurements,
        "unevaluated_required_connections": [
            {
                "connection_id": connection.connection_id,
                "kind": connection.kind,
                "required": True,
                "reason": "non_mechanical_connection_not_evaluated_by_v1",
            }
            for connection in plan.connections
            if connection.required and connection.kind != "mechanical"
        ],
        "errors": [],
        "limitations": ["limit one", "limit two", "limit three"],
    }
    payload["evidence_sha256"] = canonical_evidence_sha256(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _completion_inputs(tmp_path: Path) -> dict:
    requirements, scene = _requirements_and_scene()
    registry = AssetRegistry(Path("assets/manifests"))
    selected_assets = [
        registry.get(scene.tower.asset_id),
        registry.get(scene.sectors[0].antenna_asset_id),
        registry.get(scene.sectors[0].radio_asset_id),
    ]
    blueprint = BlueprintComposer().compose(
        workflow_id=scene.scene_id,
        requirements=requirements,
        selected_assets=selected_assets,
        tower_validation=TowerEngineerAgent().validate(requirements, selected_assets[0]),
        rf_validation=RfEngineerAgent().validate(requirements),
        planning_resolution=None,
    )
    blueprint_requirement_coverage = evaluate_blueprint_requirement_coverage(
        requirements,
        blueprint,
    )
    blueprint_scene_coverage = evaluate_blueprint_scene_coverage(blueprint, scene)
    glb = tmp_path / "design.glb"
    preview = tmp_path / "preview.png"
    metadata = tmp_path / "scene_metadata.json"
    build_lock = tmp_path / "build.lock.json"
    glb.write_bytes(b"real-glb-binary-evidence")
    preview.write_bytes(b"real-preview-evidence")
    metadata.write_bytes(b'{"generation_mode":"real_blender"}')
    build_lock.write_bytes(b'{"build_id":"verified-test-build"}')
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=10,
        artifacts={
            "glb": str(glb),
            "preview": str(preview),
            "metadata": str(metadata),
            "build_lock": str(build_lock),
        },
    )
    coverage = evaluate_requirement_coverage(requirements, scene)
    qa_report = ValidationReport(
        design_id=scene.scene_id,
        status="passed",
        score=1.0,
        checks={"all": True},
    )
    glb_inspection = GlbInspectionReport(
        inspection_mode="glb_parse",
        file_exists=True,
        file_size_bytes=glb.stat().st_size,
        format_valid=True,
        node_count=10,
        mesh_count=10,
        primitive_count=10,
        valid_primitive_count=10,
        position_accessor_count=10,
        buffer_count=1,
        buffer_view_count=10,
        binary_chunk_count=1,
        material_count=1,
        checks={
            "expected_objects_present": True,
            "semantic_mesh_coverage_complete": True,
        },
        structural_qa_passed=True,
    )
    geometry_validation = GeometryValidationReport(
        status="passed",
        checks={"all": True},
        mesh_qa=MeshQAReport(
            glb_parse_ok=True,
            checks=[],
            mesh_qa_passed=True,
        ),
        mesh_qa_level="mesh_level_basic",
    )
    preview_inspection = PreviewInspectionReport(
        inspection_mode="png_parse",
        file_exists=True,
        file_size_bytes=preview.stat().st_size,
        width=1920,
        height=1080,
        format="png",
        minimum_resolution_valid=True,
        visual_quality_valid=True,
        preview_qa_passed=True,
    )
    return {
        "workflow_id": scene.scene_id,
        "requirements": requirements,
        "design_blueprint": blueprint,
        "blueprint_requirement_coverage": blueprint_requirement_coverage,
        "blueprint_scene_coverage": blueprint_scene_coverage,
        "scene": scene,
        "requirement_coverage": coverage,
        "generation": generation,
        "qa_report": qa_report,
        "glb_inspection": glb_inspection,
        "geometry_validation": geometry_validation,
        "preview_inspection": preview_inspection,
        "pre_blender_gate": QualityGateReport(
            stage="pre_blender", passed=True, checks={"all": True}
        ),
        "post_blender_gate": QualityGateReport(
            stage="post_blender", passed=True, checks={"all": True}
        ),
    }
