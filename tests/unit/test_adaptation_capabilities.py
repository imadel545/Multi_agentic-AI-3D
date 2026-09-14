from pathlib import Path

import pytest

from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.adaptation import AdaptationOperation, AssetAdaptationPlan
from core.contracts.assets import RadioGeometryProfile
from core.contracts.geometry_program import GeometryProgram
from core.contracts.scene import (
    SceneAccessoryPlacement,
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)
from core.orchestration.langgraph_orchestrator import _scene_with_revision_dependencies
from core.services.adaptation_capabilities import AdaptationCapabilityService
from core.services.asset_registry import AssetRegistry
from core.services.checkpoint_saver import SqliteCheckpointSaver

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _services() -> tuple[AssetRegistry, AdaptationCapabilityService]:
    registry = AssetRegistry(PROJECT_ROOT / "assets/manifests")
    return registry, AdaptationCapabilityService(PROJECT_ROOT, registry)


def _scene(
    *,
    accessory: bool = False,
    radio: bool = False,
    tower_strategy: str = "parametric_generated",
) -> SceneSpec:
    accessories = []
    visuals = VisualElements()
    if accessory:
        visuals = VisualElements(include_gps_antenna=True)
        accessories = [
            SceneAccessoryPlacement(
                asset_id="GPS_ANTENNA_001",
                asset_type="gps",
                dimensions_m={"width": 0.32, "depth": 0.32, "height": 0.22},
                position=[0.0, 0.8, 29.5],
                rotation_deg=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
            )
        ]
    return SceneSpec(
        scene_id="wf_adaptation",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=30.0,
            generation_strategy=tower_strategy,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                install_height_m=24.0,
                azimuth_deg=0.0,
                beamwidth_deg=65.0,
                radio_asset_id="RRU_SMALL_001" if radio else None,
                radio_geometry_profile=RadioGeometryProfile() if radio else None,
            )
        ],
        visual_elements=visuals,
        accessory_assets=accessories,
    )


def _geometry_program(*, body_width_m: float, prompt_hash_character: str) -> GeometryProgram:
    return GeometryProgram.model_validate(
        {
            "schema_version": "1.0.0",
            "program_id": "equipment_shelter.llm_v1",
            "semantic_role": "equipment_shelter",
            "requested_quantity": 1,
            "units": "meters",
            "authorship": "llm_generated",
            "generator_provider": "groq",
            "generator_model": "openai/gpt-oss-120b",
            "structured_output_mode": "strict_json_schema",
            "source_prompt_sha256": prompt_hash_character * 64,
            "materials": [
                {
                    "material_id": "steel",
                    "base_color_rgba": {
                        "r": 0.55,
                        "g": 0.6,
                        "b": 0.62,
                        "a": 1.0,
                    },
                    "metallic": 0.35,
                    "roughness": 0.42,
                }
            ],
            "nodes": [
                {
                    "kind": "primitive",
                    "node_id": "shelter_body",
                    "semantic_role": "equipment_shelter",
                    "primitive": "box",
                    "size_m": {"x": body_width_m, "y": 2.2, "z": 2.5},
                    "material_id": "steel",
                    "transform": {"translation_m": {"x": 7.0, "y": 0.0, "z": 1.25}},
                    "bevel_m": 0.04,
                },
                {
                    "kind": "primitive",
                    "node_id": "shelter_door",
                    "primitive": "box",
                    "size_m": {"x": 0.8, "y": 0.08, "z": 1.8},
                    "material_id": "steel",
                    "transform": {"translation_m": {"x": 7.0, "y": -1.14, "z": 1.0}},
                },
                {
                    "kind": "primitive",
                    "node_id": "shelter_roof",
                    "primitive": "box",
                    "size_m": {"x": body_width_m + 0.2, "y": 2.4, "z": 0.12},
                    "material_id": "steel",
                    "transform": {"translation_m": {"x": 7.0, "y": 0.0, "z": 2.56}},
                },
            ],
            "assumptions": ["Generic outdoor technical enclosure."],
            "limitations": ["Not vendor-qualified."],
        }
    )


