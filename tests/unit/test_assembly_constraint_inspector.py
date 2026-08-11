from __future__ import annotations

import json
import math
import struct
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from core.agents.scene_planner import ScenePlanner
from core.contracts.assembly import AssemblyPlan
from core.contracts.assembly_evidence import AssemblyConstraintEvidence
from core.qa.assembly_constraint_inspector import AssemblyConstraintInspector
from core.services.assembly_compiler import _euler_xyz_matrix
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = PROJECT_ROOT / "assets" / "manifests"


def test_inspector_measures_hierarchical_trs_marker_and_fixed_roots_in_scenespec_space(
    tmp_path: Path,
) -> None:
    plan = _resolved_plan(include_rru=False)
    glb_path = tmp_path / "three_part_assembly.glb"
    _write_plan_glb(glb_path, plan, encode_one_root_as_trs=True)

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "passed"
    assert evidence.coordinate_space == "scenespec_z_up_meters"
    assert evidence.expected_measurement_count == 2
    assert evidence.measured_constraint_count == 2
    assert evidence.failed_constraint_count == 0
    assert evidence.errors == []
    by_connection = {item.connection_id: item for item in evidence.measurements}
    mount = by_connection["mount-to-support"]
    assert mount.source_frame.source == "glb_fixed_anchor"
    assert mount.target_frame.source == "glb_resolved_anchor"
    assert mount.target_frame.gltf_node_name == "constraint_marker_mount-to-support_S1_target"
    antenna = by_connection["antenna-to-mount"]
    assert antenna.source_frame.source == "glb_fixed_anchor"
    assert antenna.target_frame.source == "glb_fixed_anchor"
    assert antenna.position_error_m == pytest.approx(0.0, abs=1e-9)
    assert antenna.normal_opposition_error_deg == pytest.approx(0.0, abs=1e-7)
    assert antenna.up_alignment_error_deg == pytest.approx(0.0, abs=1e-7)
    assert all(item.passed for item in evidence.measurements)
    assert all(
        frame.gltf_node_index is not None
        for item in evidence.measurements
        for frame in (item.source_frame, item.target_frame)
    )
    assert len(evidence.limitations) == 3


@pytest.mark.parametrize(
    ("marker_mode", "expected_error"),
    [
        ("absent", "ASSEMBLY_CONSTRAINT_MARKER_MISSING"),
        ("duplicate", "ASSEMBLY_CONSTRAINT_MARKER_DUPLICATE"),
        ("mismatched", "ASSEMBLY_CONSTRAINT_MARKER_MISMATCH"),
    ],
)
def test_inspector_fails_closed_for_missing_duplicate_or_mismatched_marker(
    tmp_path: Path,
    marker_mode: str,
    expected_error: str,
) -> None:
    plan = _resolved_plan(include_rru=False)
    glb_path = tmp_path / f"marker_{marker_mode}.glb"
    _write_plan_glb(glb_path, plan, marker_mode=marker_mode)

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "failed"
    assert evidence.expected_measurement_count == 2
    assert evidence.measured_constraint_count == 1
    assert evidence.failed_constraint_count == 0
    assert any(expected_error in error for error in evidence.errors)
    assert all(
        frame.gltf_node_index is not None
        for item in evidence.measurements
        for frame in (item.source_frame, item.target_frame)
    )


def test_inspector_measures_and_rejects_known_marker_offset(tmp_path: Path) -> None:
    plan = _resolved_plan(include_rru=False)
    glb_path = tmp_path / "known_marker_offset.glb"
    _write_plan_glb(
        glb_path,
        plan,
        marker_offset=("mount-to-support", "S1", "target", (0.02, 0.0, 0.0)),
    )

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "failed"
    assert evidence.measured_constraint_count == 2
    assert evidence.failed_constraint_count == 1
    failure = next(item for item in evidence.measurements if not item.passed)
    assert failure.connection_id == "mount-to-support"
    assert failure.target_frame.source == "glb_resolved_anchor"
    assert failure.position_error_m == pytest.approx(0.02, abs=1e-9)
    assert failure.position_error_m > failure.position_tolerance_m
    assert evidence.errors == []


