from pathlib import Path

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


def test_scene_repair_antenna_height_success(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        (
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 35m. "
            "Azimuts : 0°, 120°, 240°."
        ),
    )

    assert result.status == "completed"
    assert result.requirements is not None
    assert result.requirements.antenna_install_height_m == 27
    assert _repair_codes(result) == ["SCENE_SPEC_REPAIRED_ANTENNA_HEIGHT"]
    assert "scene_repair_handler" in [entry["node"] for entry in result.trace]
    assert result.generation is not None


def test_scene_repair_azimuth_normalization_success(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        "Créer un site 5G sur pylône treillis 30m. Installer 1 secteur à 24m. Azimuts : 370°.",
    )

    assert result.status == "completed"
    assert result.scene is not None
    assert result.scene.sectors[0].azimuth_deg == 10
    assert _repair_codes(result) == ["SCENE_SPEC_REPAIRED_AZIMUTH_NORMALIZED"]


def test_scene_repair_sector_count_success_or_explicit_fail(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        (
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°."
        ),
    )

    assert result.status == "completed"
    assert result.scene is not None
    assert [sector.azimuth_deg for sector in result.scene.sectors] == [0, 120, 240]
    assert _repair_codes(result) == ["SCENE_SPEC_REPAIRED_SECTOR_COUNT"]


def test_scene_repair_exhausts_attempts_without_blender(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
    )
    orchestrator.scene_planner = BrokenScenePlanner()

    result = orchestrator.run(
        workflow_id="wf_non_repairable_scene",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "non_repairable",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert result.generation is None
    assert nodes.count("scene_repair_handler") == 2
    assert "generate_blender" not in nodes


def _run_prompt(tmp_path: Path, prompt: str):
    registry = AssetRegistry(Path("assets/manifests"))
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
    )
    return orchestrator.run(
        workflow_id="wf_scene_repair",
        requirements_text=prompt,
        detail_level="high",
        output_dir=tmp_path / "outputs",
        use_llm=False,
    )


def _repair_codes(result) -> list[str]:
    return [
        event["warning_code"]
        for route in result.route_history
        for event in route.get("events", [])
        if event.get("handler") == "scene_repair_handler"
    ]


class BrokenScenePlanner:
    def build_scene_spec(self, workflow_id, requirements, tower, antenna, radio):
        return SceneSpec(
            scene_id=workflow_id,
            network_type=requirements.network_type,
            tower=SceneAssetPlacement(
                asset_id=tower.asset_id,
                position=[0, 0, 0],
                rotation_deg=[0, 0, 0],
                height_m=requirements.tower_height_m,
            ),
            sectors=[
                SectorSpec(
                    sector_id="S1",
                    antenna_asset_id="MISSING_ANTENNA",
                    radio_asset_id=radio.asset_id if radio else None,
                    install_height_m=requirements.antenna_install_height_m,
                    azimuth_deg=requirements.azimuths_deg[0],
                    beamwidth_deg=requirements.beamwidth_deg,
                )
            ],
        )
