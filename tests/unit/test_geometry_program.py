import hashlib
import json
import shutil
import struct
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from core.agents.geometry_program_planner import (
    GeometryProgramPlanner,
    _fit_to_maximum_dimensions,
    _normalize_disclosures,
    _normalize_explicit_point_placeholders,
    _normalize_profile_definitions,
    _strict_json_schema,
)
from core.agents.scene_planner import ScenePlanner
from core.contracts.geometry_program import (
    GeometryProgram,
    GeometryProgramVector3,
    geometry_program_dimensions,
)
from core.contracts.scene import SceneSpec
from core.llm.transport import GroqTransportError
from core.qa.glb_geometry_validator import GLBGeometryValidator
from core.qa.glb_inspector import GLBInspector
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.requirement_parser import parse_requirements_text


def test_geometry_program_rejects_parent_cycles() -> None:
    payload = _program_payload()
    payload["nodes"][0]["parent_id"] = "roof"
    payload["nodes"][1]["parent_id"] = "body"

    with pytest.raises(ValidationError, match="parent graph contains a cycle"):
        GeometryProgram.model_validate(payload)


def test_geometry_program_rejects_unknown_material_and_unbounded_scale() -> None:
    payload = _program_payload()
    payload["nodes"][0]["material_id"] = "missing"
    payload["nodes"][0]["transform"] = {"scale": _xyz(101.0, 1.0, 1.0)}

    with pytest.raises(ValidationError) as exc_info:
        GeometryProgram.model_validate(payload)

    message = str(exc_info.value)
    assert "geometry-program scale components" in message


def test_geometry_program_rejects_instance_cycles_and_oversized_envelopes() -> None:
    payload = _program_payload()
    payload["nodes"] = [
        {
            "kind": "instance",
            "node_id": "copy_a",
            "source_node_id": "copy_b",
            "semantic_role": "equipment_shelter",
        },
        {
            "kind": "instance",
            "node_id": "copy_b",
            "source_node_id": "copy_a",
        },
    ]
    with pytest.raises(ValidationError, match="instance graph contains a cycle"):
        GeometryProgram.model_validate(payload)

    payload = _program_payload()
    payload["maximum_dimensions_m"] = _xyz(3.0, 3.0, 3.0)
    with pytest.raises(ValidationError, match="dimension .* exceeds maximum"):
        GeometryProgram.model_validate(payload)


def test_geometry_program_checks_rotated_hierarchical_envelope() -> None:
    payload = _program_payload()
    payload["authorship"] = "deterministic_generated"
    payload["nodes"] = [
        {
            "kind": "primitive",
            "node_id": "body",
            "primitive": "box",
            "size_m": _xyz(2.0, 1.0, 1.0),
            "semantic_role": "equipment_shelter",
            "transform": {
                "rotation_deg": _xyz(0.0, 0.0, 90.0),
                "translation_m": _xyz(12.0, -4.0, 1.0),
            },
        }
    ]
    payload["maximum_dimensions_m"] = _xyz(1.1, 2.1, 1.1)

    program = GeometryProgram.model_validate(payload)

    assert program.maximum_dimensions_m is not None


def test_deterministic_envelope_adapter_fits_only_otherwise_valid_programs() -> None:
    payload = _program_payload()
    payload["maximum_dimensions_m"] = _xyz(4.0, 4.0, 2.0)

    fitted = _fit_to_maximum_dimensions(payload)

    assert fitted is not None
    program = GeometryProgram.model_validate(fitted)
    assert program.deterministic_adjustments
    assert "factor=" in program.deterministic_adjustments[0]


def test_geometry_program_v2_validates_closed_generic_registry_and_envelope() -> None:
    program = GeometryProgram.model_validate(_v2_program_payload())

    assert program.schema_version == "2.0.0"
    assert {node.kind for node in program.nodes} == {
        "primitive",
        "profile",
        "extrude",
        "revolve",
        "sweep",
        "array",
        "boolean",
        "modifier",
        "terrain",
        "instance",
    }
    assert len(program.anchors) == 2
    assert len(program.connectors) == 2
    assert len(program.semantic_groups) == 3
    assert all(value > 0 for value in geometry_program_dimensions(program))


