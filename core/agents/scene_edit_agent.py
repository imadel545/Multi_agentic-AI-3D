import json
import logging
import re
import unicodedata
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from core.agents.geometry_program_planner import GeometryProgramPlanner
from core.contracts.adaptation import (
    AdaptationDecision,
    AdaptationOperation,
    AssetAdaptationPlan,
    SceneAdaptationCapabilities,
)
from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.validation import ValidationReport
from core.llm.groq import GroqStructuredClient
from core.llm.groq_policy import GroqRequestPolicy
from core.services.adaptation_capabilities import AdaptationCapabilityService
from core.services.dependent_constraints import with_dependent_operations
from core.services.patch_applier import PatchApplier

logger = logging.getLogger(__name__)


class AdaptationGraphState(TypedDict, total=False):
    workflow_id: str
    scene: SceneSpec
    edit_prompt: str
    capabilities: SceneAdaptationCapabilities
    allowed_paths: list[str]
    plan: AssetAdaptationPlan
    patch: ScenePatch
    patched_scene: SceneSpec
    validation_report: ValidationReport
    planner_provider: str
    planner_fallback_used: bool
    planner_fallback_reason: str | None
    graph_trace: list[dict[str, Any]]


class SceneEditAgent:
    def __init__(
        self,
        groq_client: GroqStructuredClient | None = None,
        capability_service: AdaptationCapabilityService | None = None,
        checkpoint_saver: Any | None = None,
        geometry_program_planner: GeometryProgramPlanner | None = None,
    ) -> None:
        self.groq = groq_client
        self.capability_service = capability_service
        self.patch_applier = PatchApplier()
        self.checkpoint_saver = checkpoint_saver
        self.geometry_program_planner = geometry_program_planner
        self.graph = self._build_graph() if capability_service is not None else None

    def _build_graph(self):
        graph = StateGraph(AdaptationGraphState)
        graph.add_node("discover_capabilities", self._discover_capabilities)
        graph.add_node("plan_adaptation", self._plan_adaptation)
        graph.add_node("validate_adaptation", self._validate_adaptation)
        graph.add_node("execute_adaptation", self._execute_adaptation)
        graph.add_edge(START, "discover_capabilities")
        graph.add_edge("discover_capabilities", "plan_adaptation")
        graph.add_edge("plan_adaptation", "validate_adaptation")
        graph.add_edge("validate_adaptation", "execute_adaptation")
        graph.add_edge("execute_adaptation", END)
        return graph.compile(checkpointer=self.checkpoint_saver)

    def create_adaptation(
        self,
        workflow_id: str,
        scene: SceneSpec,
        edit_prompt: str,
        *,
        allowed_paths: set[str] | None = None,
    ) -> AdaptationDecision:
        if self.graph is None or self.capability_service is None:
            raise RuntimeError("adaptation capability service is unavailable")
        geometry_index = (
            next(
                (
                    int(path.split("/")[2])
                    for path in allowed_paths
                    if re.fullmatch(r"/geometry_programs/\d+", path)
                ),
                None,
            )
            if allowed_paths is not None
            else self._geometry_program_index_for_prompt(scene, edit_prompt)
        )
        if geometry_index is not None:
            if self.geometry_program_planner is None:
                raise RuntimeError(
                    "La révision du composant généré exige le spécialiste GeometryProgram."
                )
            return self._create_geometry_program_adaptation(
                workflow_id,
                scene,
                edit_prompt,
                geometry_index,
                allowed_paths=allowed_paths,
            )
        thread_id = f"{workflow_id}:adaptation:{uuid.uuid4().hex}"
        try:
            state = self.graph.invoke(
                {
                    "workflow_id": workflow_id,
                    "scene": scene,
                    "edit_prompt": edit_prompt,
                    "graph_trace": [],
                    **(
                        {"allowed_paths": sorted(allowed_paths)}
                        if allowed_paths is not None
                        else {}
                    ),
                },
                config={"configurable": {"thread_id": thread_id}},
            )
        finally:
            if self.checkpoint_saver is not None:
                try:
                    self.checkpoint_saver.delete_thread(thread_id)
                except Exception:
                    logger.warning(
                        "Failed to remove terminal adaptation checkpoints for %s.",
                        workflow_id,
                        exc_info=True,
                    )
        return AdaptationDecision(
            workflow_id=workflow_id,
            prompt=edit_prompt,
            capabilities=state["capabilities"],
            plan=state["plan"],
            patch=state["patch"],
            patched_scene=state["patched_scene"],
            validation_report=state["validation_report"],
            planner_provider=state["planner_provider"],
            planner_fallback_used=state["planner_fallback_used"],
            planner_fallback_reason=state.get("planner_fallback_reason"),
            graph_trace=state["graph_trace"],
        )

    def _geometry_program_index_for_prompt(
        self,
        scene: SceneSpec,
        edit_prompt: str,
    ) -> int | None:
        editable_indices = [
            index
            for index, program in enumerate(scene.geometry_programs)
            if not any(node.kind == "exact_asset" for node in program.nodes)
        ]
        if not editable_indices:
            return None
        semantic_match = _semantic_geometry_program_index(scene, edit_prompt)
        if semantic_match in editable_indices:
            return semantic_match
        program_ids = [scene.geometry_programs[index].program_id for index in editable_indices]
        if self.groq is not None:
            try:
                raw = self.groq.request_json(
                    {
                        "model": self.groq.model,
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Route one 3D edit. Select regenerate_geometry_program only "
                                    "when the user targets one of the listed generated components. "
                                    "Use standard_adaptation for tower, antenna, RF, visibility or "
                                    "other declared SceneSpec edits. Never invent an ID."
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "edit_prompt": edit_prompt,
                                        "generated_components": [
                                            {
                                                "program_id": program.program_id,
                                                "semantic_role": program.semantic_role,
                                                "node_ids": [
                                                    node.node_id for node in program.nodes
                                                ],
                                            }
                                            for program in (
                                                scene.geometry_programs[index]
                                                for index in editable_indices
                                            )
                                        ],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        ],
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "geometry_revision_route",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "action": {
                                            "type": "string",
                                            "enum": [
                                                "regenerate_geometry_program",
                                                "standard_adaptation",
                                            ],
                                        },
                                        "program_id": {
                                            "anyOf": [
                                                {"type": "string", "enum": program_ids},
                                                {"type": "null"},
                                            ]
                                        },
                                        "reason": {
                                            "type": "string",
                                            "maxLength": 240,
                                        },
                                    },
                                    "required": ["action", "program_id", "reason"],
                                },
                            },
                        },
                    },
                    policy=GroqRequestPolicy(
                        capability="geometry_revision_routing",
                        reasoning_effort="low",
                        max_completion_tokens=512,
                    ),
                )
                if raw.get("action") != "regenerate_geometry_program":
                    return None
                selected = raw.get("program_id")
                return (
                    editable_indices[program_ids.index(selected)]
                    if selected in program_ids
                    else None
                )
            except Exception:
                logger.warning(
                    "Geometry-program revision routing failed; using semantic matching.",
                    exc_info=True,
                )
        return None

    def _create_geometry_program_adaptation(
        self,
        workflow_id: str,
        scene: SceneSpec,
        edit_prompt: str,
        geometry_index: int,
        *,
        allowed_paths: set[str] | None = None,
    ) -> AdaptationDecision:
        if self.capability_service is None or self.geometry_program_planner is None:
            raise RuntimeError("geometry-program adaptation is unavailable")
        current = scene.geometry_programs[geometry_index]
        path = f"/geometry_programs/{geometry_index}"
        capabilities = self.capability_service.resolve(scene)
        if allowed_paths is not None:
            capabilities = capabilities.model_copy(
                update={
                    "capabilities": [
                        item for item in capabilities.capabilities if item.path in allowed_paths
                    ]
                }
            )
        capability = next(
            (item for item in capabilities.capabilities if item.path == path),
            None,
        )
        if capability is None:
            raise RuntimeError("geometry-program capability was not resolved")
        request_id = re.sub(r"\.llm_v[12]$", "", current.program_id)
        source_description_available = (
            current.source_description is not None
            and current.source_description_origin != "legacy_unavailable"
        )
        original_intent = (
            current.source_description
            if source_description_available
            else "Intention source indisponible pour ce composant historique."
        )
        revised = self.geometry_program_planner.plan(
            prompt=(
                "Réviser le composant existant selon la demande utilisateur. "
                "Conserver son rôle, sa quantité et les caractéristiques non modifiées. "
                f"Demande de révision: {edit_prompt}"
            ),
            semantic_role=current.semantic_role,
            request_id=request_id,
            quantity=current.requested_quantity,
            source_description=original_intent,
            source_description_origin=(
                "revision_preserved" if source_description_available else "legacy_unavailable"
            ),
            placement_context=current.placement_context,
            maximum_dimensions_m=current.maximum_dimensions_m,
            schema_version=current.schema_version,
            design_context={
                "operation": "revision",
                "current_geometry_program": current.model_dump(mode="json"),
                "scene_network_type": scene.network_type,
                "scene_tower_height_m": scene.tower.height_m if scene.tower is not None else None,
                "design_domain": scene.design_domain,
                "site_coordinate_frame": "meters, Z-up, tower center at origin",
            },
        )
        operation = AdaptationOperation(
            capability_id=capability.capability_id,
            path=path,
            value=revised.model_dump(mode="json"),
            execution_tool="geometry_program_rebuild",
            rationale="Composant ciblé régénéré sous le contrat GeometryProgram validé.",
        )
        plan = AssetAdaptationPlan(
            edit_description=edit_prompt,
            operations=[operation],
        )
        self.capability_service.validate_plan(capabilities, plan)
        patch = _patch_from_plan(
            plan,
            edit_llm_provider=f"groq:{revised.generator_model}",
            edit_llm_fallback_used=False,
            capability_catalog_hash=capabilities.catalog_hash,
            adaptation_tools=["geometry_program_rebuild"],
        )
        patched_scene, report = self.patch_applier.apply(
            scene,
            patch,
            allowed_paths=capabilities.allowed_paths,
        )
        if report.status == "failed":
            detail = "; ".join(issue.message for issue in report.errors)
            raise ValueError(f"GeometryProgram revision failed SceneSpec validation: {detail}")
        return AdaptationDecision(
            workflow_id=workflow_id,
            prompt=edit_prompt,
            capabilities=capabilities,
            plan=plan,
            patch=patch,
            patched_scene=patched_scene,
            validation_report=report,
            planner_provider=f"groq:{revised.generator_model}",
            planner_fallback_used=False,
            planner_fallback_reason=None,
            graph_trace=[
                {
                    "node": "discover_capabilities",
                    "status": "completed",
                    "capability_count": len(capabilities.capabilities),
                    "catalog_hash": capabilities.catalog_hash,
                },
                {
                    "node": "plan_geometry_program_revision",
                    "status": "completed",
                    "provider": revised.generator_model,
                    "structured_output_mode": revised.structured_output_mode,
                    "program_id": revised.program_id,
                },
                {
                    "node": "validate_adaptation",
                    "status": "completed",
                    "validated_paths": [path],
                },
                {
                    "node": "execute_adaptation",
                    "status": "completed",
                    "tools": ["geometry_program_rebuild"],
                    "scene_validation": report.status,
                },
            ],
        )

    def create_patch(
        self,
        workflow_id: str,
        scene: SceneSpec,
        edit_prompt: str,
    ) -> ScenePatch:
        if self.graph is not None:
            return self.create_adaptation(workflow_id, scene, edit_prompt).patch
        fallback_reason = "groq_edit_client_unavailable"
        if self.groq is not None:
            try:
                return with_dependent_operations(scene, self._llm_patch(scene, edit_prompt))
            except Exception as exc:
                fallback_reason = f"groq_edit_failed:{type(exc).__name__}"
                logger.warning(
                    "LLM scene edit failed for workflow %s; falling back to deterministic parser.",
                    workflow_id,
                    exc_info=True,
                )
        return with_dependent_operations(
            scene, self._fallback_patch(scene, edit_prompt, fallback_reason=fallback_reason)
        )

    def _discover_capabilities(self, state: AdaptationGraphState) -> dict[str, Any]:
        if self.capability_service is None:
            raise RuntimeError("adaptation capability service is unavailable")
        capabilities = self.capability_service.resolve(state["scene"])
        if "allowed_paths" in state:
            capabilities = capabilities.model_copy(
                update={
                    "capabilities": [
                        item
                        for item in capabilities.capabilities
                        if item.path in state["allowed_paths"]
                    ]
                }
            )
            if not capabilities.capabilities:
                raise ValueError("La sélection ne dispose pas de modification prise en charge.")
        return {
            "capabilities": capabilities,
            "graph_trace": [
                *state.get("graph_trace", []),
                {
                    "node": "discover_capabilities",
                    "status": "completed",
                    "capability_count": len(capabilities.capabilities),
                    "catalog_hash": capabilities.catalog_hash,
                },
            ],
        }

    def _plan_adaptation(self, state: AdaptationGraphState) -> dict[str, Any]:
        fallback_reason = "groq_edit_client_unavailable"
        provider = "deterministic_fallback"
        fallback_used = True
        if self.groq is not None:
            try:
                plan = self._llm_adaptation_plan(
                    state["scene"], state["edit_prompt"], state["capabilities"]
                )
                if self.capability_service is None:
                    raise RuntimeError("adaptation capability service is unavailable")
                self.capability_service.validate_plan(state["capabilities"], plan)
                _validate_patch_alignment(
                    state["scene"],
                    state["edit_prompt"],
                    _patch_from_plan(plan),
                )
                provider = f"groq:{self.groq.model}"
                fallback_used = False
                fallback_reason = None
            except Exception as exc:
                fallback_reason = f"groq_edit_failed:{type(exc).__name__}"
                logger.warning(
                    "LLM adaptation planning failed for workflow %s; using bounded parser.",
                    state["workflow_id"],
                    exc_info=True,
                )
                patch = self._fallback_patch(
                    state["scene"],
                    state["edit_prompt"],
                    fallback_reason=fallback_reason,
                    capabilities=state["capabilities"],
                )
                plan = _plan_from_patch(patch, state["capabilities"])
        else:
            patch = self._fallback_patch(
                state["scene"],
                state["edit_prompt"],
                fallback_reason=fallback_reason,
                capabilities=state["capabilities"],
            )
            plan = _plan_from_patch(patch, state["capabilities"])
        return {
            "plan": plan,
            "planner_provider": provider,
            "planner_fallback_used": fallback_used,
            "planner_fallback_reason": fallback_reason,
            "graph_trace": [
                *state.get("graph_trace", []),
                {
                    "node": "plan_adaptation",
                    "status": "completed",
                    "provider": provider,
                    "fallback_used": fallback_used,
                    "operation_count": len(plan.operations),
                },
            ],
        }

    def _validate_adaptation(self, state: AdaptationGraphState) -> dict[str, Any]:
        if self.capability_service is None:
            raise RuntimeError("adaptation capability service is unavailable")
        plan = state["plan"]
        self.capability_service.validate_plan(state["capabilities"], plan)
        patch = _patch_from_plan(
            plan,
            edit_llm_provider=state["planner_provider"],
            edit_llm_fallback_used=state["planner_fallback_used"],
            edit_llm_fallback_reason=state.get("planner_fallback_reason"),
            capability_catalog_hash=state["capabilities"].catalog_hash,
            adaptation_tools=list(
                dict.fromkeys(operation.execution_tool for operation in plan.operations)
            ),
        )
        _validate_patch_alignment(state["scene"], state["edit_prompt"], patch)
        patch = with_dependent_operations(
            state["scene"],
            patch,
            allowed_paths=state["capabilities"].allowed_paths,
        )
        return {
            "patch": patch,
            "graph_trace": [
                *state.get("graph_trace", []),
                {
                    "node": "validate_adaptation",
                    "status": "completed",
                    "validated_paths": [operation.path for operation in plan.operations],
                },
            ],
        }

    def _execute_adaptation(self, state: AdaptationGraphState) -> dict[str, Any]:
        patched_scene, report = self.patch_applier.apply(
            state["scene"],
            state["patch"],
            allowed_paths=state["capabilities"].allowed_paths,
        )
        if report.status == "failed":
            detail = "; ".join(issue.message for issue in report.errors)
            raise ValueError(f"Adaptation plan failed SceneSpec validation: {detail}")
        patched_scene = _mark_user_defined_accessory_positions(
            patched_scene,
            state["patch"],
        )
        return {
            "patched_scene": patched_scene,
            "validation_report": report,
            "graph_trace": [
                *state.get("graph_trace", []),
                {
                    "node": "execute_adaptation",
                    "status": "completed",
                    "tools": state["patch"].adaptation_tools,
                    "scene_validation": report.status,
                },
            ],
        }

    def _llm_adaptation_plan(
        self,
        scene: SceneSpec,
        edit_prompt: str,
        capabilities: SceneAdaptationCapabilities,
    ) -> AssetAdaptationPlan:
        if self.groq is None:
            raise RuntimeError("Groq edit client is unavailable")
        capability_payload = [
            capability.model_dump(mode="json") for capability in capabilities.capabilities
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the decision planner for a verified telecom 3D adaptation system. "
                    "Select only declared capabilities. Never generate Blender code, invent a "
                    "path, or claim an unsupported mesh modification. Every numeric value must "
                    "come from the user request. If part of the request is unsupported, record "
                    "it in unsupported_requests and plan only the supported part. Use explicit "
                    "sector and accessory indices from the capability list. Encode every target "
                    "value as a canonical JSON literal inside value_json, for example true, 34, "
                    "or [1.2, 1.2, 1.2]."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current SceneSpec:\n{scene.model_dump_json()}\n\n"
                    "Resolved executable capabilities:\n"
                    f"{json.dumps(capability_payload, ensure_ascii=False)}\n\n"
                    f"Requested adaptation:\n{edit_prompt}"
                ),
            },
        ]
        payload = {
            "model": self.groq.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "telecom_asset_adaptation_plan",
                    "strict": True,
                    "schema": _adaptation_plan_schema(capabilities),
                },
            },
        }
        raw = self.groq._post_raw(payload)
        return AssetAdaptationPlan.model_validate(_normalize_llm_adaptation_payload(raw))

    def _llm_patch(self, scene: SceneSpec, edit_prompt: str) -> ScenePatch:
        scene_json = json.dumps(scene.model_dump(mode="json"), indent=2, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a telecom scene editing assistant. "
                    "Given a SceneSpec JSON and a user edit prompt (in French or English), "
                    "produce a JSON object containing an array of patch operations. "
                    "Allowed paths: /tower/height_m, /tower/characteristics/*, "
                    "/sectors/*/azimuth_deg, /sectors/*/install_height_m, "
                    "/sectors/*/mechanical_tilt_deg, /sectors/*/electrical_tilt_deg, "
                    "/sectors/*/beamwidth_deg, /sectors/*/include_cable, "
                    "/sectors/*/include_label, /visual_elements/*. "
                    "Operations: replace, add, remove. "
                    "Return ONLY the JSON object with keys: edit_description, operations."
                ),
            },
            {
                "role": "user",
                "content": f"SceneSpec:\n{scene_json}\n\nEdit prompt:\n{edit_prompt}",
            },
        ]
        payload = {
            "model": self.groq.model if self.groq else "openai/gpt-oss-120b",
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        raw = self.groq._post_raw(payload)
        operations = [PatchOperation.model_validate(op) for op in raw.get("operations", [])]
        patch = ScenePatch(
            edit_description=raw.get("edit_description", edit_prompt),
            operations=operations,
            edit_llm_provider="groq",
            edit_llm_fallback_used=False,
        )
        _validate_patch_alignment(scene, edit_prompt, patch)
        return patch

    def _fallback_patch(
        self,
        scene: SceneSpec,
        edit_prompt: str,
        *,
        fallback_reason: str,
        capabilities: SceneAdaptationCapabilities | None = None,
    ) -> ScenePatch:
        if capabilities is not None:
            from core.services.exact_asset_edit import fallback_rigid_patch

            rigid_patch = fallback_rigid_patch(edit_prompt, capabilities, fallback_reason)
            if rigid_patch is not None:
                return rigid_patch
        text = edit_prompt.lower()
        operations: list[PatchOperation] = []

        # Height changes
        height_match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
        tower_terms = ("tour", "tower", "pylône", "pylone")
        antenna_height_requested = any(
            term in text for term in ("antenne", "antenna", "hba")
        ) and not any(term in text for term in ("gps", "gnss"))
        if height_match and (
            any(term in text for term in ("hauteur", "height", *tower_terms))
            or antenna_height_requested
        ):
            val = float(height_match.group(1))
            if any(term in text for term in tower_terms):
                operations.append(PatchOperation(op="replace", path="/tower/height_m", value=val))
            elif antenna_height_requested:
                requested_sector = self._extract_sector_index(text)
                indices = (
                    [requested_sector]
                    if requested_sector is not None
                    else range(len(scene.sectors))
                )
                for idx in indices:
                    if not 0 <= idx < len(scene.sectors):
                        continue
                    operations.append(
                        PatchOperation(
                            op="replace", path=f"/sectors/{idx}/install_height_m", value=val
                        )
                    )

        # Azimuth changes
        azimuth_match = _target_value_match(
            text,
            ("azimut", "azimuth", "orientation", "diriger", "oriente"),
        )
        if azimuth_match and any(
            k in text for k in ("azimut", "azimuth", "orientation", "diriger", "oriente")
        ):
            val = float(azimuth_match.group(1))
            sector_idx = self._extract_sector_index(text)
            if sector_idx is not None and sector_idx < len(scene.sectors):
                operations.append(
                    PatchOperation(
                        op="replace", path=f"/sectors/{sector_idx}/azimuth_deg", value=val
                    )
                )

        # Tilt changes
        tilt_match = _target_value_match(
            text,
            (
                "tilt",
                "inclinaison",
                "incline",
                "incliner",
                "mécanique",
                "mecanique",
                "électrique",
                "electrique",
            ),
        )
        if tilt_match and any(
            k in text
            for k in (
                "tilt",
                "inclinaison",
                "incline",
                "incliner",
                "mécanique",
                "mecanique",
                "électrique",
                "electrique",
            )
        ):
            val = float(tilt_match.group(1))
            sector_idx = self._extract_sector_index(text)
            path = "/sectors/{idx}/mechanical_tilt_deg"
            if "électrique" in text or "electrical" in text:
                path = "/sectors/{idx}/electrical_tilt_deg"
            if sector_idx is not None and sector_idx < len(scene.sectors):
                operations.append(
                    PatchOperation(op="replace", path=path.format(idx=sector_idx), value=val)
                )

        # RRU placement changes. The parser only writes profile fields declared by
        # the active radio manifest; capability validation remains the authority.
        radio_terms = ("rru", "radio", "remote radio")
        vertical_terms = (
            "décalage vertical",
            "decalage vertical",
            "vertical offset",
            "distance verticale",
        )
        radial_terms = (
            "retrait radial",
            "radial inset",
            "distance radiale",
            "rapproche",
        )
        if any(term in text for term in radio_terms):
            radio_path_field = None
            match = None
            if any(term in text for term in vertical_terms):
                radio_path_field = "vertical_offset_m"
                match = _target_value_match(text, vertical_terms)
            elif any(term in text for term in radial_terms):
                radio_path_field = "radial_inset_m"
                match = _target_value_match(text, radial_terms)
            if radio_path_field is not None and match is not None:
                value = float(match.group(1).replace(",", "."))
                requested_sector = self._extract_sector_index(text)
                candidate_indices = (
                    [requested_sector]
                    if requested_sector is not None
                    else list(range(len(scene.sectors)))
                )
                for index in candidate_indices:
                    if index is None or index < 0 or index >= len(scene.sectors):
                        continue
                    sector = scene.sectors[index]
                    if sector.radio_asset_id is None or sector.radio_geometry_profile is None:
                        continue
                    operations.append(
                        PatchOperation(
                            op="replace",
                            path=(f"/sectors/{index}/radio_geometry_profile/{radio_path_field}"),
                            value=value,
                        )
                    )

        # Visual elements toggles
        transform_terms = (
            "taille",
            "échelle",
            "echelle",
            "scale",
            "position",
            "rotation",
            "déplace",
            "deplace",
            "move",
        )
        accessory_transform_requested = any(term in text for term in transform_terms)
        if any(k in text for k in ("gps", "gnss")) and accessory_transform_requested:
            scale_terms = ("taille", "échelle", "echelle", "scale", "agrandis", "réduis")
            if any(term in text for term in scale_terms):
                values = [
                    float(value.replace(",", "."))
                    for value in re.findall(r"-?\d+(?:[.,]\d+)?", text)
                ]
                gps_index = next(
                    (
                        index
                        for index, accessory in enumerate(scene.accessory_assets)
                        if accessory.asset_type == "gps"
                    ),
                    None,
                )
                if gps_index is not None and len(values) >= 3:
                    operations.append(
                        PatchOperation(
                            op="replace",
                            path=f"/accessory_assets/{gps_index}/scale",
                            value=values[-3:],
                        )
                    )
        elif any(k in text for k in ("gps", "gnss")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(op="replace", path="/visual_elements/include_gps_antenna", value=val)
            )
        normalized_text = _normalized_words(edit_prompt)
        if _contains_any_phrase(normalized_text, _POWER_CABINET_TERMS):
            val = not _contains_any_phrase(normalized_text, _REMOVAL_MARKERS)
            operations.append(
                PatchOperation(
                    op="replace", path="/visual_elements/include_power_cabinet", value=val
                )
            )
        if _contains_any_phrase(normalized_text, _ARROW_NOUN_TERMS):
            operations.append(
                PatchOperation(
                    op="replace",
                    path="/visual_elements/include_azimuth_arrows",
                    value=not _contains_any_phrase(normalized_text, _REMOVAL_MARKERS),
                )
            )
        if _contains_any_phrase(normalized_text, _LABEL_TERMS):
            operations.append(
                PatchOperation(
                    op="replace",
                    path="/visual_elements/include_labels",
                    value=not _contains_any_phrase(normalized_text, _REMOVAL_MARKERS),
                )
            )
        if any(k in text for k in ("câble", "cable")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            for idx in range(len(scene.sectors)):
                operations.append(
                    PatchOperation(op="replace", path=f"/sectors/{idx}/include_cable", value=val)
                )
        if any(k in text for k in ("beam", "faisceau")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(
                    op="replace", path="/visual_elements/include_sector_beams", value=val
                )
            )

        if not operations:
            raise ValueError(f"Fallback patch could not interpret prompt: {edit_prompt}")

        return ScenePatch(
            edit_description=edit_prompt,
            operations=operations,
            edit_llm_provider="deterministic_fallback",
            edit_llm_fallback_used=True,
            edit_llm_fallback_reason=fallback_reason,
        )

    @staticmethod
    def _extract_sector_index(text: str) -> int | None:
        match = re.search(r"secteur\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        match = re.search(r"sector\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        match = re.search(r"s\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        return None


def _plan_from_patch(
    patch: ScenePatch,
    capabilities: SceneAdaptationCapabilities,
) -> AssetAdaptationPlan:
    by_path = {capability.path: capability for capability in capabilities.capabilities}
    operations = []
    for operation in patch.operations:
        capability = by_path.get(operation.path)
        if capability is None:
            raise ValueError(f"Fallback requested an undeclared capability: {operation.path}")
        operations.append(
            AdaptationOperation(
                op="replace",
                capability_id=capability.capability_id,
                path=capability.path,
                value=operation.value,
                execution_tool=capability.execution_tool,
                rationale="Valeur explicitement extraite de la demande utilisateur.",
            )
        )
    return AssetAdaptationPlan(
        edit_description=patch.edit_description,
        operations=operations,
        unsupported_requests=[],
        assumptions=[],
    )


def _mark_user_defined_accessory_positions(
    scene: SceneSpec,
    patch: ScenePatch,
) -> SceneSpec:
    user_position_indices = {
        int(parts[2])
        for operation in patch.operations
        if operation.path.startswith("/accessory_assets/")
        and (parts := operation.path.split("/"))[2].isdigit()
        and parts[-1] == "position"
    }
    if not user_position_indices:
        return scene
    accessories = [
        accessory.model_copy(update={"placement_policy": "user_defined"})
        if index in user_position_indices
        else accessory
        for index, accessory in enumerate(scene.accessory_assets)
    ]
    return scene.model_copy(update={"accessory_assets": accessories})


def _normalize_llm_adaptation_payload(raw: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(raw)
    operations = []
    for item in candidate.get("operations", []):
        if not isinstance(item, dict):
            operations.append(item)
            continue
        operation = dict(item)
        if "value_json" in operation:
            raw_value = operation.pop("value_json")
            if not isinstance(raw_value, str):
                raise ValueError("value_json must be a string")
            operation["value"] = json.loads(raw_value)
        operations.append(operation)
    candidate["operations"] = operations
    return candidate


def _patch_from_plan(
    plan: AssetAdaptationPlan,
    **metadata: Any,
) -> ScenePatch:
    return ScenePatch(
        edit_description=plan.edit_description,
        operations=[
            PatchOperation(op=operation.op, path=operation.path, value=operation.value)
            for operation in plan.operations
        ],
        unsupported_requests=plan.unsupported_requests,
        assumptions=plan.assumptions,
        **metadata,
    )


def _adaptation_plan_schema(capabilities: SceneAdaptationCapabilities) -> dict[str, Any]:
    capability_ids = [capability.capability_id for capability in capabilities.capabilities]
    paths = [capability.path for capability in capabilities.capabilities]
    tools = sorted({capability.execution_tool for capability in capabilities.capabilities})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "edit_description": {"type": "string", "minLength": 1, "maxLength": 400},
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 32,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "op": {"type": "string", "enum": ["replace"]},
                        "capability_id": {"type": "string", "enum": capability_ids},
                        "path": {"type": "string", "enum": paths},
                        "value_json": {"type": "string", "minLength": 1, "maxLength": 240},
                        "execution_tool": {"type": "string", "enum": tools},
                        "rationale": {"type": "string", "minLength": 1, "maxLength": 240},
                    },
                    "required": [
                        "op",
                        "capability_id",
                        "path",
                        "value_json",
                        "execution_tool",
                        "rationale",
                    ],
                },
            },
            "unsupported_requests": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 16,
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 16,
            },
        },
        "required": ["edit_description", "operations", "unsupported_requests", "assumptions"],
    }


