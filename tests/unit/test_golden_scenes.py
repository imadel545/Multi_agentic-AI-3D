import json
import shutil
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner

GOLDEN_SCENES = [
    "golden_5g_lattice_30m_3sector",
    "golden_4g_rooftop_2sector",
    "golden_small_cell_pole",
    "golden_microwave_dish_site",
]


@pytest.mark.parametrize("scene_name", GOLDEN_SCENES)
def test_golden_scene_contract_rejects_missing_blender(scene_name: str, tmp_path: Path) -> None:
    golden_dir = Path("tests/golden_scenes") / scene_name
    requirements_text = (golden_dir / "input_requirements.txt").read_text(encoding="utf-8")
    expected_requirements = _load_json(golden_dir / "expected_requirement_spec.json")
    expected_scene = _load_json(golden_dir / "expected_scene_spec.json")
    expected_validation = _load_json(golden_dir / "expected_validation.json")
    registry = AssetRegistry(Path("assets/manifests"))
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
        allow_blender_fallback=True,
    )

    result = orchestrator.run(
        workflow_id=scene_name,
        requirements_text=requirements_text,
        detail_level=expected_requirements["detail_level"],
        output_dir=tmp_path / scene_name,
        use_llm=False,
    )

    assert result.status == "failed"
    assert result.requirements is not None
    assert result.scene is not None
    assert expected_validation["status"] == "passed"
    assert result.report.status == "failed"
    _assert_requirement_spec(result.requirements.model_dump(), expected_requirements)
    _assert_scene_spec(result.scene, expected_scene)
    for check in expected_validation["required_checks"]:
        assert result.report.checks[check] is True
    assert result.generation is not None
    assert result.generation.mode == "fallback_no_blender"
    assert result.qa_report is not None
    assert result.qa_report.status == "failed"
    assert result.glb_inspection is not None
    assert result.glb_inspection.structural_qa_passed is False


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
@pytest.mark.parametrize("scene_name", GOLDEN_SCENES)
def test_golden_glb_structure_if_blender_available(scene_name: str, tmp_path: Path) -> None:
    golden_dir = Path("tests/golden_scenes") / scene_name
    requirements_text = (golden_dir / "input_requirements.txt").read_text(encoding="utf-8")
    expected_requirements = _load_json(golden_dir / "expected_requirement_spec.json")
    expected_structure = _load_json(golden_dir / "expected_glb_structure.json")
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
        allow_blender_fallback=True,
    )

    result = orchestrator.run(
        workflow_id=f"{scene_name}_real_blender",
        requirements_text=requirements_text,
        detail_level=expected_requirements["detail_level"],
        output_dir=tmp_path / scene_name,
        use_llm=False,
    )

    assert result.status == "completed"
    assert result.requirement_coverage is not None
    assert result.requirement_coverage.passed is True
    assert result.completion_certificate is not None
    assert result.completion_certificate.status == "issued"
    assert result.generation is not None
    assert result.generation.mode == "real_blender"
    assert result.glb_inspection is not None
    assert result.glb_inspection.inspection_mode == "glb_parse"
    assert result.glb_inspection.valid_primitive_count == result.glb_inspection.primitive_count
    assert result.glb_inspection.binary_chunk_count == 1
    assert result.glb_inspection.checks["semantic_mesh_coverage_complete"] is True
    assert result.glb_inspection.node_count >= expected_structure["min_node_count"]
    assert result.glb_inspection.mesh_count >= expected_structure["min_mesh_count"]
    for check, expected in expected_structure["expected"].items():
        assert result.glb_inspection.checks[check] is expected


def _assert_requirement_spec(actual: dict, expected: dict) -> None:
    for key, value in expected.items():
        assert actual[key] == value


def _assert_scene_spec(scene, expected: dict) -> None:
    assert scene.network_type == expected["network_type"]
    assert scene.tower.asset_id == expected["tower_asset_id"]
    assert scene.tower.height_m == expected["tower_height_m"]
    assert len(scene.sectors) == expected["sector_count"]
    assert scene.sectors[0].antenna_asset_id == expected["antenna_asset_id"]
    assert scene.sectors[0].radio_asset_id == expected["radio_asset_id"]
    assert scene.sectors[0].install_height_m == expected["install_height_m"]
    assert [sector.azimuth_deg for sector in scene.sectors] == expected["azimuths_deg"]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
