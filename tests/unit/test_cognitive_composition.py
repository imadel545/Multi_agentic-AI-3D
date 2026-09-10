from copy import deepcopy

import pytest

from core.contracts.cognitive_design import CognitiveDesignPlan
from core.qa.rigid_relation_inspector import inspect_rigid_relations
from core.services.cognitive_scene_compiler import CognitiveSceneCompiler
from tests.unit.test_cognitive_asset_reuse import reuse_plan


def composition_plan(offset=0.8):
    registry, raw = reuse_plan()
    components = raw["component_graph"]["components"]
    first = components[0]
    second = deepcopy(first)
    second["component_id"] = "panel_b"
    components.append(second)
    decisions = raw["asset_decision_plan"]["decisions"]
    second_decision = deepcopy(decisions[0])
    second_decision.update(component_id="panel_b", strategy="compose", placement=None)
    decisions.append(second_decision)
    raw["component_graph"]["relationships"] = [
        {
            "relationship_id": "panel_alignment",
            "kind": "aligned_with",
            "source_component_id": "panel_b",
            "target_component_id": first["component_id"],
            "required": True,
            "parameters": {"offset_world_m": {"x": offset, "y": 0, "z": 0}},
        }
    ]
    return registry, raw


def compile_plan(registry, raw):
    return CognitiveSceneCompiler(registry=registry).compile(
        workflow_id="wf_composition",
        plan=CognitiveDesignPlan.model_validate(raw),
        geometry_programs=[],
    )


def test_relation_controls_real_compiler_placement_without_mutating_plan():
    registry, raw = composition_plan()
    original = deepcopy(raw)
    scene = compile_plan(registry, raw)
    assert raw == original
    first, second = scene.geometry_programs
    assert first.nodes[0].transform.translation_m.x == 0
    assert second.nodes[0].transform.translation_m.x == pytest.approx(0.8)
    assert second.nodes[0].transform.translation_m.z == 1
    assert scene.rigid_component_relations[0].source_program_id == second.program_id
    assert first.nodes[0].asset_sha256 == second.nodes[0].asset_sha256
    raw["component_graph"]["relationships"][0]["parameters"]["offset_world_m"]["x"] = 1.2
    changed = compile_plan(registry, raw)
    assert changed.geometry_programs[0] == first
    assert changed.geometry_programs[1].nodes[0].transform.translation_m.x == 1.2


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("missing", "REQUIRES_ALIGNMENT_DRIVER"),
        ("kind", "RELATION_UNSUPPORTED"),
        ("placement", "PLACEMENT_MUST_BE_DERIVED"),
        ("far", "TRANSFORM_OUT_OF_BOUNDS"),
        ("cycle", "CYCLE"),
        ("multiple", "MULTIPLE_DRIVERS"),
        ("nan", "finite"),
        ("port", "port"),
        ("parameters", "RELATION_UNSUPPORTED"),
    ],
)
def test_unsupported_composition_is_refused(mutation, error):
    registry, raw = composition_plan()
    relationships = raw["component_graph"]["relationships"]
    if mutation == "missing":
        relationships.clear()
    elif mutation == "kind":
        relationships[0]["kind"] = "supported_by"
    elif mutation == "placement":
        raw["asset_decision_plan"]["decisions"][1]["placement"] = {
            "translation_m": {"x": 1, "y": 0, "z": 0}
        }
    elif mutation in {"far", "nan"}:
        relationships[0]["parameters"]["offset_world_m"]["x"] = (
            101 if mutation == "far" else float("nan")
        )
    elif mutation == "cycle":
        first = raw["asset_decision_plan"]["decisions"][0]
        first.update(strategy="compose", placement=None)
        relationships.append(
            {
                **relationships[0],
                "relationship_id": "cycle",
                "source_component_id": first["component_id"],
                "target_component_id": "panel_b",
            }
        )
    elif mutation == "multiple":
        relationships.append({**relationships[0], "relationship_id": "second_driver"})
    elif mutation == "port":
        relationships[0]["source_port_id"] = "invented"
    elif mutation == "parameters":
        relationships[0]["parameters"]["scale"] = 2
    with pytest.raises(ValueError, match=error):
        compile_plan(registry, raw)


def test_exported_relation_qa_detects_displacement_rotation_and_missing_identity():
    registry, raw = composition_plan()
    scene = compile_plan(registry, raw)
    payload = {
        "nodes": [
            {
                "translation": [x, 1, 0],
                "extras": {
                    "geometry_program_id": program.program_id,
                    "geometry_program_node_id": "catalog_asset",
                },
            }
            for x, program in zip((0, 0.8), scene.geometry_programs, strict=True)
        ]
    }
    for index, program in enumerate(scene.geometry_programs):
        payload["nodes"][index]["children"] = [len(payload["nodes"])]
        payload["nodes"].append(
            {"mesh": index, "extras": {"geometry_program_id": program.program_id}}
        )
    assert all(check.passed for check in inspect_rigid_relations(scene, payload))
    payload["nodes"][1]["translation"][0] = 0.9
    assert not all(check.passed for check in inspect_rigid_relations(scene, payload))
    payload["nodes"][1]["translation"][0] = 0.8
    payload["nodes"][1]["rotation"] = [0, 0, 1, 0]
    assert not all(check.passed for check in inspect_rigid_relations(scene, payload))
    payload["nodes"][1].pop("rotation")
    payload["nodes"][1].pop("children")
    assert not all(check.passed for check in inspect_rigid_relations(scene, payload))