_COLOR_TERMS: tuple[str, ...] = (
    "couleur",
    "color",
    "colour",
    "peins",
    "peint",
    "peindre",
    "repeins",
    "teinte",
    "rouge",
    "bleu",
    "vert",
    "blanc",
    "noir",
    "gris",
    "jaune",
    "orange",
    "violet",
    "rose",
    "marron",
    "red",
    "blue",
    "green",
    "white",
    "black",
    "grey",
    "gray",
    "yellow",
    "ral",
    "#",
)

_POWER_CABINET_TERMS: tuple[str, ...] = (
    "power cabinet",
    "armoire",
    "cabinet",
    "boîte alimentation",
    "boite alimentation",
    "boîtier alimentation",
    "boitier alimentation",
    "coffret alimentation",
)
_AZIMUTH_ARROW_TERMS: tuple[str, ...] = (
    "azimut",
    "azimuth",
    "flèche",
    "fleche",
    "flèches",
    "fleches",
    "arrow",
    "arrows",
)
_ARROW_NOUN_TERMS: tuple[str, ...] = (
    "flèche",
    "fleche",
    "flèches",
    "fleches",
    "arrow",
    "arrows",
)
_LABEL_TERMS: tuple[str, ...] = (
    "label",
    "labels",
    "étiquette",
    "etiquette",
    "étiquettes",
    "etiquettes",
)

