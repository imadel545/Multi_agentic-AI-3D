from pathlib import Path

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


def test_incoherent_antenna_height_requires_confirmation_before_scene(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        (
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 35m. "
            "Azimuts : 0°, 120°, 240°."
        ),
    )

    assert result.status == "failed"
    assert result.requirements is not None
    assert result.requirements.antenna_install_height_m == 27
    assert result.requirements.requires_confirmation is True
    assert result.scene is None
    assert result.generation is None
    assert [error.code for error in result.report.errors] == ["INPUT_CONFIRMATION_REQUIRED"]


def test_invalid_explicit_azimuth_is_traceably_normalized_before_scene(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        "Créer un site 5G sur pylône treillis 30m. Installer 1 secteur à 24m. Azimuts : 370°.",
    )

    assert result.status == "failed"
    assert result.requirements is not None
    assert result.requirements.azimuths_deg == [10]
    assert result.requirements.repair_events[0].before == {"azimuths_deg": [370.0]}
    assert result.requirements.repair_events[0].after == {"azimuths_deg": [10.0]}
    assert result.scene is not None
    assert result.scene.sectors[0].azimuth_deg == 10


def test_sector_azimuth_mismatch_requires_confirmation_before_scene(tmp_path: Path) -> None:
    result = _run_prompt(
        tmp_path,
        (
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°."
        ),
    )

    assert result.status == "failed"
    assert result.requirements is not None
    assert result.requirements.requires_confirmation is True
    assert result.scene is None
    assert result.generation is None
    assert [error.code for error in result.report.errors] == ["INPUT_CONFIRMATION_REQUIRED"]


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
        allow_blender_fallback=True,
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
        allow_blender_fallback=True,
    )
    return orchestrator.run(
        workflow_id="wf_scene_repair",
        requirements_text=prompt,
        detail_level="high",
        output_dir=tmp_path / "outputs",
        use_llm=False,
    )


class BrokenScenePlanner:
    def build_scene_spec(self, workflow_id, requirements, tower, antenna, radio, **kwargs):
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