def test_geometry_program_v2_features_fail_closed_in_v1_and_on_invalid_graphs() -> None:
    v1_with_v2_node = _v2_program_payload()
    v1_with_v2_node["schema_version"] = "1.0.0"
    with pytest.raises(ValidationError, match="V2 capabilities require"):
        GeometryProgram.model_validate(v1_with_v2_node)

    unknown_kind = _v2_program_payload()
    unknown_kind["nodes"][0]["kind"] = "arbitrary_blender_operator"
    with pytest.raises(ValidationError):
        GeometryProgram.model_validate(unknown_kind)

    bad_connector = _v2_program_payload()
    bad_connector["connectors"][0]["anchor_id"] = "missing_anchor"
    with pytest.raises(ValidationError, match="unknown anchor"):
        GeometryProgram.model_validate(bad_connector)

    dependency_cycle = _v2_program_payload()
    _v2_node(dependency_cycle, "steps")["parent_id"] = "mirrored_rail"
    _v2_node(dependency_cycle, "handrail")["parent_id"] = "steps"
    with pytest.raises(ValidationError, match="dependency graph contains a cycle"):
        GeometryProgram.model_validate(dependency_cycle)


def test_geometry_program_v2_rejects_unsafe_profiles_terrain_and_operator_parameters() -> None:
    self_intersecting = _v2_program_payload()
    _v2_node(self_intersecting, "rail_profile")["points_m"] = [
        _xy(-0.1, -0.1),
        _xy(0.1, 0.1),
        _xy(-0.1, 0.1),
        _xy(0.1, -0.1),
    ]
    with pytest.raises(ValidationError, match="non-zero area|self-intersect"):
        GeometryProgram.model_validate(self_intersecting)

    wrong_height_count = _v2_program_payload()
    _v2_node(wrong_height_count, "terrain_surface")["heights_m"] = [0.0] * 8
    with pytest.raises(ValidationError, match="columns times rows"):
        GeometryProgram.model_validate(wrong_height_count)

    arbitrary_modifier = _v2_program_payload()
    _v2_node(arbitrary_modifier, "beveled_wall")["modifier"] = "python_callback"
    with pytest.raises(ValidationError):
        GeometryProgram.model_validate(arbitrary_modifier)


def test_geometry_program_planner_uses_strict_schema_and_pins_provenance() -> None:
    class FakeGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.payload = None
            self.policy = None

        def request_json(self, payload, *, policy):
            self.payload = payload
            self.policy = policy
            return {
                "schema_version": "1.0.0",
                "program_id": "model_chosen_id",
                "semantic_role": "wrong_role",
                "requested_quantity": 1,
                "units": "meters",
                "authorship": "llm_generated",
                "generator_provider": "untrusted",
                "generator_model": "untrusted",
                "structured_output_mode": "strict_json_schema",
                "source_prompt_sha256": "0" * 64,
                "materials": [],
                "nodes": [
                    {
                        "kind": "primitive",
                        "node_id": "body",
                        "parent_id": None,
                        "material_id": None,
                        "semantic_role": "equipment_shelter",
                        "transform": {
                            "translation_m": _xyz(0.0, 0.0, 1.0),
                            "rotation_deg": _xyz(0.0, 0.0, 0.0),
                            "scale": _xyz(1.0, 1.0, 1.0),
                        },
                        "primitive": "box",
                        "size_m": _xyz(2.0, 2.0, 2.0),
                        "radius_m": None,
                        "top_radius_m": None,
                        "height_m": None,
                        "vertices": 24,
                        "bevel_m": 0.02,
                    },
                    {
                        "kind": "primitive",
                        "node_id": "door",
                        "primitive": "box",
                        "size_m": _xyz(0.8, 0.08, 1.8),
                        "transform": {
                            "translation_m": _xyz(0.0, -1.01, 0.9),
                        },
                    },
                    {
                        "kind": "primitive",
                        "node_id": "roof",
                        "primitive": "box",
                        "size_m": _xyz(2.2, 2.2, 0.12),
                        "transform": {
                            "translation_m": _xyz(0.0, 0.0, 2.06),
                        },
                    },
                ],
                "assumptions": [],
                "limitations": ["Not vendor-specific."],
            }

    fake = FakeGroq()
    planner = GeometryProgramPlanner(fake)  # type: ignore[arg-type]

    program = planner.plan(
        prompt="Créer un shelter technique compact.",
        semantic_role="equipment shelter",
        design_context={"maximum_dimensions_m": [4.0, 4.0, 3.0]},
        maximum_dimensions_m=GeometryProgramVector3(x=4.0, y=4.0, z=3.0),
    )

    assert program.program_id == "equipment_shelter.llm_v2"
    assert program.schema_version == "2.0.0"
    assert program.semantic_role == "equipment_shelter"
    assert program.requested_quantity == 1
    assert program.generator_provider == "groq"
    assert program.generator_model == "openai/gpt-oss-120b"
    assert program.structured_output_mode == "strict_json_schema"
    assert program.maximum_dimensions_m == GeometryProgramVector3(x=4.0, y=4.0, z=3.0)
    assert fake.policy.capability == "geometry_program_generation"
    assert fake.policy.reasoning_effort == "medium"
    response_format = fake.payload["response_format"]["json_schema"]
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    assert set(response_format["schema"]["required"]) == set(
        response_format["schema"]["properties"]
    )


