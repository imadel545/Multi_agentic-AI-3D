from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from core.contracts.assembly import (
    AssemblyComponentSelection,
    AssemblyConnection,
    AssemblyOperation,
    AssemblyPlan,
    _canonical_sha256,
)
from core.contracts.assembly_evidence import (
    ASSEMBLY_ANGULAR_TOLERANCE_DEG,
    AssemblyConstraintEvidence,
    AssemblyConstraintMeasurement,
    MeasuredAssemblyFrame,
    ResolvedEndpointSupport,
    UnevaluatedAssemblyConnection,
    canonical_evidence_sha256,
)
from core.contracts.assets import AssetAnchor
from core.qa.gltf_integrity import inspect_gltf_integrity

type Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]
type MarkerKey = tuple[str, str, str, str]
type MarkerRecord = tuple[int, str | None, str, str, Matrix4]
type SupportKey = tuple[str, str, str, str]
type SupportRecord = tuple[int, str | None, int | None, str, str, str]

_IDENTITY: Matrix4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

# Blender/SceneSpec uses right-handed Z-up coordinates. glTF uses right-handed
# Y-up coordinates. Blender's exporter maps (x, y, z) -> (x, z, -y).
_SCENE_TO_GLTF: Matrix4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)
_GLTF_TO_SCENE: Matrix4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

_LIMITATIONS = [
    (
        "Required non-mechanical connections are reported but are not geometrically "
        "evaluated by AssemblyConstraintEvidence v1."
    ),
    (
        "Anchor frames are semantic coordinate frames reconstructed from exported glTF "
        "component roots or dedicated constraint-marker nodes; they are not contact mesh."
    ),
    (
        "Collision, physical contact, fastener engagement, deformation, load capacity "
        "and electrical or routing continuity are not evaluated."
    ),
]


class AssemblyConstraintInspector:
    """Measure required mechanical connections from the exported GLB.

    Fixed anchors are measured from actual glTF component roots. Every non-fixed
    endpoint requires a dedicated exported constraint-marker node. Plan-only
    endpoint frames are never measurement evidence.
    """

    def inspect(self, glb_path: Path, plan: AssemblyPlan) -> AssemblyConstraintEvidence:
        if plan.schema_version != "1.1.0":
            raise ValueError("ASSEMBLY_CONSTRAINT_EVIDENCE_REQUIRES_PLAN_1_1")
        # Revalidate a serialized copy so nested post-construction mutation cannot
        # bypass manifest, builder-profile, operation, or plan invariants.
        plan = AssemblyPlan.model_validate(plan.model_dump(mode="json"))
        if plan.compilation_status != "resolved":
            raise ValueError("ASSEMBLY_CONSTRAINT_EVIDENCE_REQUIRES_RESOLVED_PLAN")

        glb_path = Path(glb_path)
        glb_sha256 = _file_sha256_or_empty(glb_path)
        plan_sha256 = _canonical_sha256(plan.model_dump(mode="json"))
        integrity = inspect_gltf_integrity(glb_path)
        errors = list(integrity.errors)
        measurements: list[AssemblyConstraintMeasurement] = []
        expected_count = sum(
            len(operation.instances)
            for operation in plan.operations
            if operation.kind == "mechanical"
            and _required_connection(plan, operation.connection_id)
        )

        roots: dict[tuple[str, str], tuple[int, str | None, Matrix4]] = {}
        if integrity.payload is None:
            errors.append("ASSEMBLY_GLB_PAYLOAD_UNAVAILABLE")
        elif errors:
            errors.append("ASSEMBLY_GLB_INTEGRITY_FAILED")
        else:
            try:
                world_matrices, parents = _world_matrices(integrity.payload)
                roots = _component_roots(integrity.payload, world_matrices, parents)
                markers, marker_errors = _constraint_markers(
                    integrity.payload,
                    world_matrices,
                )
                supports, support_errors = _constraint_supports(integrity.payload)
                measurements, measurement_errors = _measure_required_mechanics(
                    plan,
                    roots,
                    markers,
                    supports,
                )
                errors.extend(marker_errors)
                errors.extend(support_errors)
                errors.extend(measurement_errors)
            except ValueError as exc:
                errors.append(str(exc))

        errors = list(dict.fromkeys(errors))
        unevaluated = [
            UnevaluatedAssemblyConnection(
                connection_id=connection.connection_id,
                kind=connection.kind,
            )
            for connection in plan.connections
            if connection.required and connection.kind != "mechanical"
        ]
        failed_count = sum(not item.passed for item in measurements)
        status = (
            "passed"
            if expected_count > 0
            and len(measurements) == expected_count
            and failed_count == 0
            and not errors
            else "failed"
        )
        payload: dict[str, Any] = {
            "schema_version": "1.0.0",
            "assembly_plan_schema_version": "1.1.0",
            "workflow_id": plan.workflow_id,
            "status": status,
            "coordinate_space": "scenespec_z_up_meters",
            "glb_sha256": glb_sha256,
            "assembly_plan_sha256": plan_sha256,
            "angular_tolerance_deg": ASSEMBLY_ANGULAR_TOLERANCE_DEG,
            "expected_measurement_count": expected_count,
            "measured_constraint_count": len(measurements),
            "failed_constraint_count": failed_count,
            "measurements": [item.model_dump(mode="json") for item in measurements],
            "unevaluated_required_connections": [
                item.model_dump(mode="json") for item in unevaluated
            ],
            "errors": errors,
            "limitations": list(_LIMITATIONS),
        }
        payload["evidence_sha256"] = canonical_evidence_sha256(payload)
        return AssemblyConstraintEvidence.model_validate(payload)