def _generic_scene(program: GeometryProgram) -> SceneSpec:
    return SceneSpec(
        schema_version="2.0.0",
        scene_id="wf_generic_adaptation",
        design_domain="architecture",
        design_intent_id="wf_generic_adaptation:intent:v1",
        component_graph_id="wf_generic_adaptation:components:v1",
        asset_decision_plan_id="wf_generic_adaptation:asset-decisions:v1",
        specialist_route_id="wf_generic_adaptation:specialists:v1",
        cognitive_plan_sha256="a" * 64,
        geometry_programs=[program],
    )


def test_capabilities_are_resolved_from_manifest_profiles() -> None:
    registry, service = _services()
    capabilities = service.resolve(_scene(accessory=True))
    paths = capabilities.allowed_paths

    assert "/tower/height_m" in paths
    assert "/sectors/0/azimuth_deg" in paths
    assert "/accessory_assets/0/scale" in paths
    assert "/visual_elements/include_sector_beams" in paths
    assert "/tower/characteristics/vendor_secret" not in paths
    assert not capabilities.missing_profiles
    assert all(
        asset.adaptation_profile_id
        or (
            asset.allows_generation_mode("imported_glb_exact")
            and not asset.allowed_parameters
            and asset.compatibility_rules.maximum_adaptation_effort == "none"
        )
        for asset in registry.list_assets()
    )


def test_rru_capabilities_are_resolved_from_the_active_radio_manifest() -> None:
    _, service = _services()

    capabilities = service.resolve(_scene(radio=True))
    by_path = {item.path: item for item in capabilities.capabilities}

    vertical_path = "/sectors/0/radio_geometry_profile/vertical_offset_m"
    radial_path = "/sectors/0/radio_geometry_profile/radial_inset_m"
    assert by_path[vertical_path].asset_id == "RRU_SMALL_001"
    assert by_path[vertical_path].profile_id == "rru_installation_v1"
    assert by_path[vertical_path].execution_tool == "sector_layout"
    assert by_path[vertical_path].minimum == 0.25
    assert by_path[vertical_path].maximum == 3.0
    assert by_path[radial_path].maximum == 0.5


def test_rru_capabilities_fail_closed_without_a_typed_scene_profile() -> None:
    _, service = _services()
    scene = _scene(radio=True)
    sector = scene.sectors[0].model_copy(update={"radio_geometry_profile": None})

    capabilities = service.resolve(scene.model_copy(update={"sectors": [sector]}))

    assert not any("radio_geometry_profile" in path for path in capabilities.allowed_paths)
    assert "RRU_SMALL_001:radio_geometry_profile" in capabilities.missing_profiles
    assert any(
        "adaptation reste désactivée" in item for item in capabilities.unsupported_operations
    )


def test_bounded_fallback_applies_explicit_rru_vertical_offset() -> None:
    _, service = _services()
    agent = SceneEditAgent(groq_client=None, capability_service=service)

    decision = agent.create_adaptation(
        "wf_rru_adaptation",
        _scene(radio=True),
        "mets le décalage vertical du RRU du secteur 1 à 1,6 m",
    )

    assert [operation.path for operation in decision.patch.operations] == [
        "/sectors/0/radio_geometry_profile/vertical_offset_m"
    ]
    assert decision.patched_scene.sectors[0].radio_geometry_profile is not None
    assert decision.patched_scene.sectors[0].radio_geometry_profile.vertical_offset_m == 1.6
    assert decision.patch.adaptation_tools == ["sector_layout"]


