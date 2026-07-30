import json
import logging
import re
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

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
from core.services.adaptation_capabilities import AdaptationCapabilityService
from core.services.patch_applier import PatchApplier

logger = logging.getLogger(__name__)


class AdaptationGraphState(TypedDict, total=False):
    workflow_id: str
    scene: SceneSpec
    edit_prompt: str
    capabilities: SceneAdaptationCapabilities
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
    ) -> None:
        self.groq = groq_client
        self.capability_service = capability_service
        self.patch_applier = PatchApplier()
        self.checkpoint_saver = checkpoint_saver
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
    ) -> AdaptationDecision:
        if self.graph is None or self.capability_service is None:
            raise RuntimeError("adaptation capability service is unavailable")
        thread_id = f"{workflow_id}:adaptation:{uuid.uuid4().hex}"
        try:
            state = self.graph.invoke(
                {
                    "workflow_id": workflow_id,
                    "scene": scene,
                    "edit_prompt": edit_prompt,
                    "graph_trace": [],
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
                return self._llm_patch(scene, edit_prompt)
            except Exception as exc:
                fallback_reason = f"groq_edit_failed:{type(exc).__name__}"
                logger.warning(
                    "LLM scene edit failed for workflow %s; falling back to deterministic parser.",
                    workflow_id,
                    exc_info=True,
                )
        return self._fallback_patch(scene, edit_prompt, fallback_reason=fallback_reason)

    def _discover_capabilities(self, state: AdaptationGraphState) -> dict[str, Any]:
        if self.capability_service is None:
            raise RuntimeError("adaptation capability service is unavailable")
        capabilities = self.capability_service.resolve(state["scene"])
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
                    state["scene"], state["edit_prompt"], fallback_reason=fallback_reason
                )
                plan = _plan_from_patch(patch, state["capabilities"])
        else:
            patch = self._fallback_patch(
                state["scene"], state["edit_prompt"], fallback_reason=fallback_reason
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
    ) -> ScenePatch:
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
                for idx in range(len(scene.sectors)):
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
            ("tilt", "inclinaison", "mécanique", "mecanique", "électrique", "electrique"),
        )
        if tilt_match and any(
            k in text for k in ("tilt", "inclinaison", "mécanique", "mécanique", "electrique")
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
        if any(k in text for k in ("power cabinet", "armoire", "cabinet")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(
                    op="replace", path="/visual_elements/include_power_cabinet", value=val
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


_PATH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/tower/height_m", ("hauteur", "height", "tour", "tower", "pylône", "pylone")),
    ("/tower/characteristics/structure", ("structure", "treillis", "lattice", "monopole")),
    ("/tower/characteristics/leg_count", ("jambe", "pied", "leg")),
    ("/tower/characteristics/base_width_m", ("largeur", "base", "width")),
    ("/tower/characteristics/top_width_m", ("largeur", "sommet", "top", "width")),
    ("/tower/characteristics/foundation_type", ("fondation", "dalle", "foundation", "base")),
    ("/tower/characteristics/has_platform", ("plateforme", "platform")),
    ("/tower/characteristics/platform_count", ("plateforme", "platform")),
    ("/tower/characteristics/has_ladder", ("échelle", "echelle", "ladder")),
    ("/tower/characteristics/has_lightning_rod", ("paratonnerre", "lightning")),
    ("/tower/characteristics/has_aviation_light", ("balisage", "aviation")),
    (
        "/tower/characteristics/material",
        ("matériau", "materiau", "material", "acier", "béton", "beton"),
    ),
    ("/visual_elements/include_gps_antenna", ("gps", "gnss")),
    ("/visual_elements/include_power_cabinet", ("armoire", "cabinet", "alimentation", "power")),
    ("/visual_elements/include_sector_beams", ("faisceau", "beam", "secteur")),
    ("/visual_elements/include_azimuth_arrows", ("azimut", "azimuth", "flèche", "fleche", "arrow")),
    (
        "/visual_elements/include_height_markers",
        ("hauteur", "height", "marker", "repère", "repere"),
    ),
    ("/visual_elements/include_labels", ("label", "étiquette", "etiquette")),
)

_SECTOR_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "azimuth_deg": ("azimut", "azimuth", "orientation", "diriger", "oriente"),
    "install_height_m": ("hauteur", "height", "hba", "antenne", "antenna"),
    "mechanical_tilt_deg": ("tilt", "inclinaison", "mécanique", "mecanique"),
    "electrical_tilt_deg": ("tilt", "inclinaison", "électrique", "electrique"),
    "beamwidth_deg": ("beamwidth", "ouverture", "faisceau", "beam"),
    "include_cable": ("câble", "cable"),
    "include_label": ("label", "étiquette", "etiquette"),
}

_ACCESSORY_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "position": ("position", "déplace", "deplace", "move", "x", "y", "z"),
    "rotation_deg": ("rotation", "tourne", "rotate", "orientation"),
    "scale": ("taille", "échelle", "echelle", "scale", "agrandis", "réduis", "reduis"),
}