def _measure_required_mechanics(
    plan: AssemblyPlan,
    roots: dict[tuple[str, str], tuple[int, str | None, Matrix4]],
    markers: dict[MarkerKey, list[MarkerRecord]],
    supports: dict[SupportKey, list[SupportRecord]],
) -> tuple[list[AssemblyConstraintMeasurement], list[str]]:
    measurements: list[AssemblyConstraintMeasurement] = []
    errors: list[str] = []
    required_mechanical_ids = {
        connection.connection_id
        for connection in plan.connections
        if connection.required and connection.kind == "mechanical"
    }
    operations = {
        operation.connection_id: operation
        for operation in plan.operations
        if operation.kind == "mechanical"
    }
    connections = {connection.connection_id: connection for connection in plan.connections}
    components = {component.role_id: component for component in plan.components}
    for connection_id in sorted(required_mechanical_ids):
        operation = operations.get(connection_id)
        if operation is None:
            errors.append(f"ASSEMBLY_MECHANICAL_OPERATION_MISSING:{connection_id}")
            continue
        connection = connections[connection_id]
        try:
            source_component = components[connection.source_role_id]
            target_component = components[connection.target_role_id]
            if (
                source_component.manifest_snapshot is None
                or target_component.manifest_snapshot is None
            ):
                raise ValueError("ASSEMBLY_MEASUREMENT_MANIFEST_SNAPSHOT_MISSING")
            source_connector = source_component.manifest_snapshot.connector(
                connection.source_connector_id
            )
            target_connector = target_component.manifest_snapshot.connector(
                connection.target_connector_id
            )
            source_anchor = source_component.manifest_snapshot.anchor(source_connector.anchor_id)
            target_anchor = target_component.manifest_snapshot.anchor(target_connector.anchor_id)
            tolerance_m = min(source_connector.tolerance_m, target_connector.tolerance_m)
            _validate_operation_contract(
                operation=operation,
                connection=connection,
                source_asset_id=source_component.selected_asset_id,
                target_asset_id=target_component.selected_asset_id,
                source_anchor=source_anchor,
                target_anchor=target_anchor,
                tolerance_m=tolerance_m,
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"{connection_id}:{exc}")
            continue
        for instance in operation.instances:
            measurement_id = f"{connection_id}:{instance.instance_id}"
            try:
                source_frame = _endpoint_frame(
                    connection_id=connection_id,
                    operation_id=operation.operation_id,
                    endpoint="source",
                    role_id=operation.source_role_id,
                    instance_id=instance.instance_id,
                    anchor=source_anchor,
                    component=source_component,
                    roots=roots,
                    markers=markers,
                    supports=supports,
                )
                target_frame = _endpoint_frame(
                    connection_id=connection_id,
                    operation_id=operation.operation_id,
                    endpoint="target",
                    role_id=operation.target_role_id,
                    instance_id=instance.instance_id,
                    anchor=target_anchor,
                    component=target_component,
                    roots=roots,
                    markers=markers,
                    supports=supports,
                )
                measurements.append(
                    _measurement(
                        measurement_id=measurement_id,
                        operation=operation,
                        instance_id=instance.instance_id,
                        source_frame=source_frame,
                        target_frame=target_frame,
                        source_anchor=source_anchor,
                        target_anchor=target_anchor,
                        tolerance_m=tolerance_m,
                    )
                )
            except ValueError as exc:
                errors.append(f"{measurement_id}:{exc}")
    return measurements, errors