def test_llm_geometry_program_revision_uses_typed_patch_and_produces_new_scene() -> None:
    class RevisedGeometryPlanner:
        def __init__(self) -> None:
            self.call = None

        def plan(self, **kwargs):
            self.call = kwargs
            return _geometry_program(body_width_m=4.2, prompt_hash_character="b")

    original_program = _geometry_program(body_width_m=3.0, prompt_hash_character="a")
    scene = _scene().model_copy(update={"geometry_programs": [original_program]})
    _, service = _services()
    planner = RevisedGeometryPlanner()
    agent = SceneEditAgent(
        groq_client=None,
        capability_service=service,
        geometry_program_planner=planner,  # type: ignore[arg-type]
    )

    decision = agent.create_adaptation(
        "wf_geometry_revision",
        scene,
        "agrandis equipment shelter à 4,2 m et conserve son rôle",
    )

    assert decision.validation_report.status == "passed"
    assert decision.patched_scene is not scene
    assert decision.patched_scene.geometry_programs[0] is not original_program
    assert scene.geometry_programs[0].nodes[0].size_m.x == 3.0  # type: ignore[union-attr]
    revised = decision.patched_scene.geometry_programs[0]
    assert revised.nodes[0].size_m.x == 4.2  # type: ignore[union-attr]
    assert revised.semantic_role == original_program.semantic_role
    assert revised.requested_quantity == original_program.requested_quantity
    assert revised.source_prompt_sha256 == "b" * 64
    assert [operation.path for operation in decision.patch.operations] == ["/geometry_programs/0"]
    assert decision.patch.adaptation_tools == ["geometry_program_rebuild"]
    assert decision.plan.operations[0].execution_tool == "geometry_program_rebuild"
    assert (
        decision.capabilities.capabilities[
            next(
                index
                for index, capability in enumerate(decision.capabilities.capabilities)
                if capability.path == "/geometry_programs/0"
            )
        ].value_type
        == "geometry_program"
    )
    assert planner.call["semantic_role"] == "equipment_shelter"
    assert planner.call["request_id"] == "equipment_shelter"
    assert planner.call["quantity"] == 1
    assert planner.call["source_description_origin"] == "legacy_unavailable"
    assert planner.call["source_description"].startswith("Intention source indisponible")
    assert planner.call["design_context"]["current_geometry_program"] == (
        original_program.model_dump(mode="json")
    )
    assert [step["node"] for step in decision.graph_trace] == [
        "discover_capabilities",
        "plan_geometry_program_revision",
        "validate_adaptation",
        "execute_adaptation",
    ]


def test_generic_scene_resolves_and_executes_geometry_program_revision() -> None:
    class RevisedGeometryPlanner:
        def plan(self, **kwargs):
            assert kwargs["design_context"]["design_domain"] == "architecture"
            assert kwargs["design_context"]["scene_tower_height_m"] is None
            return _geometry_program(body_width_m=4.2, prompt_hash_character="b")

    original_program = _geometry_program(body_width_m=3.0, prompt_hash_character="a")
    scene = _generic_scene(original_program)
    _, service = _services()
    agent = SceneEditAgent(
        groq_client=None,
        capability_service=service,
        geometry_program_planner=RevisedGeometryPlanner(),  # type: ignore[arg-type]
    )

    decision = agent.create_adaptation(
        "wf_generic_adaptation",
        scene,
        "agrandis equipment shelter a 4,2 m et conserve son role",
    )

    assert decision.validation_report.status == "passed"
    assert decision.patched_scene.schema_version == "2.0.0"
    assert decision.patched_scene.tower is None
    assert decision.patched_scene.geometry_programs[0].nodes[0].size_m.x == 4.2  # type: ignore[union-attr]
    assert [operation.path for operation in decision.patch.operations] == ["/geometry_programs/0"]


def test_geometry_revision_preserves_original_intent_and_placement_provenance() -> None:
    class CapturingPlanner:
        def __init__(self) -> None:
            self.call = None

        def plan(self, **kwargs):
            self.call = kwargs
            return _geometry_program(body_width_m=3.2, prompt_hash_character="c")

    original = _geometry_program(
        body_width_m=3.0,
        prompt_hash_character="a",
    ).model_copy(
        update={
            "source_description": "Créer un shelter technique extérieur à double porte.",
            "source_description_origin": "user_requirement",
            "placement_context": "à sept mètres à droite du pylône",
        }
    )
    scene = _scene().model_copy(update={"geometry_programs": [original]})
    _, service = _services()
    planner = CapturingPlanner()
    agent = SceneEditAgent(
        capability_service=service,
        geometry_program_planner=planner,  # type: ignore[arg-type]
    )

    agent.create_adaptation(
        "wf_geometry_revision_provenance",
        scene,
        "ajoute au shelter deux grilles de ventilation sans changer l'implantation",
    )

    assert planner.call["source_description"] == original.source_description
    assert planner.call["source_description_origin"] == "revision_preserved"
    assert planner.call["placement_context"] == original.placement_context


