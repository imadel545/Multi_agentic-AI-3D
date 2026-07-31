import hashlib
import json
import shutil
import struct
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agents.geometry_program_planner import (
    GeometryProgramPlanner,
    _fit_to_maximum_dimensions,
    _normalize_disclosures,
)
from core.agents.scene_planner import ScenePlanner
from core.contracts.geometry_program import GeometryProgram, GeometryProgramVector3
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

    assert program.program_id == "equipment_shelter.llm_v1"
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

    assert result.status == "generated"
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


def _xyz(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _rgba(r: float, g: float, b: float, a: float) -> dict[str, float]:
    return {"r": r, "g": g, "b": b, "a": a}


def _read_glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    assert chunk_type == 0x4E4F534A
    return json.loads(payload[20 : 20 + chunk_length].rstrip(b" \x00"))
