from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.parametric import MeshQAReport
from core.contracts.quality import QualityGateReport
from core.contracts.validation import ValidationReport
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import GenerationResult
from core.services.requirement_parser import parse_requirements_text
from core.validation.completion_certificate import (
    build_completion_certificate,
    verify_completion_certificate,
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
        scene=inputs["scene"],
        generation=inputs["generation"],
    )
    Path(inputs["generation"].artifacts["glb"]).write_bytes(b"tampered")
    assert not verify_completion_certificate(
        certificate,
        requirements=inputs["requirements"],
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


def _completion_inputs(tmp_path: Path) -> dict:
    requirements, scene = _requirements_and_scene()
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
