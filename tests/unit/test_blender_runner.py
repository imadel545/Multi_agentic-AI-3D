import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.agents import ScenePlanner
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.requirement_parser import parse_requirements_text


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
    assert Path(result.artifacts["glb"]).exists()
    assert Path(result.artifacts["preview"]).exists()
    assert Path(result.artifacts["metadata"]).exists()
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["generation_mode"] == "fallback_no_blender"
    assert metadata["scene_id"] == "wf_blender"
    assert metadata["sector_count"] == 3
    assert metadata["azimuths_deg"] == [0, 120, 240]
    assert metadata["tower_characteristics"]["structure"] == "lattice"
    assert metadata["tower_characteristics"]["base_width_m"] == 4.0
    assert metadata["preview_camera"]["camera"] == "fallback_preview"
    assert metadata["preview_camera"]["ortho_scale"] >= 18
    assert "TOWER_LATTICE_30M" in metadata["assets_used"]
    assert metadata["asset_import_summary"]["asset_count"] == 7
    assert metadata["asset_import_summary"]["imported_glb_count"] == 0
    assert metadata["asset_import_summary"]["procedural_fallback_count"] == 7
    assert metadata["asset_import_summary"]["asset_file_exists_count"] == 7
    assert {record["import_mode"] for record in metadata["asset_imports"]} == {
        "procedural_fallback"
    }


def test_blender_runner_reports_accessory_fallback_when_file_missing(tmp_path: Path) -> None:
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
    assert gps_record["import_mode"] == "procedural_fallback"
    assert gps_record["asset_file_exists"] is False
    assert "ASSET_FILE_MISSING" in gps_record["warnings"]
    assert metadata["asset_import_summary"]["asset_count"] == 9


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
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["generation_mode"] == "real_blender"
    assert metadata["tower_characteristics"]["structure"] == "lattice"
    assert metadata["preview_camera"]["camera"] == "camera_technical_front_full_tower"
    assert metadata["preview_camera"]["camera_type"] == "ORTHO"
    assert metadata["preview_camera"]["framing"] == "full_tower_front"
    assert metadata["preview_camera"]["render_backdrop"] == "preview_only_light_plane"
    assert metadata["procedural_objects_created"]
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
    assert all(record["asset_import_success"] is True for record in parametric_records)
    tower_record = next(
        record for record in parametric_records if record["asset_id"] == "TOWER_LATTICE_30M"
    )
    assert tower_record["import_mode"] == "parametric_generated"


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_runner_imports_requested_accessory_glbs_when_available(tmp_path: Path) -> None:
    scene = _accessory_scene()

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    assert result.mode == "real_blender"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["visual_elements"]["include_gps_antenna"] is True
    assert metadata["visual_elements"]["include_power_cabinet"] is True
    assert metadata["mechanical_tilts_deg"] == [5, 5, 5]
    assert metadata["asset_import_summary"]["asset_count"] == 9
    assert metadata["asset_import_summary"]["imported_glb_count"] == 2
    assert metadata["asset_import_summary"]["parametric_generated_count"] == 1
    assert metadata["asset_import_summary"]["internal_project_generated_count"] == 6
    records = {record["asset_id"]: record for record in metadata["asset_imports"]}
    assert records["GPS_ANTENNA_001"]["import_mode"] == "imported_glb"
    assert records["POWER_CABINET_001"]["import_mode"] == "imported_glb"
    assert records["TOWER_LATTICE_30M"]["import_mode"] == "parametric_generated"
    assert records["ANT_PANEL_5G_001"]["import_mode"] == "internal_project_generated"
    assert records["GPS_ANTENNA_001"]["asset_import_success"] is True
    assert records["POWER_CABINET_001"]["asset_import_success"] is True


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

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return subprocess.CompletedProcess(command, 42, stdout="", stderr="")
        output_dir = Path(command[-1])
        (output_dir / "design.glb").write_bytes(b"x" * 64)
        (output_dir / "preview.png").write_bytes(b"x" * 64)
        (output_dir / "scene_metadata.json").write_text('{"generation_mode":"real_blender"}')
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_resolve_blender_binary", lambda: Path("/fake/blender"))
    monkeypatch.setattr(runner, "_run_blender_command", fake_run)

    result = runner.generate(scene, tmp_path)

    assert attempts == 2
    assert result.status == "generated"
    assert result.mode == "real_blender"


def _accessory_scene():
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
