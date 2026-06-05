import json
import shutil
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
    assert "TOWER_LATTICE_30M" in metadata["assets_used"]


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
    assert metadata["procedural_objects_created"]