def test_geometry_program_strict_schema_uses_only_supported_union_and_refs() -> None:
    schema = _strict_json_schema(GeometryProgram.model_json_schema())

    def visit(value):
        if isinstance(value, dict):
            assert "oneOf" not in value
            assert "discriminator" not in value
            if "$ref" in value:
                assert set(value) == {"$ref"}
            if value.get("type") == "object" or "properties" in value:
                assert value.get("additionalProperties") is False
                assert set(value.get("required", [])) == set(value.get("properties", {}))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    assert "anyOf" in schema["properties"]["nodes"]["items"]


@pytest.mark.parametrize("transport_backed", [False, True])
def test_geometry_program_planner_falls_back_after_strict_groq_400(
    transport_backed: bool,
) -> None:
    class FakeGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.payloads = []

        def request_json(self, payload, *, policy):
            self.payloads.append(payload)
            if len(self.payloads) == 1:
                if transport_backed:
                    raise GroqTransportError(
                        "model_output_rejected",
                        attempts=1,
                        retryable=False,
                        status_code=400,
                    )
                request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
                response = httpx.Response(400, request=request)
                raise httpx.HTTPStatusError(
                    "strict structured output rejected",
                    request=request,
                    response=response,
                )
            payload = _program_payload()
            payload["nodes"][0]["semantic_role"] = "perimeter_fence"
            return payload

    fake = FakeGroq()
    planner = GeometryProgramPlanner(fake)  # type: ignore[arg-type]

    program = planner.plan(
        prompt="Créer une clôture grillagée galvanisée autour du site.",
        semantic_role="perimeter fence",
        design_context={"site_envelope_m": {"x": 14.0, "y": 14.0, "z": 2.4}},
    )

    assert len(fake.payloads) == 2
    assert fake.payloads[0]["response_format"]["type"] == "json_schema"
    assert "must contain at least three nodes" in fake.payloads[0]["messages"][0]["content"]
    assert "never put a primary semantic node" in fake.payloads[0]["messages"][0]["content"]
    assert fake.payloads[1]["response_format"] == {"type": "json_object"}
    fallback_contract = fake.payloads[1]["messages"][-1]["content"]
    assert 'base_color_rgba as {"r":0..1' in fallback_contract
    assert '"translation_m":{"x":7.0' in fallback_contract
    assert "at least three nodes in total" in fallback_contract
    assert "must never appear in construction_node_ids" in fallback_contract
    assert "ellipsis tokens" in fallback_contract
    assert "placeholder objects" in fallback_contract
    assert "Never emit ellipsis tokens" in fake.payloads[0]["messages"][0]["content"]
    assert program.semantic_role == "perimeter_fence"
    assert program.structured_output_mode == "json_object_validated"
    assert program.schema_version == "2.0.0"


def test_geometry_program_disclosure_normalization_never_changes_geometry() -> None:
    payload = _program_payload()
    original_nodes = json.loads(json.dumps(payload["nodes"]))
    payload["assumptions"] = [{"basis": "generic outdoor enclosure"}]
    payload["limitations"] = [{"not_certified": True}]

    _normalize_disclosures(payload)

    assert payload["nodes"] == original_nodes
    assert payload["assumptions"] == ['{"basis":"generic outdoor enclosure"}']
    assert payload["limitations"] == ['{"not_certified":true}']
    GeometryProgram.model_validate(payload)


