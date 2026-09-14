from pathlib import Path

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.requirements import RequirementSpec
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner


def test_unknown_tower_family_blocks_before_scene_and_blender(tmp_path: Path) -> None:
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

    assert result.status == "failed"
    assert result.scene is None
    assert result.generation is None
    assert result.assembly_plan is None
    assert [error.code for error in result.report.errors] == ["ASSET_SELECTION_FAILED"]
    assert [entry["node"] for entry in result.trace][-1] == "select_assets"


def test_missing_required_asset_blocks_without_looser_registry_fallback(tmp_path: Path) -> None:
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

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert result.scene is None
    assert result.generation is None
    assert "select_assets" in nodes
    assert "asset_fallback_handler" not in nodes
    assert [error.code for error in result.report.errors] == ["ASSET_SELECTION_FAILED"]


def test_asset_selection_failure_trace_is_user_safe_and_terminal(tmp_path: Path) -> None:
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

    selection = result.trace[-1]
    assert selection["node"] == "select_assets"
    assert selection["status"] == "failed"
    assert selection["errors"] == ["ASSET_SELECTION_FAILED"]
    assert "fallback" not in selection["detail"]


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
        allow_blender_fallback=True,
    )
    return orchestrator.run(
        workflow_id="wf_asset_selection",
        requirements_text="static",
        detail_level="high",
        output_dir=tmp_path / "outputs",
        use_llm=True,
    )


class StaticRequirementProvider:
    def __init__(self, requirements: RequirementSpec) -> None:
        self.requirements = requirements

    def extract_requirements(self, requirements_text: str, detail_level: str) -> RequirementSpec:
        return self.requirements


class MissingExactAntennaRegistry(AssetRegistry):
    def select_asset(self, asset_type: str, network_type: str, tower_type: str | None = None):
        if asset_type == "antenna":
            raise LookupError("no qualified antenna satisfies the requested slot")
        return super().select_asset(asset_type, network_type, tower_type)
