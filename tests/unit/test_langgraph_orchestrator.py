import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.agents.scene_planner import ScenePlanner
from core.contracts.common import WarningItem
from core.contracts.planning_decision import PlanningModelDecision
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import (
    SceneAccessoryPlacement,
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)
from core.contracts.tower import TowerCharacteristics
from core.contracts.validation import ValidationIssue, ValidationReport
from core.llm.planning_decision import resolve_model_decision
from core.memory import MemoryService
from core.orchestration import DesignOrchestrator
from core.orchestration.langgraph_orchestrator import (
    _emit_node_started_runtime_event,
    _scene_with_revision_dependencies,
)
from core.rag import RagService
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner, GenerationResult


def test_scene_revision_rebinds_tower_and_repositions_derived_accessories() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    scene = SceneSpec(
        scene_id="wf_revision_dependencies",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=40.0,
            characteristics=TowerCharacteristics(
                structure="monopole",
                leg_count=1,
                base_width_m=1.2,
                top_width_m=0.6,
                foundation_type="pole_base",
            ),
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                radio_asset_id="RRU_SMALL_001",
                install_height_m=24.0,
                azimuth_deg=0.0,
                beamwidth_deg=65.0,
            )
        ],
        visual_elements=VisualElements(
            include_power_cabinet=True,
            include_gps_antenna=True,
        ),
        accessory_assets=[
            SceneAccessoryPlacement(
                asset_id="GPS_ANTENNA_001",
                asset_type="gps",
                position=[0.0, 2.1, 29.5],
                rotation_deg=[0.0, 0.0, 0.0],
            )
        ],
    )

    normalized = _scene_with_revision_dependencies(scene, registry)

    assert normalized.tower.asset_id == "TOWER_MONOPOLE_30M"
    assert normalized.tower.generation_reason == (
        "revision dependencies normalized from tower structure"
    )
    gps = next(item for item in normalized.accessory_assets if item.asset_type == "gps")
    cabinet = next(item for item in normalized.accessory_assets if item.asset_type == "cabinet")
    assert gps.position[2] == 39.5
    assert cabinet.position[2] == 0.0


def test_scene_revision_removes_disabled_derived_accessories() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    scene = SceneSpec(
        scene_id="wf_revision_remove_accessory",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=30.0,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                install_height_m=24.0,
                azimuth_deg=0.0,
                beamwidth_deg=65.0,
            )
        ],
        visual_elements=VisualElements(include_gps_antenna=False),
        accessory_assets=[
            SceneAccessoryPlacement(
                asset_id="GPS_ANTENNA_001",
                asset_type="gps",
                position=[0.0, 2.1, 29.5],
                rotation_deg=[0.0, 0.0, 0.0],
            )
        ],
    )

    normalized = _scene_with_revision_dependencies(scene, registry)

    assert all(item.asset_type != "gps" for item in normalized.accessory_assets)