_PATH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "/tower/height_m",
        (
            "hauteur",
            "height",
            "mets la tour",
            "met la tour",
            "tour à",
            "set tower to",
            "raccourcis pylône",
            "raccourcis pylone",
            "raccourcis le pylône",
            "raccourcis le pylone",
            "raccourcis la tour",
            "shorten tower",
        ),
    ),
    ("/tower/characteristics/structure", ("structure", "treillis", "lattice", "monopole")),
    ("/tower/characteristics/leg_count", ("jambe", "pied", "leg")),
    ("/tower/characteristics/base_width_m", ("largeur", "base", "width")),
    ("/tower/characteristics/top_width_m", ("largeur", "sommet", "top", "width")),
    ("/tower/characteristics/foundation_type", ("fondation", "dalle", "foundation", "base")),
    (
        "/tower/characteristics/has_platform",
        ("plateforme", "plateformes", "platform", "platforms"),
    ),
    (
        "/tower/characteristics/platform_count",
        ("plateforme", "plateformes", "platform", "platforms"),
    ),
    ("/tower/characteristics/has_ladder", ("échelle", "echelle", "ladder")),
    ("/tower/characteristics/has_lightning_rod", ("paratonnerre", "lightning")),
    ("/tower/characteristics/has_aviation_light", ("balisage", "aviation")),
    (
        "/tower/characteristics/paint_color_hex",
        _COLOR_TERMS,
    ),
    (
        "/tower/characteristics/material",
        (
            "matériau",
            "materiau",
            "material",
            "acier",
            "béton",
            "beton",
            "galvanis",
        ),
    ),
    ("/visual_elements/include_gps_antenna", ("gps", "gnss")),
    ("/visual_elements/include_power_cabinet", _POWER_CABINET_TERMS),
    ("/visual_elements/include_sector_beams", ("faisceau", "beam", "secteur")),
    ("/visual_elements/include_azimuth_arrows", _AZIMUTH_ARROW_TERMS),
    (
        "/visual_elements/include_height_markers",
        ("hauteur", "height", "marker", "repère", "repere"),
    ),
    ("/visual_elements/include_labels", _LABEL_TERMS),
)

