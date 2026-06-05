from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.assets import AssetManifest
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.requirements import RequirementSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import GenerationResult
from core.validation.quality_gates import (
    evaluate_post_blender_gate,
    evaluate_pre_blender_gate,
)


def test_pre_blender_gate_passes_valid_scene() -> None:
    requirements, scene, assets = _valid_scene_inputs()
    report = _passed_report("wf_quality_gate")

    gate = evaluate_pre_blender_gate(
        requirements=requirements,
        requirement_report=report,
        scene=scene,
        scene_report=report,
        selected_assets=assets,
        all_assets=AssetRegistry(Path("assets/manifests")).list_assets(),
        repair_attempts=0,
        max_repair_attempts=2,
    )

    assert gate.passed is True
    assert gate.critical_errors == []
    assert all(gate.checks.values())


def test_pre_blender_gate_blocks_unvalidated_asset() -> None:
    requirements, scene, assets = _valid_scene_inputs()
    report = _passed_report("wf_quality_gate_unvalidated")
    unvalidated_assets = [
        asset.model_copy(update={"status": "draft"}) if asset.type == "antenna" else asset
        for asset in assets
    ]

    gate = evaluate_pre_blender_gate(
        requirements=requirements,
        requirement_report=report,
        scene=scene,
        scene_report=report,
        selected_assets=unvalidated_assets,
        all_assets=AssetRegistry(Path("assets/manifests")).list_assets(),
        repair_attempts=0,
        max_repair_attempts=2,
    )

    assert gate.passed is False
    assert gate.checks["assets_valid"] is False
    assert "assets_valid" in gate.critical_errors


def test_pre_blender_gate_accepts_asset_fallback_tower_family() -> None:
    requirements, scene, assets = _valid_scene_inputs()
    requirements = requirements.model_copy(update={"tower_type": "lattice_tower_variant"})
    report = _passed_report("wf_quality_gate_fallback_family")

    gate = evaluate_pre_blender_gate(
        requirements=requirements,
        requirement_report=report,
        scene=scene,
        scene_report=report,
        selected_assets=assets,
        all_assets=AssetRegistry(Path("assets/manifests")).list_assets(),
        repair_attempts=0,
        max_repair_attempts=2,
    )

    assert gate.checks["assets_tower_compatible"] is True


def test_post_blender_gate_requires_metadata(tmp_path: Path) -> None:
    glb = tmp_path / "design.glb"
    preview = tmp_path / "preview.png"
    glb.write_bytes(b"x" * 2048)
    preview.write_bytes(b"png")
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts={
            "glb": str(glb),
            "preview": str(preview),
            "metadata": str(tmp_path / "missing_metadata.json"),
        },
    )

    gate = evaluate_post_blender_gate(generation, _passed_report("wf_missing_metadata"))

    assert gate.passed is False
    assert gate.checks["metadata_exists"] is False
    assert "metadata_exists" in gate.critical_errors


def test_post_blender_gate_requires_real_blender_model_size(tmp_path: Path) -> None:
    glb = tmp_path / "design.glb"
    preview = tmp_path / "preview.png"
    metadata = tmp_path / "scene_metadata.json"
    glb.write_bytes(b"tiny")
    preview.write_bytes(b"png")
    metadata.write_text("{}", encoding="utf-8")
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts={"glb": str(glb), "preview": str(preview), "metadata": str(metadata)},
    )

    gate = evaluate_post_blender_gate(generation, _passed_report("wf_small_model"))

    assert gate.passed is False
    assert gate.checks["model_exists"] is False
    assert gate.critical_errors


def test_post_blender_gate_uses_glb_inspection(tmp_path: Path) -> None:
    glb = tmp_path / "design.glb"
    preview = tmp_path / "preview.png"
    metadata = tmp_path / "scene_metadata.json"
    glb.write_bytes(b"x" * 2048)
    preview.write_bytes(b"png")
    metadata.write_text("{}", encoding="utf-8")
    generation = GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts={"glb": str(glb), "preview": str(preview), "metadata": str(metadata)},
    )
    qa_report = _passed_report("wf_gate_uses_glb")
    glb_report = {
        "inspection_mode": "glb_parse",
        "file_exists": True,
        "file_size_bytes": 2048,
        "format_valid": True,
        "node_count": 1,
        "mesh_count": 1,
        "material_count": 1,
        "object_names": ["tower_only"],
        "expected_object_prefixes_found": {"tower": True, "antennas": False},
        "checks": {
            "expected_objects_present": False,
            "minimum_node_count_valid": False,
        },
        "warnings": [],
        "critical_errors": ["EXPECTED_GLB_OBJECTS_MISSING"],
        "structural_qa_passed": False,
    }
    preview_report = {
        "inspection_mode": "png_parse",
        "file_exists": True,
        "file_size_bytes": 2048,
        "width": 1920,
        "height": 1080,
        "format": "png",
        "minimum_resolution_valid": True,
        "luminance_mean": 180.0,
        "luminance_stddev": 22.0,
        "non_dark_pixel_ratio": 1.0,
        "visual_quality_valid": True,
        "checks": {"minimum_resolution_valid": True},
        "warnings": [],
        "critical_errors": [],
        "preview_qa_passed": True,
    }

    gate = evaluate_post_blender_gate(
        generation,
        qa_report,
        GlbInspectionReport(**glb_report),
        PreviewInspectionReport(**preview_report),
    )

    assert gate.passed is False
    assert gate.checks["glb_structure_valid"] is False
    assert gate.checks["expected_objects_present"] is False
    assert "glb_inspection" in gate.details


def _valid_scene_inputs() -> tuple[RequirementSpec, object, list[AssetManifest]]:
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        detail_level="high",
    )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower("lattice_tower", "5G", 30)
    antenna = registry.select_asset("antenna", "5G", "lattice_tower")
    radio = registry.select_asset("radio", "5G", "lattice_tower")
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_quality_gate",
        requirements=requirements,
        tower=tower,
        antenna=antenna,
        radio=radio,
    )
    return requirements, scene, [tower, antenna, radio]


def _passed_report(design_id: str) -> ValidationReport:
    return ValidationReport(
        design_id=design_id,
        status="passed",
        score=1.0,
        checks={"valid": True},
        warnings=[
            ValidationIssue(
                code="INFO",
                message="Informational warning.",
                severity="info",
            )
        ],
    )