def _endpoint_frame(
    *,
    connection_id: str,
    operation_id: str,
    endpoint: str,
    role_id: str,
    instance_id: str,
    anchor: AssetAnchor,
    component: AssemblyComponentSelection,
    roots: dict[tuple[str, str], tuple[int, str | None, Matrix4]],
    markers: dict[MarkerKey, list[MarkerRecord]],
    supports: dict[SupportKey, list[SupportRecord]],
) -> MeasuredAssemblyFrame:
    if anchor.placement_policy != "fixed":
        resolved_support = None
        if anchor.placement_policy == "resolved_from_operation":
            if anchor.resolved_support_anchor_id is None:
                raise ValueError(
                    f"ASSEMBLY_CONSTRAINT_SUPPORT_CONTRACT_MISSING:{role_id}:{anchor.anchor_id}"
                )
            resolved_support = _constraint_support(
                connection_id=connection_id,
                operation_id=operation_id,
                instance_id=instance_id,
                endpoint=endpoint,
                role_id=role_id,
                resolved_anchor_id=anchor.anchor_id,
                support_anchor_id=anchor.resolved_support_anchor_id,
                supports=supports,
            )
        return _constraint_marker_frame(
            connection_id=connection_id,
            operation_id=operation_id,
            instance_id=instance_id,
            endpoint=endpoint,
            role_id=role_id,
            anchor_id=anchor.anchor_id,
            markers=markers,
            resolved_support=resolved_support,
        )

    builder = component.builder_profile
    if builder is None:
        raise ValueError(f"ASSEMBLY_COMPONENT_BUILDER_PROFILE_MISSING:{role_id}")
    root_instance_id = instance_id if builder.instance_strategy == "per_sector" else "global"
    root = roots.get((role_id, root_instance_id))
    if root is None:
        raise ValueError(f"ASSEMBLY_COMPONENT_ROOT_MISSING:{role_id}:{root_instance_id}")
    node_index, node_name, gltf_world = root
    scene_world = _multiply(_multiply(_GLTF_TO_SCENE, gltf_world), _SCENE_TO_GLTF)
    return MeasuredAssemblyFrame(
        position_m=_transform_point(scene_world, anchor.position_m),
        normal=_normalize(_transform_vector(scene_world, anchor.normal)),
        up=_normalize(_transform_vector(scene_world, anchor.up)),
        source="glb_fixed_anchor",
        gltf_node_index=node_index,
        gltf_node_name=node_name,
    )


def _constraint_marker_frame(
    *,
    connection_id: str,
    operation_id: str,
    instance_id: str,
    endpoint: str,
    role_id: str,
    anchor_id: str,
    markers: dict[MarkerKey, list[MarkerRecord]],
    resolved_support: ResolvedEndpointSupport | None,
) -> MeasuredAssemblyFrame:
    key = (connection_id, operation_id, instance_id, endpoint)
    candidates = markers.get(key, [])
    if not candidates:
        related = [
            marker_key
            for marker_key in markers
            if marker_key[0] == connection_id
            and marker_key[2] == instance_id
            and marker_key[3] == endpoint
        ]
        code = (
            "ASSEMBLY_CONSTRAINT_MARKER_MISMATCH"
            if related
            else "ASSEMBLY_CONSTRAINT_MARKER_MISSING"
        )
        raise ValueError(f"{code}:{connection_id}:{instance_id}:{endpoint}")
    if len(candidates) != 1:
        raise ValueError(
            f"ASSEMBLY_CONSTRAINT_MARKER_DUPLICATE:{connection_id}:{instance_id}:{endpoint}"
        )
    node_index, node_name, marker_role_id, marker_anchor_id, gltf_world = candidates[0]
    if marker_role_id != role_id or marker_anchor_id != anchor_id:
        raise ValueError(
            f"ASSEMBLY_CONSTRAINT_MARKER_MISMATCH:{connection_id}:{instance_id}:{endpoint}"
        )
    scene_world = _multiply(_multiply(_GLTF_TO_SCENE, gltf_world), _SCENE_TO_GLTF)
    return MeasuredAssemblyFrame(
        position_m=_transform_point(scene_world, (0.0, 0.0, 0.0)),
        normal=_normalize(_transform_vector(scene_world, (1.0, 0.0, 0.0))),
        up=_normalize(_transform_vector(scene_world, (0.0, 0.0, 1.0))),
        source="glb_resolved_anchor",
        gltf_node_index=node_index,
        gltf_node_name=node_name,
        resolved_support=resolved_support,
    )