_SECTOR_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "azimuth_deg": (
        "azimut",
        "azimuth",
        "orientation",
        "diriger",
        "oriente",
        "tourne",
        "tourner",
        "pivote",
        "rotate",
        "rotation",
        "vers le nord",
        "vers le sud",
        "vers l est",
        "vers l ouest",
    ),
    "install_height_m": (
        "hauteur",
        "height",
        "hba",
        "antenne à",
        "antenna to",
        "monte",
        "remonte",
        "baisse",
        "descend",
        "abaisse",
        "rehausse",
        "plus haut",
        "plus bas",
    ),
    "mechanical_tilt_deg": (
        "tilt",
        "inclinaison",
        "incline",
        "incliner",
        "mécanique",
        "mecanique",
    ),
    "electrical_tilt_deg": ("tilt", "inclinaison", "électrique", "electrique"),
    "beamwidth_deg": ("beamwidth", "ouverture", "faisceau", "beam"),
    "include_cable": ("câble", "cable"),
    "include_label": _LABEL_TERMS,
    "vertical_offset_m": (
        "décalage vertical",
        "decalage vertical",
        "vertical offset",
        "distance verticale",
        "baisse",
        "descend",
        "abaisse",
        "monte",
        "remonte",
        "plus bas",
        "plus haut",
    ),
    "radial_inset_m": (
        "retrait radial",
        "radial inset",
        "distance radiale",
        "rapproche",
    ),
}