def test_geometry_program_capability_rejects_free_form_blender_code() -> None:
    scene = _scene().model_copy(
        update={
            "geometry_programs": [_geometry_program(body_width_m=3.0, prompt_hash_character="a")]
        }
    )
    _, service = _services()
    capabilities = service.resolve(scene)
    unsafe_value = scene.geometry_programs[0].model_dump(mode="json")
    unsafe_value["python_code"] = "import bpy; bpy.ops.mesh.primitive_cube_add()"
    plan = AssetAdaptationPlan(
        edit_description="Injecter un script Blender libre",
        operations=[
            AdaptationOperation(
                capability_id="geometry_program_1:rebuild",
                path="/geometry_programs/0",
                value=unsafe_value,
                execution_tool="geometry_program_rebuild",
                rationale="Ce champ exécutable doit être refusé.",
            )
        ],
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        service.validate_plan(capabilities, plan)


def test_non_parametric_tower_does_not_claim_geometry_editing() -> None:
    _, service = _services()
    capabilities = service.resolve(_scene(tower_strategy="imported_glb_exact"))

    assert "/tower/height_m" not in capabilities.allowed_paths
    assert any("GLB non paramétrique" in item for item in capabilities.unsupported_operations)


def test_plan_validator_rejects_wrong_tool_and_unknown_capability() -> None:
    _, service = _services()
    capabilities = service.resolve(_scene())
    invalid = AssetAdaptationPlan(
        edit_description="invalid",
        operations=[
            AdaptationOperation(
                capability_id="scene:tower_height",
                path="/tower/height_m",
                value=40,
                execution_tool="scene_visibility",
                rationale="wrong tool",
            )
        ],
    )

    with pytest.raises(ValueError, match="requires parametric_rebuild"):
        service.validate_plan(capabilities, invalid)


def test_langgraph_adaptation_uses_strict_groq_schema_and_executes_scene_spec() -> None:
    class RecordingGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.payload = None

        def _post_raw(self, payload):
            self.payload = payload
            return {
                "edit_description": "Passer le pylône à 40 m",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "scene:tower_height",
                        "path": "/tower/height_m",
                        "value": 40,
                        "execution_tool": "parametric_rebuild",
                        "rationale": "La demande fixe explicitement 40 m.",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    groq = RecordingGroq()
    agent = SceneEditAgent(groq_client=groq, capability_service=service)  # type: ignore[arg-type]
    decision = agent.create_adaptation("wf_adaptation", _scene(), "mets la tour à 40 m")

    assert decision.patched_scene.tower.height_m == 40
    assert decision.planner_fallback_used is False
    assert [item["node"] for item in decision.graph_trace] == [
        "discover_capabilities",
        "plan_adaptation",
        "validate_adaptation",
        "execute_adaptation",
    ]
    response_format = groq.payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    path_schema = response_format["json_schema"]["schema"]["properties"]["operations"]["items"][
        "properties"
    ]["path"]
    assert "/tower/height_m" in path_schema["enum"]
    operation_properties = response_format["json_schema"]["schema"]["properties"]["operations"][
        "items"
    ]["properties"]
    assert "value_json" in operation_properties
    assert "value" not in operation_properties


def test_terminal_adaptation_removes_its_checkpoint_thread(tmp_path: Path, monkeypatch) -> None:
    _, service = _services()
    saver = SqliteCheckpointSaver(tmp_path / "checkpoints.db")
    deleted_threads: list[str] = []
    original_delete = saver.delete_thread

    def record_delete(thread_id: str) -> None:
        deleted_threads.append(thread_id)
        original_delete(thread_id)

    monkeypatch.setattr(saver, "delete_thread", record_delete)
    agent = SceneEditAgent(
        groq_client=None,
        capability_service=service,
        checkpoint_saver=saver,
    )

    decision = agent.create_adaptation(
        "wf_checkpoint_cleanup",
        _scene(),
        "mets la tour à 40 m",
    )

    assert decision.patched_scene.tower.height_m == 40
    assert len(deleted_threads) == 1
    assert deleted_threads[0].startswith("wf_checkpoint_cleanup:adaptation:")
    assert (
        list(saver.list({"configurable": {"thread_id": deleted_threads[0], "checkpoint_ns": ""}}))
        == []
    )


def test_invalid_llm_plan_falls_back_before_scene_mutation() -> None:
    class InvalidGroq:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, _payload):
            return {
                "edit_description": "unsafe",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "scene:tower_height",
                        "path": "/visual_elements/include_labels",
                        "value": 99,
                        "execution_tool": "parametric_rebuild",
                        "rationale": "invented",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    agent = SceneEditAgent(
        groq_client=InvalidGroq(),  # type: ignore[arg-type]
        capability_service=service,
    )
    decision = agent.create_adaptation("wf_adaptation", _scene(), "mets la tour à 40 m")

    assert decision.patched_scene.tower.height_m == 40
    assert decision.planner_fallback_used is True
    assert decision.planner_fallback_reason == "groq_edit_failed:ValueError"


def test_accessory_vector_transform_is_bounded_and_applied() -> None:
    class AccessoryGroq:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, _payload):
            return {
                "edit_description": "Agrandir le GPS",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "accessory_1:accessory_scale",
                        "path": "/accessory_assets/0/scale",
                        "value": [1.5, 1.5, 1.5],
                        "execution_tool": "asset_transform",
                        "rationale": "Échelle explicite de 1.5 sur XYZ.",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    agent = SceneEditAgent(
        groq_client=AccessoryGroq(),  # type: ignore[arg-type]
        capability_service=service,
    )
    decision = agent.create_adaptation(
        "wf_adaptation",
        _scene(accessory=True),
        "change la taille GPS avec une échelle 1.5, 1.5, 1.5",
    )

    assert decision.patched_scene.accessory_assets[0].scale == [1.5, 1.5, 1.5]
    assert decision.patch.adaptation_tools == ["asset_transform"]


def test_bounded_fallback_applies_explicit_gps_scale_without_toggling_visibility() -> None:
    _, service = _services()
    agent = SceneEditAgent(groq_client=None, capability_service=service)

    decision = agent.create_adaptation(
        "wf_adaptation",
        _scene(accessory=True),
        "change la taille GPS avec une échelle 1.2, 1.2, 1.2",
    )

    assert [operation.path for operation in decision.patch.operations] == [
        "/accessory_assets/0/scale"
    ]
    assert decision.patched_scene.accessory_assets[0].scale == [1.2, 1.2, 1.2]


def test_revision_dependency_rebind_preserves_scale_and_follows_tower_height() -> None:
    registry, _ = _services()
    original = _scene(accessory=True)
    gps = original.accessory_assets[0].model_copy(update={"scale": [1.2, 1.2, 1.2]})
    raised = original.model_copy(
        update={
            "tower": original.tower.model_copy(update={"height_m": 34.0}),
            "accessory_assets": [gps],
        }
    )

    rebound = _scene_with_revision_dependencies(raised, registry)

    assert rebound.accessory_assets[0].scale == [1.2, 1.2, 1.2]
    assert rebound.accessory_assets[0].position[2] == 33.5


def test_user_defined_accessory_position_survives_dependency_rebind() -> None:
    registry, _ = _services()
    original = _scene(accessory=True)
    gps = original.accessory_assets[0].model_copy(
        update={"position": [2.0, 3.0, 4.0], "placement_policy": "user_defined"}
    )
    moved = original.model_copy(update={"accessory_assets": [gps]})

    rebound = _scene_with_revision_dependencies(moved, registry)

    assert rebound.accessory_assets[0].position == [2.0, 3.0, 4.0]
    assert rebound.accessory_assets[0].placement_policy == "user_defined"
