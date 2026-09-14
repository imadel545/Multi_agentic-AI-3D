import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Command
from pydantic import ValidationError

from core.agents import GeometryProgramPlanner, ScenePlanner
from core.agents.blueprint_composer import BlueprintComposer
from core.agents.cognitive_design_planner import CognitiveDesignPlanner
from core.agents.cognitive_domain_router import (
    ConservativeDesignDomainRouter,
    DesignDomainRouteClient,
)
from core.agents.requirement_extractor import RequirementExtractor
from core.agents.rf_engineer import RfEngineerAgent
from core.agents.tower_engineer import TowerEngineerAgent, apply_tower_engineer_recommendations
from core.contracts.assembly import AssemblyPlan
from core.contracts.assets import AssetManifest
from core.contracts.capabilities import CapabilityObservation
from core.contracts.cognitive_design import CognitiveDesignPlan, DesignRouteDecision
from core.contracts.completion import (
    CompletionCertificate,
    RequirementCoverageCheck,
    RequirementCoverageReport,
)
from core.contracts.design_blueprint import BlueprintCoverageReport, DesignBlueprint
from core.contracts.geometry_program import GeometryProgram
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.memory import MemoryRecallResult
from core.contracts.planning_decision import (
    PlanningCandidate,
    PlanningCandidateProvenance,
    PlanningCurrentValues,
    PlanningDecisionRequest,
    PlanningMemoryRisk,
)
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import GeometryRequest, RequirementSpec
from core.contracts.rf_validation import RfValidationReport
from core.contracts.runtime import ActorKind, AgentStepTrace, DecisionAuthority, WorkflowTrace
from core.contracts.scene import RuntimeAssetMetadata, SceneSpec
from core.contracts.tower_validation import TowerValidationReport
from core.contracts.validation import ValidationIssue, ValidationReport
from core.llm.planning_decision import GroqPlanningDecisionClient
from core.memory import MemoryService
from core.performance import knowledge_index_hash, requirements_hash, scene_spec_hash
from core.qa import GenerationQA, GLBGeometryValidator, GLBInspector, PreviewInspector
from core.rag import RagService
from core.rag.planning import (
    RagPlanningEvidence,
    apply_bounded_planning_decision,
    collect_planning_evidence,
    resolve_planning_hints,
)
from core.repair.scene_repair import repair_scene_spec
from core.rules import RuleEngine
from core.services.assembly_compiler import resolve_scene_assembly
from core.services.assembly_planner import AssetAssemblyPlanner, BoundedAssemblyDecisionClient
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner, GenerationResult
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler, cognitive_plan_hash
from core.validation import validate_scene_spec
from core.validation.completion_certificate import build_completion_certificate
from core.validation.design_blueprint import (
    evaluate_blueprint_requirement_coverage,
    evaluate_blueprint_scene_coverage,
)
from core.validation.library_first import library_first_scene_violations
from core.validation.quality_gates import (
    evaluate_post_blender_gate,
    evaluate_pre_blender_gate,
)
from core.validation.requirement_coverage import evaluate_requirement_coverage

logger = logging.getLogger(__name__)

RuntimeEventSink = Callable[[str, str, dict], Any]
_RUNTIME_EVENT_SINKS: dict[str, RuntimeEventSink] = {}
_RUNTIME_EVENT_SINKS_LOCK = threading.Lock()


def _initial_checkpoint_thread_id(workflow_id: str) -> str:
    return f"{workflow_id}:initial"


def _revision_checkpoint_thread_id(workflow_id: str, revision_id: str | None) -> str:
    return f"{workflow_id}:revision:{revision_id or 'unknown'}"


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    runtime_event_sink_id: str
    entry_mode: str
    revision_id: str | None
    requirements_text: str
    detail_level: str
    use_llm: bool | None
    output_dir: Path
    requirements: RequirementSpec
    extraction_provider: str
    extraction_fallback_used: bool
    extraction_error: str | None
    rag_context: list[dict]
    rag_planning_resolution: dict
    planning_decision: dict
    memory_recall: dict
    memory_writeback: dict
    asset_error: str
    tower: AssetManifest
    antenna: AssetManifest
    radio: AssetManifest | None
    accessory_assets: list[AssetManifest]
    selected_assets: list[AssetManifest]
    assembly_plan: AssemblyPlan
    requirement_report: ValidationReport
    scene: SceneSpec
    scene_report: ValidationReport
    requirement_coverage: RequirementCoverageReport
    pre_blender_gate: QualityGateReport
    generation: GenerationResult
    glb_inspection: GlbInspectionReport
    geometry_validation: GeometryValidationReport
    preview_inspection: PreviewInspectionReport
    qa_report: ValidationReport
    post_blender_gate: QualityGateReport
    completion_certificate: CompletionCertificate
    quality_gate_reports: list[dict]
    requirements_hash: str
    scene_spec_hash: str
    asset_manifest_hash: str
    knowledge_index_hash: str
    cache_metrics: dict[str, int]
    report: ValidationReport
    trace: list[dict]
    errors: list[str]
    max_repair_attempts: int
    repair_attempts: int
    scene_repair_recorded: bool
    route_history: list[dict]
    tower_validation: TowerValidationReport
    rf_validation: RfValidationReport
    design_blueprint: DesignBlueprint
    blueprint_requirement_coverage: BlueprintCoverageReport
    blueprint_scene_coverage: BlueprintCoverageReport
    geometry_programs: list[GeometryProgram]
    geometry_program_error: str
    design_route: DesignRouteDecision
    cognitive_plan: CognitiveDesignPlan
    capability_observations: list[CapabilityObservation]


@dataclass(frozen=True)
class OrchestratorResult:
    workflow_id: str
    status: str
    requirements: RequirementSpec | None
    scene: SceneSpec | None
    llm_provider: str | None
    llm_fallback_used: bool | None
    llm_error: str | None
    report: ValidationReport
    requirement_report: ValidationReport | None
    scene_report: ValidationReport | None
    qa_report: ValidationReport | None
    glb_inspection: GlbInspectionReport | None
    geometry_validation: GeometryValidationReport | None
    preview_inspection: PreviewInspectionReport | None
    requirement_coverage: RequirementCoverageReport | None
    completion_certificate: CompletionCertificate | None
    quality_gate_reports: list[QualityGateReport]
    generation: GenerationResult | None
    rag_context: list[dict]
    planning_decision: dict | None
    memory_recall: MemoryRecallResult | None
    memory_writeback: dict | None
    trace: list[dict]
    workflow_trace: WorkflowTrace
    total_duration_ms: int
    tower_validation: TowerValidationReport | None
    rf_validation: RfValidationReport | None
    design_blueprint: DesignBlueprint | None
    assembly_plan: AssemblyPlan | None
    blueprint_requirement_coverage: BlueprintCoverageReport | None
    blueprint_scene_coverage: BlueprintCoverageReport | None
    metrics: dict[str, int | float | str | bool | None]
    route_history: list[dict]
    cognitive_plan: CognitiveDesignPlan | None = None
    capability_observations: list[CapabilityObservation] = field(default_factory=list)