def _constraint_support(
    *,
    connection_id: str,
    operation_id: str,
    instance_id: str,
    endpoint: str,
    role_id: str,
    resolved_anchor_id: str,
    support_anchor_id: str,
    supports: dict[SupportKey, list[SupportRecord]],
) -> ResolvedEndpointSupport:
    key = (connection_id, operation_id, instance_id, endpoint)
    candidates = supports.get(key, [])
    if not candidates:
        related = [
            support_key
            for support_key in supports
            if support_key[0] == connection_id
            and support_key[2] == instance_id
            and support_key[3] == endpoint
        ]
        code = (
            "ASSEMBLY_CONSTRAINT_SUPPORT_MISMATCH"
            if related
            else "ASSEMBLY_CONSTRAINT_SUPPORT_MISSING"
        )
        raise ValueError(f"{code}:{connection_id}:{instance_id}:{endpoint}")
    if len(candidates) != 1:
        raise ValueError(
            f"ASSEMBLY_CONSTRAINT_SUPPORT_DUPLICATE:{connection_id}:{instance_id}:{endpoint}"
        )
    (
        node_index,
        node_name,
        mesh_index,
        support_role_id,
        support_resolved_anchor_id,
        actual_support_anchor_id,
    ) = candidates[0]
    if mesh_index is None:
        raise ValueError(
            f"ASSEMBLY_CONSTRAINT_SUPPORT_NOT_MESH:{connection_id}:{instance_id}:{endpoint}"
        )
    if (
        support_role_id != role_id
        or support_resolved_anchor_id != resolved_anchor_id
        or actual_support_anchor_id != support_anchor_id
    ):
        raise ValueError(
            f"ASSEMBLY_CONSTRAINT_SUPPORT_MISMATCH:{connection_id}:{instance_id}:{endpoint}"
        )
    return ResolvedEndpointSupport(
        connection_id=connection_id,
        operation_id=operation_id,
        instance_id=instance_id,
        endpoint=endpoint,
        role_id=role_id,
        resolved_anchor_id=resolved_anchor_id,
        support_anchor_id=support_anchor_id,
        gltf_node_index=node_index,
        gltf_node_name=node_name,
        gltf_mesh_index=mesh_index,
    )


def _measurement(
    *,
    measurement_id: str,
    operation: AssemblyOperation,
    instance_id: str,
    source_frame: MeasuredAssemblyFrame,
    target_frame: MeasuredAssemblyFrame,
    source_anchor: AssetAnchor,
    target_anchor: AssetAnchor,
    tolerance_m: float,
) -> AssemblyConstraintMeasurement:
    position_error = math.dist(source_frame.position_m, target_frame.position_m)
    normal_error = _angle_deg(
        source_frame.normal,
        tuple(-component for component in target_frame.normal),
    )
    up_error = _angle_deg(source_frame.up, target_frame.up)
    position_passed = position_error <= tolerance_m + 1e-12
    normal_passed = normal_error <= ASSEMBLY_ANGULAR_TOLERANCE_DEG + 1e-12
    up_passed = up_error <= ASSEMBLY_ANGULAR_TOLERANCE_DEG + 1e-12
    return AssemblyConstraintMeasurement(
        measurement_id=measurement_id,
        connection_id=operation.connection_id,
        operation_id=operation.operation_id,
        instance_id=instance_id,
        source_role_id=operation.source_role_id,
        source_connector_id=operation.source_connector_id,
        source_anchor_id=source_anchor.anchor_id,
        target_role_id=operation.target_role_id,
        target_connector_id=operation.target_connector_id,
        target_anchor_id=target_anchor.anchor_id,
        source_frame=source_frame,
        target_frame=target_frame,
        position_error_m=position_error,
        position_tolerance_m=tolerance_m,
        normal_opposition_error_deg=normal_error,
        up_alignment_error_deg=up_error,
        angular_tolerance_deg=ASSEMBLY_ANGULAR_TOLERANCE_DEG,
        position_passed=position_passed,
        normal_opposition_passed=normal_passed,
        up_alignment_passed=up_passed,
        passed=position_passed and normal_passed and up_passed,
    )