def test_geometry_program_planner_canonicalizes_profile_fields_from_strict_output() -> None:
    class FakeGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.call_count = 0

        def request_json(self, payload, *, policy):
            self.call_count += 1
            return {
                "schema_version": "2.0.0",
                "program_id": "model_generated_id",
                "semantic_role": "perimeter_fence",
                "requested_quantity": 1,
                "units": "meters",
                "authorship": "llm_generated",
                "generator_provider": "groq",
                "generator_model": self.model,
                "structured_output_mode": "strict_json_schema",
                "source_prompt_sha256": "0" * 64,
                "materials": [
                    {
                        "material_id": "galvanized_steel",
                        "base_color_rgba": _rgba(0.55, 0.58, 0.6, 1.0),
                    }
                ],
                "nodes": [
                    {
                        "kind": "profile",
                        "node_id": "fence_panel_profile",
                        "points_m": [
                            _xy(-7.0, 0.0),
                            _xy(7.0, 0.0),
                            _xy(7.0, 2.4),
                            _xy(-7.0, 2.4),
                        ],
                        "closed": True,
                        "parent_id": "fence_panel",
                        "material_id": "galvanized_steel",
                        "semantic_role": "profile_definition",
                        "transform": {
                            "translation_m": _xyz(0.0, 0.0, 1.2),
                            "rotation_deg": _xyz(0.0, 0.0, 0.0),
                            "scale": _xyz(1.0, 1.0, 1.0),
                        },
                    },
                    {
                        "kind": "extrude",
                        "node_id": "fence_panel",
                        "profile_node_id": "fence_panel_profile",
                        "depth_m": 0.04,
                        "material_id": "galvanized_steel",
                        "semantic_role": "perimeter_fence",
                    },
                    {
                        "kind": "primitive",
                        "node_id": "gate_post_left",
                        "primitive": "box",
                        "size_m": _xyz(0.12, 0.12, 2.4),
                        "material_id": "galvanized_steel",
                    },
                ],
                "construction_node_ids": [],
                "assumptions": ["Rectangular galvanized perimeter fence."],
                "limitations": ["No structural certification."],
            }

    fake = FakeGroq()
    planner = GeometryProgramPlanner(fake)  # type: ignore[arg-type]

    program = planner.plan(
        prompt=(
            "Créer une clôture périmétrique rectangulaire galvanisée de 14 x 14 m, "
            "hauteur 2,4 m, avec un portail de 4 m."
        ),
        semantic_role="perimeter fence",
        design_context={"site_envelope_m": {"x": 14.0, "y": 14.0, "z": 2.4}},
    )

    assert fake.call_count == 1
    profile = next(node for node in program.nodes if node.node_id == "fence_panel_profile")
    assert profile.parent_id is None
    assert profile.material_id is None
    assert profile.semantic_role is None
    assert profile.transform.model_dump(mode="json") == {
        "translation_m": _xyz(0.0, 0.0, 0.0),
        "rotation_deg": _xyz(0.0, 0.0, 0.0),
        "scale": _xyz(1.0, 1.0, 1.0),
    }
    assert "fence_panel_profile" in program.construction_node_ids
    assert program.deterministic_adjustments
    assert "transform-free geometry profile" in program.deterministic_adjustments[0]


def test_profile_normalization_is_idempotent() -> None:
    payload = _v2_program_payload()
    profile = _v2_node(payload, "rail_profile")
    profile["transform"] = {"translation_m": _xyz(1.0, 2.0, 3.0)}
    profile["material_id"] = "steel"

    _normalize_profile_definitions(payload)
    first = json.loads(json.dumps(payload))
    _normalize_profile_definitions(payload)

    assert payload == first
    GeometryProgram.model_validate(payload)


