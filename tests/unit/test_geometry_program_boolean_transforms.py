import hashlib
import json
import shutil
from pathlib import Path

import pytest

from core.agents.geometry_program_planner import _fit_to_maximum_dimensions
from core.contracts.geometry_program import GeometryProgram, geometry_program_dimensions
from core.contracts.scene import SceneSpec
from core.services.blender_runner import BlenderRunner


def test_boolean_envelope_includes_translated_operand_transforms() -> None:
    program = GeometryProgram.model_validate(_translated_boolean_program_payload())

    assert geometry_program_dimensions(program) == pytest.approx((6.0, 2.0, 2.0))


def test_difference_cutter_never_inflates_visible_envelope() -> None:
    payload = _translated_boolean_program_payload()
    cutter = next(node for node in payload["nodes"] if node["node_id"] == "cutter")
    cutter["size_m"] = _xyz(40.0, 20.0, 10.0)

    program = GeometryProgram.model_validate(payload)

    assert geometry_program_dimensions(program) == pytest.approx((6.0, 2.0, 2.0))


def test_envelope_adapter_scales_only_visible_boolean_outputs() -> None:
    payload = _translated_boolean_program_payload()
    payload["maximum_dimensions_m"] = _xyz(5.4, 1.8, 1.8)
    unbounded_payload = json.loads(json.dumps(payload))
    unbounded_payload["maximum_dimensions_m"] = None
    canonical_unbounded = GeometryProgram.model_validate(unbounded_payload).model_dump(mode="json")
    original_construction_transforms = {
        node["node_id"]: node["transform"]
        for node in canonical_unbounded["nodes"]
        if node["node_id"] in canonical_unbounded["construction_node_ids"]
    }

    fitted = _fit_to_maximum_dimensions(payload)

    assert fitted is not None
    program = GeometryProgram.model_validate(fitted)
    assert geometry_program_dimensions(program) == pytest.approx((5.4, 1.8, 1.8))
    assert {
        node["node_id"]: node.get("transform")
        for node in fitted["nodes"]
        if node["node_id"] in fitted["construction_node_ids"]
    } == original_construction_transforms
    result = next(node for node in fitted["nodes"] if node["node_id"] == "result")
    assert result["transform"]["scale"] == pytest.approx(_xyz(0.9, 0.9, 0.9))


@pytest.mark.skipif(
    shutil.which("blender") is None
    and not Path("/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender").exists()
    and not Path("/Applications/Blender.app/Contents/MacOS/Blender").exists(),
    reason="Blender executable is not available",
)
def test_blender_exact_booleans_preserve_translated_operand_bounds(tmp_path: Path) -> None:
    program = GeometryProgram.model_validate(_translated_boolean_program_payload())
    scene = SceneSpec(
        schema_version="2.0.0",
        scene_id="wf_boolean_transform",
        design_domain="generic",
        design_intent_id="wf_boolean_transform:intent:v1",
        component_graph_id="wf_boolean_transform:components:v1",
        asset_decision_plan_id="wf_boolean_transform:asset-decisions:v1",
        specialist_route_id="wf_boolean_transform:intent:v1:specialists:v1",
        cognitive_plan_sha256="c" * 64,
        geometry_programs=[program],
    )

    result = BlenderRunner(project_root=Path.cwd()).generate(scene, tmp_path)

    assert result.status == "generated", result.error
    assert result.mode == "real_blender"
    proofs = json.loads(Path(result.artifacts["component_proofs"]).read_text(encoding="utf-8"))
    proof = next(
        item
        for item in proofs["geometry_programs"]
        if item["component_id"] == "geometry_program:boolean_transform_regression"
    )
    bounds = proof["bounding_box_m"]
    assert bounds["minimum_m"] == pytest.approx([8.0, -1.0, 1.0], abs=1e-5)
    assert bounds["maximum_m"] == pytest.approx([14.0, 1.0, 3.0], abs=1e-5)
    assert proof["qa"]["passed"] is True


def _translated_boolean_program_payload() -> dict:
    return {
        "schema_version": "2.0.0",
        "program_id": "boolean_transform_regression",
        "semantic_role": "test_enclosure",
        "requested_quantity": 1,
        "units": "meters",
        "authorship": "deterministic_generated",
        "generator_provider": "test_provider",
        "generator_model": "test_model",
        "structured_output_mode": "strict_json_schema",
        "source_prompt_sha256": hashlib.sha256(b"translated exact boolean regression").hexdigest(),
        "source_description": "Translated boxes combined through exact union and difference.",
        "source_description_origin": "user_requirement",
        "maximum_dimensions_m": _xyz(6.0, 2.0, 2.0),
        "materials": [],
        "nodes": [
            {
                "kind": "primitive",
                "node_id": "left_box",
                "primitive": "box",
                "size_m": _xyz(4.0, 2.0, 2.0),
                "transform": {"translation_m": _xyz(10.0, 0.0, 2.0)},
            },
            {
                "kind": "primitive",
                "node_id": "right_box",
                "primitive": "box",
                "size_m": _xyz(4.0, 2.0, 2.0),
                "transform": {"translation_m": _xyz(12.0, 0.0, 2.0)},
            },
            {
                "kind": "primitive",
                "node_id": "cutter",
                "primitive": "box",
                "size_m": _xyz(1.0, 2.0, 1.0),
                "transform": {"translation_m": _xyz(10.0, 0.0, 2.0)},
            },
            {
                "kind": "boolean",
                "node_id": "combined",
                "left_node_id": "left_box",
                "right_node_id": "right_box",
                "operation": "union",
                "solver": "exact",
            },
            {
                "kind": "boolean",
                "node_id": "result",
                "left_node_id": "combined",
                "right_node_id": "cutter",
                "operation": "difference",
                "solver": "exact",
                "semantic_role": "test_enclosure",
            },
        ],
        "construction_node_ids": ["left_box", "right_box", "cutter", "combined"],
        "assumptions": [],
        "limitations": [],
    }


def _xyz(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}