def test_inspector_exposes_non_mechanical_limit_after_all_mechanical_markers_pass(
    tmp_path: Path,
) -> None:
    plan = _resolved_plan(include_rru=True)
    glb_path = tmp_path / "radio_resolved_marker.glb"
    _write_plan_glb(glb_path, plan)

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "passed"
    assert evidence.expected_measurement_count == 3
    assert evidence.measured_constraint_count == 3
    assert evidence.failed_constraint_count == 0
    radio = next(item for item in evidence.measurements if item.connection_id == "radio-to-mount")
    assert radio.source_frame.source == "glb_fixed_anchor"
    assert radio.target_frame.source == "glb_resolved_anchor"
    assert radio.target_frame.resolved_support is not None
    assert radio.target_frame.resolved_support.support_anchor_id == "radio_adapter_base"
    assert radio.target_frame.resolved_support.resolved_anchor_id == "radio_rail"
    assert radio.target_frame.resolved_support.gltf_node_name == (
        "constraint_support_radio-to-mount_S1_target"
    )
    assert radio.target_frame.resolved_support.gltf_node_index >= 0
    assert radio.target_frame.resolved_support.gltf_mesh_index == 0
    assert radio.passed is True
    assert radio.source_frame.gltf_node_index is not None
    assert radio.target_frame.gltf_node_index is not None
    assert [item.model_dump() for item in evidence.unevaluated_required_connections] == [
        {
            "connection_id": "antenna-to-radio-rf",
            "kind": "rf",
            "required": True,
            "reason": "non_mechanical_connection_not_evaluated_by_v1",
        }
    ]


@pytest.mark.parametrize(
    ("support_mode", "expected_error"),
    [
        ("absent", "ASSEMBLY_CONSTRAINT_SUPPORT_MISSING"),
        ("duplicate", "ASSEMBLY_CONSTRAINT_SUPPORT_DUPLICATE"),
        ("mismatched", "ASSEMBLY_CONSTRAINT_SUPPORT_MISMATCH"),
        ("not_mesh", "ASSEMBLY_CONSTRAINT_SUPPORT_NOT_MESH"),
    ],
)
def test_inspector_fails_closed_for_invalid_resolved_endpoint_support(
    tmp_path: Path,
    support_mode: str,
    expected_error: str,
) -> None:
    plan = _resolved_plan(include_rru=True)
    glb_path = tmp_path / f"support_{support_mode}.glb"
    _write_plan_glb(glb_path, plan, support_mode=support_mode)

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "failed"
    assert evidence.expected_measurement_count == 3
    assert evidence.measured_constraint_count == 2
    assert any(expected_error in error for error in evidence.errors)


def test_inspector_does_not_fallback_per_sector_component_root_to_global(
    tmp_path: Path,
) -> None:
    plan = _resolved_plan(include_rru=False)
    glb_path = tmp_path / "wrong_global_antenna_root.glb"
    _write_plan_glb(
        glb_path,
        plan,
        force_global_root_for_role="sector_antenna",
    )

    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    assert evidence.status == "failed"
    assert any(
        "ASSEMBLY_COMPONENT_ROOT_MISSING:sector_antenna:S1" in error for error in evidence.errors
    )


def test_evidence_hash_is_canonical_and_rejects_altered_measurement(tmp_path: Path) -> None:
    plan = _resolved_plan(include_rru=False)
    glb_path = tmp_path / "assembly.glb"
    _write_plan_glb(glb_path, plan)
    evidence = AssemblyConstraintInspector().inspect(glb_path, plan)

    round_trip = AssemblyConstraintEvidence.model_validate_json(evidence.model_dump_json())
    assert round_trip.evidence_sha256 == evidence.evidence_sha256

    altered = deepcopy(evidence.model_dump(mode="json"))
    altered["limitations"][0] += " Altered."
    with pytest.raises(ValidationError, match="assembly constraint evidence hash mismatch"):
        AssemblyConstraintEvidence.model_validate(altered)