def test_geometry_program_planner_removes_safe_explicit_point_ellipsis() -> None:
    class FakeGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.call_count = 0

        def request_json(self, payload, *, policy):
            self.call_count += 1
            candidate = _v2_program_payload()
            path = _v2_node(candidate, "handrail")["path_points_m"]
            path.insert(3, {"...": "..."})
            return candidate

    fake = FakeGroq()
    planner = GeometryProgramPlanner(fake)  # type: ignore[arg-type]

    program = planner.plan(
        prompt="Créer un escalier technique avec garde-corps et palier.",
        semantic_role="technical staircase",
        design_context={"design_domain": "generic_technical_access"},
    )

    assert fake.call_count == 1
    handrail = next(node for node in program.nodes if node.node_id == "handrail")
    assert len(handrail.path_points_m) == 3
    assert any(
        "explicit non-geometric ellipsis" in adjustment
        for adjustment in program.deterministic_adjustments
    )


def test_point_ellipsis_normalization_is_idempotent_and_keeps_unsafe_list_invalid() -> None:
    payload = _v2_program_payload()
    handrail = _v2_node(payload, "handrail")
    handrail["path_points_m"].append({"x": "…", "y": "…", "z": "…"})

    _normalize_explicit_point_placeholders(payload)
    first = json.loads(json.dumps(payload))
    _normalize_explicit_point_placeholders(payload)

    assert payload == first
    assert len(handrail["path_points_m"]) == 3
    GeometryProgram.model_validate(payload)

    unsafe = _v2_program_payload()
    profile = _v2_node(unsafe, "rail_profile")
    profile["points_m"] = [_xy(-0.1, -0.1), {"...": "..."}, _xy(0.1, 0.1)]
    before = json.loads(json.dumps(unsafe))

    _normalize_explicit_point_placeholders(unsafe)

    assert unsafe == before
    with pytest.raises(ValidationError):
        GeometryProgram.model_validate(unsafe)


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_compiles_validated_geometry_program_without_executing_model_code(
    tmp_path: Path,
) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    scene = (
        ScenePlanner()
        .build_scene_spec(
            "wf_geometry_program",
            requirements,
            tower,
            antenna,
            radio,
        )
        .model_copy(
            update={"geometry_programs": [GeometryProgram.model_validate(_program_payload())]}
        )
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated", result.error
    assert result.mode == "real_blender"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    record = next(
        item
        for item in metadata["asset_imports"]
        if item["asset_id"] == "GEOMETRY_PROGRAM_SITE_SHELTER"
    )
    assert record["import_mode"] == "internal_project_generated"
    assert record["generation_success"] is True
    assert record["generated_object_count"] == 6
    assert record["asset_metadata"]["program_authorship"] == "llm_generated"
    assert record["asset_metadata"]["requested_quantity"] == 1
    assert record["asset_metadata"]["qualification_status"] == "validated_geometry_program"
    assert len(record["asset_metadata"]["program_sha256"]) == 64
    glb = _read_glb_json(Path(result.artifacts["glb"]))
    nodes = {node.get("name"): node.get("extras", {}) for node in glb["nodes"]}
    assert nodes["site_shelter_body"]["role"] == "equipment_shelter"
    assert nodes["site_shelter_body"]["semantic_root"] == "site_shelter_body"
    assert nodes["site_shelter_body"]["semantic_id"] == "site_shelter:body"
    assert nodes["program_site_shelter"]["geometry_program_authorship"] == "llm_generated"
    assert nodes["program_site_shelter"]["geometry_program_requested_quantity"] == 1
    assert "site_shelter_body" in nodes
    assert "site_shelter_door_right" in nodes


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_compiles_geometry_program_v2_closed_registry(tmp_path: Path) -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    program = GeometryProgram.model_validate(_v2_program_payload())
    scene = (
        ScenePlanner()
        .build_scene_spec(
            "wf_geometry_program_v2",
            requirements,
            tower,
            antenna,
            radio,
        )
        .model_copy(update={"geometry_programs": [program]})
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated"
    assert result.mode == "real_blender"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    record = next(
        item
        for item in metadata["asset_imports"]
        if item["asset_id"] == "GEOMETRY_PROGRAM_GENERIC_SITE_CORE"
    )
    assert record["generation_success"] is True
    assert record["generated_object_count"] >= len(program.nodes) + len(program.anchors) + 1
    assert record["asset_metadata"]["qualification_method"] == "typed_geometry_program_v2"
    assert record["asset_metadata"]["geometry_program_schema_version"] == "2.0.0"
    proofs = json.loads(Path(result.artifacts["component_proofs"]).read_text(encoding="utf-8"))
    proof = next(
        item
        for item in proofs["geometry_programs"]
        if item["component_id"] == "geometry_program:generic_site_core"
    )
    assert proof["generation_strategy"] == "typed_geometry_program_v2"
    assert proof["qa"]["passed"] is True
    glb = _read_glb_json(Path(result.artifacts["glb"]))
    nodes = {node.get("name"): node.get("extras", {}) for node in glb["nodes"]}
    root = nodes["program_generic_site_core"]
    assert root["geometry_program_schema_version"] == "2.0.0"
    assert root["geometry_program_registry"] == "generic_cognitive_3d_core_v1"
    assert root["geometry_program_anchor_count"] == 2
    steps = nodes["generic_site_core_steps"]
    assert steps["role"] == "technical_staircase"
    assert "stair_system" in steps["geometry_program_semantic_groups"]


@pytest.mark.blender_runtime
@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_compiles_generic_scene_spec_without_telecom_placeholders(
    tmp_path: Path,
) -> None:
    program = GeometryProgram.model_validate(_v2_program_payload())
    scene = SceneSpec(
        schema_version="2.0.0",
        scene_id="wf_generic_scene_v2",
        design_domain="generic",
        design_intent_id="wf_generic_scene_v2:intent:v1",
        component_graph_id="wf_generic_scene_v2:components:v1",
        asset_decision_plan_id="wf_generic_scene_v2:asset-decisions:v1",
        specialist_route_id="wf_generic_scene_v2:intent:v1:specialists:v1",
        cognitive_plan_sha256="b" * 64,
        geometry_programs=[program],
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated", result.error
    assert result.mode == "real_blender"
    metadata = json.loads(Path(result.artifacts["metadata"]).read_text(encoding="utf-8"))
    assert metadata["design_domain"] == "generic"
    assert metadata["network_type"] is None
    assert metadata["tower_height_m"] is None
    assert metadata["sector_count"] == 0
    assert metadata["cognitive_plan_sha256"] == "b" * 64
    assert Path(result.artifacts["glb"]).stat().st_size > 0
    assert Path(result.artifacts["preview"]).stat().st_size > 0
    inspection = GLBInspector().inspect(
        Path(result.artifacts["glb"]),
        scene,
        Path(result.artifacts["metadata"]),
    )
    validation = GLBGeometryValidator().validate(
        scene,
        inspection,
        Path(result.artifacts["metadata"]),
        Path(result.artifacts["glb"]),
    )
    assert inspection.structural_qa_passed is True
    assert validation.status == "passed", validation.critical_errors


def _program_payload() -> dict:
    prompt_hash = hashlib.sha256(b"create a bounded equipment shelter").hexdigest()
    return {
        "schema_version": "1.0.0",
        "program_id": "site_shelter",
        "semantic_role": "equipment_shelter",
        "requested_quantity": 1,
        "units": "meters",
        "authorship": "llm_generated",
        "generator_provider": "test_provider",
        "generator_model": "test_model",
        "structured_output_mode": "strict_json_schema",
        "source_prompt_sha256": prompt_hash,
        "materials": [
            {
                "material_id": "steel",
                "base_color_rgba": _rgba(0.55, 0.6, 0.62, 1.0),
                "metallic": 0.35,
                "roughness": 0.42,
            },
            {
                "material_id": "dark",
                "base_color_rgba": _rgba(0.08, 0.1, 0.11, 1.0),
                "metallic": 0.2,
                "roughness": 0.5,
            },
        ],
        "nodes": [
            {
                "kind": "primitive",
                "node_id": "body",
                "primitive": "box",
                "size_m": _xyz(3.0, 2.2, 2.5),
                "material_id": "steel",
                "semantic_role": "equipment_shelter",
                "transform": {"translation_m": _xyz(7.0, 0.0, 1.25)},
                "bevel_m": 0.04,
            },
            {
                "kind": "primitive",
                "node_id": "roof",
                "primitive": "box",
                "size_m": _xyz(3.3, 2.5, 0.16),
                "material_id": "steel",
                "transform": {"translation_m": _xyz(7.0, 0.0, 2.58)},
                "bevel_m": 0.03,
            },
            {
                "kind": "primitive",
                "node_id": "door_left",
                "primitive": "box",
                "size_m": _xyz(0.72, 0.08, 1.95),
                "material_id": "dark",
                "transform": {"translation_m": _xyz(6.6, -1.14, 1.12)},
                "bevel_m": 0.015,
            },
            {
                "kind": "instance",
                "node_id": "door_right",
                "source_node_id": "door_left",
                "transform": {"translation_m": _xyz(7.4, -1.14, 1.12)},
            },
            {
                "kind": "curve",
                "node_id": "grounding_route",
                "points_m": [
                    _xyz(7.0, 1.1, 0.1),
                    _xyz(5.5, 1.5, 0.05),
                    _xyz(4.0, 1.8, 0.05),
                ],
                "bevel_depth_m": 0.025,
                "material_id": "dark",
            },
        ],
        "assumptions": ["Generic outdoor equipment shelter, not vendor-specific."],
        "limitations": ["No structural or electrical certification."],
    }


def _v2_program_payload() -> dict:
    payload = {
        "schema_version": "2.0.0",
        "program_id": "generic_site_core",
        "semantic_role": "technical_staircase",
        "requested_quantity": 1,
        "units": "meters",
        "authorship": "deterministic_generated",
        "generator_provider": "test_provider",
        "generator_model": "bounded_geometry_contract",
        "structured_output_mode": "strict_json_schema",
        "source_prompt_sha256": hashlib.sha256(b"generic stairs garden telecom").hexdigest(),
        "materials": [
            {
                "material_id": "steel",
                "base_color_rgba": _rgba(0.3, 0.34, 0.38, 1.0),
                "metallic": 0.65,
                "roughness": 0.32,
            },
            {
                "material_id": "ground",
                "base_color_rgba": _rgba(0.18, 0.32, 0.12, 1.0),
                "metallic": 0.0,
                "roughness": 0.9,
            },
        ],
        "nodes": [
            {
                "kind": "primitive",
                "node_id": "step_seed",
                "primitive": "box",
                "size_m": _xyz(0.45, 1.2, 0.18),
                "material_id": "steel",
            },
            {
                "kind": "array",
                "node_id": "steps",
                "source_node_id": "step_seed",
                "count": 6,
                "offset_m": _xyz(0.42, 0.0, 0.2),
                "material_id": "steel",
                "semantic_role": "technical_staircase",
                "transform": {"translation_m": _xyz(0.0, 0.0, 0.1)},
            },
            {
                "kind": "profile",
                "node_id": "rail_profile",
                "points_m": [
                    _xy(-0.025, -0.025),
                    _xy(0.025, -0.025),
                    _xy(0.025, 0.025),
                    _xy(-0.025, 0.025),
                ],
                "closed": True,
            },
            {
                "kind": "sweep",
                "node_id": "handrail",
                "profile_node_id": "rail_profile",
                "path_points_m": [
                    _xyz(0.0, -0.7, 0.9),
                    _xyz(1.1, -0.7, 1.4),
                    _xyz(2.2, -0.7, 1.9),
                ],
                "material_id": "steel",
            },
            {
                "kind": "instance",
                "node_id": "rail_copy",
                "source_node_id": "handrail",
                "parent_id": "steps",
                "transform": {"translation_m": _xyz(0.0, 1.4, 0.0)},
            },
            {
                "kind": "modifier",
                "node_id": "mirrored_rail",
                "source_node_id": "handrail",
                "modifier": "mirror",
                "mirror_axes": ["y"],
                "material_id": "steel",
            },
            {
                "kind": "profile",
                "node_id": "landing_profile",
                "points_m": [
                    _xy(-0.8, -0.8),
                    _xy(0.8, -0.8),
                    _xy(0.8, 0.8),
                    _xy(-0.8, 0.8),
                ],
                "closed": True,
            },
            {
                "kind": "extrude",
                "node_id": "landing",
                "profile_node_id": "landing_profile",
                "depth_m": 0.16,
                "material_id": "steel",
                "transform": {"translation_m": _xyz(2.5, 0.0, 1.2)},
            },
            {
                "kind": "profile",
                "node_id": "planter_profile",
                "points_m": [
                    _xy(0.35, 0.0),
                    _xy(0.48, 0.0),
                    _xy(0.48, 0.6),
                    _xy(0.35, 0.6),
                ],
                "closed": True,
            },
            {
                "kind": "revolve",
                "node_id": "planter",
                "profile_node_id": "planter_profile",
                "angle_deg": 360.0,
                "segments": 24,
                "material_id": "steel",
                "transform": {"translation_m": _xyz(4.0, 2.0, 0.0)},
            },
            {
                "kind": "terrain",
                "node_id": "terrain_surface",
                "width_m": 8.0,
                "depth_m": 6.0,
                "columns": 3,
                "rows": 3,
                "heights_m": [0.0, 0.04, 0.0, 0.03, 0.08, 0.02, 0.0, 0.02, 0.0],
                "material_id": "ground",
            },
            {
                "kind": "modifier",
                "node_id": "terrain_solid",
                "source_node_id": "terrain_surface",
                "modifier": "solidify",
                "thickness_m": -0.12,
                "material_id": "ground",
            },
            {
                "kind": "primitive",
                "node_id": "wall_source",
                "primitive": "box",
                "size_m": _xyz(2.8, 0.3, 2.2),
                "material_id": "steel",
            },
            {
                "kind": "primitive",
                "node_id": "door_cutter",
                "primitive": "box",
                "size_m": _xyz(0.9, 0.5, 1.8),
            },
            {
                "kind": "boolean",
                "node_id": "wall_opening",
                "left_node_id": "wall_source",
                "right_node_id": "door_cutter",
                "operation": "difference",
                "solver": "exact",
                "material_id": "steel",
            },
            {
                "kind": "modifier",
                "node_id": "beveled_wall",
                "source_node_id": "wall_opening",
                "modifier": "bevel",
                "width_m": 0.03,
                "segments": 2,
                "material_id": "steel",
                "transform": {"translation_m": _xyz(5.0, -2.0, 1.1)},
            },
        ],
        "anchors": [
            {
                "anchor_id": "stair_base",
                "node_id": "steps",
                "position_m": _xyz(0.0, 0.0, 0.0),
                "normal": _xyz(-1.0, 0.0, 0.0),
                "up": _xyz(0.0, 0.0, 1.0),
            },
            {
                "anchor_id": "stair_top",
                "node_id": "landing",
                "position_m": _xyz(0.0, 0.0, 0.08),
                "normal": _xyz(1.0, 0.0, 0.0),
                "up": _xyz(0.0, 0.0, 1.0),
            },
        ],
        "connectors": [
            {
                "connector_id": "base_mount",
                "anchor_id": "stair_base",
                "kind": "mechanical",
                "gender": "source",
                "compatible_kinds": ["mechanical"],
                "tolerance_m": 0.02,
            },
            {
                "connector_id": "top_mount",
                "anchor_id": "stair_top",
                "kind": "mechanical",
                "gender": "target",
                "compatible_kinds": ["mechanical"],
                "tolerance_m": 0.02,
            },
        ],
        "semantic_groups": [
            {
                "group_id": "stair_system",
                "semantic_role": "access_system",
                "node_ids": ["steps", "handrail", "rail_copy", "mirrored_rail", "landing"],
            },
            {
                "group_id": "garden_system",
                "semantic_role": "landscape",
                "node_ids": ["planter", "terrain_solid"],
            },
            {
                "group_id": "telecom_enclosure",
                "semantic_role": "equipment_boundary",
                "node_ids": ["beveled_wall"],
            },
        ],
        "construction_node_ids": [
            "step_seed",
            "rail_profile",
            "landing_profile",
            "planter_profile",
            "terrain_surface",
            "wall_source",
            "door_cutter",
            "wall_opening",
        ],
        "assumptions": ["Generic technical access and landscape geometry."],
        "limitations": ["No structural, accessibility or civil-engineering certification."],
    }
    return payload


def _v2_node(payload: dict, node_id: str) -> dict:
    return next(node for node in payload["nodes"] if node["node_id"] == node_id)


def _xyz(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _xy(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _rgba(r: float, g: float, b: float, a: float) -> dict[str, float]:
    return {"r": r, "g": g, "b": b, "a": a}


def _read_glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    assert chunk_type == 0x4E4F534A
    return json.loads(payload[20 : 20 + chunk_length].rstrip(b" \x00"))
