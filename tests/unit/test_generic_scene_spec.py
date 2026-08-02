from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from core.contracts.scene import SceneSpec


def _program() -> dict:
    return {
        "program_id": "generic_structure.llm_v1",
        "semantic_role": "generic_structure",
        "requested_quantity": 1,
        "authorship": "llm_generated",
        "generator_provider": "groq",
        "generator_model": "openai/gpt-oss-120b",
        "structured_output_mode": "strict_json_schema",
        "source_prompt_sha256": hashlib.sha256(b"generic structure").hexdigest(),
        "nodes": [
            {
                "kind": "primitive",
                "node_id": "structure",
                "primitive": "box",
                "size_m": {"x": 2.0, "y": 2.0, "z": 0.2},
                "semantic_role": "generic_structure",
            },
            {
                "kind": "primitive",
                "node_id": "support_left",
                "primitive": "box",
                "size_m": {"x": 0.2, "y": 0.2, "z": 2.0},
            },
            {
                "kind": "primitive",
                "node_id": "support_right",
                "primitive": "box",
                "size_m": {"x": 0.2, "y": 0.2, "z": 2.0},
            },
        ],
    }


def test_scene_spec_v2_accepts_governed_generic_geometry_without_telecom_placeholders() -> None:
    scene = SceneSpec.model_validate(
        {
            "schema_version": "2.0.0",
            "scene_id": "wf_123456789abc",
            "design_domain": "generic",
            "design_intent_id": "wf_123456789abc:intent:v1",
            "component_graph_id": "wf_123456789abc:components:v1",
            "asset_decision_plan_id": "wf_123456789abc:asset-decisions:v1",
            "specialist_route_id": "wf_123456789abc:intent:v1:specialists:v1",
            "cognitive_plan_sha256": "a" * 64,
            "detail_level": "high",
            "geometry_programs": [_program()],
        }
    )

    assert scene.network_type is None
    assert scene.tower is None
    assert scene.sectors == []
    assert scene.model_dump(mode="json")["design_domain"] == "generic"


def test_scene_spec_v2_rejects_empty_or_telecom_disguised_generic_scene() -> None:
    with pytest.raises(ValidationError, match="governed geometry"):
        SceneSpec.model_validate(
            {
                "schema_version": "2.0.0",
                "scene_id": "wf_123456789abc",
                "design_domain": "generic",
                "design_intent_id": "wf_123456789abc:intent:v1",
                "component_graph_id": "wf_123456789abc:components:v1",
                "asset_decision_plan_id": "wf_123456789abc:asset-decisions:v1",
                "specialist_route_id": "wf_123456789abc:intent:v1:specialists:v1",
                "cognitive_plan_sha256": "a" * 64,
            }
        )