def test_inspector_rejects_unresolved_or_legacy_plan(tmp_path: Path) -> None:
    resolved = _resolved_plan(include_rru=False)
    declared_payload = resolved.model_dump(mode="json")
    declared_payload["compilation_status"] = "declared"
    declared_payload["operations"] = []
    declared = AssemblyPlan.model_validate(declared_payload)

    with pytest.raises(
        ValueError,
        match="ASSEMBLY_CONSTRAINT_EVIDENCE_REQUIRES_RESOLVED_PLAN",
    ):
        AssemblyConstraintInspector().inspect(tmp_path / "unused.glb", declared)

    legacy = AssemblyPlan.model_construct(
        schema_version="1.0.0",
        compilation_status="legacy_uncompiled",
    )
    with pytest.raises(
        ValueError,
        match="ASSEMBLY_CONSTRAINT_EVIDENCE_REQUIRES_PLAN_1_1",
    ):
        AssemblyConstraintInspector().inspect(tmp_path / "unused.glb", legacy)


def _resolved_plan(*, include_rru: bool) -> AssemblyPlan:
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 1 secteur à 24m. Azimut : 0°."
    ).model_copy(
        update={
            "include_rru": include_rru,
            "include_cables": False,
            "include_power_cabinet": False,
            "include_gps_antenna": False,
        }
    )
    planning = AssetAssemblyPlanner(AssetRegistry(MANIFESTS_DIR)).plan(
        workflow_id=("wf_constraint_with_radio" if include_rru else "wf_constraint_three_part"),
        requirements=requirements,
    )
    scene = ScenePlanner().build_scene_spec(
        planning.plan.workflow_id,
        requirements,
        planning.assets_by_role["support_structure"],
        planning.assets_by_role["sector_antenna"],
        planning.assets_by_role.get("remote_radio"),
        assembly_plan=planning.plan,
    )
    assert scene.assembly_plan is not None
    assert scene.assembly_plan.schema_version == "1.1.0"
    assert scene.assembly_plan.compilation_status == "resolved"
    return scene.assembly_plan