def test_gpt_planning_decision_uses_only_validated_rag_candidates(tmp_path: Path) -> None:
    class SelectingPlanningClient:
        def __init__(self) -> None:
            self.request = None

        def decide(self, request):
            self.request = request
            decision = PlanningModelDecision.model_validate(
                {
                    "selections": [
                        {
                            "field": field,
                            "action": "select_candidate"
                            if field == "antenna_install_height_m"
                            else "keep_current",
                            "candidate_id": next(
                                (
                                    candidate.candidate_id
                                    for candidate in request.candidates
                                    if candidate.field == field
                                ),
                                None,
                            )
                            if field == "antenna_install_height_m"
                            else None,
                            "reason": "Selected validated evidence."
                            if field.startswith("antenna")
                            else "Kept source value.",
                        }
                        for field in (
                            "antenna_install_height_m",
                            "beamwidth_deg",
                            "include_cables",
                            "include_sector_beams",
                        )
                    ]
                }
            )
            return resolve_model_decision(
                request,
                decision,
                model_name="openai/gpt-oss-120b",
            )

    client = SelectingPlanningClient()
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd(), blender_binary="missing"),
        planning_decision_client=client,  # type: ignore[arg-type]
    )
    requirements = RequirementSpec(
        network_type="5G",
        site_type="telecom_site",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_type="panel_5g",
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        mechanical_tilt_deg=3,
        electrical_tilt_deg=0,
        beamwidth_deg=65,
        include_rru=True,
        include_cables=True,
        include_beams=True,
        include_labels=True,
        detail_level="high",
        warnings=[
            WarningItem(
                code="DEFAULT_INSTALL_HEIGHT_USED",
                message="Antenna install height was inferred.",
            )
        ],
    )
    state = {
        "workflow_id": "wf_planning_decision",
        "requirements": requirements,
        "rag_context": [
            {
                "collection": "telecom_rules",
                "doc_id": "rule:hba",
                "score": 0.94,
                "text": "For this 30 m lattice profile, use 25 m when HBA is unspecified.",
                "payload": {
                    "network_type": "5G",
                    "tower_type": "lattice_tower",
                    "planning_hints": {
                        "antenna_install_height_m": 25,
                        "beamwidth_deg": 90,
                    },
                },
            }
        ],
        "memory_recall": {
            "error_patterns": [
                {
                    "issue_code": "RF_SPACING_WARNING",
                    "message": "A prior matching site had RF spacing warnings.",
                    "severity": "warning",
                }
            ]
        },
        "trace": [],
    }

    update = orchestrator._decide_planning_context(state)  # noqa: SLF001

    assert update["rag_planning_resolution"]["antenna_install_height_m"] == 25
    assert update["rag_planning_resolution"]["beamwidth_deg"] == 65
    assert update["planning_decision"]["status"] == "primary"
    assert update["planning_decision"]["memory_risk_count"] == 1
    assert client.request is not None
    assert client.request.protected_fields == [
        "beamwidth_deg",
        "include_cables",
        "include_sector_beams",
    ]
    assert state["rag_context"][0]["payload"]["planning_hints"] == {
        "antenna_install_height_m": 25.0
    }


def test_runtime_event_sinks_are_isolated_per_concurrent_invocation(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
    )

    class ConcurrentGraph:
        def invoke(self, state: dict, config: dict) -> dict:
            barrier.wait(timeout=5)
            _emit_node_started_runtime_event(state, "extract_requirements")
            raise RuntimeError("stop after event")

    orchestrator.graph = ConcurrentGraph()
    received: dict[str, list[str]] = {"a": [], "b": []}

    def invoke(workflow_id: str, sink_name: str) -> None:
        def sink(event_workflow_id: str, _event_type: str, _payload: dict) -> None:
            received[sink_name].append(event_workflow_id)

        with pytest.raises(RuntimeError, match="stop after event"):
            orchestrator.run(
                workflow_id=workflow_id,
                requirements_text="Créer un site 5G",
                detail_level="high",
                output_dir=tmp_path / workflow_id,
                use_llm=False,
                runtime_event_sink=sink,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(invoke, "wf_concurrent_a", "a"),
            executor.submit(invoke, "wf_concurrent_b", "b"),
        ]
        for future in futures:
            future.result(timeout=10)

    assert received == {"a": ["wf_concurrent_a"], "b": ["wf_concurrent_b"]}


def test_scene_revision_asset_failure_has_one_terminal_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_type="panel_5g",
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_revision_missing_asset",
        requirements=requirements,
        tower=registry.get("TOWER_LATTICE_30M"),
        antenna=registry.get("ANT_PANEL_5G_001"),
        radio=registry.get("RRU_SMALL_001"),
    )
    scene = scene.model_copy(
        update={"tower": scene.tower.model_copy(update={"asset_id": "MISSING_TOWER"})}
    )
    monkeypatch.setattr(
        registry,
        "select_tower",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(LookupError("tower unavailable")),
    )

    result = orchestrator.run_scene_revision(
        workflow_id="wf_revision_missing_asset",
        scene=scene,
        output_dir=tmp_path / "revision",
        detail_level="high",
        revision_id="edit_missing_asset",
    )

    assert result.status == "failed"
    assert result.report.status == "failed"
    assert any(issue.code == "SCENE_REVISION_ASSET_ERROR" for issue in result.report.errors)
    assert [entry["node"] for entry in result.trace] == ["edit_prepare_revision"]