def _validate_operation_contract(
    *,
    operation: AssemblyOperation,
    connection: AssemblyConnection,
    source_asset_id: str | None,
    target_asset_id: str | None,
    source_anchor: AssetAnchor,
    target_anchor: AssetAnchor,
    tolerance_m: float,
) -> None:
    expected = {
        "connection_id": connection.connection_id,
        "kind": connection.kind,
        "source_role_id": connection.source_role_id,
        "source_asset_id": source_asset_id,
        "source_connector_id": connection.source_connector_id,
        "source_anchor": source_anchor,
        "target_role_id": connection.target_role_id,
        "target_asset_id": target_asset_id,
        "target_connector_id": connection.target_connector_id,
        "target_anchor": target_anchor,
    }
    for field, expected_value in expected.items():
        if getattr(operation, field) != expected_value:
            raise ValueError(f"ASSEMBLY_MEASUREMENT_OPERATION_CONTRACT_MISMATCH:{field}")
    if not math.isclose(operation.tolerance_m, tolerance_m, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("ASSEMBLY_MEASUREMENT_OPERATION_CONTRACT_MISMATCH:tolerance_m")


def _world_matrices(payload: dict[str, Any]) -> tuple[list[Matrix4], dict[int, int]]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("ASSEMBLY_GLTF_NODES_INVALID")
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"ASSEMBLY_GLTF_NODE_INVALID:{parent_index}")
        for child in node.get("children", []):
            parents[int(child)] = parent_index
    cache: dict[int, Matrix4] = {}

    def resolve(node_index: int) -> Matrix4:
        cached = cache.get(node_index)
        if cached is not None:
            return cached
        local = _node_matrix(nodes[node_index])
        parent_index = parents.get(node_index)
        world = local if parent_index is None else _multiply(resolve(parent_index), local)
        cache[node_index] = world
        return world

    return [resolve(index) for index in range(len(nodes))], parents


def _component_roots(
    payload: dict[str, Any],
    world_matrices: list[Matrix4],
    parents: dict[int, int],
) -> dict[tuple[str, str], tuple[int, str | None, Matrix4]]:
    nodes = payload["nodes"]
    candidates: dict[tuple[str, str], list[int]] = {}
    keys_by_index: dict[int, tuple[str, str]] = {}
    for node_index, node in enumerate(nodes):
        extras = node.get("extras")
        if not isinstance(extras, dict):
            continue
        role_id = extras.get("assembly_role_id")
        instance_id = extras.get("assembly_instance_id")
        if not isinstance(role_id, str) or not isinstance(instance_id, str):
            continue
        key = (role_id, instance_id)
        keys_by_index[node_index] = key
        candidates.setdefault(key, []).append(node_index)

    roots: dict[tuple[str, str], tuple[int, str | None, Matrix4]] = {}
    for key, node_indices in candidates.items():
        topmost = [
            node_index
            for node_index in node_indices
            if keys_by_index.get(parents.get(node_index, -1)) != key
        ]
        if len(topmost) != 1:
            raise ValueError(f"ASSEMBLY_COMPONENT_ROOT_AMBIGUOUS:{key[0]}:{key[1]}")
        node_index = topmost[0]
        name = nodes[node_index].get("name")
        roots[key] = (
            node_index,
            name if isinstance(name, str) and name else None,
            world_matrices[node_index],
        )
    return roots


def _constraint_markers(
    payload: dict[str, Any],
    world_matrices: list[Matrix4],
) -> tuple[dict[MarkerKey, list[MarkerRecord]], list[str]]:
    nodes = payload["nodes"]
    markers: dict[MarkerKey, list[MarkerRecord]] = {}
    errors: list[str] = []
    required_string_fields = (
        "constraint_connection_id",
        "constraint_operation_id",
        "constraint_instance_id",
        "constraint_endpoint",
        "constraint_role_id",
        "constraint_anchor_id",
    )
    for node_index, node in enumerate(nodes):
        extras = node.get("extras")
        if not isinstance(extras, dict) or extras.get("assembly_constraint_anchor") is not True:
            continue
        values = {field: extras.get(field) for field in required_string_fields}
        if any(not isinstance(value, str) or not value for value in values.values()) or values[
            "constraint_endpoint"
        ] not in {"source", "target"}:
            errors.append(f"ASSEMBLY_CONSTRAINT_MARKER_EXTRAS_INVALID:{node_index}")
            continue
        key: MarkerKey = (
            str(values["constraint_connection_id"]),
            str(values["constraint_operation_id"]),
            str(values["constraint_instance_id"]),
            str(values["constraint_endpoint"]),
        )
        name = node.get("name")
        markers.setdefault(key, []).append(
            (
                node_index,
                name if isinstance(name, str) and name else None,
                str(values["constraint_role_id"]),
                str(values["constraint_anchor_id"]),
                world_matrices[node_index],
            )
        )
    return markers, errors