def _write_plan_glb(
    path: Path,
    plan: AssemblyPlan,
    *,
    encode_one_root_as_trs: bool = False,
    marker_mode: str = "normal",
    support_mode: str = "normal",
    force_global_root_for_role: str | None = None,
    marker_offset: tuple[str, str, str, tuple[float, float, float]] | None = None,
) -> None:
    transforms: dict[tuple[str, str], list[list[float]]] = {}
    required_roots: set[tuple[str, str]] = set()
    components_by_role = {component.role_id: component for component in plan.components}
    for operation in plan.operations:
        for instance in operation.instances:
            if operation.source_anchor.placement_policy == "fixed":
                source_strategy = components_by_role[
                    operation.source_role_id
                ].builder_profile.instance_strategy
                source_instance_id = (
                    instance.instance_id if source_strategy == "per_sector" else "global"
                )
                if operation.source_role_id == force_global_root_for_role:
                    source_instance_id = "global"
                required_roots.add((operation.source_role_id, source_instance_id))
            if operation.target_anchor.placement_policy == "fixed":
                target_strategy = components_by_role[
                    operation.target_role_id
                ].builder_profile.instance_strategy
                target_instance_id = (
                    instance.instance_id if target_strategy == "per_sector" else "global"
                )
                if operation.target_role_id == force_global_root_for_role:
                    target_instance_id = "global"
                required_roots.add((operation.target_role_id, target_instance_id))
            if operation.kind == "mechanical":
                transforms[(instance.apply_to_role_id, instance.instance_id)] = _scene_matrix(
                    instance.translation_m,
                    instance.rotation_deg,
                    instance.scale,
                )

    wrapper_translation = (0.25, 0.0, 0.0)
    wrapper_inverse = _translation_matrix((-wrapper_translation[0], 0.0, 0.0))
    nodes: list[dict[str, Any]] = [
        {
            "name": "export_wrapper",
            "translation": list(wrapper_translation),
            "children": [],
        }
    ]
    for root_number, (role_id, instance_id) in enumerate(sorted(required_roots)):
        scene_world = transforms.get((role_id, instance_id), _identity())
        gltf_world = _multiply(_multiply(_scene_to_gltf(), scene_world), _gltf_to_scene())
        root: dict[str, Any] = {
            "name": f"{role_id}_{instance_id}",
            "mesh": 0,
            "extras": {
                "assembly_role_id": role_id,
                "assembly_instance_id": instance_id,
            },
        }
        if encode_one_root_as_trs and root_number == 0:
            root.update(_matrix_as_trs(gltf_world))
            nodes.append(root)
        else:
            local = _multiply(wrapper_inverse, gltf_world)
            root["matrix"] = _column_major(local)
            nodes[0]["children"].append(len(nodes))
            nodes.append(root)

    marker_number = 0
    for operation in plan.operations:
        if operation.kind != "mechanical":
            continue
        for instance in operation.instances:
            endpoint_frames = (
                (
                    "source",
                    operation.source_role_id,
                    operation.source_anchor,
                    instance.source_frame_world,
                ),
                (
                    "target",
                    operation.target_role_id,
                    operation.target_anchor,
                    instance.target_frame_world,
                ),
            )
            for endpoint, role_id, anchor, frame in endpoint_frames:
                if anchor.placement_policy == "fixed":
                    continue
                marker_number += 1
                if marker_mode == "absent" and marker_number == 1:
                    continue
                offset = (0.0, 0.0, 0.0)
                if marker_offset is not None and marker_offset[:3] == (
                    operation.connection_id,
                    instance.instance_id,
                    endpoint,
                ):
                    offset = marker_offset[3]
                scene_world = _frame_matrix(
                    frame.position_m,
                    frame.normal,
                    frame.up,
                    offset=offset,
                )
                gltf_world = _multiply(
                    _multiply(_scene_to_gltf(), scene_world),
                    _gltf_to_scene(),
                )
                local = _multiply(wrapper_inverse, gltf_world)
                extras = {
                    "assembly_constraint_anchor": True,
                    "constraint_connection_id": operation.connection_id,
                    "constraint_operation_id": operation.operation_id,
                    "constraint_instance_id": instance.instance_id,
                    "constraint_endpoint": endpoint,
                    "constraint_role_id": role_id,
                    "constraint_anchor_id": anchor.anchor_id,
                }
                if marker_mode == "mismatched" and marker_number == 1:
                    extras["constraint_role_id"] = "mismatched_role"
                marker: dict[str, Any] = {
                    "name": (
                        f"constraint_marker_{operation.connection_id}_"
                        f"{instance.instance_id}_{endpoint}"
                    ),
                    "extras": extras,
                    **_matrix_as_trs(local),
                }
                nodes[0]["children"].append(len(nodes))
                nodes.append(marker)
                if marker_mode == "duplicate" and marker_number == 1:
                    duplicate = deepcopy(marker)
                    duplicate["name"] += "_duplicate"
                    nodes[0]["children"].append(len(nodes))
                    nodes.append(duplicate)

                if anchor.placement_policy != "resolved_from_operation":
                    continue
                if support_mode == "absent":
                    continue
                support_extras = {
                    "assembly_constraint_support": True,
                    "constraint_connection_id": operation.connection_id,
                    "constraint_operation_id": operation.operation_id,
                    "constraint_instance_id": instance.instance_id,
                    "constraint_endpoint": endpoint,
                    "constraint_role_id": role_id,
                    "constraint_anchor_id": anchor.anchor_id,
                    "constraint_support_anchor_id": anchor.resolved_support_anchor_id,
                }
                if support_mode == "mismatched":
                    support_extras["constraint_support_anchor_id"] = "wrong_support_anchor"
                support: dict[str, Any] = {
                    "name": (
                        f"constraint_support_{operation.connection_id}_"
                        f"{instance.instance_id}_{endpoint}"
                    ),
                    "extras": support_extras,
                }
                if support_mode != "not_mesh":
                    support["mesh"] = 0
                nodes[0]["children"].append(len(nodes))
                nodes.append(support)
                if support_mode == "duplicate":
                    duplicate_support = deepcopy(support)
                    duplicate_support["name"] += "_duplicate"
                    nodes[0]["children"].append(len(nodes))
                    nodes.append(duplicate_support)

    vertices = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    indices = struct.pack("<3H", 0, 1, 2) + b"\0\0"
    binary_chunk = vertices + indices
    payload = {
        "asset": {"version": "2.0"},
        "nodes": nodes,
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(binary_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vertices)},
            {"buffer": 0, "byteOffset": len(vertices), "byteLength": len(indices)},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "count": 3,
                "type": "VEC3",
                "componentType": 5126,
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            },
            {"bufferView": 1, "count": 3, "type": "SCALAR", "componentType": 5123},
        ],
    }
    json_chunk = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    binary_record = struct.pack("<II", len(binary_chunk), 0x004E4942) + binary_chunk
    length = 12 + 8 + len(json_chunk) + len(binary_record)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + binary_record
    )


