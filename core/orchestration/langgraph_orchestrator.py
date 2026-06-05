import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from core.agents import ScenePlanner
from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.assets import AssetManifest
from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport, PreviewInspectionReport
from core.contracts.memory import MemoryRecallResult
from core.contracts.quality import QualityGateReport
from core.contracts.requirements import RequirementSpec
from core.contracts.runtime import AgentStepTrace, WorkflowTrace
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.memory import MemoryService
from core.performance import knowledge_index_hash, requirements_hash, scene_spec_hash
from core.qa import GenerationQA, GLBGeometryValidator, GLBInspector, PreviewInspector
from core.rag import RagService
from core.rules import RuleEngine
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner, GenerationResult
from core.validation import validate_scene_spec
from core.validation.quality_gates import (
    evaluate_post_blender_gate,
    evaluate_pre_blender_gate,
)


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    requirements_text: str
    detail_level: str
    use_llm: bool | None
    output_dir: Path
    requirements: RequirementSpec
    extraction_provider: str
    extraction_fallback_used: bool
    extraction_error: str | None
    rag_context: list[dict]
    memory_recall: dict
    memory_writeback: dict
    asset_error: str
    asset_fallback_failed: bool
    asset_fallback_warnings: list[ValidationIssue]
    tower: AssetManifest
    antenna: AssetManifest
    radio: AssetManifest | None
    selected_assets: list[AssetManifest]
    requirement_report: ValidationReport
    scene: SceneSpec
    scene_report: ValidationReport
    pre_blender_gate: QualityGateReport
    generation: GenerationResult
    glb_inspection: GlbInspectionReport
    geometry_validation: GeometryValidationReport
    preview_inspection: PreviewInspectionReport
    qa_report: ValidationReport
    post_blender_gate: QualityGateReport
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
    quality_gate_reports: list[QualityGateReport]
    generation: GenerationResult | None
    rag_context: list[dict]
    memory_recall: MemoryRecallResult | None
    memory_writeback: dict | None
    trace: list[dict]
    workflow_trace: WorkflowTrace
    total_duration_ms: int
    metrics: dict[str, int | float | str | bool | None]
    route_history: list[dict]