def _constraint_supports(
    payload: dict[str, Any],
) -> tuple[dict[SupportKey, list[SupportRecord]], list[str]]:
    """Collect explicitly tagged mesh support nodes without name inference."""

    nodes = payload["nodes"]
    supports: dict[SupportKey, list[SupportRecord]] = {}
    errors: list[str] = []
    required_string_fields = (
        "constraint_connection_id",
        "constraint_operation_id",
        "constraint_instance_id",
        "constraint_endpoint",
        "constraint_role_id",
        "constraint_anchor_id",
        "constraint_support_anchor_id",
    )
    for node_index, node in enumerate(nodes):
        extras = node.get("extras")
        if not isinstance(extras, dict) or extras.get("assembly_constraint_support") is not True:
            continue
        values = {field: extras.get(field) for field in required_string_fields}
        if any(not isinstance(value, str) or not value for value in values.values()) or values[
            "constraint_endpoint"
        ] not in {"source", "target"}:
            errors.append(f"ASSEMBLY_CONSTRAINT_SUPPORT_EXTRAS_INVALID:{node_index}")
            continue
        key: SupportKey = (
            str(values["constraint_connection_id"]),
            str(values["constraint_operation_id"]),
            str(values["constraint_instance_id"]),
            str(values["constraint_endpoint"]),
        )
        name = node.get("name")
        mesh = node.get("mesh")
        supports.setdefault(key, []).append(
            (
                node_index,
                name if isinstance(name, str) and name else None,
                (
                    mesh
                    if isinstance(mesh, int) and not isinstance(mesh, bool) and mesh >= 0
                    else None
                ),
                str(values["constraint_role_id"]),
                str(values["constraint_anchor_id"]),
                str(values["constraint_support_anchor_id"]),
            )
        )
    return supports, errors


def _node_matrix(node: dict[str, Any]) -> Matrix4:
    raw_matrix = node.get("matrix")
    if raw_matrix is not None:
        values = [float(value) for value in raw_matrix]
        return tuple(tuple(values[column * 4 + row] for column in range(4)) for row in range(4))  # type: ignore[return-value]

    translation = tuple(float(value) for value in node.get("translation", (0.0, 0.0, 0.0)))
    rotation = tuple(float(value) for value in node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
    scale = tuple(float(value) for value in node.get("scale", (1.0, 1.0, 1.0)))
    x, y, z, w = rotation
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    rotation_matrix: Matrix4 = (
        (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy), 0.0),
        (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx), 0.0),
        (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    scale_matrix: Matrix4 = (
        (scale[0], 0.0, 0.0, 0.0),
        (0.0, scale[1], 0.0, 0.0),
        (0.0, 0.0, scale[2], 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    transform = _multiply(rotation_matrix, scale_matrix)
    rows = [list(row) for row in transform]
    for index in range(3):
        rows[index][3] = translation[index]
    return tuple(tuple(row) for row in rows)  # type: ignore[return-value]


def _multiply(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(
            sum(left[row][axis] * right[axis][column] for axis in range(4)) for column in range(4)
        )
        for row in range(4)
    )  # type: ignore[return-value]


def _transform_point(
    matrix: Matrix4,
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    homogeneous = (*value, 1.0)
    return tuple(
        sum(matrix[row][axis] * homogeneous[axis] for axis in range(4)) for row in range(3)
    )  # type: ignore[return-value]


def _transform_vector(
    matrix: Matrix4,
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(sum(matrix[row][axis] * value[axis] for axis in range(3)) for row in range(3))  # type: ignore[return-value]


def _normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    if length <= 1e-12:
        raise ValueError("ASSEMBLY_MEASURED_FRAME_VECTOR_ZERO")
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _angle_deg(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    cosine = max(
        -1.0,
        min(1.0, sum(normalized_left[index] * normalized_right[index] for index in range(3))),
    )
    return math.degrees(math.acos(cosine))


def _required_connection(plan: AssemblyPlan, connection_id: str) -> bool:
    return any(
        connection.connection_id == connection_id and connection.required
        for connection in plan.connections
    )


def _file_sha256_or_empty(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return hashlib.sha256(b"").hexdigest()