def _validate_patch_alignment(scene: SceneSpec, edit_prompt: str, patch: ScenePatch) -> None:
    normalized = edit_prompt.lower()
    source_numbers = [
        float(value.replace(",", ".")) for value in re.findall(r"-?\d+(?:[.,]\d+)?", normalized)
    ]
    mentioned_sectors = {
        int(value) - 1
        for value in re.findall(r"(?:secteur|sector|s)\s*(\d+)", normalized)
        if int(value) > 0
    }
    for operation in patch.operations:
        terms = _terms_for_path(operation.path)
        if not terms or not any(term in normalized for term in terms):
            raise ValueError(
                f"Patch operation is not grounded in the edit prompt: {operation.path}"
            )
        parts = operation.path.split("/")
        if operation.path.startswith("/sectors/") and parts[2].isdigit() and mentioned_sectors:
            if int(parts[2]) not in mentioned_sectors:
                raise ValueError(f"Patch targets an unrequested sector: {operation.path}")
        if isinstance(operation.value, int | float) and not isinstance(operation.value, bool):
            if not _numeric_value_is_grounded(
                scene,
                operation,
                source_numbers,
                normalized,
            ):
                raise ValueError(
                    f"Patch numeric value is not grounded in the prompt: {operation.path}"
                )
        if (
            isinstance(operation.value, list)
            and operation.value
            and all(
                isinstance(item, int | float) and not isinstance(item, bool)
                for item in operation.value
            )
        ):
            if not all(
                any(abs(float(item) - source) <= 0.01 for source in source_numbers)
                for item in operation.value
            ):
                raise ValueError(
                    f"Patch vector value is not grounded in the prompt: {operation.path}"
                )
        if isinstance(operation.value, bool):
            expected = not any(
                marker in normalized
                for marker in ("supprime", "retire", "enlève", "enleve", "remove", "sans ")
            )
            if operation.value is not expected:
                raise ValueError(f"Patch boolean value contradicts the prompt: {operation.path}")


def _terms_for_path(path: str) -> tuple[str, ...]:
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
    source_numbers: list[float],
    normalized_prompt: str,
) -> bool:
    value = float(operation.value)
    if any(abs(value - source) <= 0.01 for source in source_numbers):
        return True
    current = _current_numeric_value(scene, operation.path)
    if current is None:
        return False
    if any(term in normalized_prompt for term in ("augmente", "increase", "ajoute", "raise")):
        return any(abs(value - (current + delta)) <= 0.01 for delta in source_numbers)
    if any(
        term in normalized_prompt for term in ("diminue", "decrease", "réduit", "reduit", "lower")
    ):
        return any(abs(value - (current - delta)) <= 0.01 for delta in source_numbers)
    return False


def _current_numeric_value(scene: SceneSpec, path: str) -> float | None:
    if path == "/tower/height_m":
        return float(scene.tower.height_m)
    parts = path.split("/")
    if path.startswith("/sectors/") and parts[2].isdigit():
        index = int(parts[2])
        if index >= len(scene.sectors):
            return None
        value = getattr(scene.sectors[index], parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    if path.startswith("/tower/characteristics/"):
        value = getattr(scene.tower.characteristics, parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None