def test_langgraph_orchestrator_runs_full_controlled_workflow(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    rag_service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
    )
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

    assert result.status == "failed"
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
        "decide_planning_context",
        "select_assets",
        "validate_requirements",
        "plan_scene",
        "validate_scene",
        "pre_blender_gate",
        "generate_blender",
        "blender_failure_handler",
        "qa_generation",
        "qa_failure_handler",
    ]
    assert len(result.quality_gate_reports) == 1
    assert all(gate.passed for gate in result.quality_gate_reports)
    assert len(result.workflow_trace.quality_gates) == 1
    assert all("duration_ms" in entry for entry in result.trace)
    assert result.metrics["rag_duration_ms"] >= 0
    assert result.metrics["planning_duration_ms"] >= 0
    assert result.metrics["blender_duration_ms"] >= 0
    assert result.metrics["qa_duration_ms"] >= 0
    assert result.metrics["artifact_size_bytes"] > 0
    assert result.glb_inspection is not None
    assert result.glb_inspection.structural_qa_passed is False
    assert result.preview_inspection is not None
    assert result.preview_inspection.preview_qa_passed is False
    assert result.qa_report is not None
    assert result.qa_report.checks["generation_real_blender"] is False
    assert result.qa_report.checks["glb_inspection_available"] is False
    assert not Path(result.generation.artifacts["glb"]).exists()
    assert not Path(result.generation.artifacts["preview"]).exists()
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

    assert result.status == "failed"
    assert result.qa_report is not None
    assert result.qa_report.status == "failed"
    assert result.qa_report.checks["generation_real_blender"] is False
    assert result.qa_report.checks["glb_structure_valid"] is False
    assert result.qa_report.checks["expected_objects_present"] is False
    assert result.qa_report.checks["preview_resolution_valid"] is False
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

    assert first.status == "failed"
    assert second.status == "failed"
    assert first.memory_recall is not None
    assert first.memory_recall.memory_hits == 0
    assert second.memory_recall is not None
    assert second.memory_recall.memory_hits >= 1
    assert second.memory_recall.memory_context_count >= 1
    assert second.memory_recall.similar_workflows == []
    assert second.memory_recall.reusable_patterns == []
    assert second.memory_recall.error_patterns
    assert second.memory_writeback is not None
    assert second.memory_writeback["workflow_memory_count"] == 2
    assert "memory_recall" in [entry["node"] for entry in second.trace]
    assert "memory_writeback" in [entry["node"] for entry in second.trace]
    assert len(second.quality_gate_reports) == 1
    assert second.metrics["memory_hits"] >= 1
    assert second.metrics["memory_context_count"] >= 1
    assert second.metrics["memory_duration_ms"] >= 0


def test_memory_failures_are_visible_but_do_not_abort_the_graph(tmp_path: Path) -> None:
    class FailingMemory:
        def recall(self, _requirements):
            raise RuntimeError("recall unavailable")

        def write_workflow_summary(self, **_kwargs):
            raise RuntimeError("writeback unavailable")

    orchestrator = DesignOrchestrator(
        registry=AssetRegistry(Path("assets/manifests")),
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        memory_service=FailingMemory(),  # type: ignore[arg-type]
        blender_runner=BlenderRunner(
            project_root=Path.cwd(),
            blender_binary="definitely-missing-blender-binary",
        ),
        allow_blender_fallback=True,
    )

    result = orchestrator.run(
        workflow_id="wf_memory_unavailable",
        requirements_text=(
            "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        ),
        detail_level="high",
        output_dir=tmp_path / "memory-unavailable",
        use_llm=False,
    )

    traces = {entry["node"]: entry for entry in result.trace}
    assert traces["memory_recall"]["status"] == "failed"
    assert traces["memory_writeback"]["status"] == "failed"
    assert result.memory_recall is not None
    assert result.memory_recall.memory_hits == 0
    assert result.memory_writeback == {
        "status": "failed_non_blocking",
        "error": "RuntimeError: writeback unavailable",
    }


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
