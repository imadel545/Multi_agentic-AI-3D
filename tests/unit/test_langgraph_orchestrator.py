from pathlib import Path

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.quality import QualityGateReport
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.rag import RagService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner, GenerationResult


def test_langgraph_orchestrator_runs_full_controlled_workflow(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    rag_service = RagService(project_root=Path.cwd(), qdrant_path=tmp_path / "qdrant")
    rag_service.reindex()
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=rag_service,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
        allow_blender_fallback=True,
    )

    result = orchestrator.run(
        workflow_id="wf_langgraph",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "outputs",
        use_llm=False,
    )

    assert result.status == "completed"
    assert result.scene is not None
    assert result.generation is not None
    assert result.generation.mode == "fallback_no_blender"
    assert result.total_duration_ms >= 0
    assert result.workflow_trace.workflow_id == "wf_langgraph"
    assert result.workflow_trace.total_duration_ms == result.total_duration_ms
    assert result.workflow_trace.metrics["rag_context_count"] == len(result.rag_context)
    assert [entry["node"] for entry in result.trace] == [
        "extract_requirements",
        "retrieve_rag_context",
        "select_assets",
        "validate_requirements",
        "plan_scene",
        "validate_scene",
        "pre_blender_gate",
        "generate_blender",
        "blender_failure_handler",
        "qa_generation",
        "post_blender_gate",
    ]
    assert len(result.quality_gate_reports) == 2
    assert all(gate.passed for gate in result.quality_gate_reports)
    assert len(result.workflow_trace.quality_gates) == 2
    assert all("duration_ms" in entry for entry in result.trace)
    assert result.metrics["rag_duration_ms"] >= 0
    assert result.metrics["planning_duration_ms"] >= 0
    assert result.metrics["blender_duration_ms"] >= 0
    assert result.metrics["qa_duration_ms"] >= 0
    assert result.metrics["artifact_size_bytes"] > 0
    assert result.glb_inspection is not None
    assert result.glb_inspection.structural_qa_passed is True
    assert result.preview_inspection is not None
    assert result.preview_inspection.preview_qa_passed is True
    assert result.workflow_trace.glb_inspection is not None
    assert result.workflow_trace.preview_inspection is not None
    assert result.metrics["requirements_hash"]
    assert result.metrics["scene_spec_hash"]
    assert result.metrics["asset_manifest_hash"]
    assert result.metrics["knowledge_index_hash"]
    assert "cache_hits" in result.metrics
    assert "cache_misses" in result.metrics


def test_glb_inspection_integrated_in_qa(tmp_path: Path) -> None:
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
        workflow_id="wf_structural_qa",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "structural_qa",
        use_llm=False,
    )

    assert result.status == "completed"
    assert result.qa_report is not None
    assert result.qa_report.checks["glb_structure_valid"] is True
    assert result.qa_report.checks["expected_objects_present"] is True
    assert result.qa_report.checks["preview_resolution_valid"] is True
    assert result.report.glb_inspection is not None
    assert result.report.preview_inspection is not None


def test_langgraph_orchestrator_recalls_and_writes_sqlite_memory(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    memory_service = MemoryService(tmp_path / "memory.db")
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        memory_service=memory_service,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
        allow_blender_fallback=True,
    )
    prompt = (
        "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°."
    )

    first = orchestrator.run(
        workflow_id="wf_memory_first",
        requirements_text=prompt,
        detail_level="high",
        output_dir=tmp_path / "first",
        use_llm=False,
    )
    second = orchestrator.run(
        workflow_id="wf_memory_second",
        requirements_text=prompt,
        detail_level="high",
        output_dir=tmp_path / "second",
        use_llm=False,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.memory_recall is not None
    assert first.memory_recall.memory_hits == 0
    assert second.memory_recall is not None
    assert second.memory_recall.memory_hits >= 1
    assert second.memory_recall.memory_context_count >= 1
    assert second.memory_writeback is not None
    assert second.memory_writeback["workflow_memory_count"] == 2
    assert "memory_recall" in [entry["node"] for entry in second.trace]
    assert "memory_writeback" in [entry["node"] for entry in second.trace]
    assert len(second.quality_gate_reports) == 2
    assert second.metrics["memory_hits"] >= 1
    assert second.metrics["memory_context_count"] >= 1
    assert second.metrics["memory_duration_ms"] >= 0


def test_invalid_rule_blocks_blender(tmp_path: Path) -> None:
    registry = MissingRadioRegistry(Path("assets/manifests"))
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
        workflow_id="wf_invalid_rule",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "invalid",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert result.generation is None
    assert "rule_violation_handler" in nodes
    assert "generate_blender" not in nodes
    assert result.route_history[0]["route"] == "rule_violation"


def test_pre_blender_quality_gate_blocks_blender(tmp_path: Path) -> None:
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
        workflow_id="wf_quality_gate_blocks_blender",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "quality_gate_blocks",
        use_llm=False,
    )

    nodes = [entry["node"] for entry in result.trace]
    assert result.status == "failed"
    assert runner.calls == 0
    assert result.generation is None
    assert "pre_blender_gate" in nodes
    assert "quality_gate_failure_handler" in nodes
    assert "generate_blender" not in nodes
    assert result.route_history[0]["route"] == "quality_gate_failed"


class MissingRadioRegistry(AssetRegistry):
    def select_asset(self, asset_type: str, network_type: str, tower_type: str | None = None):
        if asset_type == "radio":
            return None
        return super().select_asset(asset_type, network_type, tower_type)


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