def _scene_matrix(
    translation: tuple[float, float, float],
    rotation_deg: tuple[float, float, float],
    scale: tuple[float, float, float],
) -> list[list[float]]:
    rotation = _euler_xyz_matrix(list(rotation_deg))
    matrix = _identity()
    for row in range(3):
        for column in range(3):
            matrix[row][column] = rotation[row][column] * scale[column]
        matrix[row][3] = translation[row]
    return matrix


def _frame_matrix(
    position: tuple[float, float, float],
    normal: tuple[float, float, float],
    up: tuple[float, float, float],
    *,
    offset: tuple[float, float, float],
) -> list[list[float]]:
    x_axis = _normalize(normal)
    z_axis = _normalize(up)
    y_axis = _normalize(_cross(z_axis, x_axis))
    z_axis = _normalize(_cross(x_axis, y_axis))
    matrix = _identity()
    for row in range(3):
        matrix[row][0] = x_axis[row]
        matrix[row][1] = y_axis[row]
        matrix[row][2] = z_axis[row]
        matrix[row][3] = position[row] + offset[row]
    return matrix


def _matrix_as_trs(matrix: list[list[float]]) -> dict[str, list[float]]:
    scale = [math.sqrt(sum(matrix[row][column] ** 2 for row in range(3))) for column in range(3)]
    rotation = [[matrix[row][column] / scale[column] for column in range(3)] for row in range(3)]
    return {
        "translation": [matrix[row][3] for row in range(3)],
        "rotation": _quaternion_from_rotation(rotation),
        "scale": scale,
    }


def _quaternion_from_rotation(matrix: list[list[float]]) -> list[float]:
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        return [
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
            0.25 * scale,
        ]
    diagonal = [matrix[index][index] for index in range(3)]
    axis = max(range(3), key=diagonal.__getitem__)
    if axis == 0:
        scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        return [
            0.25 * scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
            (matrix[2][1] - matrix[1][2]) / scale,
        ]
    if axis == 1:
        scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        return [
            (matrix[0][1] + matrix[1][0]) / scale,
            0.25 * scale,
            (matrix[1][2] + matrix[2][1]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
        ]
    scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
    return [
        (matrix[0][2] + matrix[2][0]) / scale,
        (matrix[1][2] + matrix[2][1]) / scale,
        0.25 * scale,
        (matrix[1][0] - matrix[0][1]) / scale,
    ]


def _identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _translation_matrix(value: tuple[float, float, float]) -> list[list[float]]:
    matrix = _identity()
    for index in range(3):
        matrix[index][3] = value[index]
    return matrix


def _scene_to_gltf() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _gltf_to_scene() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][axis] * right[axis][column] for axis in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _column_major(matrix: list[list[float]]) -> list[float]:
    return [matrix[row][column] for column in range(4) for row in range(4)]


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    return tuple(component / length for component in value)