_ACCESSORY_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "position": (
        "position",
        "déplace",
        "deplace",
        "move",
        "x",
        "y",
        "z",
        "rapproche",
        "éloigne",
        "eloigne",
        "recule",
        "avance",
        "décale",
        "decale",
    ),
    "rotation_deg": ("rotation", "tourne", "rotate", "orientation", "pivote"),
    "scale": (
        "taille",
        "échelle",
        "echelle",
        "scale",
        "agrandis",
        "agrandir",
        "réduis",
        "reduis",
        "réduire",
        "plus grand",
        "plus petit",
        "grossis",
        "dimension",
    ),
}


def _semantic_geometry_program_index(scene: SceneSpec, edit_prompt: str) -> int | None:
    normalized_prompt = _normalized_words(edit_prompt)
    prompt_tokens = set(normalized_prompt.split())
    ignored = {
        "component",
        "generated",
        "geometry",
        "program",
        "technical",
        "external",
        "llm",
    }
    matches: list[tuple[int, int]] = []
    for index, program in enumerate(scene.geometry_programs):
        identifiers = " ".join(
            [
                program.program_id,
                program.semantic_role,
                *[node.node_id for node in program.nodes],
            ]
        )
        tokens = {
            token
            for token in _normalized_words(identifiers).split()
            if len(token) >= 4 and token not in ignored
        }
        score = len(prompt_tokens & tokens)
        if score:
            matches.append((score, index))
    if not matches:
        return None
    matches.sort(reverse=True)
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return None
    return matches[0][1]