class DesignOrchestrator:
    def __init__(
        self,
        registry: AssetRegistry,
        extractor: RequirementExtractor,
        rag_service: RagService | None,
        blender_runner: BlenderRunner,
        memory_service: MemoryService | None = None,
        checkpoint_saver: Any | None = None,
        planning_decision_client: GroqPlanningDecisionClient | None = None,
        asset_selection_client: BoundedAssemblyDecisionClient | None = None,
        allow_blender_fallback: bool = False,
        runtime_event_sink: RuntimeEventSink | None = None,
        blueprint_composer: BlueprintComposer | None = None,
        geometry_program_planner: GeometryProgramPlanner | None = None,
        design_domain_router: DesignDomainRouteClient | None = None,
        cognitive_design_planner: CognitiveDesignPlanner | None = None,
        cognitive_scene_compiler: CognitiveSceneCompiler | None = None,
        library_first_generation: bool = False,
        project_specific_roles: frozenset[str] = frozenset(),
    ) -> None:
        self.registry = registry
        self.extractor = extractor
        self.rag_service = rag_service
        self.memory_service = memory_service
        self.blender_runner = blender_runner
        self.allow_blender_fallback = allow_blender_fallback
        self.default_runtime_event_sink = runtime_event_sink
        self.checkpoint_saver = checkpoint_saver
        self.planning_decision_client = planning_decision_client
        self.assembly_planner = AssetAssemblyPlanner(registry, asset_selection_client)
        self.blueprint_composer = blueprint_composer or BlueprintComposer()
        self.geometry_program_planner = geometry_program_planner
        self.design_domain_router = design_domain_router
        self.cognitive_design_planner = cognitive_design_planner
        self.library_first_generation = library_first_generation
        self.project_specific_roles = project_specific_roles
        self.cognitive_scene_compiler = cognitive_scene_compiler or CognitiveSceneCompiler(
            registry=registry
        )
        self.rule_engine = RuleEngine()
        self.tower_engineer = TowerEngineerAgent()
        self.rf_engineer = RfEngineerAgent()
        self.scene_planner = ScenePlanner()
        self.qa = GenerationQA()
        self.glb_inspector = GLBInspector()
        self.geometry_validator = GLBGeometryValidator()
        self.preview_inspector = PreviewInspector()
        self.graph = self._build_graph()

    def _register_runtime_event_sink(
        self,
        invocation_id: str,
        runtime_event_sink: RuntimeEventSink | None,
    ) -> None:
        sink = runtime_event_sink or self.default_runtime_event_sink
        if sink is None:
            return
        with _RUNTIME_EVENT_SINKS_LOCK:
            _RUNTIME_EVENT_SINKS[invocation_id] = sink

    def _clear_runtime_event_sink(self, invocation_id: str) -> None:
        with _RUNTIME_EVENT_SINKS_LOCK:
            _RUNTIME_EVENT_SINKS.pop(invocation_id, None)

    def _invoke_graph(
        self,
        initial_state: WorkflowState,
        config: dict,
        runtime_event_sink: RuntimeEventSink | None,
    ) -> WorkflowState:
        workflow_id = initial_state["workflow_id"]
        invocation_id = f"{workflow_id}:{uuid.uuid4().hex}"
        initial_state["runtime_event_sink_id"] = invocation_id
        self._register_runtime_event_sink(invocation_id, runtime_event_sink)
        try:
            return self.graph.invoke(initial_state, config=config)
        finally:
            self._clear_runtime_event_sink(invocation_id)

    def run(
        self,
        workflow_id: str,
        requirements_text: str,
        detail_level: str,
        output_dir: Path,
        use_llm: bool | None = None,
        runtime_event_sink: RuntimeEventSink | None = None,
    ) -> OrchestratorResult:
        started = time.perf_counter()
        config = {"configurable": {"thread_id": _initial_checkpoint_thread_id(workflow_id)}}
        initial_state = {
            "workflow_id": workflow_id,
            "entry_mode": (
                "natural_language" if self.design_domain_router is not None else "legacy_telecom"
            ),
            "requirements_text": requirements_text,
            "detail_level": detail_level,
            "use_llm": use_llm,
            "output_dir": output_dir,
            "trace": [],
            "errors": [],
            "rag_context": [],
            "max_repair_attempts": 2,
            "repair_attempts": 0,
            "scene_repair_recorded": False,
            "route_history": [],
        }
        state = self._invoke_graph(initial_state, config, runtime_event_sink)
        state["total_duration_ms"] = _duration_ms(started)
        return _result_from_state(state)

    def run_requirements(
        self,
        workflow_id: str,
        requirements: RequirementSpec,
        detail_level: str,
        output_dir: Path,
        source_label: str = "project_design_spec",
        runtime_event_sink: RuntimeEventSink | None = None,
    ) -> OrchestratorResult:
        started = time.perf_counter()
        initial_state: WorkflowState = {
            "workflow_id": workflow_id,
            "entry_mode": "validated_requirements",
            "requirements_text": _requirements_context_text(requirements, source_label),
            "detail_level": detail_level,
            "use_llm": False,
            "output_dir": output_dir,
            "requirements": requirements,
            "requirements_hash": requirements_hash(requirements),
            "asset_manifest_hash": self.registry.manifest_hash,
            "knowledge_index_hash": knowledge_index_hash(self.rag_service.project_root)
            if self.rag_service is not None
            else "",
            "extraction_provider": source_label,
            "extraction_fallback_used": False,
            "extraction_error": None,
            "trace": [],
            "errors": [],
            "rag_context": [],
            "max_repair_attempts": 2,
            "repair_attempts": 0,
            "scene_repair_recorded": False,
            "route_history": [],
            "quality_gate_reports": [],
            "cache_metrics": self._cache_metrics(),
        }
        state = self._invoke_graph(
            initial_state,
            {"configurable": {"thread_id": _initial_checkpoint_thread_id(workflow_id)}},
            runtime_event_sink,
        )
        state["total_duration_ms"] = _duration_ms(started)
        return _result_from_state(state)

    def run_scene_revision(
        self,
        workflow_id: str,
        scene: SceneSpec,
        output_dir: Path,
        detail_level: str = "high",
        revision_id: str | None = None,
        cognitive_plan: CognitiveDesignPlan | None = None,
        runtime_event_sink: RuntimeEventSink | None = None,
    ) -> OrchestratorResult:
        started = time.perf_counter()
        # Scene revisions preserve the qualified generation strategy stamped on
        # the incoming SceneSpec. Re-resolving here could silently replace an
        # explicit edit decision; asset qualification is enforced when the scene
        # is planned and again before Blender import.
        initial_state: WorkflowState = {
            "workflow_id": workflow_id,
            "entry_mode": "scene_revision",
            "requirements_text": f"validated scene revision {revision_id or 'unknown'}",
            "detail_level": detail_level,
            "use_llm": False,
            "output_dir": output_dir,
            "scene": scene,
            "cognitive_plan": cognitive_plan,
            "revision_id": revision_id,
            "trace": [],
            "errors": [],
            "rag_context": [],
            "max_repair_attempts": 2,
            "repair_attempts": 0,
            "scene_repair_recorded": False,
            "route_history": [],
            "quality_gate_reports": [],
            "asset_manifest_hash": self.registry.manifest_hash,
            "knowledge_index_hash": knowledge_index_hash(self.rag_service.project_root)
            if self.rag_service is not None
            else "",
            "scene_spec_hash": scene_spec_hash(scene),
            "cache_metrics": self._cache_metrics(),
            "extraction_provider": "scene_revision",
            "extraction_fallback_used": False,
            "extraction_error": None,
        }
        state = self._invoke_graph(
            initial_state,
            {
                "configurable": {
                    "thread_id": _revision_checkpoint_thread_id(workflow_id, revision_id)
                }
            },
            runtime_event_sink,
        )
        state["total_duration_ms"] = _duration_ms(started)
        return _result_from_state(state)

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        terminal_node = "memory_writeback" if self.memory_service is not None else END
        graph.add_node("_entry_point", self._entry_point)
        graph.add_node(
            "infer_design_domain",
            self._runtime_node("infer_design_domain", self._infer_design_domain),
        )
        graph.add_node(
            "plan_cognitive_design",
            self._runtime_node("plan_cognitive_design", self._plan_cognitive_design),
        )
        graph.add_node(
            "plan_cognitive_geometry",
            self._runtime_node("plan_cognitive_geometry", self._plan_cognitive_geometry),
        )
        graph.add_node(
            "compile_cognitive_scene",
            self._runtime_node("compile_cognitive_scene", self._compile_cognitive_scene),
        )
        graph.add_node(
            "validate_cognitive_scene",
            self._runtime_node("validate_cognitive_scene", self._validate_cognitive_scene),
        )
        graph.add_node(
            "cognitive_planning_failure_handler",
            self._runtime_node(
                "cognitive_planning_failure_handler",
                self._cognitive_planning_failure_handler,
            ),
        )
        graph.add_node(
            "_prepare_scene_revision",
            self._runtime_node("edit_prepare_revision", self._prepare_scene_revision),
        )
        graph.add_node(
            "extract_requirements",
            self._runtime_node("extract_requirements", self._extract_requirements),
        )
        graph.add_node(
            "missing_data_handler",
            self._runtime_node("missing_data_handler", self._missing_data_handler),
        )
        graph.add_node(
            "retrieve_rag_context",
            self._runtime_node("retrieve_rag_context", self._retrieve_rag_context),
        )
        graph.add_node(
            "decide_planning_context",
            self._runtime_node("decide_planning_context", self._decide_planning_context),
        )
        if self.memory_service is not None:
            graph.add_node(
                "memory_recall", self._runtime_node("memory_recall", self._memory_recall)
            )
            graph.add_node(
                "memory_writeback",
                self._runtime_node("memory_writeback", self._memory_writeback),
            )
        graph.add_node("select_assets", self._runtime_node("select_assets", self._select_assets))
        graph.add_node(
            "validate_requirements",
            self._runtime_node("validate_requirements", self._validate_requirements),
        )
        graph.add_node(
            "rule_violation_handler",
            self._runtime_node("rule_violation_handler", self._rule_violation_handler),
        )
        graph.add_node(
            "compose_design_blueprint",
            self._runtime_node("compose_design_blueprint", self._compose_design_blueprint),
        )
        graph.add_node("plan_scene", self._runtime_node("plan_scene", self._plan_scene))
        if self.geometry_program_planner is not None:
            graph.add_node(
                "plan_generated_geometry",
                self._runtime_node(
                    "plan_generated_geometry",
                    self._plan_generated_geometry,
                ),
            )
            graph.add_node(
                "geometry_program_failure_handler",
                self._runtime_node(
                    "geometry_program_failure_handler",
                    self._geometry_program_failure_handler,
                ),
            )
        graph.add_node("validate_scene", self._runtime_node("validate_scene", self._validate_scene))
        graph.add_node(
            "scene_repair_handler",
            self._runtime_node("scene_repair_handler", self._scene_repair_handler),
        )
        graph.add_node(
            "pre_blender_gate",
            self._runtime_node("pre_blender_gate", self._pre_blender_gate),
        )
        graph.add_node(
            "generate_blender",
            self._runtime_node("generate_blender", self._generate_blender),
        )
        graph.add_node(
            "blender_failure_handler",
            self._runtime_node("blender_failure_handler", self._blender_failure_handler),
        )
        graph.add_node("qa_generation", self._runtime_node("qa_generation", self._qa_generation))
        graph.add_node(
            "post_blender_gate",
            self._runtime_node("post_blender_gate", self._post_blender_gate),
        )
        graph.add_node(
            "certify_completion",
            self._runtime_node("certify_completion", self._certify_completion),
        )
        graph.add_node(
            "qa_failure_handler",
            self._runtime_node("qa_failure_handler", self._qa_failure_handler),
        )
        graph.add_node(
            "quality_gate_failure_handler",
            self._runtime_node("quality_gate_failure_handler", self._quality_gate_failure_handler),
        )
        graph.set_entry_point("_entry_point")
        graph.add_conditional_edges(
            "_entry_point",
            _entry_route,
            {
                "natural_language": "infer_design_domain",
                "legacy_telecom": "extract_requirements",
                "validated_requirements": "retrieve_rag_context",
                "scene_revision": "_prepare_scene_revision",
            },
        )
        graph.add_conditional_edges(
            "infer_design_domain",
            _design_domain_route,
            {
                "telecom_v1": "extract_requirements",
                "generic_cognitive_v1": "plan_cognitive_design",
                "blocked": "cognitive_planning_failure_handler",
            },
        )
        graph.add_conditional_edges(
            "plan_cognitive_design",
            _cognitive_plan_route,
            {
                "continue": "plan_cognitive_geometry",
                "failed": "cognitive_planning_failure_handler",
            },
        )
        graph.add_conditional_edges(
            "plan_cognitive_geometry",
            _cognitive_geometry_route,
            {
                "continue": "compile_cognitive_scene",
                "failed": "cognitive_planning_failure_handler",
            },
        )
        graph.add_conditional_edges(
            "compile_cognitive_scene",
            _cognitive_scene_route,
            {
                "continue": "validate_cognitive_scene",
                "failed": "cognitive_planning_failure_handler",
            },
        )
        graph.add_conditional_edges(
            "validate_cognitive_scene",
            _cognitive_validation_route,
            {
                "continue": "pre_blender_gate",
                "failed": "cognitive_planning_failure_handler",
            },
        )
        graph.add_edge("cognitive_planning_failure_handler", terminal_node)
        graph.add_conditional_edges(
            "extract_requirements",
            _extraction_route,
            {
                "continue": "retrieve_rag_context",
                "missing_data": "missing_data_handler",
                "rule_violation": "rule_violation_handler",
            },
        )
        graph.add_edge("missing_data_handler", terminal_node)
        if self.memory_service is not None:
            graph.add_edge("retrieve_rag_context", "memory_recall")
            graph.add_edge("memory_recall", "decide_planning_context")
        else:
            graph.add_edge("retrieve_rag_context", "decide_planning_context")
        graph.add_edge("decide_planning_context", "select_assets")
        graph.add_conditional_edges(
            "select_assets",
            _asset_route,
            {"continue": "validate_requirements", "blocked": terminal_node},
        )
        graph.add_conditional_edges(
            "validate_requirements",
            _requirements_route,
            {
                "continue": "compose_design_blueprint",
                "rule_violation": "rule_violation_handler",
            },
        )
        graph.add_edge("rule_violation_handler", terminal_node)
        graph.add_conditional_edges(
            "compose_design_blueprint",
            _blueprint_route,
            {
                "plan_scene": "plan_scene",
                "validate_scene": "validate_scene",
            },
        )
        if self.geometry_program_planner is not None:
            graph.add_conditional_edges(
                "plan_scene",
                _geometry_request_route,
                {
                    "generate": "plan_generated_geometry",
                    "continue": "validate_scene",
                },
            )
            graph.add_conditional_edges(
                "plan_generated_geometry",
                _geometry_program_route,
                {
                    "continue": "validate_scene",
                    "failed": "geometry_program_failure_handler",
                },
            )
            graph.add_edge("geometry_program_failure_handler", terminal_node)
        else:
            graph.add_edge("plan_scene", "validate_scene")
        graph.add_conditional_edges(
            "validate_scene",
            _scene_route,
            {
                "continue": "pre_blender_gate",
                "scene_repair": "scene_repair_handler",
            },
        )
        graph.add_conditional_edges(
            "scene_repair_handler",
            _scene_repair_route,
            {"retry": "validate_scene", "blocked": terminal_node},
        )
        graph.add_conditional_edges(
            "pre_blender_gate",
            _pre_blender_gate_route,
            {"continue": "generate_blender", "quality_gate_failed": "quality_gate_failure_handler"},
        )
        graph.add_conditional_edges(
            "generate_blender",
            _generation_route,
            {"continue": "qa_generation", "blender_failure": "blender_failure_handler"},
        )
        graph.add_edge("blender_failure_handler", "qa_generation")
        graph.add_conditional_edges(
            "qa_generation",
            _qa_route,
            {"continue": "post_blender_gate", "qa_failure": "qa_failure_handler"},
        )
        graph.add_conditional_edges(
            "post_blender_gate",
            _post_blender_gate_route,
            {
                "continue": "certify_completion",
                "quality_gate_failed": "quality_gate_failure_handler",
            },
        )
        graph.add_conditional_edges(
            "certify_completion",
            _completion_certificate_route,
            {"issued": terminal_node, "rejected": terminal_node},
        )
        graph.add_edge("qa_failure_handler", terminal_node)
        graph.add_edge("quality_gate_failure_handler", terminal_node)
        if self.memory_service is not None:
            graph.add_edge("memory_writeback", END)
        return graph.compile(checkpointer=self.checkpoint_saver)

    def _cache_metrics(self) -> dict[str, int]:
        rag_stats = self.rag_service.cache_stats() if self.rag_service is not None else {}
        return self.registry.cache_stats() | rag_stats

    def _runtime_node(
        self,
        node: str,
        handler: Callable[[WorkflowState], dict | Command],
    ) -> Callable[[WorkflowState], dict | Command]:
        def _wrapped(state: WorkflowState) -> dict | Command:
            _emit_node_started_runtime_event(state, node)
            try:
                return handler(state)
            except Exception as exc:
                _emit_node_exception_runtime_event(state, node, exc)
                raise

        return _wrapped

    def _assets_for_scene_revision(
        self, scene: SceneSpec
    ) -> tuple[list[AssetManifest], AssetManifest, AssetManifest, AssetManifest | None]:
        tower = self.registry.get(scene.tower.asset_id)
        antennas = []
        radios = []
        accessories = []
        for sector in scene.sectors:
            antennas.append(self.registry.get(sector.antenna_asset_id))
            if sector.radio_asset_id:
                radios.append(self.registry.get(sector.radio_asset_id))
        for accessory in scene.accessory_assets:
            accessories.append(self.registry.get(accessory.asset_id))
        assembly_assets = []
        if scene.assembly_plan is not None:
            assembly_assets = [
                self.registry.get(component.selected_asset_id)
                for component in scene.assembly_plan.components
                if component.selected_asset_id
            ]
        selected_assets = _unique_assets(
            [tower, *antennas, *radios, *accessories, *assembly_assets]
        )
        if not antennas:
            raise ValueError("scene revision requires at least one antenna asset")
        return selected_assets, tower, antennas[0], radios[0] if radios else None

    @staticmethod
    def _apply_update(state: WorkflowState, update: dict) -> None:
        state.update(update)

    def _entry_point(self, state: WorkflowState) -> dict:
        mode = state.get("entry_mode", "natural_language")
        if mode == "validated_requirements":
            return {
                "trace": _trace(
                    state,
                    "use_validated_requirements",
                    state.get("extraction_provider", "project_design_spec"),
                    time.perf_counter(),
                )
            }
        return {}

    def _infer_design_domain(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if self.design_domain_router is None:
            decision = DesignRouteDecision(
                route="telecom_v1",
                inferred_domain="telecom",
                rationale="The optional cognitive runtime is not configured; preserve telecom V1.",
                provider="legacy_route",
                model="none",
            )
        else:
            try:
                decision = self.design_domain_router.route(state["requirements_text"])
            except Exception as exc:
                decision = ConservativeDesignDomainRouter().route(state["requirements_text"])
                decision = decision.model_copy(
                    update={
                        "fallback_reason": (
                            f"LLM domain routing failed ({type(exc).__name__}); "
                            f"{decision.fallback_reason}"
                        )[:600]
                    }
                )
        status = "failed" if decision.route == "blocked" else "passed"
        report = None
        if decision.route == "blocked":
            report = _failed_report(
                design_id=state["workflow_id"],
                code="DESIGN_DOMAIN_ROUTING_BLOCKED",
                message=decision.fallback_reason or decision.rationale,
            )
        return {
            "design_route": decision,
            "extraction_provider": f"{decision.provider}:{decision.model}",
            "extraction_fallback_used": decision.fallback_used,
            "extraction_error": decision.fallback_reason,
            **({"report": report, "requirement_report": report} if report else {}),
            "trace": _trace(
                state,
                "infer_design_domain",
                f"{decision.route}:{decision.inferred_domain}",
                started,
                status=status,
                warnings=["DOMAIN_ROUTING_FALLBACK"] if decision.fallback_used else [],
                errors=["DESIGN_DOMAIN_ROUTING_BLOCKED"] if report else [],
                actor_kind=(
                    "llm_decision" if not decision.fallback_used else "deterministic_specialist"
                ),
                decision_authority="llm_bounded" if not decision.fallback_used else "deterministic",
            ),
        }

    def _plan_cognitive_design(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if self.cognitive_design_planner is None:
            report = _failed_report(
                state["workflow_id"],
                "COGNITIVE_PLANNER_UNAVAILABLE",
                "La planification cognitive générique n'est pas configurée.",
            )
            return {"report": report, "requirement_report": report}
        try:
            plan = self.cognitive_design_planner.plan(
                workflow_id=state["workflow_id"],
                request=state["requirements_text"],
            )
        except Exception as exc:
            report = _failed_report(
                state["workflow_id"],
                "COGNITIVE_PLAN_INVALID",
                f"Le plan 3D générique a été rejeté: {exc}",
            )
            return {
                "report": report,
                "requirement_report": report,
                "trace": _trace(
                    state,
                    "plan_cognitive_design",
                    "rejected",
                    started,
                    status="failed",
                    errors=["COGNITIVE_PLAN_INVALID"],
                    actor_kind="llm_decision",
                    decision_authority="llm_bounded",
                ),
            }
        report = ValidationReport(
            design_id=state["workflow_id"],
            status="passed",
            score=1.0,
            checks={
                "design_intent_valid": True,
                "component_graph_valid": True,
                "asset_decisions_valid": True,
                "specialist_route_valid": True,
                "clarification_not_required": not plan.design_intent.clarification_required,
            },
            warnings=[],
            errors=[],
        )
        if plan.design_intent.clarification_required:
            report = _failed_report(
                state["workflow_id"],
                "COGNITIVE_CLARIFICATION_REQUIRED",
                "Informations manquantes: " + ", ".join(plan.design_intent.missing_information),
            )
        return {
            "cognitive_plan": plan,
            "requirement_report": report,
            "report": report,
            "planning_decision": plan.asset_decision_plan.model_dump(mode="json"),
            "trace": _trace(
                state,
                "plan_cognitive_design",
                (
                    f"domain={plan.design_intent.domain}; "
                    f"components={len(plan.component_graph.components)}; "
                    f"specialists={len(plan.specialist_route.steps)}"
                ),
                started,
                status=report.status,
                errors=[item.code for item in report.errors],
                actor_kind="llm_decision",
                decision_authority="llm_bounded",
            ),
        }

    def _plan_cognitive_geometry(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        needs_geometry = any(
            decision.strategy in {"procedural_generate", "compose_and_generate"}
            for decision in state["cognitive_plan"].asset_decision_plan.decisions
        )
        if self.geometry_program_planner is None and needs_geometry:
            report = _failed_report(
                state["workflow_id"],
                "GEOMETRY_PROGRAM_PLANNER_UNAVAILABLE",
                "Le spécialiste de géométrie déclarative GPT-OSS n'est pas configuré.",
            )
            return {"report": report, "geometry_program_error": report.errors[0].message}
        plan = state["cognitive_plan"]
        components = {item.component_id: item for item in plan.component_graph.components}
        programs: list[GeometryProgram] = []
        try:
            for decision in plan.asset_decision_plan.decisions:
                if decision.strategy not in {"procedural_generate", "compose_and_generate"}:
                    continue
                component = components[decision.component_id]
                description = (
                    f"Create {component.quantity} component(s) for role "
                    f"{component.semantic_role}: {component.description}"
                )
                programs.append(
                    self.geometry_program_planner.plan(
                        prompt=description,
                        semantic_role=component.semantic_role,
                        request_id=component.component_id,
                        quantity=component.quantity,
                        source_description=description,
                        placement_context=_component_placement_context(
                            plan, component.component_id
                        ),
                        maximum_dimensions_m=component.target_dimensions_m,
                        design_context={
                            "design_intent": plan.design_intent.model_dump(mode="json"),
                            "component": component.model_dump(mode="json"),
                            "relationships": [
                                item.model_dump(mode="json")
                                for item in plan.component_graph.relationships
                                if component.component_id
                                in {item.source_component_id, item.target_component_id}
                            ],
                            "asset_decision": decision.model_dump(mode="json"),
                        },
                        schema_version="2.0.0",
                    )
                )
        except Exception as exc:
            report = _failed_report(
                state["workflow_id"],
                "COGNITIVE_GEOMETRY_INVALID",
                f"La géométrie déclarative a été rejetée: {exc}",
            )
            return {
                "report": report,
                "geometry_program_error": str(exc),
                "trace": _trace(
                    state,
                    "plan_cognitive_geometry",
                    "rejected",
                    started,
                    status="failed",
                    errors=["COGNITIVE_GEOMETRY_INVALID"],
                    actor_kind="llm_decision",
                    decision_authority="llm_bounded",
                ),
            }
        return {
            "geometry_programs": programs,
            "trace": _trace(
                state,
                "plan_cognitive_geometry",
                f"programs={len(programs)};nodes={sum(len(item.nodes) for item in programs)}",
                started,
                actor_kind="llm_decision" if programs else "deterministic_specialist",
                decision_authority="llm_bounded" if programs else "deterministic",
            ),
        }

    def _compile_cognitive_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        try:
            compilation = self.cognitive_scene_compiler.compile_with_observations(
                workflow_id=state["workflow_id"],
                plan=state["cognitive_plan"],
                geometry_programs=state.get("geometry_programs", []),
                detail_level=state["detail_level"],
            )
        except Exception as exc:
            report = _failed_report(
                state["workflow_id"],
                "COGNITIVE_SCENE_COMPILATION_FAILED",
                f"La compilation SceneSpec V2 a été rejetée: {exc}",
            )
            return {
                "report": report,
                "trace": _trace(
                    state,
                    "compile_cognitive_scene",
                    "rejected",
                    started,
                    status="failed",
                    errors=["COGNITIVE_SCENE_COMPILATION_FAILED"],
                ),
            }
        scene = compilation.scene
        return {
            "scene": scene,
            "scene_spec_hash": scene_spec_hash(scene),
            "capability_observations": list(compilation.capability_observations),
            "selected_assets": self._cognitive_assets_for_scene(scene),
            "trace": _trace(
                state,
                "compile_cognitive_scene",
                f"capability_observations={len(compilation.capability_observations)}",
                started,
                actor_kind="deterministic_specialist",
                decision_authority="deterministic",
            ),
        }

    def _cognitive_assets_for_scene(self, scene: SceneSpec) -> list[AssetManifest]:
        return [
            self.registry.get(asset_id)
            for asset_id in sorted(
                {
                    node.asset_id
                    for program in scene.geometry_programs
                    for node in program.nodes
                    if node.kind == "exact_asset"
                }
            )
        ]

    def _validate_cognitive_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        scene_report = validate_scene_spec(state["scene"], [])
        plan = state["cognitive_plan"]
        scene = state["scene"]
        checks = [
            RequirementCoverageCheck(
                path="design_intent_id",
                expected=plan.design_intent.intent_id,
                actual=scene.design_intent_id,
                passed=scene.design_intent_id == plan.design_intent.intent_id,
            ),
            RequirementCoverageCheck(
                path="component_graph_id",
                expected=plan.component_graph.graph_id,
                actual=scene.component_graph_id,
                passed=scene.component_graph_id == plan.component_graph.graph_id,
            ),
            RequirementCoverageCheck(
                path="cognitive_plan_sha256",
                expected=cognitive_plan_hash(plan),
                actual=scene.cognitive_plan_sha256,
                passed=scene.cognitive_plan_sha256 == cognitive_plan_hash(plan),
            ),
        ]
        coverage = RequirementCoverageReport(
            workflow_id=state["workflow_id"],
            passed=all(item.passed for item in checks),
            coverage_ratio=sum(item.passed for item in checks) / len(checks),
            checks=checks,
            critical_errors=[item.path for item in checks if not item.passed],
        )
        report = _merge_reports(
            state["workflow_id"],
            [state["requirement_report"], scene_report],
        )
        if not coverage.passed:
            report = _merge_reports(
                state["workflow_id"],
                [
                    report,
                    _failed_report(
                        state["workflow_id"],
                        "COGNITIVE_PLAN_NOT_COMPILED",
                        "SceneSpec V2 ne préserve pas tous les liens du plan cognitif.",
                    ),
                ],
            )
        return {
            "scene_report": scene_report,
            "requirement_coverage": coverage,
            "report": report,
            "trace": _trace(
                state,
                "validate_cognitive_scene",
                report.status,
                started,
                status=report.status,
                errors=[item.code for item in report.errors],
            ),
        }

    def _cognitive_planning_failure_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = state.get("report") or _failed_report(
            state["workflow_id"],
            "COGNITIVE_WORKFLOW_BLOCKED",
            "Le workflow cognitif a été bloqué avant Blender.",
        )
        return {
            "report": report,
            "trace": _trace(
                state,
                "cognitive_planning_failure_handler",
                "blocked",
                started,
                status="failed",
                errors=[item.code for item in report.errors],
            ),
        }

    def _prepare_scene_revision(self, state: WorkflowState) -> Command:
        started = time.perf_counter()
        scene = state["scene"]
        if scene.schema_version == "2.0.0":
            plan = state.get("cognitive_plan")
            if plan is None:
                report = _failed_report(
                    design_id=state["workflow_id"],
                    code="COGNITIVE_REVISION_PLAN_MISSING",
                    message=(
                        "La révision générique exige le plan cognitif certifié de la version "
                        "active."
                    ),
                )
                return Command(
                    goto=END,
                    update={
                        "report": report,
                        "requirement_report": report,
                        "trace": _trace(
                            state,
                            "edit_prepare_revision",
                            "cognitive_plan_missing",
                            started,
                            status="failed",
                            errors=["COGNITIVE_REVISION_PLAN_MISSING"],
                        ),
                    },
                )
            try:
                compilation = self.cognitive_scene_compiler.compile_with_observations(
                    workflow_id=state["workflow_id"],
                    plan=plan,
                    geometry_programs=scene.geometry_programs,
                    detail_level=scene.detail_level,
                )
                if compilation.scene.cognitive_plan_sha256 != scene.cognitive_plan_sha256:
                    raise ValueError("COGNITIVE_REVISION_PLAN_HASH_MISMATCH")
            except (KeyError, LookupError, ValueError) as exc:
                report = _failed_report(
                    design_id=state["workflow_id"],
                    code="COGNITIVE_REVISION_INVALID",
                    message=str(exc),
                )
                return Command(
                    goto=END,
                    update={
                        "report": report,
                        "requirement_report": report,
                        "trace": _trace(
                            state,
                            "edit_prepare_revision",
                            "cognitive_revision_rejected",
                            started,
                            status="failed",
                            errors=["COGNITIVE_REVISION_INVALID"],
                        ),
                    },
                )
            report = ValidationReport(
                design_id=state["workflow_id"],
                status="passed",
                score=1.0,
                checks={
                    "cognitive_plan_present": True,
                    "cognitive_plan_hash_preserved": True,
                    "geometry_programs_revalidated": True,
                },
                warnings=[],
                errors=[],
            )
            return Command(
                goto="validate_cognitive_scene",
                update={
                    "scene": scene,
                    "scene_spec_hash": scene_spec_hash(scene),
                    "requirement_report": report,
                    "report": report,
                    "planning_decision": plan.asset_decision_plan.model_dump(mode="json"),
                    "capability_observations": list(compilation.capability_observations),
                    "selected_assets": self._cognitive_assets_for_scene(scene),
                    "trace": _trace(
                        state,
                        "edit_prepare_revision",
                        "cognitive_revision_validated",
                        started,
                        actor_kind="deterministic_specialist",
                        decision_authority="deterministic",
                    ),
                },
            )
        try:
            scene = _scene_with_revision_dependencies(scene, self.registry)
            selected_assets, tower, antenna, radio = self._assets_for_scene_revision(scene)
            scene = _scene_with_asset_metadata(scene, selected_assets)
            scene = scene.model_copy(deep=True)
            resolved_assembly = resolve_scene_assembly(scene)
            if resolved_assembly is not None:
                scene = scene.model_copy(update={"assembly_plan": resolved_assembly})
            requirements = _requirements_from_scene(
                scene, tower, antenna, radio, state["detail_level"]
            )
        except (KeyError, LookupError, ValueError) as exc:
            report = _failed_report(
                design_id=state["workflow_id"],
                code="SCENE_REVISION_ASSET_ERROR",
                message=str(exc),
            )
            return Command(
                goto=END,
                update={
                    "report": report,
                    "trace": _trace(
                        state,
                        "edit_prepare_revision",
                        "asset_lookup_failed",
                        started,
                        status="failed",
                        errors=["SCENE_REVISION_ASSET_ERROR"],
                    ),
                },
            )
        accessory_assets = [
            asset for asset in selected_assets if asset.asset_id in _scene_accessory_ids(scene)
        ]
        return Command(
            goto="validate_requirements",
            update={
                "scene": scene,
                "scene_spec_hash": scene_spec_hash(scene),
                "requirements": requirements,
                "requirements_hash": requirements_hash(requirements),
                "tower": tower,
                "antenna": antenna,
                "radio": radio,
                "accessory_assets": accessory_assets,
                "selected_assets": selected_assets,
                "assembly_plan": scene.assembly_plan,
                "trace": [
                    *_trace(
                        state,
                        "edit_prepare_revision",
                        state.get("revision_id") or "scene_revision",
                        started,
                    )
                ],
            },
        )

    def _extract_requirements(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        try:
            extraction = self.extractor.extract(
                state["requirements_text"],
                state["detail_level"],
                enabled=state.get("use_llm"),
            )
        except ValidationError as exc:
            message = "; ".join(
                f"{error['loc'][0] if error.get('loc') else 'input'}: "
                f"{error.get('msg', 'invalid value')}"
                for error in exc.errors()
            )
            report = _failed_report(
                design_id=state["workflow_id"],
                code="INVALID_REQUIREMENTS",
                message=f"Extracted requirements are invalid: {message}",
            )
            return {
                "requirement_report": report,
                "report": report,
                "extraction_error": message,
                "trace": _trace(
                    state,
                    "extract_requirements",
                    "validation_error",
                    started,
                    status="failed",
                    errors=["INVALID_REQUIREMENTS"],
                    actor_kind="deterministic_specialist",
                    decision_authority="deterministic",
                ),
            }
        except Exception as exc:
            report = _failed_report(
                design_id=state["workflow_id"],
                code="EXTRACTION_FAILED",
                message=f"Requirement extraction failed: {exc}",
            )
            return {
                "requirement_report": report,
                "report": report,
                "extraction_error": str(exc),
                "trace": _trace(
                    state,
                    "extract_requirements",
                    "extraction_error",
                    started,
                    status="failed",
                    errors=["EXTRACTION_FAILED"],
                    actor_kind="deterministic_specialist",
                    decision_authority="deterministic",
                ),
            }
        requirements = extraction.requirements
        if requirements.requires_confirmation:
            fields = ", ".join(requirements.confirmation_fields) or "champs contradictoires"
            report = _failed_report(
                design_id=state["workflow_id"],
                code="INPUT_CONFIRMATION_REQUIRED",
                message=(
                    f"La génération est bloquée tant que l'utilisateur n'a pas confirmé: {fields}."
                ),
            )
            return {
                "requirements": requirements,
                "requirements_hash": requirements_hash(requirements),
                "asset_manifest_hash": self.registry.manifest_hash,
                "knowledge_index_hash": (
                    knowledge_index_hash(self.rag_service.project_root)
                    if self.rag_service is not None
                    else ""
                ),
                "extraction_provider": extraction.provider,
                "extraction_fallback_used": extraction.fallback_used,
                "extraction_error": extraction.error,
                "requirement_report": report,
                "report": report,
                "trace": _trace(
                    state,
                    "extract_requirements",
                    "confirmation_required",
                    started,
                    status="failed",
                    errors=["INPUT_CONFIRMATION_REQUIRED"],
                    actor_kind=(
                        "llm_decision"
                        if extraction.provider.startswith("groq") and not extraction.fallback_used
                        else "deterministic_specialist"
                    ),
                    decision_authority=(
                        "llm_bounded"
                        if extraction.provider.startswith("groq") and not extraction.fallback_used
                        else "deterministic"
                    ),
                ),
            }
        return {
            "requirements": requirements,
            "requirements_hash": requirements_hash(requirements),
            "asset_manifest_hash": self.registry.manifest_hash,
            "knowledge_index_hash": knowledge_index_hash(self.rag_service.project_root)
            if self.rag_service is not None
            else "",
            "extraction_provider": extraction.provider,
            "extraction_fallback_used": extraction.fallback_used,
            "extraction_error": extraction.error,
            "trace": _trace(
                state,
                "extract_requirements",
                extraction.provider,
                started,
                actor_kind=(
                    "llm_decision"
                    if extraction.provider.startswith("groq") and not extraction.fallback_used
                    else "deterministic_specialist"
                ),
                decision_authority=(
                    "llm_bounded"
                    if extraction.provider.startswith("groq") and not extraction.fallback_used
                    else "deterministic"
                ),
            ),
        }

    def _missing_data_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = _failed_report(
            design_id=state["workflow_id"],
            code="MISSING_REQUIREMENTS",
            message="No valid requirements were available after extraction.",
        )
        route = _route_event(state, "missing_data_handler", "missing_data")
        return {
            "report": report,
            "route_history": route,
            "trace": _trace(
                state,
                "missing_data_handler",
                "missing_data",
                started,
                status="failed",
                errors=["MISSING_REQUIREMENTS"],
                route="missing_data",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _retrieve_rag_context(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if self.rag_service is None:
            return {
                "trace": _trace(state, "retrieve_rag_context", "skipped", started, status="skipped")
            }
        try:
            query = _rag_query_text(state)
            results = self.rag_service.search(query, limit=5)
            context = [result.model_dump() for result in results]
            hint_count = _rag_hint_context_count(context)
            return {
                "rag_context": context,
                "cache_metrics": self._cache_metrics(),
                "trace": _trace(
                    state,
                    "retrieve_rag_context",
                    f"{len(context)} results, {hint_count} hint contexts",
                    started,
                ),
            }
        except Exception as exc:
            return {
                "rag_context": [],
                "cache_metrics": self._cache_metrics(),
                "trace": _trace(
                    state,
                    "retrieve_rag_context",
                    f"failed: {type(exc).__name__}",
                    started,
                    status="failed",
                    errors=[str(exc)],
                ),
            }

    def _memory_recall(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if self.memory_service is None:
            return {"trace": _trace(state, "memory_recall", "skipped", started, status="skipped")}
        try:
            recall = self.memory_service.recall(state["requirements"])
        except Exception as exc:
            return {
                "memory_recall": MemoryRecallResult().model_dump(),
                "trace": _trace(
                    state,
                    "memory_recall",
                    f"failed:{type(exc).__name__}",
                    started,
                    status="failed",
                    errors=[str(exc)],
                ),
            }
        return {
            "memory_recall": recall.model_dump(),
            "trace": _trace(state, "memory_recall", f"{recall.memory_hits} hits", started),
        }

    def _decide_planning_context(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        requirements = state["requirements"]
        contexts = state.get("rag_context", [])
        evidence = collect_planning_evidence(requirements, contexts)
        eligible_candidates = [
            candidate
            for candidate in evidence.candidates
            if candidate.field in evidence.inferred_fields
            and candidate.value != evidence.current_values[candidate.field]
        ]

        if self.planning_decision_client is None or not eligible_candidates:
            resolution = resolve_planning_hints(requirements, contexts)
            status = "not_needed" if not eligible_candidates else "deterministic_policy"
            reason = (
                "no_eligible_inferred_candidates"
                if not eligible_candidates
                else "planning_model_not_configured"
            )
            decision = {
                "authority": "validated_candidates_only",
                "status": status,
                "reason": reason,
                "provider": None,
                "model_name": None,
                "fallback_used": False,
                "candidate_count": len(evidence.candidates),
                "eligible_candidate_count": len(eligible_candidates),
                "protected_fields": sorted(
                    set(evidence.current_values) - set(evidence.inferred_fields)
                ),
                "memory_risk_count": 0,
                "selections": [],
            }
            return {
                "rag_planning_resolution": _planning_resolution_payload(resolution),
                "planning_decision": decision,
                "trace": _trace(
                    state,
                    "decide_planning_context",
                    reason,
                    started,
                    status="skipped" if status == "not_needed" else "passed",
                    actor_kind="deterministic_specialist",
                    decision_authority="deterministic",
                ),
            }

        request = _planning_decision_request(evidence, state.get("memory_recall"))
        result = self.planning_decision_client.decide(request)
        resolution = apply_bounded_planning_decision(requirements, contexts, result)
        decision = {
            "authority": "validated_candidates_only",
            "status": result.diagnostics.status,
            "reason": result.diagnostics.fallback_reason,
            "provider": result.diagnostics.provider,
            "model_name": result.diagnostics.model_name,
            "fallback_used": result.diagnostics.fallback_used,
            "latency_ms": result.diagnostics.latency_ms,
            "candidate_count": len(request.candidates),
            "eligible_candidate_count": len(eligible_candidates),
            "protected_fields": request.protected_fields,
            "memory_risk_count": len(request.memory_risks),
            "selections": [selection.model_dump() for selection in result.selections],
        }
        return {
            "rag_planning_resolution": _planning_resolution_payload(resolution),
            "planning_decision": decision,
            "trace": _trace(
                state,
                "decide_planning_context",
                (
                    "provider_fallback_keep_validated_values"
                    if result.diagnostics.fallback_used
                    else f"{len(resolution.applied_fields)} fields applied"
                ),
                started,
                warnings=["PLANNING_DECISION_FALLBACK"] if result.diagnostics.fallback_used else [],
                actor_kind="llm_decision",
                decision_authority=(
                    "deterministic" if result.diagnostics.fallback_used else "llm_bounded"
                ),
            ),
        }

    def _select_assets(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        requirements = state["requirements"]
        try:
            assembly = self.assembly_planner.plan(
                workflow_id=state["workflow_id"], requirements=requirements
            )
            assets = assembly.assets_by_role
            tower = assets["support_structure"]
            antenna = assets["sector_antenna"]
            radio = assets.get("remote_radio")
            accessory_assets = [
                asset
                for role, asset in assets.items()
                if role in {"ground_equipment", "timing_antenna"}
            ]
        except LookupError as exc:
            report = _failed_report(
                design_id=state["workflow_id"],
                code="ASSET_SELECTION_FAILED",
                message=str(exc),
            )
            return {
                "asset_error": str(exc),
                "selected_assets": [],
                "requirement_report": report,
                "report": report,
                "trace": _trace(
                    state,
                    "select_assets",
                    "asset_selection_failed",
                    started,
                    status="failed",
                    errors=["ASSET_SELECTION_FAILED"],
                ),
            }
        selected_assets = _unique_assets(list(assembly.assets_by_role.values()))
        return {
            "tower": tower,
            "antenna": antenna,
            "radio": radio,
            "accessory_assets": accessory_assets,
            "selected_assets": selected_assets,
            "assembly_plan": assembly.plan,
            "cache_metrics": self._cache_metrics(),
            "trace": _trace(
                state,
                "select_assets",
                (
                    f"{','.join(a.asset_id for a in selected_assets)}; "
                    f"authority={assembly.plan.selection_authority}"
                ),
                started,
                actor_kind="llm_decision"
                if assembly.plan.selection_authority == "llm_bounded"
                else "deterministic_specialist",
                decision_authority="llm_bounded"
                if assembly.plan.selection_authority == "llm_bounded"
                else "deterministic",
                warnings=["ASSET_SELECTION_LLM_FALLBACK"]
                if assembly.plan.llm_fallback_used
                else [],
            ),
        }

    def _validate_requirements(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = self.rule_engine.validate_requirements(
            state["requirements"], state["selected_assets"]
        )
        # Multi-agent domain validation in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            tower_future = executor.submit(
                self.tower_engineer.validate, state["requirements"], state["tower"]
            )
            rf_future = executor.submit(self.rf_engineer.validate, state["requirements"])
            tower_report = tower_future.result()
            rf_report = rf_future.result()
        requirements, applied_assumptions = apply_tower_engineer_recommendations(
            state["requirements"],
            tower_report,
            requirements_text=state.get("requirements_text") or "",
        )
        if applied_assumptions:
            tower_report = tower_report.model_copy(
                update={
                    "warnings": [
                        issue
                        for issue in tower_report.warnings
                        if issue.code != "TOWER_PLATFORM_RECOMMENDED"
                    ]
                    + [
                        ValidationIssue(
                            code="TOWER_ACCESS_APPLIED_BY_TOWER_ENGINEER",
                            message=" ".join(applied_assumptions),
                            severity="info",
                        )
                    ]
                }
            )
        merged_warnings = [
            *report.warnings,
            *tower_report.warnings,
            *rf_report.warnings,
        ]
        merged_errors = [
            *report.errors,
            *tower_report.errors,
            *rf_report.errors,
        ]
        status = "failed" if merged_errors else "passed"
        report = report.model_copy(
            update={
                "status": status,
                "warnings": merged_warnings,
                "errors": merged_errors,
            }
        )
        trace_status = status
        return {
            "requirement_report": report,
            "report": report,
            "tower_validation": tower_report,
            "rf_validation": rf_report,
            **({"requirements": requirements} if applied_assumptions else {}),
            "trace": _trace(
                state,
                "validate_requirements",
                report.status,
                started,
                status=trace_status,
                warnings=[warning.code for warning in report.warnings],
                errors=[error.code for error in report.errors],
            ),
        }

    def _rule_violation_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = state["requirement_report"]
        route = _route_event(state, "rule_violation_handler", "rule_violation")
        return {
            "report": report,
            "route_history": route,
            "trace": _trace(
                state,
                "rule_violation_handler",
                "blocked:requirements_failed",
                started,
                status="failed",
                errors=[error.code for error in report.errors],
                route="rule_violation",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _compose_design_blueprint(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        blueprint = self.blueprint_composer.compose(
            workflow_id=state["workflow_id"],
            requirements=state["requirements"],
            selected_assets=state["selected_assets"],
            tower_validation=state["tower_validation"],
            rf_validation=state["rf_validation"],
            planning_resolution=state.get("rag_planning_resolution"),
            assembly_plan=state.get("assembly_plan"),
        )
        coverage = evaluate_blueprint_requirement_coverage(
            state["requirements"],
            blueprint,
            state.get("rag_planning_resolution"),
        )
        if not coverage.passed:
            raise ValueError(
                "DesignBlueprint does not cover requirements: "
                + ", ".join(coverage.critical_errors)
            )
        domains = ",".join(blueprint.required_specialist_domains)
        return {
            "design_blueprint": blueprint,
            "blueprint_requirement_coverage": coverage,
            "trace": _trace(
                state,
                "compose_design_blueprint",
                f"{len(blueprint.component_intents)} intents; specialists={domains}",
                started,
                actor_kind="deterministic_specialist",
                decision_authority="deterministic",
                warnings=[issue.code for issue in blueprint.open_issues],
            ),
        }

    def _plan_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        scene = self.scene_planner.build_scene_spec(
            workflow_id=state["workflow_id"],
            requirements=state["requirements"],
            tower=state["tower"],
            antenna=state["antenna"],
            radio=state["radio"],
            accessory_assets=state.get("accessory_assets", []),
            rag_context=state.get("rag_context"),
            memory_recall=state.get("memory_recall"),
            planning_resolution=state.get("rag_planning_resolution"),
            assembly_plan=state.get("assembly_plan"),
        )
        return {
            "scene": scene,
            "scene_spec_hash": scene_spec_hash(scene),
            "trace": _trace(state, "plan_scene", scene.scene_id, started),
        }

    def _plan_generated_geometry(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        planner = self.geometry_program_planner
        requests = state["requirements"].geometry_requests
        if planner is None or not requests:
            return {
                "trace": _trace(
                    state,
                    "plan_generated_geometry",
                    "skipped:no_geometry_request",
                    started,
                    status="skipped",
                    actor_kind="llm_decision",
                    decision_authority="llm_bounded",
                )
            }

        programs: list[GeometryProgram] = []
        try:
            for request in requests:
                maximum_dimensions = (
                    request.maximum_dimensions_m.model_dump(mode="json")
                    if request.maximum_dimensions_m
                    else None
                )
                program = planner.plan(
                    prompt=request.description,
                    semantic_role=request.semantic_role,
                    request_id=request.request_id,
                    quantity=request.quantity,
                    source_description=request.description,
                    source_description_origin="user_requirement",
                    placement_context=request.placement_context,
                    maximum_dimensions_m=request.maximum_dimensions_m,
                    design_context={
                        "network_type": state["requirements"].network_type,
                        "tower_type": state["requirements"].tower_type,
                        "tower_height_m": state["requirements"].tower_height_m,
                        "site_coordinate_frame": "meters, Z-up, tower center at origin",
                        "placement_context": request.placement_context,
                        "maximum_dimensions_m": maximum_dimensions,
                        "selected_asset_ids": [
                            asset.asset_id for asset in state.get("selected_assets", [])
                        ],
                        "assembly_roles": [
                            component.role_id
                            for component in (
                                state["assembly_plan"].components
                                if state.get("assembly_plan")
                                else []
                            )
                        ],
                    },
                )
                programs.append(program)
                if sum(len(item.nodes) for item in programs) > 1024:
                    raise ValueError("aggregate geometry-program node budget exceeds 1024 nodes")
        except Exception as exc:
            logger.exception("Typed geometry-program planning failed")
            message = (
                "La géométrie demandée hors catalogue n'a pas pu être produite par "
                "le spécialiste LLM sous contrat; Blender n'a pas été lancé."
            )
            report = _failed_report(
                design_id=state["workflow_id"],
                code="GEOMETRY_PROGRAM_GENERATION_FAILED",
                message=message,
            )
            return {
                "geometry_program_error": f"{type(exc).__name__}: {exc}",
                "report": report,
                "trace": _trace(
                    state,
                    "plan_generated_geometry",
                    "failed:typed_geometry_program",
                    started,
                    status="failed",
                    errors=["GEOMETRY_PROGRAM_GENERATION_FAILED"],
                    actor_kind="llm_decision",
                    decision_authority="llm_bounded",
                ),
            }

        scene = state["scene"].model_copy(update={"geometry_programs": programs})
        modes = sorted({program.structured_output_mode for program in programs})
        return {
            "geometry_programs": programs,
            "scene": scene,
            "scene_spec_hash": scene_spec_hash(scene),
            "trace": _trace(
                state,
                "plan_generated_geometry",
                (
                    f"{len(programs)} programme(s), "
                    f"{sum(len(program.nodes) for program in programs)} nœud(s); "
                    f"modes={','.join(modes)}"
                ),
                started,
                warnings=[
                    "GEOMETRY_PROGRAM_LLM_REPAIRED"
                    for program in programs
                    if program.structured_output_mode == "json_object_repaired"
                ],
                actor_kind="llm_decision",
                decision_authority="llm_bounded",
            ),
        }

    def _geometry_program_failure_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        route = _route_event(
            state,
            "geometry_program_failure_handler",
            "geometry_program_failed",
        )
        return {
            "route_history": route,
            "report": state["report"],
            "trace": _trace(
                state,
                "geometry_program_failure_handler",
                "blocked:geometry_program_failed",
                started,
                status="failed",
                errors=["GEOMETRY_PROGRAM_GENERATION_FAILED"],
                route="geometry_program_failed",
            ),
        }

    def _validate_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = validate_scene_spec(state["scene"], self.registry.list_assets())
        blueprint_coverage = evaluate_blueprint_scene_coverage(
            state["design_blueprint"],
            state["scene"],
        )
        requirement_coverage = evaluate_requirement_coverage(
            state["requirements"],
            state["scene"],
            state.get("rag_planning_resolution"),
        )
        if not requirement_coverage.passed or not blueprint_coverage.passed:
            coverage_errors = [
                ValidationIssue(
                    code="REQUIREMENT_NOT_COVERED",
                    message=f"SceneSpec does not preserve requirement: {path}",
                    severity="error",
                )
                for path in requirement_coverage.critical_errors
            ]
            coverage_errors.extend(
                ValidationIssue(
                    code="BLUEPRINT_NOT_COMPILED",
                    message=f"SceneSpec does not compile blueprint intent: {path}",
                    severity="error",
                )
                for path in blueprint_coverage.critical_errors
            )
            report = report.model_copy(
                update={
                    "status": "failed",
                    "checks": {
                        **report.checks,
                        "requirement_coverage_valid": False,
                        "blueprint_scene_coverage_valid": blueprint_coverage.passed,
                    },
                    "errors": [*report.errors, *coverage_errors],
                }
            )
        else:
            report = report.model_copy(
                update={
                    "checks": {
                        **report.checks,
                        "requirement_coverage_valid": True,
                        "blueprint_scene_coverage_valid": True,
                    }
                }
            )
        merged = _merge_reports(state["scene"].scene_id, [state["requirement_report"], report])
        return {
            "scene_report": report,
            "requirement_coverage": requirement_coverage,
            "blueprint_scene_coverage": blueprint_coverage,
            "report": merged,
            "trace": _trace(
                state,
                "validate_scene",
                report.status,
                started,
                status=report.status,
                warnings=[warning.code for warning in report.warnings],
                errors=[error.code for error in report.errors],
            ),
        }

    def _pre_blender_gate(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if state.get("cognitive_plan") is not None:
            observations = state.get("capability_observations", [])
            checks = {
                "cognitive_plan_valid": state["requirement_report"].status == "passed",
                "scene_spec_v2_valid": state["scene_report"].status == "passed",
                "cognitive_coverage_passed": state["requirement_coverage"].passed,
                "capabilities_executed": bool(observations),
                "capabilities_completed": bool(observations)
                and all(item.status == "completed" for item in observations),
                "geometry_programs_present": bool(state["scene"].geometry_programs),
            }
            gate = QualityGateReport(
                stage="pre_blender",
                passed=all(checks.values()),
                checks=checks,
                details={
                    "design_domain": state["scene"].design_domain,
                    "capability_observation_count": len(observations),
                },
                critical_errors=[name for name, passed in checks.items() if not passed],
                duration_ms=_duration_ms(started),
            )
        else:
            gate = evaluate_pre_blender_gate(
                requirements=state.get("requirements"),
                requirement_report=state.get("requirement_report"),
                scene=state.get("scene"),
                scene_report=state.get("scene_report"),
                selected_assets=state.get("selected_assets", []),
                all_assets=self.registry.list_assets(),
                repair_attempts=state.get("repair_attempts", 0),
                max_repair_attempts=state.get("max_repair_attempts", 2),
                requirement_coverage=state.get("requirement_coverage"),
            )
        if self.library_first_generation:
            violations = library_first_scene_violations(
                state["scene"], registry=self.registry, generated_roles=self.project_specific_roles
            )
            if violations:
                gate = gate.model_copy(
                    update={
                        "passed": False,
                        "checks": {**gate.checks, "library_first_assets": False},
                        "details": {
                            **gate.details,
                            "library_first_violations": violations,
                        },
                        "critical_errors": [
                            *gate.critical_errors,
                            "LIBRARY_SOURCE_REQUIRED",
                        ],
                    }
                )
            else:
                gate = gate.model_copy(
                    update={"checks": {**gate.checks, "library_first_assets": True}}
                )
        report = (
            state["report"]
            if gate.passed
            else _merge_quality_gate_report(
                state["workflow_id"],
                state["report"],
                gate,
            )
        )
        return {
            "pre_blender_gate": gate,
            "quality_gate_reports": [*state.get("quality_gate_reports", []), gate.model_dump()],
            "report": report,
            "trace": _trace(
                state,
                "pre_blender_gate",
                "passed" if gate.passed else "failed",
                started,
                status="passed" if gate.passed else "failed",
                warnings=gate.warnings,
                errors=gate.critical_errors,
                route=None if gate.passed else "quality_gate_failed",
            ),
        }

    def _scene_repair_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        attempt = state.get("repair_attempts", 0) + 1
        report = state["scene_report"]

        # First, try deterministic SceneSpec repairs (height, azimuth normalization).
        scene = state["scene"]
        repaired_scene, repair_report = repair_scene_spec(scene, attempt=attempt)
        if repair_report.events:
            repair_events = [event.model_dump() for event in repair_report.events]
            route = _route_event(
                state,
                "scene_repair_handler",
                "scene_repair",
                attempt=attempt,
                events=repair_events,
            )
            return {
                "scene": repaired_scene,
                "scene_spec_hash": scene_spec_hash(repaired_scene),
                "repair_attempts": attempt,
                "report": report,
                "route_history": route,
                "trace": _trace(
                    state,
                    "scene_repair_handler",
                    f"repaired:{len(repair_report.events)} events",
                    started,
                    warnings=[event.warning_code for event in repair_report.events],
                    route="scene_repair",
                    attempt=attempt,
                ),
            }

        # If the scene passed validation but requirement-level repairs were applied,
        # record them once so the trace is honest.
        requirement_repair_events = [
            event.model_dump() for event in state["requirements"].repair_events if event.success
        ]
        if (
            requirement_repair_events
            and report.status == "passed"
            and not state.get("scene_repair_recorded")
        ):
            route = _route_event(
                state,
                "scene_repair_handler",
                "scene_repair",
                attempt=attempt,
                events=requirement_repair_events,
            )
            return {
                "repair_attempts": attempt,
                "scene_repair_recorded": True,
                "report": report,
                "route_history": route,
                "trace": _trace(
                    state,
                    "scene_repair_handler",
                    f"recorded:{len(requirement_repair_events)} events",
                    started,
                    warnings=[event["warning_code"] for event in requirement_repair_events],
                    route="scene_repair",
                    attempt=attempt,
                ),
            }

        route = _route_event(state, "scene_repair_handler", "scene_repair", attempt=attempt)
        return {
            "repair_attempts": attempt,
            "report": report,
            "route_history": route,
            "trace": _trace(
                state,
                "scene_repair_handler",
                "blocked:non_repairable_scene",
                started,
                status="failed",
                errors=[error.code for error in report.errors],
                route="scene_repair",
                attempt=attempt,
            ),
        }

    def _generate_blender(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        generation = self.blender_runner.generate(state["scene"], state["output_dir"])
        real_generation = generation.status == "generated" and generation.mode == "real_blender"
        status = "passed" if real_generation else "failed"
        return {
            "generation": generation,
            "trace": _trace(
                state,
                "generate_blender",
                generation.mode,
                started,
                status=status,
                errors=[generation.error] if generation.error else [],
                actor_kind="external_tool",
                decision_authority=("external_verified" if real_generation else "deterministic"),
            ),
        }

    def _blender_failure_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        generation = state["generation"]
        route = _route_event(state, "blender_failure_handler", "blender_failure")
        return {
            "route_history": route,
            "trace": _trace(
                state,
                "blender_failure_handler",
                f"qa_continues:{generation.mode}",
                started,
                warnings=[generation.mode],
                errors=[generation.error] if generation.error else [],
                status="failed",
                route="blender_failure",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _qa_generation(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        generation = state["generation"]
        glb_inspection = self.glb_inspector.inspect(
            Path(generation.artifacts["glb"]),
            state["scene"],
            Path(generation.artifacts["metadata"]),
        )
        preview_inspection = self.preview_inspector.inspect(
            Path(generation.artifacts["preview"]),
            state["scene"],
        )
        geometry_validation = self.geometry_validator.validate(
            state["scene"],
            glb_inspection,
            Path(generation.artifacts["metadata"]),
            glb_path=Path(generation.artifacts["glb"]),
        )
        qa_report = self.qa.validate(
            state["scene"],
            generation,
            glb_inspection,
            preview_inspection,
            geometry_validation,
            allow_fallback=self.allow_blender_fallback,
        )
        merged = _merge_reports(
            state["scene"].scene_id,
            [state["requirement_report"], state["scene_report"], qa_report],
        )
        return {
            "glb_inspection": glb_inspection,
            "geometry_validation": geometry_validation,
            "preview_inspection": preview_inspection,
            "qa_report": qa_report,
            "report": merged,
            "trace": _trace(
                state,
                "qa_generation",
                qa_report.status,
                started,
                status=qa_report.status,
                warnings=[warning.code for warning in qa_report.warnings],
                errors=[error.code for error in qa_report.errors],
            ),
        }

    def _post_blender_gate(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        gate = evaluate_post_blender_gate(
            generation=state.get("generation"),
            qa_report=state.get("qa_report"),
            glb_inspection=state.get("glb_inspection"),
            preview_inspection=state.get("preview_inspection"),
            geometry_validation=state.get("geometry_validation"),
            allow_fallback=self.allow_blender_fallback,
        )
        report = (
            state["report"]
            if gate.passed
            else _merge_quality_gate_report(
                state["workflow_id"],
                state["report"],
                gate,
            )
        )
        return {
            "post_blender_gate": gate,
            "quality_gate_reports": [*state.get("quality_gate_reports", []), gate.model_dump()],
            "report": report,
            "trace": _trace(
                state,
                "post_blender_gate",
                "passed" if gate.passed else "failed",
                started,
                status="passed" if gate.passed else "failed",
                warnings=gate.warnings,
                errors=gate.critical_errors,
                route=None if gate.passed else "quality_gate_failed",
            ),
        }

    def _certify_completion(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        certificate = build_completion_certificate(
            workflow_id=state["workflow_id"],
            requirements=state.get("requirements"),
            design_blueprint=state.get("design_blueprint"),
            blueprint_requirement_coverage=state.get("blueprint_requirement_coverage"),
            blueprint_scene_coverage=state.get("blueprint_scene_coverage"),
            scene=state.get("scene"),
            requirement_coverage=state.get("requirement_coverage"),
            generation=state.get("generation"),
            qa_report=state.get("qa_report"),
            glb_inspection=state.get("glb_inspection"),
            geometry_validation=state.get("geometry_validation"),
            preview_inspection=state.get("preview_inspection"),
            pre_blender_gate=state.get("pre_blender_gate"),
            post_blender_gate=state.get("post_blender_gate"),
            cognitive_plan=state.get("cognitive_plan"),
        )
        report = state["report"]
        if certificate.status == "rejected":
            errors = [
                ValidationIssue(
                    code=f"COMPLETION_CERTIFICATE_{blocker.upper()}",
                    message=f"Completion proof failed: {blocker}",
                    severity="error",
                )
                for blocker in certificate.blockers
            ]
            checks = {
                **report.checks,
                **{
                    f"completion_certificate_{name}": passed
                    for name, passed in certificate.checks.items()
                },
            }
            report = report.model_copy(
                update={
                    "status": "failed",
                    "score": sum(checks.values()) / len(checks) if checks else 0.0,
                    "checks": checks,
                    "errors": [*report.errors, *errors],
                }
            )
        return {
            "completion_certificate": certificate,
            "report": report,
            "trace": _trace(
                state,
                "certify_completion",
                certificate.status,
                started,
                status="passed" if certificate.status == "issued" else "failed",
                errors=certificate.blockers,
            ),
        }

    def _qa_failure_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        qa_report = state["qa_report"]
        route = _route_event(state, "qa_failure_handler", "qa_failure")
        return {
            "report": state["report"],
            "route_history": route,
            "trace": _trace(
                state,
                "qa_failure_handler",
                "blocked:qa_failed",
                started,
                status="failed",
                errors=[error.code for error in qa_report.errors],
                route="qa_failure",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _quality_gate_failure_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        gate = state.get("post_blender_gate") or state.get("pre_blender_gate")
        route = _route_event(
            state,
            "quality_gate_failure_handler",
            "quality_gate_failed",
            events=[gate.model_dump()] if gate else [],
        )
        errors = gate.critical_errors if gate else ["QUALITY_GATE_FAILED"]
        return {
            "route_history": route,
            "report": state["report"],
            "trace": _trace(
                state,
                "quality_gate_failure_handler",
                ",".join(errors),
                started,
                status="failed",
                errors=errors,
                route="quality_gate_failed",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _memory_writeback(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        if self.memory_service is None:
            return {
                "trace": _trace(state, "memory_writeback", "skipped", started, status="skipped")
            }
        report = state.get("report")
        if report is None:
            return {
                "trace": _trace(
                    state, "memory_writeback", "skipped:no_report", started, status="skipped"
                )
            }
        try:
            summary = self.memory_service.write_workflow_summary(
                workflow_id=state["workflow_id"],
                requirements=state.get("requirements"),
                scene=state.get("scene"),
                report=report,
                generation=state.get("generation"),
                scene_spec_path=state["output_dir"] / "scene_spec.json",
                validation_report_path=state["output_dir"] / "validation_report.json",
            )
            stats = self.memory_service.stats()
        except Exception as exc:
            return {
                "memory_writeback": {
                    "status": "failed_non_blocking",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "trace": _trace(
                    state,
                    "memory_writeback",
                    f"failed_non_blocking:{type(exc).__name__}",
                    started,
                    status="failed",
                    errors=[str(exc)],
                ),
            }
        writeback = stats | {
            "summary": summary.model_dump() if summary else None,
            "index": self.memory_service.last_index_result.model_dump(),
        }
        return {
            "memory_writeback": writeback,
            "trace": _trace(
                state,
                "memory_writeback",
                f"{stats['workflow_memory_count']} workflows",
                started,
            ),
        }


def _planning_decision_request(
    evidence: RagPlanningEvidence,
    memory_recall: dict | None,
) -> PlanningDecisionRequest:
    candidates = []
    for candidate in evidence.candidates[:24]:
        provenance = candidate.provenance
        score = provenance.get("score")
        candidates.append(
            PlanningCandidate(
                candidate_id=candidate.candidate_id,
                field=candidate.field,  # type: ignore[arg-type]
                value=candidate.value,  # type: ignore[arg-type]
                provenance=PlanningCandidateProvenance(
                    source="rag",
                    reference_id=str(
                        provenance.get("doc_id") or f"context-{candidate.context_index + 1}"
                    )[:120],
                    rank=int(provenance.get("rank") or candidate.context_index + 1),
                    score=float(score) if isinstance(score, int | float) else None,
                    collection=_bounded_text(provenance.get("collection"), 120),
                    document_name=_bounded_text(provenance.get("filename"), 180),
                    excerpt=_bounded_text(provenance.get("excerpt"), 320),
                ),
            )
        )
    memory_risks = _planning_memory_risks(memory_recall)
    return PlanningDecisionRequest(
        current_values=PlanningCurrentValues.model_validate(evidence.current_values),
        protected_fields=sorted(set(evidence.current_values) - set(evidence.inferred_fields)),  # type: ignore[arg-type]
        candidates=candidates,
        memory_risks=memory_risks,
    )


def _planning_memory_risks(memory_recall: dict | None) -> list[PlanningMemoryRisk]:
    if not isinstance(memory_recall, dict):
        return []
    patterns = memory_recall.get("error_patterns")
    if not isinstance(patterns, list):
        return []
    risks: list[PlanningMemoryRisk] = []
    for index, pattern in enumerate(patterns[:12], start=1):
        if not isinstance(pattern, dict):
            continue
        code = str(pattern.get("issue_code") or "prior_issue")
        safe_code = re.sub(r"[^A-Za-z0-9._:-]+", "-", code).strip("-.") or "prior_issue"
        raw_severity = str(pattern.get("severity") or "warning").lower()
        severity = "high" if raw_severity in {"error", "critical", "high"} else "medium"
        summary = str(pattern.get("message") or code).strip() or code
        risks.append(
            PlanningMemoryRisk(
                risk_id=f"memory:{index}:{safe_code}"[:96],
                severity=severity,
                summary=summary[:240],
            )
        )
    return risks


def _planning_resolution_payload(resolution: Any) -> dict:
    return {
        "antenna_install_height_m": resolution.antenna_install_height_m,
        "beamwidth_deg": resolution.beamwidth_deg,
        "mechanical_tilt_deg": resolution.mechanical_tilt_deg,
        "electrical_tilt_deg": resolution.electrical_tilt_deg,
        "include_cables": resolution.include_cables,
        "include_sector_beams": resolution.include_sector_beams,
        "decisions": list(resolution.decisions),
    }


def _bounded_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _entry_route(state: WorkflowState) -> str:
    return state.get("entry_mode", "natural_language")


def _design_domain_route(state: WorkflowState) -> str:
    decision = state.get("design_route")
    return decision.route if decision is not None else "blocked"


def _cognitive_plan_route(state: WorkflowState) -> str:
    report = state.get("requirement_report")
    ready = state.get("cognitive_plan") is not None and report and report.status == "passed"
    return "continue" if ready else "failed"


def _cognitive_geometry_route(state: WorkflowState) -> str:
    return "failed" if state.get("geometry_program_error") else "continue"


def _cognitive_scene_route(state: WorkflowState) -> str:
    return "continue" if state.get("scene") is not None else "failed"


def _cognitive_validation_route(state: WorkflowState) -> str:
    report = state.get("report")
    return "continue" if report is not None and report.status == "passed" else "failed"


def _component_placement_context(plan: CognitiveDesignPlan, component_id: str) -> str:
    relationships = [
        (f"{item.kind}:{item.source_component_id}->{item.target_component_id}")
        for item in plan.component_graph.relationships
        if component_id in {item.source_component_id, item.target_component_id}
    ]
    return "; ".join(relationships)[:600] or "Place in the design coordinate frame."


def _extraction_route(state: WorkflowState) -> str:
    requirement_report = state.get("requirement_report")
    if requirement_report is not None and requirement_report.status == "failed":
        return "rule_violation"
    return "continue" if state.get("requirements") is not None else "missing_data"


def _requirements_context_text(requirements: RequirementSpec, source_label: str) -> str:
    return "\n".join(
        [
            f"source: {source_label}",
            f"network_type: {requirements.network_type}",
            f"tower_type: {requirements.tower_type}",
            f"tower_height_m: {requirements.tower_height_m}",
            f"sector_count: {requirements.sector_count}",
            "azimuths_deg: " + ", ".join(str(value) for value in requirements.azimuths_deg),
            f"antenna_install_height_m: {requirements.antenna_install_height_m}",
            f"include_rru: {requirements.include_rru}",
            f"include_cables: {requirements.include_cables}",
        ]
    )


def _rag_query_text(state: WorkflowState) -> str:
    requirements = state.get("requirements")
    raw_text = state.get("requirements_text", "")
    if not isinstance(requirements, RequirementSpec):
        return raw_text
    characteristics = requirements.tower_characteristics
    lines = [
        raw_text,
        "",
        "Structured RequirementSpec for retrieval:",
        f"network_type: {requirements.network_type}",
        f"tower_type: {requirements.tower_type}",
        f"tower_height_m: {requirements.tower_height_m}",
        f"tower_structure: {characteristics.structure}",
        f"foundation_type: {characteristics.foundation_type}",
        f"sector_count: {requirements.sector_count}",
        f"antenna_install_height_m: {requirements.antenna_install_height_m}",
        "azimuths_deg: " + ", ".join(str(value) for value in requirements.azimuths_deg),
        f"beamwidth_deg: {requirements.beamwidth_deg}",
        f"include_rru: {requirements.include_rru}",
        f"include_cables: {requirements.include_cables}",
        f"include_beams: {requirements.include_beams}",
        f"include_labels: {requirements.include_labels}",
        f"include_power_cabinet: {requirements.include_power_cabinet}",
        f"include_gps_antenna: {requirements.include_gps_antenna}",
    ]
    return "\n".join(lines)


def _rag_hint_context_count(context: list[dict]) -> int:
    count = 0
    for item in context:
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        hints = payload.get("planning_hints")
        if isinstance(hints, dict) and hints:
            count += 1
    return count


def _requirements_from_scene(
    scene: SceneSpec,
    tower: AssetManifest,
    antenna: AssetManifest,
    radio: AssetManifest | None,
    detail_level: str,
) -> RequirementSpec:
    first_sector = scene.sectors[0]
    return RequirementSpec(
        network_type=scene.network_type,
        site_type="telecom_site",
        tower_type=tower.compatible_tower_types[0]
        if tower.compatible_tower_types
        else scene.tower.asset_id,
        tower_height_m=scene.tower.height_m,
        tower_characteristics=scene.tower.characteristics,
        sector_count=len(scene.sectors),
        antenna_type=antenna.asset_id,
        antenna_install_height_m=first_sector.install_height_m,
        azimuths_deg=[sector.azimuth_deg for sector in scene.sectors],
        mechanical_tilt_deg=first_sector.mechanical_tilt_deg,
        electrical_tilt_deg=first_sector.electrical_tilt_deg,
        beamwidth_deg=first_sector.beamwidth_deg,
        include_rru=radio is not None,
        include_cables=any(sector.include_cable for sector in scene.sectors),
        include_beams=scene.visual_elements.include_sector_beams,
        include_labels=scene.visual_elements.include_labels,
        include_power_cabinet=scene.visual_elements.include_power_cabinet,
        include_gps_antenna=scene.visual_elements.include_gps_antenna,
        geometry_requests=[
            GeometryRequest(
                request_id=re.sub(r"\.llm_v[12]$", "", program.program_id),
                semantic_role=program.semantic_role,
                description=(
                    program.source_description
                    or (
                        "Composant généré existant conservé pendant la révision : "
                        f"{program.semantic_role}."
                    )
                ),
                quantity=program.requested_quantity,
                placement_context=program.placement_context,
                maximum_dimensions_m=program.maximum_dimensions_m,
            )
            for program in scene.geometry_programs
        ],
        detail_level=detail_level,  # type: ignore[arg-type]
        warnings=[],
        repair_events=[],
    )


def _unique_assets(assets: list[AssetManifest]) -> list[AssetManifest]:
    unique: dict[str, AssetManifest] = {}
    for asset in assets:
        unique[asset.asset_id] = asset
    return list(unique.values())


def _scene_with_asset_metadata(scene: SceneSpec, assets: list[AssetManifest]) -> SceneSpec:
    assets_by_id = {asset.asset_id: asset for asset in assets}
    tower_asset = assets_by_id[scene.tower.asset_id]
    tower = scene.tower.model_copy(
        update={
            "asset_file": tower_asset.file,
            "asset_source": tower_asset.source,
            "asset_metadata": _runtime_asset_metadata(tower_asset),
            "import_fallback_allowed": tower_asset.import_fallback_allowed,
            "dimensions_m": tower_asset.dimensions_m,
        }
    )
    sectors = []
    for sector in scene.sectors:
        antenna_asset = assets_by_id[sector.antenna_asset_id]
        radio_asset = assets_by_id.get(sector.radio_asset_id) if sector.radio_asset_id else None
        sectors.append(
            sector.model_copy(
                update={
                    "antenna_asset_file": antenna_asset.file,
                    "antenna_asset_source": antenna_asset.source,
                    "antenna_asset_metadata": _runtime_asset_metadata(antenna_asset),
                    "antenna_import_fallback_allowed": antenna_asset.import_fallback_allowed,
                    "radio_asset_file": radio_asset.file if radio_asset else None,
                    "radio_asset_source": radio_asset.source if radio_asset else None,
                    "radio_asset_metadata": _runtime_asset_metadata(radio_asset)
                    if radio_asset
                    else RuntimeAssetMetadata(),
                    "radio_import_fallback_allowed": radio_asset.import_fallback_allowed
                    if radio_asset
                    else True,
                }
            )
        )
    accessories = []
    for accessory in scene.accessory_assets:
        asset = assets_by_id[accessory.asset_id]
        accessories.append(
            accessory.model_copy(
                update={
                    "asset_file": asset.file,
                    "asset_source": asset.source,
                    "asset_metadata": _runtime_asset_metadata(asset),
                    "import_fallback_allowed": asset.import_fallback_allowed,
                    "dimensions_m": asset.dimensions_m,
                }
            )
        )
    return scene.model_copy(
        update={"tower": tower, "sectors": sectors, "accessory_assets": accessories}
    )


def _scene_with_revision_dependencies(scene: SceneSpec, registry: AssetRegistry) -> SceneSpec:
    """Rebind derived assets and placements after a validated SceneSpec edit."""

    tower_type = _tower_type_for_structure(scene.tower.characteristics.structure)
    tower_asset = registry.select_tower(tower_type, scene.network_type, scene.tower.height_m)
    tower = scene.tower.model_copy(
        update={
            "asset_id": tower_asset.asset_id,
            "asset_file": tower_asset.file,
            "asset_source": tower_asset.source,
            "asset_metadata": _runtime_asset_metadata(tower_asset),
            "import_fallback_allowed": tower_asset.import_fallback_allowed,
            "dimensions_m": tower_asset.dimensions_m,
            "generation_strategy": "parametric_generated",
            "geometry_source": "parametric_generated",
            "generation_reason": "revision dependencies normalized from tower structure",
        }
    )

    sectors = []
    for sector in scene.sectors:
        antenna = registry.get(sector.antenna_asset_id)
        if antenna.compatible_tower_types and tower_type not in antenna.compatible_tower_types:
            antenna = registry.select_asset("antenna", scene.network_type, tower_type)
        radio = registry.get(sector.radio_asset_id) if sector.radio_asset_id else None
        if (
            radio is not None
            and radio.compatible_tower_types
            and tower_type not in radio.compatible_tower_types
        ):
            radio = registry.select_asset("radio", scene.network_type, tower_type)
        sectors.append(
            sector.model_copy(
                update={
                    "antenna_asset_id": antenna.asset_id,
                    "radio_asset_id": radio.asset_id if radio else None,
                }
            )
        )

    characteristics = tower.characteristics
    base_width = float(characteristics.base_width_m or tower_asset.dimensions_m.width or 4.0)
    top_width = float(characteristics.top_width_m or min(base_width, base_width * 0.25))
    accessories = []
    if scene.visual_elements.include_power_cabinet:
        cabinet = registry.select_asset("cabinet", scene.network_type, tower_type)
        accessories.append(
            _rebind_revision_accessory(
                scene,
                cabinet,
                asset_type="cabinet",
                default_position=[max(3.0, base_width * 1.2), 0.0, 0.0],
            )
        )
    if scene.visual_elements.include_gps_antenna:
        gps = registry.select_asset("gps", scene.network_type, tower_type)
        gps_height = max(0.5, scene.tower.height_m - 0.5)
        tower_width = base_width + (top_width - base_width) * (
            gps_height / max(scene.tower.height_m, 1e-6)
        )
        accessories.append(
            _rebind_revision_accessory(
                scene,
                gps,
                asset_type="gps",
                default_position=[0.0, tower_width / 2 + 0.1, gps_height],
            )
        )
    accessories.extend(
        accessory
        for accessory in scene.accessory_assets
        if accessory.asset_type not in {"cabinet", "gps"}
    )
    return scene.model_copy(
        update={"tower": tower, "sectors": sectors, "accessory_assets": accessories}
    )


def _tower_type_for_structure(structure: str) -> str:
    return "lattice_tower" if structure == "lattice" else structure


def _rebind_revision_accessory(
    scene: SceneSpec,
    asset: AssetManifest,
    *,
    asset_type: str,
    default_position: list[float],
):
    existing = next(
        (item for item in scene.accessory_assets if item.asset_type == asset_type),
        None,
    )
    rebound = _accessory_from_asset(
        asset,
        asset_type=asset_type,
        position=default_position,
    )
    if existing is None:
        return rebound
    position = (
        existing.position if existing.placement_policy == "user_defined" else default_position
    )
    return rebound.model_copy(
        update={
            "position": position,
            "rotation_deg": existing.rotation_deg,
            "scale": existing.scale,
            "placement_policy": existing.placement_policy,
        }
    )


def _accessory_from_asset(asset: AssetManifest, *, asset_type: str, position: list[float]):
    from core.contracts.scene import SceneAccessoryPlacement

    if asset.allows_generation_mode("imported_glb_exact"):
        generation_strategy = "imported_glb_exact"
        geometry_source = "imported_glb_exact"
        generation_reason = "qualified exact GLB import authorized by pinned asset manifest"
    elif asset.allows_generation_mode("parametric_generated"):
        generation_strategy = "internal_project_generated"
        geometry_source = "internal_project_generated"
        generation_reason = "qualified SceneSpec-driven parametric component profile"
    else:
        generation_strategy = "procedural_fallback"
        geometry_source = "degraded"
        generation_reason = (
            "asset is not qualified for generation; controlled procedural fallback required"
        )

    return SceneAccessoryPlacement(
        asset_id=asset.asset_id,
        asset_file=asset.file,
        asset_source=asset.source,
        asset_metadata=_runtime_asset_metadata(asset),
        import_fallback_allowed=asset.import_fallback_allowed,
        asset_type=asset_type,  # type: ignore[arg-type]
        dimensions_m=asset.dimensions_m,
        position=position,
        rotation_deg=[0.0, 0.0, 0.0],
        generation_strategy=generation_strategy,
        geometry_source=geometry_source,
        generation_reason=generation_reason,
    )


def _scene_accessory_ids(scene: SceneSpec) -> set[str]:
    return {accessory.asset_id for accessory in scene.accessory_assets}


def _runtime_asset_metadata(asset: AssetManifest) -> RuntimeAssetMetadata:
    return RuntimeAssetMetadata(
        geometry_fidelity=asset.geometry_fidelity,
        license=asset.license,
        attribution_required=asset.attribution_required,
        attribution=asset.attribution,
        original_url=asset.original_url,
        original_author=asset.original_author,
        normalized_by=asset.normalized_by,
        pivot_policy=asset.pivot_policy,
        front_axis=asset.front_axis,
        qualification_status=asset.qualification.status,
        allowed_generation_modes=list(asset.qualification.allowed_generation_modes),
        verified_file_sha256=asset.qualification.verified_file_sha256,
        qualification_method=asset.qualification.qualification_method,
        qualification_limitations=list(asset.qualification.limitations),
        builder_profile_id=asset.builder_profile_id,
    )


def _asset_route(state: WorkflowState) -> str:
    return "blocked" if state.get("asset_error") else "continue"


def _requirements_route(state: WorkflowState) -> str:
    if state["requirement_report"].status not in ("passed", "warning"):
        return "rule_violation"
    return "continue"


def _blueprint_route(state: WorkflowState) -> str:
    if state.get("entry_mode") == "scene_revision" and state.get("scene") is not None:
        return "validate_scene"
    return "plan_scene"


def _geometry_request_route(state: WorkflowState) -> str:
    return "generate" if state["requirements"].geometry_requests else "continue"


def _geometry_program_route(state: WorkflowState) -> str:
    return "failed" if state.get("geometry_program_error") else "continue"


def _scene_route(state: WorkflowState) -> str:
    if state["scene_report"].status == "passed" and (
        state["requirements"].repair_events and not state.get("scene_repair_recorded")
    ):
        return "scene_repair"
    return "continue" if state["scene_report"].status == "passed" else "scene_repair"


def _scene_repair_route(state: WorkflowState) -> str:
    return (
        "retry"
        if state.get("repair_attempts", 0) < state.get("max_repair_attempts", 2)
        else "blocked"
    )


def _generation_route(state: WorkflowState) -> str:
    generation = state["generation"]
    real_generation = generation.status == "generated" and generation.mode == "real_blender"
    if not real_generation:
        return "blender_failure"
    return "continue"


def _pre_blender_gate_route(state: WorkflowState) -> str:
    return "continue" if state["pre_blender_gate"].passed else "quality_gate_failed"


def _post_blender_gate_route(state: WorkflowState) -> str:
    return "continue" if state["post_blender_gate"].passed else "quality_gate_failed"


def _completion_certificate_route(state: WorkflowState) -> str:
    certificate = state.get("completion_certificate")
    return "issued" if certificate and certificate.status == "issued" else "rejected"


def _qa_route(state: WorkflowState) -> str:
    return "continue" if state["qa_report"].status == "passed" else "qa_failure"


def _trace(
    state: WorkflowState,
    node: str,
    detail: str,
    started: float,
    status: str = "passed",
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    route: str | None = None,
    attempt: int | None = None,
    actor_kind: ActorKind | None = None,
    decision_authority: DecisionAuthority | None = None,
) -> list[dict]:
    default_actor_kind, default_decision_authority = _step_truth_defaults(node)
    step = AgentStepTrace(
        node=node,
        status=status,
        actor_kind=actor_kind or default_actor_kind,
        decision_authority=decision_authority or default_decision_authority,
        detail=detail,
        duration_ms=_duration_ms(started),
        warnings=warnings or [],
        errors=errors or [],
        route=route,
        attempt=attempt,
    )
    _emit_node_runtime_event(state, step)
    return state.get("trace", []) + [step.model_dump()]


def _step_truth_defaults(node: str) -> tuple[ActorKind, DecisionAuthority]:
    if node in {
        "validate_requirements",
        "plan_scene",
        "validate_scene",
        "scene_repair_handler",
        "geometry_program_failure_handler",
    }:
        return "deterministic_specialist", "deterministic"
    if node == "plan_generated_geometry":
        return "llm_decision", "llm_bounded"
    if node in {
        "pre_blender_gate",
        "qa_generation",
        "post_blender_gate",
        "certify_completion",
        "qa_failure_handler",
        "quality_gate_failure_handler",
    }:
        return "quality_gate", "deterministic"
    if node == "generate_blender":
        # A started/failed tool call is not externally verified yet. The
        # generation node promotes this authority only after real artifacts
        # have been produced.
        return "external_tool", "deterministic"
    return "service", "deterministic"


def _emit_node_started_runtime_event(state: WorkflowState, node: str) -> None:
    sink = _runtime_event_sink(state)
    if sink is None:
        return
    actor_kind, decision_authority = _step_truth_defaults(node)
    sink(
        state["workflow_id"],
        "node_started",
        {
            "node": node,
            "phase": _phase_for_node(node),
            "status": "running",
            "actor_kind": actor_kind,
            "decision_authority": decision_authority,
            "detail": "started",
            "duration_ms": None,
            "warnings": [],
            "errors": [],
            "human_label": _human_label_for_node(node),
            "progress_message": _progress_message_for_node(node),
        },
    )


def _emit_node_exception_runtime_event(
    state: WorkflowState,
    node: str,
    exc: Exception,
) -> None:
    sink = _runtime_event_sink(state)
    if sink is None:
        return
    actor_kind, decision_authority = _step_truth_defaults(node)
    sink(
        state["workflow_id"],
        "node_failed",
        {
            "node": node,
            "phase": _phase_for_node(node),
            "status": "failed",
            "actor_kind": actor_kind,
            "decision_authority": decision_authority,
            "detail": type(exc).__name__,
            "duration_ms": None,
            "warnings": [],
            "errors": [str(exc)],
            "human_label": _human_label_for_node(node),
            "progress_message": f"Échec pendant : {_human_label_for_node(node)}.",
        },
    )


def _emit_node_runtime_event(state: WorkflowState, step: AgentStepTrace) -> None:
    sink = _runtime_event_sink(state)
    if sink is None:
        return
    event_type = {
        "failed": "node_failed",
        "skipped": "node_skipped",
    }.get(step.status, "node_completed")
    sink(
        state["workflow_id"],
        event_type,
        {
            "node": step.node,
            "phase": _phase_for_node(step.node),
            "status": step.status,
            "actor_kind": step.actor_kind,
            "decision_authority": step.decision_authority,
            "detail": step.detail,
            "duration_ms": step.duration_ms,
            "warnings": step.warnings,
            "errors": step.errors,
            "route": step.route,
            "attempt": step.attempt,
            "human_label": _human_label_for_node(step.node),
            "progress_message": _completed_message_for_node(step.node, step.status),
        },
    )


def _runtime_event_sink(state: WorkflowState) -> RuntimeEventSink | None:
    invocation_id = state.get("runtime_event_sink_id")
    if not invocation_id:
        return None
    with _RUNTIME_EVENT_SINKS_LOCK:
        return _RUNTIME_EVENT_SINKS.get(invocation_id)


def _phase_for_node(node: str) -> str:
    if node in {
        "extract_requirements",
        "use_validated_requirements",
        "validate_requirements",
        "missing_data_handler",
        "rule_violation_handler",
    }:
        return "requirements"
    if node in {"retrieve_rag_context", "decide_planning_context"}:
        return "rag"
    if node in {"memory_recall", "memory_writeback"}:
        return "memory"
    if node == "select_assets":
        return "assets"
    if node in {
        "plan_scene",
        "plan_generated_geometry",
        "geometry_program_failure_handler",
        "validate_scene",
        "scene_repair_handler",
    }:
        return "scene"
    if node in {"pre_blender_gate", "post_blender_gate", "quality_gate_failure_handler"}:
        return "quality_gate"
    if node in {"generate_blender", "blender_failure_handler"}:
        return "blender"
    if node in {"qa_generation", "qa_failure_handler"}:
        return "qa"
    if node == "edit_prepare_revision":
        return "edit"
    return "workflow"


def _human_label_for_node(node: str) -> str:
    return {
        "extract_requirements": "Analyse du cahier de charge",
        "use_validated_requirements": "Lecture des exigences validées",
        "missing_data_handler": "Vérification des données manquantes",
        "retrieve_rag_context": "Recherche dans la connaissance telecom",
        "decide_planning_context": "Arbitrage des preuves de conception",
        "memory_recall": "Rappel mémoire projet",
        "select_assets": "Sélection des assets telecom",
        "validate_requirements": "Validation des contraintes telecom",
        "rule_violation_handler": "Blocage par règle métier",
        "plan_scene": "Construction de la scène 3D",
        "plan_generated_geometry": "Conception géométrique spécialisée",
        "geometry_program_failure_handler": "Blocage de la géométrie spécialisée",
        "validate_scene": "Validation SceneSpec",
        "scene_repair_handler": "Réparation SceneSpec",
        "pre_blender_gate": "Contrôle avant Blender",
        "generate_blender": "Génération Blender",
        "blender_failure_handler": "Analyse d'échec Blender",
        "qa_generation": "Vérification géométrique",
        "post_blender_gate": "Contrôle final",
        "certify_completion": "Certification des preuves",
        "qa_failure_handler": "Analyse d'échec QA",
        "quality_gate_failure_handler": "Blocage qualité",
        "memory_writeback": "Écriture mémoire",
        "edit_prepare_revision": "Préparation de la révision",
    }.get(node, node.replace("_", " ").capitalize())


def _progress_message_for_node(node: str) -> str:
    return {
        "extract_requirements": "Le backend extrait les contraintes importantes du brief.",
        "retrieve_rag_context": "Le backend cherche le contexte telecom pertinent.",
        "decide_planning_context": (
            "GPT-OSS compare les preuves RAG validées sans modifier les contraintes explicites."
        ),
        "memory_recall": "Le backend récupère les souvenirs utiles de designs précédents.",
        "select_assets": "Le backend choisit les assets compatibles avec le site.",
        "validate_requirements": "Le backend vérifie les contraintes radio et pylône.",
        "plan_scene": "Le backend place le pylône, les secteurs, antennes et équipements.",
        "plan_generated_geometry": (
            "GPT-OSS écrit un programme géométrique typé; le backend vérifie chaque "
            "nœud avant Blender."
        ),
        "validate_scene": "Le backend vérifie que la SceneSpec est cohérente.",
        "pre_blender_gate": "Le backend vérifie que la génération 3D peut démarrer.",
        "generate_blender": "Blender génère le GLB, la preview et les métadonnées.",
        "qa_generation": "Le backend inspecte le GLB, la géométrie et la preview.",
        "post_blender_gate": "Le backend vérifie que le résultat est exploitable.",
        "certify_completion": (
            "Le backend recalcule les hashes et vérifie toutes les preuves avant de terminer."
        ),
        "memory_writeback": "Le backend sauvegarde un résumé dans la mémoire locale.",
        "edit_prepare_revision": "Le backend prépare la scène modifiée avant régénération.",
    }.get(node, f"Étape en cours : {_human_label_for_node(node)}.")


def _completed_message_for_node(node: str, status: str) -> str:
    if status == "failed":
        return f"Échec pendant : {_human_label_for_node(node)}."
    if status == "skipped":
        return f"Étape ignorée : {_human_label_for_node(node)}."
    return f"Étape terminée : {_human_label_for_node(node)}."


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _route_event(
    state: WorkflowState,
    handler: str,
    route: str,
    attempt: int | None = None,
    events: list[dict] | None = None,
) -> list[dict]:
    return state.get("route_history", []) + [
        {
            "handler": handler,
            "route": route,
            "attempt": state.get("repair_attempts", 0) if attempt is None else attempt,
            "events": events or [],
        }
    ]


def _failed_report(design_id: str, code: str, message: str) -> ValidationReport:
    issue = ValidationIssue(code=code, message=message, severity="error")
    return ValidationReport(
        design_id=design_id,
        status="failed",
        score=0.0,
        checks={code.lower(): False},
        warnings=[],
        errors=[issue],
    )


def _merge_reports(design_id: str, reports: list[ValidationReport]) -> ValidationReport:
    checks: dict[str, bool] = {}
    warnings = []
    errors = []
    glb_inspection = None
    geometry_validation = None
    preview_inspection = None
    for report in reports:
        checks.update(report.checks)
        warnings.extend(report.warnings)
        errors.extend(report.errors)
        glb_inspection = report.glb_inspection or glb_inspection
        geometry_validation = report.geometry_validation or geometry_validation
        preview_inspection = report.preview_inspection or preview_inspection
    score = sum(1 for passed in checks.values() if passed) / len(checks) if checks else 1.0
    return ValidationReport(
        design_id=design_id,
        status="passed" if not errors else "failed",
        score=score,
        checks=checks,
        warnings=warnings,
        errors=errors,
        glb_inspection=glb_inspection,
        geometry_validation=geometry_validation,
        preview_inspection=preview_inspection,
    )


def _merge_quality_gate_report(
    design_id: str,
    report: ValidationReport,
    gate: QualityGateReport,
) -> ValidationReport:
    checks = report.checks | {f"{gate.stage}_{key}": value for key, value in gate.checks.items()}
    errors = [
        *report.errors,
        *[
            ValidationIssue(
                code=f"{gate.stage.upper()}_{error.upper()}",
                message=(
                    "Un composant demandé ne dispose pas encore d’un modèle 3D de bibliothèque "
                    "admis pour cette utilisation. Aucun remplacement n’a été fabriqué."
                    if error == "LIBRARY_SOURCE_REQUIRED"
                    else f"Quality gate failed: {gate.stage}.{error}"
                ),
                severity="error",
            )
            for error in gate.critical_errors
        ],
    ]
    warnings = [
        *report.warnings,
        *[
            ValidationIssue(
                code=f"{gate.stage.upper()}_{warning}",
                message=f"Quality gate warning: {warning}",
                severity="warning",
            )
            for warning in gate.warnings
        ],
    ]
    passed_count = sum(1 for passed in checks.values() if passed)
    score = passed_count / len(checks) if checks else 0.0
    return ValidationReport(
        design_id=design_id,
        status="passed" if not errors else "failed",
        score=score,
        checks=checks,
        warnings=warnings,
        errors=errors,
        glb_inspection=report.glb_inspection,
        geometry_validation=report.geometry_validation,
        preview_inspection=report.preview_inspection,
    )


def _result_from_state(state: dict[str, Any]) -> OrchestratorResult:
    report = state.get("report")
    certificate = state.get("completion_certificate")
    status = (
        "completed"
        if report
        and report.status in ("passed", "warning")
        and certificate is not None
        and certificate.status == "issued"
        else "failed"
    )
    metrics = _workflow_metrics(state, status)
    memory_recall = state.get("memory_recall")
    workflow_trace = WorkflowTrace(
        workflow_id=state["workflow_id"],
        total_duration_ms=state.get("total_duration_ms", 0),
        steps=[AgentStepTrace(**entry) for entry in state.get("trace", [])],
        route_history=state.get("route_history", []),
        quality_gates=state.get("quality_gate_reports", []),
        glb_inspection=state["glb_inspection"].model_dump()
        if state.get("glb_inspection")
        else None,
        geometry_validation=state["geometry_validation"].model_dump()
        if state.get("geometry_validation")
        else None,
        preview_inspection=state["preview_inspection"].model_dump()
        if state.get("preview_inspection")
        else None,
        requirement_coverage=state["requirement_coverage"].model_dump()
        if state.get("requirement_coverage")
        else None,
        completion_certificate=certificate.model_dump(mode="json") if certificate else None,
        metrics=metrics,
    )
    return OrchestratorResult(
        workflow_id=state["workflow_id"],
        status=status,
        requirements=state.get("requirements"),
        scene=state.get("scene"),
        llm_provider=state.get("extraction_provider"),
        llm_fallback_used=state.get("extraction_fallback_used"),
        llm_error=state.get("extraction_error"),
        report=report,
        requirement_report=state.get("requirement_report"),
        scene_report=state.get("scene_report"),
        qa_report=state.get("qa_report"),
        glb_inspection=state.get("glb_inspection"),
        geometry_validation=state.get("geometry_validation"),
        preview_inspection=state.get("preview_inspection"),
        requirement_coverage=state.get("requirement_coverage"),
        completion_certificate=certificate,
        generation=state.get("generation"),
        rag_context=state.get("rag_context", []),
        planning_decision=state.get("planning_decision"),
        memory_recall=MemoryRecallResult(**memory_recall) if memory_recall else None,
        memory_writeback=state.get("memory_writeback"),
        trace=state.get("trace", []),
        workflow_trace=workflow_trace,
        total_duration_ms=workflow_trace.total_duration_ms,
        metrics=metrics,
        route_history=state.get("route_history", []),
        quality_gate_reports=[
            QualityGateReport(**report) for report in state.get("quality_gate_reports", [])
        ],
        tower_validation=state.get("tower_validation"),
        rf_validation=state.get("rf_validation"),
        design_blueprint=state.get("design_blueprint"),
        assembly_plan=state.get("assembly_plan"),
        blueprint_requirement_coverage=state.get("blueprint_requirement_coverage"),
        blueprint_scene_coverage=state.get("blueprint_scene_coverage"),
        cognitive_plan=state.get("cognitive_plan"),
        capability_observations=state.get("capability_observations", []),
    )


def _workflow_metrics(
    state: dict[str, Any],
    status: str,
) -> dict[str, int | float | str | bool | None]:
    generation: GenerationResult | None = state.get("generation")
    qa_report: ValidationReport | None = state.get("qa_report")
    memory_recall = state.get("memory_recall") or {}
    requirement_coverage = state.get("requirement_coverage")
    completion_certificate = state.get("completion_certificate")
    trace = state.get("trace", [])
    artifact_size_bytes = 0
    metrics: dict[str, int | float | str | bool | None] = {
        "status": status,
        "use_llm": state.get("use_llm"),
        "total_workflow_duration_ms": state.get("total_duration_ms", 0),
        "total_duration_ms": state.get("total_duration_ms", 0),
        "trace_steps": len(trace),
        "rag_context_count": len(state.get("rag_context", [])),
        "rag_planning_hint_context_count": _rag_hint_context_count(state.get("rag_context", [])),
        "planning_decision_status": (state.get("planning_decision") or {}).get("status"),
        "planning_decision_fallback_used": (state.get("planning_decision") or {}).get(
            "fallback_used"
        ),
        "memory_hits": memory_recall.get("memory_hits", 0),
        "memory_context_count": memory_recall.get("memory_context_count", 0),
        "rag_duration_ms": _duration_for_nodes(trace, {"retrieve_rag_context"}),
        "planning_duration_ms": _duration_for_nodes(
            trace,
            {
                "select_assets",
                "decide_planning_context",
                "validate_requirements",
                "plan_scene",
                "validate_scene",
                "scene_repair_handler",
                "rule_violation_handler",
            },
        ),
        "blender_duration_ms": generation.duration_ms
        if generation
        else _duration_for_nodes(trace, {"generate_blender", "blender_failure_handler"}),
        "qa_duration_ms": _duration_for_nodes(trace, {"qa_generation", "qa_failure_handler"}),
        "memory_duration_ms": _duration_for_nodes(trace, {"memory_recall", "memory_writeback"}),
        "qa_score": qa_report.score if qa_report else None,
        "requirement_coverage_passed": requirement_coverage.passed
        if requirement_coverage
        else None,
        "requirement_coverage_ratio": requirement_coverage.coverage_ratio
        if requirement_coverage
        else None,
        "completion_certificate_status": completion_certificate.status
        if completion_certificate
        else None,
        "completion_certificate_issued": bool(
            completion_certificate and completion_certificate.status == "issued"
        ),
        "generation_mode": generation.mode if generation else None,
        "generation_duration_ms": generation.duration_ms if generation else None,
        "blender_available": generation.blender_available if generation else None,
        "requirements_hash": state.get("requirements_hash"),
        "scene_spec_hash": state.get("scene_spec_hash"),
        "asset_manifest_hash": state.get("asset_manifest_hash"),
        "knowledge_index_hash": state.get("knowledge_index_hash"),
    }
    glb_inspection: GlbInspectionReport | None = state.get("glb_inspection")
    geometry_validation: GeometryValidationReport | None = state.get("geometry_validation")
    preview_inspection: PreviewInspectionReport | None = state.get("preview_inspection")
    if glb_inspection is not None:
        metrics.update(
            {
                "structural_qa_passed": glb_inspection.structural_qa_passed,
                "expected_objects_present": glb_inspection.checks.get("expected_objects_present"),
                "glb_node_count": glb_inspection.node_count,
                "glb_mesh_count": glb_inspection.mesh_count,
                "glb_material_count": glb_inspection.material_count,
            }
        )
    if geometry_validation is not None:
        metrics.update(
            {
                "geometry_validation_passed": geometry_validation.status == "passed",
                "geometry_missing_objects": len(geometry_validation.missing_objects),
                "geometry_critical_errors": len(geometry_validation.critical_errors),
            }
        )
    if preview_inspection is not None:
        metrics.update(
            {
                "preview_width": preview_inspection.width,
                "preview_height": preview_inspection.height,
                "preview_minimum_resolution_valid": preview_inspection.minimum_resolution_valid,
            }
        )
    cache_metrics = state.get("cache_metrics", {})
    asset_cache_hits = int(cache_metrics.get("asset_cache_hits", 0))
    asset_cache_misses = int(cache_metrics.get("asset_cache_misses", 0))
    rag_cache_hits = int(cache_metrics.get("rag_cache_hits", 0))
    rag_cache_misses = int(cache_metrics.get("rag_cache_misses", 0))
    metrics.update(
        {
            "asset_cache_hits": asset_cache_hits,
            "asset_cache_misses": asset_cache_misses,
            "rag_cache_hits": rag_cache_hits,
            "rag_cache_misses": rag_cache_misses,
            "cache_hits": asset_cache_hits + rag_cache_hits,
            "cache_misses": asset_cache_misses + rag_cache_misses,
        }
    )
    if generation:
        for artifact_name, artifact_path in generation.artifacts.items():
            path = Path(artifact_path)
            artifact_bytes = path.stat().st_size if path.exists() else 0
            artifact_size_bytes += artifact_bytes
            metrics[f"{artifact_name}_bytes"] = artifact_bytes
    metrics["artifact_size_bytes"] = artifact_size_bytes
    return metrics


def _duration_for_nodes(trace: list[dict], nodes: set[str]) -> int:
    return sum(int(entry.get("duration_ms", 0)) for entry in trace if entry.get("node") in nodes)
