import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from core.agents import ScenePlanner
from core.qa.glb_geometry_validator import GLBGeometryValidator
from core.qa.glb_inspector import GLBInspector
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import (
    BlenderRunner,
    _command_failure_details,
    _write_assembly_constraint_evidence,
)
from core.services.requirement_parser import parse_requirements_text


def test_blender_failure_details_keep_stdout_stderr_and_signal() -> None:
    completed = subprocess.CompletedProcess(
        ["blender"],
        -11,
        stdout="Python traceback",
        stderr="GPU warning",
    )

    detail = _command_failure_details(completed)

    assert "process_terminated_by=SIGSEGV" in detail
    assert "Python traceback" in detail
    assert "GPU warning" in detail


def test_runner_writes_passed_constraint_evidence_for_assembly_plan_1_1(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scene = _accessory_scene(trusted_assembly=True)
    glb_path = tmp_path / "design.glb"
    glb_path.write_bytes(b"post-export-glb")
    payload = {
        "schema_version": "1.0.0",
        "workflow_id": scene.scene_id,
        "status": "passed",
    }

    class _PassedEvidence:
        status = "passed"

        @staticmethod
        def model_dump(*, mode: str) -> dict:
            assert mode == "json"
            return payload

    monkeypatch.setattr(
        "core.qa.assembly_constraint_inspector.AssemblyConstraintInspector.inspect",
        lambda _self, inspected_glb, inspected_plan: (
            _PassedEvidence()
            if inspected_glb == glb_path and inspected_plan is scene.assembly_plan
            else pytest.fail("runner did not inspect the staged GLB and resolved plan")
        ),
    )

    error = _write_assembly_constraint_evidence(tmp_path, scene, glb_path)

    assert error is None
    assert json.loads((tmp_path / "constraint_evidence.json").read_text()) == payload


def test_runner_fails_staging_but_persists_failed_constraint_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scene = _accessory_scene(trusted_assembly=True)
    glb_path = tmp_path / "design.glb"
    glb_path.write_bytes(b"post-export-glb")

    class _FailedEvidence:
        status = "failed"

        @staticmethod
        def model_dump(*, mode: str) -> dict:
            assert mode == "json"
            return {"status": "failed", "errors": ["measured constraint failed"]}

    monkeypatch.setattr(
        "core.qa.assembly_constraint_inspector.AssemblyConstraintInspector.inspect",
        lambda *_: _FailedEvidence(),
    )

    error = _write_assembly_constraint_evidence(tmp_path, scene, glb_path)

    assert error == "BLENDER_ASSEMBLY_CONSTRAINT_EVIDENCE_FAILED"
    assert json.loads((tmp_path / "constraint_evidence.json").read_text())["status"] == "failed"


def test_blender_runner_uses_explicit_fallback_when_binary_missing(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    scene = ScenePlanner().build_scene_spec("wf_blender", requirements, tower, antenna, radio)
    runner = BlenderRunner(
        project_root=Path.cwd(),
        blender_binary="definitely-missing-blender-binary",
    )

    result = runner.generate(scene, tmp_path)

    assert result.status == "fallback"
    assert result.mode == "fallback_no_blender"
    assert not Path(result.artifacts["glb"]).exists()
    assert not Path(result.artifacts["preview"]).exists()
    assert Path(result.artifacts["metadata"]).exists()
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["generation_mode"] == "fallback_no_blender"
    assert metadata["scene_id"] == "wf_blender"
    assert metadata["sector_count"] == 3
    assert metadata["azimuths_deg"] == [0, 120, 240]
    assert metadata["tower_characteristics"]["structure"] == "lattice"
    assert metadata["tower_characteristics"]["base_width_m"] == 4.0
    assert metadata["preview_camera"]["camera"] == "not_rendered"
    assert metadata["preview_camera"]["ortho_scale"] >= 18
    assert "TOWER_LATTICE_30M" in metadata["assets_used"]
    assert metadata["asset_import_summary"]["asset_count"] == 7
    assert metadata["asset_import_summary"]["imported_glb_count"] == 0
    assert metadata["asset_import_summary"]["procedural_fallback_count"] == 7
    assert metadata["asset_import_summary"]["asset_file_exists_count"] == 7
    assert {record["import_mode"] for record in metadata["asset_imports"]} == {
        "procedural_fallback"
    }


def test_blender_runner_reports_fail_closed_exact_accessory_when_file_missing(
    tmp_path: Path,
) -> None:
    base_scene = _accessory_scene()
    scene = base_scene.model_copy(
        update={
            "accessory_assets": [
                accessory.model_copy(update={"asset_file": "assets/missing/gps_missing.glb"})
                if accessory.asset_type == "gps"
                else accessory
                for accessory in base_scene.accessory_assets
            ]
        }
    )
    runner = BlenderRunner(
        project_root=Path.cwd(),
        blender_binary="definitely-missing-blender-binary",
    )

    result = runner.generate(scene, tmp_path)

    assert result.status == "fallback"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    gps_record = next(
        record for record in metadata["asset_imports"] if record["asset_id"] == "GPS_ANTENNA_001"
    )
    assert gps_record["import_mode"] == "missing_file"
    assert gps_record["asset_file_exists"] is False
    assert "ASSET_FILE_MISSING" in gps_record["warnings"]
    assert "PROCEDURAL_FALLBACK_NOT_ALLOWED" in gps_record["warnings"]
    assert metadata["asset_import_summary"]["asset_count"] == 9


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_generates_real_artifacts_when_blender_available(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    scene = ScenePlanner().build_scene_spec("wf_real_blender", requirements, tower, antenna, radio)

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    assert result.mode == "real_blender"
    assert result.blender_available is True
    assert Path(result.artifacts["glb"]).stat().st_size > 1000
    assert Path(result.artifacts["preview"]).stat().st_size > 1000
    for artifact_name in (
        "preview_front",
        "preview_side",
        "preview_top",
        "preview_closeup",
    ):
        assert Path(result.artifacts[artifact_name]).stat().st_size > 1000
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["generation_mode"] == "real_blender"
    assert metadata["tower_characteristics"]["structure"] == "lattice"
    assert metadata["preview_camera"]["camera"] == "camera_technical_three_quarter_full_tower"
    assert metadata["preview_camera"]["camera_type"] == "ORTHO"
    assert metadata["preview_camera"]["framing"] == "geometry_bounds_three_quarter"
    assert metadata["preview_camera"]["render_backdrop"] == "preview_only_light_plane"
    preview_views = metadata["preview_camera"]["preview_views"]
    assert [view["view_id"] for view in preview_views] == [
        "primary",
        "front",
        "side",
        "top",
        "closeup",
    ]
    assert {view["file_name"] for view in preview_views} == {
        "preview.png",
        "preview_front.png",
        "preview_side.png",
        "preview_top.png",
        "preview_closeup.png",
    }
    assert all(len(view["sha256"]) == 64 for view in preview_views)
    assert all(view["size_bytes"] > 1000 for view in preview_views)
    assert metadata["segment_connectivity"]["passed"] is True
    assert metadata["segment_connectivity"]["evaluated_segment_count"] > 0
    assert metadata["segment_connectivity"]["failed_segment_count"] == 0
    assert metadata["segment_connectivity"]["maximum_endpoint_error_m"] <= 0.001
    assert metadata["procedural_objects_created"]
    assert "foundation_concrete_pad" in metadata["procedural_objects_created"]
    assert "label:S1" in metadata["procedural_objects_created"]
    assert "label:S2" in metadata["procedural_objects_created"]
    assert "label:S3" in metadata["procedural_objects_created"]
    assert metadata["asset_import_summary"]["asset_count"] == 7
    assert metadata["asset_import_summary"]["imported_glb_count"] == 0
    assert metadata["asset_import_summary"]["procedural_fallback_count"] == 0
    assert metadata["asset_import_summary"]["parametric_generated_count"] == 1
    assert metadata["asset_import_summary"]["internal_project_generated_count"] == 6
    assert metadata["asset_import_summary"]["asset_file_exists_count"] == 7
    parametric_records = [
        record
        for record in metadata["asset_imports"]
        if record["import_mode"] in {"parametric_generated", "internal_project_generated"}
    ]
    assert len(parametric_records) == 7
    assert all(record["asset_import_success"] is False for record in parametric_records)
    assert all(record["generation_success"] is True for record in parametric_records)
    assert metadata["asset_import_summary"]["import_success_count"] == 0
    assert metadata["asset_import_summary"]["generation_success_count"] == 7
    tower_record = next(
        record for record in parametric_records if record["asset_id"] == "TOWER_LATTICE_30M"
    )
    assert tower_record["import_mode"] == "parametric_generated"
    glb_payload = _read_glb_json(Path(result.artifacts["glb"]))
    semantic_roots = {
        node.get("name"): node.get("extras", {})
        for node in glb_payload.get("nodes", [])
        if node.get("extras", {}).get("semantic_root") == node.get("name")
    }
    assert semantic_roots["tower_TOWER_LATTICE_30M"]["role"] == "tower"
    assert semantic_roots["tower_TOWER_LATTICE_30M"]["tower_material"] == "galvanized_steel"
    for sector_id, azimuth in (("S1", 0.0), ("S2", 120.0), ("S3", 240.0)):
        root = semantic_roots[f"antenna_{sector_id}_ANT_PANEL_5G_001"]
        assert root["role"] == "antenna"
        assert root["sector_id"] == sector_id
        assert root["requested_azimuth_deg"] == azimuth
        assert root["requested_hba_m"] == 24.0
        assert root["geometry_family"] == "panel"
    glb_report = GLBInspector().inspect(
        Path(result.artifacts["glb"]),
        scene,
        Path(result.artifacts["metadata"]),
    )
    geometry_report = GLBGeometryValidator().validate(
        scene,
        glb_report,
        Path(result.artifacts["metadata"]),
        Path(result.artifacts["glb"]),
    )
    assert glb_report.checks["has_foundation"] is True
    assert glb_report.checks["has_labels"] is True
    assert glb_report.checks["all_mesh_primitives_have_binary_data"] is True
    assert glb_report.checks["semantic_mesh_coverage_complete"] is True
    assert glb_report.valid_primitive_count == glb_report.primitive_count > 0
    assert glb_report.binary_chunk_count == 1
    assert geometry_report.checks["foundation_count_valid"] is True
    assert geometry_report.checks["label_count_valid"] is True
    assert geometry_report.object_counts["foundation"] >= 1
    assert geometry_report.object_counts["label"] >= 3
    assert not any(item.startswith("label:") for item in geometry_report.missing_objects)


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_imports_requested_accessory_glbs_when_available(tmp_path: Path) -> None:
    scene = _accessory_scene(trusted_assembly=True)

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    assert result.mode == "real_blender"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["visual_elements"]["include_gps_antenna"] is True
    assert metadata["visual_elements"]["include_power_cabinet"] is True
    assert metadata["mechanical_tilts_deg"] == [5, 5, 5]
    assert metadata["asset_import_summary"]["asset_count"] == 15
    assert metadata["asset_import_summary"]["imported_glb_count"] == 1
    assert metadata["asset_import_summary"]["stretched_imported_glb_count"] == 0
    assert metadata["asset_import_summary"]["parametric_generated_count"] == 1
    assert metadata["asset_import_summary"]["internal_project_generated_count"] == 13
    records = {record["asset_id"]: record for record in metadata["asset_imports"]}
    gps_component = next(
        component
        for component in scene.assembly_plan.components
        if component.role_id == "timing_antenna"
    )
    assert records["GPS_ANTENNA_001"]["import_mode"] == "imported_glb"
    assert records["GPS_ANTENNA_001"]["asset_file"] == gps_component.manifest_snapshot.asset_file
    assert records["POWER_CABINET_001"]["import_mode"] == "internal_project_generated"
    assert records["TOWER_LATTICE_30M"]["import_mode"] == "parametric_generated"
    assert records["ANT_PANEL_5G_001"]["import_mode"] == "internal_project_generated"
    assert records["GPS_ANTENNA_001"]["asset_import_success"] is True
    assert records["POWER_CABINET_001"]["asset_import_success"] is False
    assert records["POWER_CABINET_001"]["generation_success"] is True
    assert records["POWER_CABINET_001"]["generated_object_count"] >= 16
    assert records["POWER_CABINET_001"]["placement_location"][2] == 0.0
    assert records["GPS_ANTENNA_001"]["generation_success"] is False
    assert all("resolved_path" not in record for record in metadata["asset_imports"])
    assert str(Path.cwd().resolve()) not in json.dumps(metadata, ensure_ascii=False)
    assert "label:power_cabinet" in metadata["procedural_objects_created"]
    assert "label:gps_antenna" in metadata["procedural_objects_created"]
    glb_report = GLBInspector().inspect(
        Path(result.artifacts["glb"]),
        scene,
        Path(result.artifacts["metadata"]),
    )
    geometry_report = GLBGeometryValidator().validate(
        scene,
        glb_report,
        Path(result.artifacts["metadata"]),
        Path(result.artifacts["glb"]),
    )
    assert glb_report.checks["has_labels"] is True
    assert geometry_report.checks["label_count_valid"] is True
    assert geometry_report.object_counts["label"] >= 5


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_assembles_qualified_4g_glbs_with_provenance(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 4G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, GPS, armoire énergie."
    ).model_copy(
        update={
            "include_gps_antenna": True,
            "include_power_cabinet": True,
        }
    )
    scene = _trusted_assembly_scene("wf_qualified_asset_assembly", requirements, registry)

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["asset_import_summary"]["imported_glb_count"] == 4
    assert metadata["asset_import_summary"]["stretched_imported_glb_count"] == 0
    assert metadata["asset_import_summary"]["internal_project_generated_count"] == 10
    qualified_imports = [
        record for record in metadata["asset_imports"] if record["import_mode"] == "imported_glb"
    ]
    exact_asset_files = {
        component.selected_asset_id: component.manifest_snapshot.asset_file
        for component in scene.assembly_plan.components
        if component.generation_strategy == "imported_glb_exact"
    }
    assert {record["asset_id"] for record in qualified_imports} == {
        "ANT_PANEL_4G_001",
        "GPS_ANTENNA_001",
    }
    assert all(
        record["asset_metadata"]["qualification_status"] == "qualified_for_generation"
        for record in qualified_imports
    )
    assert all(record["asset_metadata"]["verified_file_sha256"] for record in qualified_imports)
    assert all(
        record["asset_file"] == exact_asset_files[record["asset_id"]]
        for record in qualified_imports
    )
    assert all("resolved_path" not in record for record in metadata["asset_imports"])
    assert str(Path.cwd().resolve()) not in json.dumps(metadata, ensure_ascii=False)
    cabinet_record = next(
        record for record in metadata["asset_imports"] if record["asset_id"] == "POWER_CABINET_001"
    )
    assert cabinet_record["import_mode"] == "internal_project_generated"
    assert cabinet_record["generation_success"] is True
    assert cabinet_record["generated_object_count"] >= 16
    glb_report = GLBInspector().inspect(
        Path(result.artifacts["glb"]),
        scene,
        Path(result.artifacts["metadata"]),
    )
    geometry_report = GLBGeometryValidator().validate(
        scene,
        glb_report,
        Path(result.artifacts["metadata"]),
        Path(result.artifacts["glb"]),
    )
    assert glb_report.structural_qa_passed is True
    assert geometry_report.status == "passed"


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_rejects_exact_import_without_trusted_assembly_snapshot(
    tmp_path: Path,
) -> None:
    scene = _accessory_scene()

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "fallback"
    assert result.mode == "fallback_blender_error"
    assert "EXACT_IMPORT_MANIFEST_SNAPSHOT_REQUIRED" in (result.error or "")
    assert not Path(result.artifacts["glb"]).exists()
    assert not Path(result.artifacts["build_lock"]).exists()


@pytest.mark.parametrize(
    ("structure", "foundation_type", "foundation_name"),
    [
        ("rooftop_mast", "rooftop_anchored", "foundation_rooftop_anchored"),
        ("small_cell_pole", "pole_base", "foundation_pole_base"),
    ],
)
@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_generates_supported_foundation_assemblies(
    tmp_path: Path,
    structure: str,
    foundation_type: str,
    foundation_name: str,
) -> None:
    base_scene = _accessory_scene()
    characteristics = base_scene.tower.characteristics.model_copy(
        update={
            "structure": structure,
            "foundation_type": foundation_type,
            "base_width_m": 0.6,
            "top_width_m": 0.25,
            "material": "painted_steel",
        }
    )
    scene = base_scene.model_copy(
        update={
            "tower": base_scene.tower.model_copy(update={"characteristics": characteristics}),
            "accessory_assets": [],
            "visual_elements": base_scene.visual_elements.model_copy(
                update={"include_power_cabinet": False, "include_gps_antenna": False}
            ),
        }
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert foundation_name in metadata["procedural_objects_created"]
    glb_payload = _read_glb_json(Path(result.artifacts["glb"]))
    foundation_nodes = [
        node
        for node in glb_payload.get("nodes", [])
        if node.get("extras", {}).get("role") == "foundation"
    ]
    assert foundation_nodes
    assert {node["extras"]["foundation_type"] for node in foundation_nodes} == {foundation_type}
    assert any(
        material.get("name") == "tower_painted_steel" for material in glb_payload["materials"]
    )


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_imports_qualified_microwave_dishes_not_panels(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un lien MW sur pylône treillis 30m avec 2 secteurs à 22m. "
        "Azimuts : 80°, 260°. Antennes paraboliques, sans RRU et sans câbles."
    )
    scene = _trusted_assembly_scene("wf_real_microwave_dish", requirements, registry)

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    import_summary = metadata["asset_import_summary"]
    assert import_summary["imported_glb_count"] == 2
    assert import_summary["stretched_imported_glb_count"] == 0
    assert import_summary["procedural_fallback_count"] == 0
    glb_payload = _read_glb_json(Path(result.artifacts["glb"]))
    semantic_roots = [
        node
        for node in glb_payload.get("nodes", [])
        if node.get("extras", {}).get("role") == "antenna"
        and node.get("extras", {}).get("semantic_root") == node.get("name")
    ]
    assert len(semantic_roots) == 2
    assert {node["extras"]["geometry_family"] for node in semantic_roots} == {"microwave_dish"}
    assert all(node.get("children") for node in semantic_roots)
    node_names = {node.get("name", "") for node in glb_payload.get("nodes", [])}
    assert not any("panel" in name.lower() for name in node_names)


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_honors_operational_scene_switches_and_build_lock(
    tmp_path: Path,
) -> None:
    base = _accessory_scene()
    scene = base.model_copy(
        update={
            "tower": base.tower.model_copy(
                update={
                    "characteristics": base.tower.characteristics.model_copy(
                        update={"foundation_type": "unknown"}
                    )
                }
            ),
            "sectors": [
                base.sectors[0].model_copy(update={"include_label": False}),
                *base.sectors[1:],
            ],
            "visual_elements": base.visual_elements.model_copy(
                update={"include_height_markers": False, "include_gps_antenna": False}
            ),
            "preview": base.preview.model_copy(update={"camera": "front"}),
            "accessory_assets": [
                accessory for accessory in base.accessory_assets if accessory.asset_type != "gps"
            ],
        }
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert "height_marker" not in metadata["procedural_objects_created"]
    assert "label:S1" not in metadata["procedural_objects_created"]
    assert "label:S2" in metadata["procedural_objects_created"]
    assert "label:S3" in metadata["procedural_objects_created"]
    assert "FOUNDATION_UNKNOWN_NO_GEOMETRY_GENERATED" in metadata["warnings"]
    assert metadata["preview_camera"]["requested_camera"] == "front"
    assert metadata["preview_camera"]["framing"] == "geometry_bounds_front"
    assert metadata["blender_runtime"]["background"] is True
    assert not any(record["object_role"] == "gps" for record in metadata["asset_imports"])
    build_lock = json.loads(Path(result.artifacts["build_lock"]).read_text(encoding="utf-8"))
    assert build_lock["schema_version"] == "1.3.0"
    assert build_lock["sector_preview_profile"] == {
        "required": False,
        "evidence_file": None,
    }
    assert build_lock["scene_id"] == scene.scene_id
    assert "generate_scene.py" in build_lock["worker_bundle"]["files"]
    assert "parametric_builder.py" in build_lock["worker_bundle"]["files"]
    assert build_lock["blender_runtime"]["background"] is True
    assert build_lock["blender_runtime"]["version"]
    assert build_lock["command_profile"]["factory_startup"] is True
    assert build_lock["trusted_inputs_sha256"]
    assert "geometry_programs" in build_lock["trusted_inputs"]

    glb_payload = _read_glb_json(Path(result.artifacts["glb"]))
    semantic_roles = {node.get("extras", {}).get("role") for node in glb_payload.get("nodes", [])}
    assert "foundation" not in semantic_roles
    assert not any(node.get("name") == "label_sector_S1_0deg" for node in glb_payload["nodes"])


def test_blender_runner_retries_transient_blender_error(tmp_path: Path, monkeypatch) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    scene = ScenePlanner().build_scene_spec("wf_blender_retry", requirements, tower, antenna, radio)
    runner = BlenderRunner(project_root=Path.cwd())
    attempts = 0
    attempt_directories: list[Path] = []
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        commands.append(command)
        attempt_directories.append(Path(command[-1]))
        if attempts == 1:
            return subprocess.CompletedProcess(command, 42, stdout="", stderr="")
        output_dir = Path(command[-1])
        (output_dir / "design.glb").write_bytes(b"x" * 64)
        (output_dir / "preview.png").write_bytes(b"x" * 64)
        for name in (
            "preview_front.png",
            "preview_side.png",
            "preview_top.png",
            "preview_closeup.png",
        ):
            (output_dir / name).write_bytes(name.encode("utf-8") * 4)
        (output_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "generation_mode": "real_blender",
                    "blender_runtime": {
                        "version": "4.5.12 LTS",
                        "version_tuple": [4, 5, 12],
                        "background": True,
                        "factory_startup": True,
                    },
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)
    monkeypatch.setattr("core.services.blender_runner._validate_staged_artifacts", lambda *_: None)

    result = runner.generate(scene, tmp_path)

    assert attempts == 2
    assert attempt_directories[0] != attempt_directories[1]
    assert all("--factory-startup" in command for command in commands)
    assert all("--python-exit-code" in command for command in commands)
    assert result.status == "generated"
    assert result.mode == "real_blender"
    assert Path(result.artifacts["build_lock"]).is_file()
    build_lock = json.loads(Path(result.artifacts["build_lock"]).read_text(encoding="utf-8"))
    assert build_lock["attempt_number"] == 2
    assert build_lock["command_profile"]["factory_startup"] is True
    assert build_lock["artifacts"]["design.glb"]["size_bytes"] == 64
    assert set(build_lock["artifacts"]) >= {
        "preview_front.png",
        "preview_side.png",
        "preview_top.png",
        "preview_closeup.png",
    }
    assert all(
        Path(result.artifacts[name]).is_file()
        for name in ("preview_front", "preview_side", "preview_top", "preview_closeup")
    )
    assert not any(path.exists() for path in attempt_directories)


def test_blender_runner_retries_build_lock_preparation_failure_then_falls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scene = _accessory_scene()
    runner = BlenderRunner(project_root=Path.cwd())
    attempts = 0
    attempt_directories: list[Path] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        attempt_dir = Path(command[-1])
        attempt_directories.append(attempt_dir)
        (attempt_dir / "design.glb").write_bytes(b"x" * 64)
        (attempt_dir / "preview.png").write_bytes(b"x" * 64)
        (attempt_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "generation_mode": "real_blender",
                    "blender_runtime": {
                        "version": "4.5.12 LTS",
                        "version_tuple": [4, 5, 12],
                        "background": True,
                        "factory_startup": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fail_build_lock(**_kwargs) -> None:
        raise ValueError("ASSET_MANIFEST_SOURCE_HASH_MISMATCH")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)
    monkeypatch.setattr("core.services.blender_runner._validate_staged_artifacts", lambda *_: None)
    monkeypatch.setattr("core.services.blender_runner._write_build_lock", fail_build_lock)
    monkeypatch.setattr("core.services.blender_runner.time.sleep", lambda *_: None)

    result = runner.generate(scene, tmp_path)

    assert attempts == 3
    assert result.status == "fallback"
    assert result.mode == "fallback_blender_error"
    assert result.error is not None
    assert result.error.count("BLENDER_BUILD_LOCK_PREPARATION_ERROR") == 3
    assert "ValueError:ASSET_MANIFEST_SOURCE_HASH_MISMATCH" in result.error
    assert not Path(result.artifacts["build_lock"]).exists()
    assert all(not path.exists() for path in attempt_directories)


def test_blender_runner_retries_worker_snapshot_preparation_failure_then_falls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scene = _accessory_scene()
    runner = BlenderRunner(project_root=Path.cwd())
    attempts = 0
    attempt_directories: list[Path] = []

    def fail_snapshot(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError("worker source disappeared")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(
        "core.services.blender_runner._snapshot_worker_sources",
        fail_snapshot,
    )
    monkeypatch.setattr("core.services.blender_runner.time.sleep", lambda *_: None)

    result = runner.generate(scene, tmp_path)

    assert attempts == 3
    assert result.status == "fallback"
    assert result.mode == "fallback_blender_error"
    assert result.error is not None
    assert result.error.count("BLENDER_WORKER_SNAPSHOT_ERROR") == 3
    assert "OSError:DETAILS_REDACTED" in result.error
    assert not Path(result.artifacts["build_lock"]).exists()
    assert not attempt_directories


def test_blender_runner_never_binds_output_to_concurrently_mutated_public_scene(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scene = _accessory_scene()
    runner = BlenderRunner(project_root=Path.cwd())
    attempts = 0
    consumed_tower_heights: list[float] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        scene_input_path = Path(command[-2])
        assert scene_input_path.parent.name == ".scene_input"
        consumed_scene = json.loads(scene_input_path.read_text(encoding="utf-8"))
        consumed_tower_heights.append(consumed_scene["tower"]["height_m"])
        public_scene_path = tmp_path / "scene_spec.json"
        public_scene = json.loads(public_scene_path.read_text(encoding="utf-8"))
        public_scene["tower"]["height_m"] += attempts
        public_scene_path.write_text(json.dumps(public_scene), encoding="utf-8")
        attempt_dir = Path(command[-1])
        (attempt_dir / "design.glb").write_bytes(b"scene-a-glb" * 8)
        (attempt_dir / "preview.png").write_bytes(b"scene-a-preview" * 8)
        (attempt_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "generation_mode": "real_blender",
                    "blender_runtime": {
                        "version": "4.5.12 LTS",
                        "version_tuple": [4, 5, 12],
                        "background": True,
                        "factory_startup": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)
    monkeypatch.setattr("core.services.blender_runner._validate_staged_artifacts", lambda *_: None)
    monkeypatch.setattr("core.services.blender_runner.time.sleep", lambda *_: None)

    result = runner.generate(scene, tmp_path)

    assert attempts == 3
    assert consumed_tower_heights == [scene.tower.height_m] * 3
    assert result.status == "fallback"
    assert result.mode == "fallback_blender_error"
    assert result.error is not None
    assert result.error.count("BLENDER_SCENE_SPEC_PUBLIC_HASH_MISMATCH") == 3
    assert not Path(result.artifacts["glb"]).exists()
    assert not Path(result.artifacts["build_lock"]).exists()


def test_blender_runner_never_reuses_failed_attempt_artifacts(tmp_path: Path, monkeypatch) -> None:
    scene = _accessory_scene()
    runner = BlenderRunner(project_root=Path.cwd())
    attempts = 0
    attempt_directories: list[Path] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        attempt_dir = Path(command[-1])
        attempt_directories.append(attempt_dir)
        if attempts == 1:
            (attempt_dir / "design.glb").write_bytes(b"stale-glb")
            (attempt_dir / "preview.png").write_bytes(b"stale-preview")
            (attempt_dir / "scene_metadata.json").write_text(
                json.dumps({"scene_id": scene.scene_id, "generation_mode": "real_blender"}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 42, stdout="", stderr="transient")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)
    monkeypatch.setattr("core.services.blender_runner.time.sleep", lambda *_: None)

    result = runner.generate(scene, tmp_path)

    assert attempts == 3
    assert len(set(attempt_directories)) == 3
    assert result.status == "fallback"
    assert result.mode == "fallback_blender_error"
    assert not Path(result.artifacts["glb"]).exists()
    assert not Path(result.artifacts["preview"]).exists()
    assert not Path(result.artifacts["build_lock"]).exists()
    assert all(not path.exists() for path in attempt_directories)


def test_blender_runner_executes_immutable_worker_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    worker_dir = project_root / "apps" / "blender_worker"
    worker_dir.mkdir(parents=True)
    (worker_dir / "__init__.py").write_text("", encoding="utf-8")
    (worker_dir / "generate_scene.py").write_text(
        "import parametric_builder\n",
        encoding="utf-8",
    )
    mutable_dependency = worker_dir / "parametric_builder.py"
    mutable_dependency.write_text("VERSION = 'before'\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    scene = _accessory_scene()
    runner = BlenderRunner(project_root=project_root)
    executed_script: Path | None = None

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal executed_script
        executed_script = Path(command[command.index("--python") + 1])
        assert executed_script.parent.name == ".worker_source"
        assert (executed_script.parent / "parametric_builder.py").read_text(
            encoding="utf-8"
        ) == "VERSION = 'before'\n"
        mutable_dependency.write_text("VERSION = 'after'\n", encoding="utf-8")
        attempt_dir = Path(command[-1])
        (attempt_dir / "design.glb").write_bytes(b"x" * 64)
        (attempt_dir / "preview.png").write_bytes(b"x" * 64)
        (attempt_dir / "scene_metadata.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.scene_id,
                    "generation_mode": "real_blender",
                    "blender_runtime": {
                        "version": "4.5.12 LTS",
                        "version_tuple": [4, 5, 12],
                        "background": True,
                        "factory_startup": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)
    monkeypatch.setattr("core.services.blender_runner._validate_staged_artifacts", lambda *_: None)

    result = runner.generate(scene, output_dir)

    assert result.status == "generated"
    assert executed_script is not None
    lock = json.loads(Path(result.artifacts["build_lock"]).read_text(encoding="utf-8"))
    before_hash = hashlib.sha256(b"VERSION = 'before'\n").hexdigest()
    after_hash = hashlib.sha256(b"VERSION = 'after'\n").hexdigest()
    assert lock["worker_bundle"]["files"]["parametric_builder.py"] == before_hash
    assert lock["worker_bundle"]["files"]["parametric_builder.py"] != after_hash


def _accessory_scene(*, trusted_assembly: bool = False):
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, GPS, armoire énergie."
    ).model_copy(
        update={
            "mechanical_tilt_deg": 5,
            "include_gps_antenna": True,
            "include_power_cabinet": True,
        }
    )
    if trusted_assembly:
        return _trusted_assembly_scene("wf_accessory_scene", requirements, registry)
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    gps = registry.select_asset("gps", requirements.network_type, requirements.tower_type)
    cabinet = registry.select_asset("cabinet", requirements.network_type, requirements.tower_type)
    return ScenePlanner().build_scene_spec(
        "wf_real_blender_accessories",
        requirements,
        tower,
        antenna,
        radio,
        accessory_assets=[gps, cabinet],
    )


def _trusted_assembly_scene(workflow_id, requirements, registry: AssetRegistry):
    planning = AssetAssemblyPlanner(registry).plan(
        workflow_id=workflow_id,
        requirements=requirements,
    )
    assets = planning.assets_by_role
    accessories = [
        assets[role_id] for role_id in ("ground_equipment", "timing_antenna") if role_id in assets
    ]
    return ScenePlanner().build_scene_spec(
        workflow_id,
        requirements,
        assets["support_structure"],
        assets["sector_antenna"],
        assets.get("remote_radio"),
        accessory_assets=accessories,
        assembly_plan=planning.plan,
    )


def _read_glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    assert chunk_type == 0x4E4F534A
    return json.loads(payload[20 : 20 + chunk_length].rstrip(b" \x00"))