def _normalized_words(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


_DECREASE_MARKERS = (
    "diminue",
    "decrease",
    "reduit",
    "reduis",
    "lower",
    "baisse",
    "abaisse",
    "descend",
    "raccourci",
    "raccourcis",
    "raccourcit",
    "raccourcir",
    "plus bas",
    "plus court",
    "plus petit",
    "moins",
)
_INCREASE_MARKERS = (
    "augmente",
    "increase",
    "ajoute",
    "raise",
    "monte",
    "remonte",
    "rehausse",
    "allonge",
    "agrandi",
    "plus haut",
    "plus long",
    "plus grand",
    "hausse",
)
_REMOVAL_MARKERS = (
    "supprime",
    "retire",
    "enleve",
    "remove",
    "sans ",
    "masque",
    "cache",
    "desactive",
    "ote ",
    "otez",
    "delete",
    "hide",
    "efface",
    "vire",
)


def _normalized_numeric_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return ascii_value.lower()


_NUMBER_WORDS: dict[str, float] = {
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "douze": 12,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "half": 0.5,
    "demi": 0.5,
    "moitie": 0.5,
    "double": 2,
}


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = _normalized_words(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?:^| ){re.escape(normalized_phrase)}(?: |$)", normalized_text) is not None


def _contains_any_phrase(normalized_text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(normalized_text, phrase) for phrase in phrases)


def _quantity_mode(prompt: str, start: int, *, directional: bool) -> str:
    prefix = prompt[:start].rstrip()
    if re.search(r"(?:\ba|\bto|=)\s*$", prefix):
        return "absolute"
    if directional:
        return "delta"
    return "absolute"


def _prompt_quantities(normalized_prompt: str) -> list[tuple[float, str, str]]:
    """Return typed prompt quantities, excluding component indices.

    Each tuple is ``(value, canonical_unit, mode)``. ``mode`` distinguishes an
    absolute target (``à 30 m``) from a relative delta (``baisse de 40 cm``).
    """

    normalized_words = _normalized_words(normalized_prompt)
    directional = _contains_any_phrase(
        normalized_words, (*_DECREASE_MARKERS, *_INCREASE_MARKERS, *_REMOVAL_MARKERS)
    )
    quantities: list[tuple[float, str, str]] = []
    for word, number in _NUMBER_WORDS.items():
        for match in re.finditer(rf"\b{re.escape(word)}\b", normalized_prompt):
            prefix = normalized_prompt[: match.start()]
            if re.search(r"(?:\bsecteur|\bsector|\bs)\s*$", prefix):
                continue
            quantities.append(
                (
                    float(number),
                    "",
                    _quantity_mode(normalized_prompt, match.start(), directional=directional),
                )
            )
    for match in re.finditer(
        r"(-?\d+(?:[.,]\d+)?)\s*(millimetres?|mm|centimetres?|cm|metres?|meters?|m\b|deg(?:rees?)?|degres?|°|%|pourcent)?",
        normalized_prompt,
    ):
        prefix = normalized_prompt[: match.start()]
        if re.search(r"(?:\bsecteur|\bsector|\bs)\s*$", prefix):
            continue
        value = float(match.group(1).replace(",", "."))
        raw_unit = (match.group(2) or "").strip()
        if raw_unit.startswith("mm") or raw_unit.startswith("millimetre"):
            unit = "mm"
        elif raw_unit.startswith("cm") or raw_unit.startswith("centimetre"):
            unit = "cm"
        elif raw_unit == "m" or raw_unit.startswith(("metre", "meter")):
            unit = "m"
        elif raw_unit.startswith(("deg",)) or raw_unit == "°":
            unit = "deg"
        elif raw_unit in {"%", "pourcent"}:
            unit = "percent"
        else:
            unit = ""
        quantities.append(
            (
                value,
                unit,
                _quantity_mode(normalized_prompt, match.start(), directional=directional),
            )
        )
    return quantities


def _candidate_values_for_path(
    path: str,
    quantities: list[tuple[float, str, str]],
    *,
    mode: str | None = None,
) -> list[float]:
    """Convert compatible prompt quantities into the edited field's unit."""

    values: list[float] = []
    metres = path.endswith("_m") or "/position" in path or "/translation_m/" in path
    degrees = path.endswith("_deg") or "/rotation_deg" in path
    count = path.endswith("_count")
    for value, unit, quantity_mode in quantities:
        if mode is not None and quantity_mode != mode:
            continue
        if unit == "percent":
            continue
        if metres:
            if unit == "cm":
                values.append(value / 100.0)
            elif unit == "mm":
                values.append(value / 1000.0)
            elif unit in {"", "m"}:
                values.append(value)
        elif degrees:
            if unit in {"", "deg"}:
                values.append(value)
        elif count:
            if unit == "":
                values.append(value)
        else:
            if unit == "":
                values.append(value)
    return values


def _validate_patch_alignment(scene: SceneSpec, edit_prompt: str, patch: ScenePatch) -> None:
    """Reject LLM operations the prompt never asked for.

    The guard is deliberately tolerant to vocabulary: an operation is grounded
    when the prompt names the edited field and, for numeric fields, a quantity
    explains the value. Naming a component family cannot authorize a different
    field on that component.
    """

    normalized = _normalized_words(edit_prompt)
    # Quantities are read from an accent-stripped copy that keeps "1,6" / "0.4".
    quantities = _prompt_quantities(_normalized_numeric_text(edit_prompt))
    mentioned_sectors = {
        int(value) - 1
        for value in re.findall(r"(?:secteur|sector|s)\s*(\d+)", normalized)
        if int(value) > 0
    }
    for operation in patch.operations:
        terms = tuple(_normalized_words(term) for term in _terms_for_path(operation.path))
        grounded_by_term = any(_contains_phrase(normalized, term) for term in terms)
        numeric = isinstance(operation.value, int | float) and not isinstance(operation.value, bool)
        grounded_by_number = numeric and _numeric_value_is_grounded(
            scene, operation, quantities, normalized
        )
        if not grounded_by_term:
            raise ValueError(
                f"Patch operation is not grounded in the edit prompt: {operation.path}"
            )
        parts = operation.path.split("/")
        if operation.path.startswith("/sectors/") and parts[2].isdigit() and mentioned_sectors:
            if int(parts[2]) not in mentioned_sectors:
                raise ValueError(f"Patch targets an unrequested sector: {operation.path}")
        if numeric and not grounded_by_number:
            raise ValueError(f"Patch numeric value is not grounded in the prompt: {operation.path}")
        if (
            isinstance(operation.value, list)
            and operation.value
            and all(
                isinstance(item, int | float) and not isinstance(item, bool)
                for item in operation.value
            )
        ):
            if not _vector_value_is_grounded(scene, operation, quantities, normalized):
                raise ValueError(
                    f"Patch vector value is not grounded in the prompt: {operation.path}"
                )
        if operation.path == "/tower/characteristics/paint_color_hex" and isinstance(
            operation.value, str
        ):
            expected_colors = _expected_paint_colors(edit_prompt)
            if not expected_colors or operation.value.lower() not in expected_colors:
                raise ValueError(
                    f"Patch colour value is not grounded in the prompt: {operation.path}"
                )
        if isinstance(operation.value, bool):
            expected = not _contains_any_phrase(normalized, _REMOVAL_MARKERS)
            if operation.value is not expected:
                raise ValueError(f"Patch boolean value contradicts the prompt: {operation.path}")


def _terms_for_path(path: str) -> tuple[str, ...]:
    if re.fullmatch(
        r"/geometry_programs/\d+/nodes/0/transform/(translation_m|rotation_deg)/[xyz]",
        path,
    ):
        return (
            (
                "position",
                "positionne",
                "positionner",
                "placement",
                "translation",
                "translate",
                "déplace",
                "deplace",
                "move",
                "place",
            )
            if "/translation_m/" in path
            else ("rotation", "tourne", "rotate", "orientation")
        )
    if path.startswith("/sectors/"):
        field = path.rsplit("/", 1)[-1]
        return _SECTOR_FIELD_TERMS.get(field, ())
    if path.startswith("/accessory_assets/"):
        field = path.rsplit("/", 1)[-1]
        return _ACCESSORY_FIELD_TERMS.get(field, ())
    return next(
        (known_terms for prefix, known_terms in _PATH_TERMS if path.startswith(prefix)),
        (),
    )


def _target_value_match(text: str, keywords: tuple[str, ...]) -> re.Match[str] | None:
    explicit = re.search(
        r"(?:à|to|=)\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*(?:deg)?",
        text,
    )
    if explicit:
        return explicit
    if not any(keyword in text for keyword in keywords):
        return None
    sector_number = SceneEditAgent._extract_sector_index(text)
    for match in re.finditer(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*(?:deg)?", text):
        value = float(match.group(1).replace(",", "."))
        if sector_number is not None and value == sector_number + 1:
            continue
        return match
    return None


def _numeric_value_is_grounded(
    scene: SceneSpec,
    operation: PatchOperation,
    quantities: list[tuple[float, str, str]],
    normalized_prompt: str,
) -> bool:
    value = float(operation.value)
    current = _current_numeric_value(scene, operation.path)
    absolute_values = _candidate_values_for_path(operation.path, quantities, mode="absolute")
    delta_values = _candidate_values_for_path(operation.path, quantities, mode="delta")
    decrease = _contains_any_phrase(normalized_prompt, _DECREASE_MARKERS)
    increase = _contains_any_phrase(normalized_prompt, _INCREASE_MARKERS)
    removal = _contains_any_phrase(normalized_prompt, _REMOVAL_MARKERS)

    if any(abs(value - target) <= 0.01 for target in absolute_values):
        return True
    if current is None:
        return False
    if isinstance(operation.value, int) and operation.path.endswith("_count"):
        # Articles are not general-purpose quantities. They mean one only for a
        # named count field with an explicit add/remove direction.
        remove_all = removal and _contains_any_phrase(
            normalized_prompt, ("tous", "toutes", "all", "every")
        )
        if remove_all:
            return value == 0.0
        steps = delta_values or [1.0]
        if (
            increase
            and not decrease
            and any(abs(value - (current + step)) <= 0.01 for step in steps)
        ):
            return True
        if (
            (decrease or removal)
            and not increase
            and any(abs(value - (current - step)) <= 0.01 for step in steps)
        ):
            return True
        return False

    direction = _relative_direction(operation.path, normalized_prompt)
    if direction == 0:
        return False
    for delta in delta_values:
        expected = current + direction * delta
        if abs(value - expected) <= 0.01:
            return True
    for percent, unit, mode in quantities:
        if unit != "percent" or mode != "delta":
            continue
        factor = 1.0 + direction * percent / 100.0
        if abs(value - current * factor) <= 0.01:
            return True
    return False


def _vector_value_is_grounded(
    scene: SceneSpec,
    operation: PatchOperation,
    quantities: list[tuple[float, str, str]],
    normalized_prompt: str,
) -> bool:
    current = _current_vector_value(scene, operation.path)
    if current is None or not isinstance(operation.value, list):
        return False
    values = [float(item) for item in operation.value]
    changed = [index for index, item in enumerate(values) if abs(item - current[index]) > 1e-9]
    if not changed:
        return False

    axis_indices = {
        index
        for index, axis in enumerate(("x", "y", "z"))
        if _contains_phrase(normalized_prompt, axis)
    }
    if axis_indices and any(index not in axis_indices for index in changed):
        return False

    absolute_values = _candidate_values_for_path(operation.path, quantities, mode="absolute")
    delta_values = _candidate_values_for_path(operation.path, quantities, mode="delta")
    direction = _relative_direction(operation.path, normalized_prompt)
    for index in changed:
        if any(abs(values[index] - target) <= 0.01 for target in absolute_values):
            continue
        if direction == 0:
            return False
        if any(
            abs(values[index] - (current[index] + direction * delta)) <= 0.01
            for delta in delta_values
        ):
            continue
        percent_match = False
        for percent, unit, mode in quantities:
            if unit != "percent" or mode != "delta":
                continue
            factor = 1.0 + direction * percent / 100.0
            if abs(values[index] - current[index] * factor) <= 0.01:
                percent_match = True
                break
        if not percent_match:
            return False
    return True


def _relative_direction(path: str, normalized_prompt: str) -> int:
    """Return +1/-1 for a requested change in the stored field's semantics."""

    increase = _contains_any_phrase(normalized_prompt, _INCREASE_MARKERS)
    decrease = _contains_any_phrase(normalized_prompt, _DECREASE_MARKERS)
    if path.endswith("/vertical_offset_m"):
        # This field is the downward distance from antenna to radio: lowering
        # the radio increases the stored offset and raising it decreases it.
        increase, decrease = decrease, increase
    elif path.endswith("/radial_inset_m"):
        closer = _contains_any_phrase(normalized_prompt, ("rapproche", "closer"))
        farther = _contains_any_phrase(
            normalized_prompt, ("eloigne", "éloigne", "farther", "further")
        )
        increase = increase or closer
        decrease = decrease or farther
    if increase == decrease:
        return 0
    return 1 if increase else -1


_NAMED_PAINT_COLORS: dict[str, str] = {
    "rouge": "#c62828",
    "red": "#c62828",
    "bleu": "#1e5aa8",
    "blue": "#1e5aa8",
    "blanc": "#f2f2f2",
    "white": "#f2f2f2",
    "gris": "#8a8f94",
    "grey": "#8a8f94",
    "gray": "#8a8f94",
    "vert": "#2e7d32",
    "green": "#2e7d32",
    "jaune": "#f9c80e",
    "yellow": "#f9c80e",
    "orange": "#ef6c00",
    "noir": "#1a1a1a",
    "black": "#1a1a1a",
}


def _expected_paint_colors(edit_prompt: str) -> set[str]:
    explicit = {match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}\b", edit_prompt)}
    if explicit:
        return explicit
    normalized = _normalized_words(edit_prompt)
    return {
        color for name, color in _NAMED_PAINT_COLORS.items() if _contains_phrase(normalized, name)
    }


def _current_vector_value(scene: SceneSpec, path: str) -> list[float] | None:
    match = re.fullmatch(r"/accessory_assets/(\d+)/(position|rotation_deg|scale)", path)
    if match is None:
        return None
    index = int(match.group(1))
    if index >= len(scene.accessory_assets):
        return None
    return [float(item) for item in getattr(scene.accessory_assets[index], match.group(2))]


def _current_numeric_value(scene: SceneSpec, path: str) -> float | None:
    if re.fullmatch(
        r"/geometry_programs/\d+/nodes/0/transform/(translation_m|rotation_deg)/[xyz]",
        path,
    ):
        parts = path.split("/")
        transform = scene.geometry_programs[int(parts[2])].nodes[0].transform
        return float(getattr(getattr(transform, parts[6]), parts[7]))
    if path == "/tower/height_m":
        return float(scene.tower.height_m)
    parts = path.split("/")
    if path.startswith("/sectors/") and parts[2].isdigit():
        index = int(parts[2])
        if index >= len(scene.sectors):
            return None
        sector = scene.sectors[index]
        if len(parts) == 5 and parts[3] == "radio_geometry_profile":
            profile = sector.radio_geometry_profile
            value = getattr(profile, parts[4], None) if profile is not None else None
        else:
            value = getattr(sector, parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    if path.startswith("/tower/characteristics/"):
        value = getattr(scene.tower.characteristics, parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None