class DesignOrchestrator:
    def __init__(
        self,
        registry: AssetRegistry,
        extractor: RequirementExtractor,
        rag_service: RagService | None,
        blender_runner: BlenderRunner,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.registry = registry
        self.extractor = extractor
        self.rag_service = rag_service
        self.memory_service = memory_service
        self.blender_runner = blender_runner
        self.rule_engine = RuleEngine()
        self.scene_planner = ScenePlanner()
        self.qa = GenerationQA()
        self.glb_inspector = GLBInspector()
        self.geometry_validator = GLBGeometryValidator()
        self.preview_inspector = PreviewInspector()
        self.graph = self._build_graph()

    def run(
        self,
        workflow_id: str,
        requirements_text: str,
        detail_level: str,
        output_dir: Path,
        use_llm: bool | None = None,
    ) -> OrchestratorResult:
        started = time.perf_counter()
        state = self.graph.invoke(
            {
                "workflow_id": workflow_id,
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
        )
        state["total_duration_ms"] = _duration_ms(started)
        return _result_from_state(state)

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        terminal_node = "memory_writeback" if self.memory_service is not None else END
        graph.add_node("extract_requirements", self._extract_requirements)
        graph.add_node("missing_data_handler", self._missing_data_handler)
        graph.add_node("retrieve_rag_context", self._retrieve_rag_context)
        if self.memory_service is not None:
            graph.add_node("memory_recall", self._memory_recall)
            graph.add_node("memory_writeback", self._memory_writeback)
        graph.add_node("select_assets", self._select_assets)
        graph.add_node("asset_fallback_handler", self._asset_fallback_handler)
        graph.add_node("validate_requirements", self._validate_requirements)
        graph.add_node("rule_violation_handler", self._rule_violation_handler)
        graph.add_node("plan_scene", self._plan_scene)
        graph.add_node("validate_scene", self._validate_scene)
        graph.add_node("scene_repair_handler", self._scene_repair_handler)
        graph.add_node("pre_blender_gate", self._pre_blender_gate)
        graph.add_node("generate_blender", self._generate_blender)
        graph.add_node("blender_failure_handler", self._blender_failure_handler)
        graph.add_node("qa_generation", self._qa_generation)
        graph.add_node("post_blender_gate", self._post_blender_gate)
        graph.add_node("qa_failure_handler", self._qa_failure_handler)
        graph.add_node("quality_gate_failure_handler", self._quality_gate_failure_handler)
        graph.set_entry_point("extract_requirements")
        graph.add_conditional_edges(
            "extract_requirements",
            _extraction_route,
            {"continue": "retrieve_rag_context", "missing_data": "missing_data_handler"},
        )
        graph.add_edge("missing_data_handler", terminal_node)
        if self.memory_service is not None:
            graph.add_edge("retrieve_rag_context", "memory_recall")
            graph.add_edge("memory_recall", "select_assets")
        else:
            graph.add_edge("retrieve_rag_context", "select_assets")
        graph.add_conditional_edges(
            "select_assets",
            _asset_route,
            {"continue": "validate_requirements", "asset_fallback": "asset_fallback_handler"},
        )
        graph.add_conditional_edges(
            "asset_fallback_handler",
            _asset_fallback_route,
            {"continue": "validate_requirements", "blocked": terminal_node},
        )
        graph.add_conditional_edges(
            "validate_requirements",
            _requirements_route,
            {
                "continue": "plan_scene",
                "rule_violation": "rule_violation_handler",
            },
        )
        graph.add_edge("rule_violation_handler", terminal_node)
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
            {"continue": terminal_node, "quality_gate_failed": "quality_gate_failure_handler"},
        )
        graph.add_edge("qa_failure_handler", terminal_node)
        graph.add_edge("quality_gate_failure_handler", terminal_node)
        if self.memory_service is not None:
            graph.add_edge("memory_writeback", END)
        return graph.compile()

    def _cache_metrics(self) -> dict[str, int]:
        rag_stats = self.rag_service.cache_stats() if self.rag_service is not None else {}
        return self.registry.cache_stats() | rag_stats

    def _extract_requirements(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        extraction = self.extractor.extract(
            state["requirements_text"],
            state["detail_level"],
            enabled=state.get("use_llm"),
        )
        return {
            "requirements": extraction.requirements,
            "requirements_hash": requirements_hash(extraction.requirements),
            "asset_manifest_hash": self.registry.manifest_hash,
            "knowledge_index_hash": knowledge_index_hash(self.rag_service.project_root)
            if self.rag_service is not None
            else "",
            "extraction_provider": extraction.provider,
            "extraction_fallback_used": extraction.fallback_used,
            "extraction_error": extraction.error,
            "trace": _trace(state, "extract_requirements", extraction.provider, started),
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
            results = self.rag_service.search(state["requirements_text"], limit=5)
            context = [result.model_dump() for result in results]
            return {
                "rag_context": context,
                "cache_metrics": self._cache_metrics(),
                "trace": _trace(state, "retrieve_rag_context", f"{len(context)} results", started),
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
        recall = self.memory_service.recall(state["requirements"])
        return {
            "memory_recall": recall.model_dump(),
            "trace": _trace(state, "memory_recall", f"{recall.memory_hits} hits", started),
        }

    def _select_assets(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        requirements = state["requirements"]
        try:
            tower = self.registry.select_tower(
                requirements.tower_type,
                requirements.network_type,
                requirements.tower_height_m,
            )
            antenna = self.registry.select_asset(
                "antenna", requirements.network_type, requirements.tower_type
            )
            radio = (
                self.registry.select_asset(
                    "radio", requirements.network_type, requirements.tower_type
                )
                if requirements.include_rru
                else None
            )
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
        selected_assets = [asset for asset in [tower, antenna, radio] if asset is not None]
        return {
            "tower": tower,
            "antenna": antenna,
            "radio": radio,
            "selected_assets": selected_assets,
            "cache_metrics": self._cache_metrics(),
            "trace": _trace(
                state,
                "select_assets",
                ",".join(a.asset_id for a in selected_assets),
                started,
            ),
        }

    def _asset_fallback_handler(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        requirements = state["requirements"]
        warnings: list[ValidationIssue] = []
        try:
            tower = self.registry.select_tower_fallback(
                requirements.tower_type,
                requirements.network_type,
                requirements.tower_height_m,
            )
            warnings.append(
                ValidationIssue(
                    code="ASSET_FALLBACK_TOWER_SELECTED",
                    message=f"Fallback tower selected: {tower.asset_id}.",
                    severity="warning",
                )
            )
            tower_type = tower.compatible_tower_types[0] if tower.compatible_tower_types else None
            antenna = self.registry.select_asset_fallback(
                "antenna",
                requirements.network_type,
                tower_type,
            )
            warnings.append(
                ValidationIssue(
                    code="ASSET_FALLBACK_ANTENNA_SELECTED",
                    message=f"Fallback antenna selected: {antenna.asset_id}.",
                    severity="warning",
                )
            )
            radio = None
            if requirements.include_rru:
                radio = self.registry.select_asset_fallback(
                    "radio",
                    requirements.network_type,
                    tower_type,
                )
                warnings.append(
                    ValidationIssue(
                        code="ASSET_FALLBACK_RADIO_SELECTED",
                        message=f"Fallback radio selected: {radio.asset_id}.",
                        severity="warning",
                    )
                )
        except LookupError as exc:
            route = _route_event(state, "asset_fallback_handler", "asset_fallback")
            report = _failed_report(
                design_id=state["workflow_id"],
                code="ASSET_FALLBACK_FAILED",
                message=str(exc),
            )
            return {
                "asset_fallback_failed": True,
                "report": report,
                "route_history": route,
                "trace": _trace(
                    state,
                    "asset_fallback_handler",
                    "blocked:asset_fallback_failed",
                    started,
                    status="failed",
                    errors=[error.code for error in report.errors],
                    route="asset_fallback",
                    attempt=state.get("repair_attempts", 0),
                ),
            }
        selected_assets = [asset for asset in [tower, antenna, radio] if asset is not None]
        route = _route_event(
            state,
            "asset_fallback_handler",
            "asset_fallback",
            events=[warning.model_dump() for warning in warnings],
        )
        return {
            "tower": tower,
            "antenna": antenna,
            "radio": radio,
            "selected_assets": selected_assets,
            "asset_fallback_failed": False,
            "asset_fallback_warnings": warnings,
            "cache_metrics": self._cache_metrics(),
            "route_history": route,
            "trace": _trace(
                state,
                "asset_fallback_handler",
                ",".join(asset.asset_id for asset in selected_assets),
                started,
                warnings=[warning.code for warning in warnings],
                route="asset_fallback",
                attempt=state.get("repair_attempts", 0),
            ),
        }

    def _validate_requirements(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = self.rule_engine.validate_requirements(
            state["requirements"], state["selected_assets"]
        )
        if state.get("asset_fallback_warnings"):
            report = report.model_copy(
                update={"warnings": [*report.warnings, *state["asset_fallback_warnings"]]}
            )
        return {
            "requirement_report": report,
            "report": report,
            "trace": _trace(
                state,
                "validate_requirements",
                report.status,
                started,
                status=report.status,
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

    def _plan_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        scene = self.scene_planner.build_scene_spec(
            workflow_id=state["workflow_id"],
            requirements=state["requirements"],
            tower=state["tower"],
            antenna=state["antenna"],
            radio=state["radio"],
        )
        return {
            "scene": scene,
            "scene_spec_hash": scene_spec_hash(scene),
            "trace": _trace(state, "plan_scene", scene.scene_id, started),
        }

    def _validate_scene(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        report = validate_scene_spec(state["scene"], self.registry.list_assets())
        merged = _merge_reports(state["scene"].scene_id, [state["requirement_report"], report])
        return {
            "scene_report": report,
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
        gate = evaluate_pre_blender_gate(
            requirements=state.get("requirements"),
            requirement_report=state.get("requirement_report"),
            scene=state.get("scene"),
            scene_report=state.get("scene_report"),
            selected_assets=state.get("selected_assets", []),
            all_assets=self.registry.list_assets(),
            repair_attempts=state.get("repair_attempts", 0),
            max_repair_attempts=state.get("max_repair_attempts", 2),
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
                time.perf_counter() - (gate.duration_ms / 1000),
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
        repair_events = [
            event.model_dump() for event in state["requirements"].repair_events if event.success
        ]
        if repair_events and report.status == "passed" and not state.get("scene_repair_recorded"):
            route = _route_event(
                state,
                "scene_repair_handler",
                "scene_repair",
                attempt=attempt,
                events=repair_events,
            )
            return {
                "repair_attempts": attempt,
                "scene_repair_recorded": True,
                "report": report,
                "route_history": route,
                "trace": _trace(
                    state,
                    "scene_repair_handler",
                    f"repaired:{len(repair_events)} events",
                    started,
                    warnings=[event["warning_code"] for event in repair_events],
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
                "attempted:no_mutation_foundation",
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
        return {
            "generation": generation,
            "trace": _trace(
                state,
                "generate_blender",
                generation.mode,
                started,
                status="passed" if generation.status in {"generated", "fallback"} else "failed",
                errors=[generation.error] if generation.error else [],
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
        )
        qa_report = self.qa.validate(
            state["scene"],
            generation,
            glb_inspection,
            preview_inspection,
            geometry_validation,
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
        gate = evaluate_post_blender_gate(
            generation=state.get("generation"),
            qa_report=state.get("qa_report"),
            glb_inspection=state.get("glb_inspection"),
            preview_inspection=state.get("preview_inspection"),
            geometry_validation=state.get("geometry_validation"),
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
                time.perf_counter() - (gate.duration_ms / 1000),
                status="passed" if gate.passed else "failed",
                warnings=gate.warnings,
                errors=gate.critical_errors,
                route=None if gate.passed else "quality_gate_failed",
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


def _extraction_route(state: WorkflowState) -> str:
    return "continue" if state.get("requirements") is not None else "missing_data"


def _asset_route(state: WorkflowState) -> str:
    return "asset_fallback" if state.get("asset_error") else "continue"


def _asset_fallback_route(state: WorkflowState) -> str:
    return "blocked" if state.get("asset_fallback_failed") else "continue"


def _requirements_route(state: WorkflowState) -> str:
    return "continue" if state["requirement_report"].status == "passed" else "rule_violation"


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
    if generation.status != "generated" or generation.mode != "real_blender":
        return "blender_failure"
    return "continue"


def _pre_blender_gate_route(state: WorkflowState) -> str:
    return "continue" if state["pre_blender_gate"].passed else "quality_gate_failed"


def _post_blender_gate_route(state: WorkflowState) -> str:
    return "continue" if state["post_blender_gate"].passed else "quality_gate_failed"


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
) -> list[dict]:
    step = AgentStepTrace(
        node=node,
        status=status,
        detail=detail,
        duration_ms=_duration_ms(started),
        warnings=warnings or [],
        errors=errors or [],
        route=route,
        attempt=attempt,
    )
    return state.get("trace", []) + [step.model_dump()]


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
    score = sum(1 for passed in checks.values() if passed) / len(checks)
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
                message=f"Quality gate failed: {gate.stage}.{error}",
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
    status = "completed" if report and report.status == "passed" else "failed"
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
        generation=state.get("generation"),
        rag_context=state.get("rag_context", []),
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
    )


def _workflow_metrics(
    state: dict[str, Any],
    status: str,
) -> dict[str, int | float | str | bool | None]:
    generation: GenerationResult | None = state.get("generation")
    qa_report: ValidationReport | None = state.get("qa_report")
    memory_recall = state.get("memory_recall") or {}
    trace = state.get("trace", [])
    artifact_size_bytes = 0
    metrics: dict[str, int | float | str | bool | None] = {
        "status": status,
        "total_workflow_duration_ms": state.get("total_duration_ms", 0),
        "total_duration_ms": state.get("total_duration_ms", 0),
        "trace_steps": len(trace),
        "rag_context_count": len(state.get("rag_context", [])),
        "memory_hits": memory_recall.get("memory_hits", 0),
        "memory_context_count": memory_recall.get("memory_context_count", 0),
        "rag_duration_ms": _duration_for_nodes(trace, {"retrieve_rag_context"}),
        "planning_duration_ms": _duration_for_nodes(
            trace,
            {
                "select_assets",
                "validate_requirements",
                "plan_scene",
                "validate_scene",
                "scene_repair_handler",
                "rule_violation_handler",
                "asset_fallback_handler",
            },
        ),
        "blender_duration_ms": generation.duration_ms
        if generation
        else _duration_for_nodes(trace, {"generate_blender", "blender_failure_handler"}),
        "qa_duration_ms": _duration_for_nodes(trace, {"qa_generation", "qa_failure_handler"}),
        "memory_duration_ms": _duration_for_nodes(trace, {"memory_recall", "memory_writeback"}),
        "qa_score": qa_report.score if qa_report else None,
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
