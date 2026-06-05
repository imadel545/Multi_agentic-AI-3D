from pathlib import Path

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.requirements import RequirementSpec
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


def test_asset_fallback_selects_compatible_tower(tmp_path: Path) -> None:
    result = _run_with_requirements(
        tmp_path,
        RequirementSpec(
            network_type="5G",
            tower_type="unknown_lattice_variant",
            tower_height_m=30,
            sector_count=3,
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
        ),
    )

    assert result.status == "completed"
    assert result.scene is not None
    assert result.scene.tower.asset_id == "TOWER_LATTICE_30M"
    assert "ASSET_FALLBACK_TOWER_SELECTED" in _warning_codes(result)


def test_asset_fallback_selects_compatible_antenna(tmp_path: Path) -> None:
    result = _run_with_requirements(
        tmp_path,
        RequirementSpec(
            network_type="5G",
            tower_type="lattice_tower",
            tower_height_m=30,
            sector_count=3,
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
        ),
        registry=MissingExactAntennaRegistry(Path("assets/manifests")),
    )

    assert result.status == "completed"
    assert result.scene is not None
    assert result.scene.sectors[0].antenna_asset_id == "ANT_PANEL_5G_001"
    assert "ASSET_FALLBACK_ANTENNA_SELECTED" in _warning_codes(result)


def test_asset_fallback_fails_when_no_compatible_asset(tmp_path: Path) -> None:
    result = _run_with_requirements(
        tmp_path,
        RequirementSpec(
            network_type="5G",
            tower_type="unknown_lattice_variant",
            tower_height_m=30,
            sector_count=3,
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
        ),
        registry=NoFallbackRegistry(Path("assets/manifests")),
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert result.generation is None
    assert "asset_fallback_handler" in nodes
    assert "ASSET_FALLBACK_FAILED" in [error.code for error in result.report.errors]


def test_asset_fallback_visible_in_trace_and_report(tmp_path: Path) -> None:
    result = _run_with_requirements(
        tmp_path,
        RequirementSpec(
            network_type="5G",
            tower_type="unknown_lattice_variant",
            tower_height_m=30,
            sector_count=3,
            antenna_install_height_m=24,
            azimuths_deg=[0, 120, 240],
        ),
    )

    fallback_step = next(
        entry for entry in result.trace if entry["node"] == "asset_fallback_handler"
    )
    assert fallback_step["route"] == "asset_fallback"
    assert "ASSET_FALLBACK_TOWER_SELECTED" in fallback_step["warnings"]
    assert "ASSET_FALLBACK_TOWER_SELECTED" in _warning_codes(result)


def _run_with_requirements(
    tmp_path: Path,
    requirements: RequirementSpec,
    registry: AssetRegistry | None = None,
):
    orchestrator = DesignOrchestrator(
        registry=registry or AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(
            provider=StaticRequirementProvider(requirements),
            provider_name="static",
            enabled=True,
        ),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
    )
    return orchestrator.run(
        workflow_id="wf_asset_fallback",
        requirements_text="static",
        detail_level="high",
        output_dir=tmp_path / "outputs",
        use_llm=True,
    )


def _warning_codes(result) -> list[str]:
    return [warning.code for warning in result.report.warnings]


class StaticRequirementProvider:
    def __init__(self, requirements: RequirementSpec) -> None:
        self.requirements = requirements

    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        return self.requirements


class MissingExactAntennaRegistry(AssetRegistry):
    def select_asset(self, asset_type: str, network_type: str, tower_type: str | None = None):
        if asset_type == "antenna":
            raise LookupError("exact antenna missing")
        return super().select_asset(asset_type, network_type, tower_type)


class NoFallbackRegistry(AssetRegistry):
    def select_tower_fallback(self, tower_type: str, network_type: str, min_height_m: float):
        raise LookupError("no fallback tower")
