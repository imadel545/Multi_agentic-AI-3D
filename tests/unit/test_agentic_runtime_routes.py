import shutil
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.quality import QualityGateReport
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner, GenerationResult

PROMPT_5G = (
    "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
    "Azimuts : 0°, 120°, 240°."
)


def test_agentic_route_blocks_unconfirmed_input_before_planning(tmp_path: Path) -> None:
    orchestrator = _orchestrator()

    result = orchestrator.run(
        workflow_id="wf_repair_success",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°."
        ),
        detail_level="high",
        output_dir=tmp_path / "repair_success",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert result.requirements is not None
    assert result.requirements.requires_confirmation is True
    assert result.requirements.azimuths_deg == [0.0, 120.0, 240.0]
    assert result.scene is None
    assert result.generation is None
    assert nodes == ["extract_requirements", "rule_violation_handler"]
    assert [error.code for error in result.report.errors] == ["INPUT_CONFIRMATION_REQUIRED"]


def test_agentic_route_unrepairable_failure(tmp_path: Path) -> None:
    orchestrator = UnrepairableSceneOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
    )

    result = orchestrator.run(
        workflow_id="wf_unrepairable",
        requirements_text=PROMPT_5G,
        detail_level="high",
        output_dir=tmp_path / "unrepairable",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    scene_repair_routes = [
        event for event in result.route_history if event["route"] == "scene_repair"
    ]
    assert result.status == "failed"
    assert result.generation is None
    assert nodes.count("scene_repair_handler") == 2
    assert "generate_blender" not in nodes
    assert [event["attempt"] for event in scene_repair_routes] == [1, 2]


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is required to create truthful workflow memory",
)
def test_memory_recall_before_planning(tmp_path: Path) -> None:
    orchestrator = _orchestrator(
        memory_service=MemoryService(tmp_path / "memory.db"), real_blender=True
    )
    _run_success(orchestrator, "wf_memory_seed", PROMPT_5G, tmp_path / "seed")

    result = _run_success(
        orchestrator,
        "wf_memory_recall",
        "Dimensionner un site 5G lattice tower 30m avec trois secteurs à 24m.",
        tmp_path / "recall",
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.memory_recall is not None
    assert result.memory_recall.memory_hits >= 1
    assert nodes.index("memory_recall") < nodes.index("plan_scene")


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is required to create truthful workflow memory",
)
def test_memory_writeback_after_success(tmp_path: Path) -> None:
    memory_service = MemoryService(tmp_path / "memory.db")
    orchestrator = _orchestrator(memory_service=memory_service, real_blender=True)

    result = _run_success(orchestrator, "wf_memory_writeback", PROMPT_5G, tmp_path / "writeback")

    nodes = [entry["node"] for entry in result.trace]
    assert result.memory_writeback is not None
    assert result.memory_writeback["workflow_memory_count"] == 1
    assert nodes.index("post_blender_gate") < nodes.index("memory_writeback")


def test_route_history_contains_input_blocking_decision(tmp_path: Path) -> None:
    result = _orchestrator().run(
        workflow_id="wf_route_history",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°."
        ),
        detail_level="high",
        output_dir=tmp_path / "route_history",
        use_llm=False,
    )

    routes = [event["route"] for event in result.route_history]
    assert routes == ["rule_violation"]
    assert all(
        {"handler", "route", "attempt", "events"} <= event.keys() for event in result.route_history
    )


def test_no_blender_call_before_quality_gate(tmp_path: Path) -> None:
    runner = CountingBlenderRunner(
        project_root=Path.cwd(),
        blender_binary="definitely-missing-blender-binary",
    )
    orchestrator = FailingPreGateOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=runner,
    )

    result = orchestrator.run(
        workflow_id="wf_no_blender_before_gate",
        requirements_text=PROMPT_5G,
        detail_level="high",
        output_dir=tmp_path / "blocked",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert runner.calls == 0
    assert "pre_blender_gate" in nodes
    assert "quality_gate_failure_handler" in nodes
    assert "generate_blender" not in nodes


def _orchestrator(
    memory_service: MemoryService | None = None, *, real_blender: bool = False
) -> DesignOrchestrator:
    return DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        memory_service=memory_service,
        blender_runner=BlenderRunner(project_root=Path.cwd())
        if real_blender
        else BlenderRunner(
            project_root=Path.cwd(), blender_binary="definitely-missing-blender-binary"
        ),
        allow_blender_fallback=True,
    )


def _run_success(
    orchestrator: DesignOrchestrator,
    workflow_id: str,
    requirements_text: str,
    output_dir: Path,
):
    result = orchestrator.run(
        workflow_id=workflow_id,
        requirements_text=requirements_text,
        detail_level="high",
        output_dir=output_dir,
        use_llm=False,
    )
    assert result.status == "completed"
    return result


class UnrepairableSceneOrchestrator(DesignOrchestrator):
    def _validate_scene(self, state: dict) -> dict:
        report = ValidationReport(
            design_id=state["workflow_id"],
            status="failed",
            score=0.0,
            checks={"forced_unrepairable_scene": False},
            warnings=[],
            errors=[
                ValidationIssue(
                    code="FORCED_UNREPAIRABLE_SCENE",
                    message="Forced unrepairable scene validation failure.",
                    severity="error",
                )
            ],
        )
        return {
            "scene_report": report,
            "report": report,
            "trace": [
                *state.get("trace", []),
                {
                    "node": "validate_scene",
                    "status": "failed",
                    "detail": "forced_unrepairable_scene",
                    "duration_ms": 0,
                    "warnings": [],
                    "errors": ["FORCED_UNREPAIRABLE_SCENE"],
                    "route": "scene_repair",
                    "attempt": state.get("repair_attempts", 0),
                },
            ],
        }


class CountingBlenderRunner(BlenderRunner):
    def __init__(self, project_root: Path, blender_binary: str) -> None:
        super().__init__(project_root=project_root, blender_binary=blender_binary)
        self.calls = 0

    def generate(self, scene: SceneSpec, output_dir: Path) -> GenerationResult:
        self.calls += 1
        return super().generate(scene, output_dir)


class FailingPreGateOrchestrator(DesignOrchestrator):
    def _pre_blender_gate(self, state: dict) -> dict:
        gate = QualityGateReport(
            stage="pre_blender",
            passed=False,
            checks={"forced_quality_gate_failure": False},
            critical_errors=["forced_quality_gate_failure"],
            warnings=[],
            duration_ms=0,
        )
        report = ValidationReport(
            design_id=state["workflow_id"],
            status="failed",
            score=0.0,
            checks={"pre_blender_forced_failure": False},
            errors=[
                ValidationIssue(
                    code="PRE_BLENDER_FORCED_FAILURE",
                    message="Forced pre-Blender quality gate failure.",
                    severity="error",
                )
            ],
        )
        return {
            "pre_blender_gate": gate,
            "quality_gate_reports": [*state.get("quality_gate_reports", []), gate.model_dump()],
            "report": report,
            "trace": [
                *state.get("trace", []),
                {
                    "node": "pre_blender_gate",
                    "status": "failed",
                    "detail": "forced_quality_gate_failure",
                    "duration_ms": 0,
                    "warnings": [],
                    "errors": gate.critical_errors,
                    "route": "quality_gate_failed",
                    "attempt": state.get("repair_attempts", 0),
                },
            ],
        }
