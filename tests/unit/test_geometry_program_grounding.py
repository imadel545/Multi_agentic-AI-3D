import hashlib
import json

import pytest

from core.agents.geometry_program_planner import _normalize_ground_contact
from core.contracts.geometry_program import (
    GeometryProgram,
    geometry_program_bounds,
    geometry_program_dimensions,
)


def test_asymmetric_sweep_envelope_matches_one_sided_profile() -> None:
    payload = _ground_fence_payload()
    payload["maximum_dimensions_m"] = None
    program = GeometryProgram.model_validate(payload)

    minimum, maximum = geometry_program_bounds(program)

    assert minimum == pytest.approx((0.0, 0.0, -2.4), abs=1e-6)
    assert 13.9 < maximum[0] <= 14.0
    assert 13.9 < maximum[1] <= 14.0
    assert maximum[2] == pytest.approx(1.2)
    dimensions = geometry_program_dimensions(program)
    assert 13.9 < dimensions[0] <= 14.0
    assert 13.9 < dimensions[1] <= 14.0
    assert dimensions[2] == pytest.approx(3.6)


def test_ground_contact_normalizer_aligns_each_visible_root_once() -> None:
    payload = _ground_fence_payload()

    _normalize_ground_contact(payload)
    first = json.loads(json.dumps(payload))
    _normalize_ground_contact(payload)

    assert payload == first
    program = GeometryProgram.model_validate(payload)
    minimum, maximum = geometry_program_bounds(program)
    assert minimum == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert 13.9 < maximum[0] <= 14.0
    assert 13.9 < maximum[1] <= 14.0
    assert maximum[2] == pytest.approx(2.4)
    dimensions = geometry_program_dimensions(program)
    assert 13.9 < dimensions[0] <= 14.0
    assert 13.9 < dimensions[1] <= 14.0
    assert dimensions[2] == pytest.approx(2.4)
    roots = {node.node_id: node for node in program.nodes}
    assert roots["fence_sweep"].transform.translation_m.z == pytest.approx(2.4)
    assert roots["fence_post"].transform.translation_m.z == pytest.approx(1.2)
    assert program.deterministic_adjustments == [
        (
            "Aligned ground-contact visible root envelope(s) to Z=0 "
            "(fence_post:+1.200000m, fence_sweep:+2.400000m); geometry and XY "
            "placement were unchanged."
        )
    ]


def test_explicit_elevated_context_is_never_ground_aligned() -> None:
    payload = _ground_fence_payload()
    payload["placement_context"] = "Elevated and mounted on tower at height 20 m"
    before = json.loads(json.dumps(payload))

    _normalize_ground_contact(payload)

    assert payload == before


def _ground_fence_payload() -> dict:
    return {
        "schema_version": "2.0.0",
        "program_id": "ground_fence_regression",
        "semantic_role": "perimeter_fence",
        "requested_quantity": 1,
        "units": "meters",
        "authorship": "llm_generated",
        "generator_provider": "groq",
        "generator_model": "openai/gpt-oss-120b",
        "structured_output_mode": "json_object_repaired",
        "source_prompt_sha256": hashlib.sha256(b"ground fence regression").hexdigest(),
        "source_description": "Rectangular perimeter fence around the site.",
        "source_description_origin": "user_requirement",
        "placement_context": "around tower and power cabinet, no intersection",
        "maximum_dimensions_m": _xyz(14.0, 14.0, 2.4),
        "materials": [],
        "nodes": [
            {
                "kind": "profile",
                "node_id": "fence_profile",
                "points_m": [
                    _xy(-0.025, 0.0),
                    _xy(0.025, 0.0),
                    _xy(0.025, 2.4),
                    _xy(-0.025, 2.4),
                ],
                "closed": True,
            },
            {
                "kind": "sweep",
                "node_id": "fence_sweep",
                "profile_node_id": "fence_profile",
                "path_points_m": [
                    _xyz(0.025, 0.025, 0.0),
                    _xyz(13.975, 0.025, 0.0),
                    _xyz(13.975, 13.975, 0.0),
                    _xyz(0.025, 13.975, 0.0),
                    _xyz(0.025, 0.025, 0.0),
                ],
                "cyclic": True,
                "semantic_role": "perimeter_fence",
            },
            {
                "kind": "primitive",
                "node_id": "fence_post",
                "primitive": "cylinder",
                "radius_m": 0.025,
                "height_m": 2.4,
                "vertices": 24,
                "transform": {"translation_m": _xyz(0.025, 0.025, 0.0)},
            },
        ],
        "construction_node_ids": ["fence_profile"],
        "assumptions": [],
        "limitations": [],
        "deterministic_adjustments": [],
    }


def _xyz(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _xy(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}
