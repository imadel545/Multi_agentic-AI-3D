from __future__ import annotations

import math
from collections.abc import Iterable

from core.contracts.assembly import (
    AssemblyFrame,
    AssemblyOperation,
    AssemblyPlan,
    ResolvedAssemblyInstance,
    _canonical_sha256,
    validate_component_parameter_contract,
)
from core.contracts.assets import AssetAnchor, AssetConnector
from core.contracts.scene import SceneSpec, SectorSpec


def resolve_scene_assembly(scene: SceneSpec) -> AssemblyPlan | None:
    """Resolve declared connector frames into immutable executable operations."""

    plan = scene.assembly_plan
    if plan is None or plan.schema_version == "1.0.0":
        return plan
    components = {component.role_id: component for component in plan.components}
    for component in components.values():
        validate_component_parameter_contract(component)
    transforms: dict[tuple[str, str], tuple[list[list[float]], tuple[float, float, float]]] = {
        ("support_structure", sector.sector_id): (_identity_matrix(), (0.0, 0.0, 0.0))
        for sector in scene.sectors
    }
    operations: list[AssemblyOperation] = []
    for connection in plan.connections:
        source = components[connection.source_role_id]
        target = components[connection.target_role_id]
        if source.manifest_snapshot is None or target.manifest_snapshot is None:
            raise ValueError(f"ASSEMBLY_MANIFEST_SNAPSHOT_MISSING:{connection.connection_id}")
        if source.builder_profile is None:
            raise ValueError(f"ASSEMBLY_BUILDER_SNAPSHOT_MISSING:{connection.source_role_id}")
        source_connector = source.manifest_snapshot.connector(connection.source_connector_id)
        target_connector = target.manifest_snapshot.connector(connection.target_connector_id)
        _validate_connector_pair(connection.kind, source_connector, target_connector)
        source_anchor = source.manifest_snapshot.anchor(source_connector.anchor_id)
        target_anchor = target.manifest_snapshot.anchor(target_connector.anchor_id)
        instances: list[ResolvedAssemblyInstance] = []
        for sector in _connection_instances(scene, source, target):
            instance_id = sector.sector_id if sector is not None else "global"
            target_frame = _resolved_anchor_frame(
                scene,
                target.role_id,
                target_anchor,
                sector,
                transforms,
            )
            resolved_parameters = _resolved_instance_parameters(
                connection.connection_id,
                sector,
            )
            if connection.connection_id == "radio-to-mount" and sector is not None:
                target_frame = _adapt_radio_target_frame(
                    target_frame,
                    sector,
                    resolved_parameters,
                )
            if connection.kind == "mechanical":
                rotation, translation = _solve_attachment_transform(source_anchor, target_frame)
                transforms[(source.role_id, instance_id)] = (rotation, translation)
                source_frame = _transform_anchor(source_anchor, rotation, translation)
                route_points: list[tuple[float, float, float]] = []
                operation_type = "place_component"
                apply_to_role = source.role_id
            else:
                source_frame = _resolved_anchor_frame(
                    scene,
                    source.role_id,
                    source_anchor,
                    sector,
                    transforms,
                )
                route_points = _route_points(source_frame.position_m, target_frame.position_m)
                operation_type = "route_connection"
                apply_to_role = (
                    target.role_id
                    if target.builder_profile
                    and target.builder_profile.worker_handler == "cable_route"
                    else source.role_id
                )
                rotation, translation = transforms.get(
                    (apply_to_role, instance_id),
                    (_identity_matrix(), target_frame.position_m),
                )
            error = math.dist(source_frame.position_m, target_frame.position_m)
            if connection.kind == "mechanical" and error > min(
                source_connector.tolerance_m, target_connector.tolerance_m
            ):
                raise ValueError(
                    f"ASSEMBLY_CONNECTOR_TOLERANCE_EXCEEDED:{connection.connection_id}:{error:.6f}"
                )
            instances.append(
                ResolvedAssemblyInstance(
                    instance_id=instance_id,
                    apply_to_role_id=apply_to_role,
                    source_frame_world=source_frame,
                    target_frame_world=target_frame,
                    translation_m=translation,
                    rotation_deg=_matrix_to_euler_xyz_deg(rotation),
                    route_points_m=route_points,
                    resolved_parameters=resolved_parameters,
                    connector_error_m=error if connection.kind != "mechanical" else 0.0,
                )
            )
        operation_payload = {
            "operation_id": f"assembly:{connection.connection_id}",
            "connection_id": connection.connection_id,
            "operation_type": operation_type,
            "kind": connection.kind,
            "source_role_id": source.role_id,
            "source_asset_id": source.selected_asset_id,
            "source_connector_id": source_connector.connector_id,
            "source_anchor": source_anchor.model_dump(mode="json"),
            "target_role_id": target.role_id,
            "target_asset_id": target.selected_asset_id,
            "target_connector_id": target_connector.connector_id,
            "target_anchor": target_anchor.model_dump(mode="json"),
            "builder_profile_id": source.builder_profile_id,
            "tolerance_m": min(source_connector.tolerance_m, target_connector.tolerance_m),
            "instances": [instance.model_dump(mode="json") for instance in instances],
            "provenance": [
                f"assembly_plan:{plan.workflow_id}:{plan.schema_version}",
                f"source_manifest:{source.manifest_snapshot.snapshot_sha256}",
                f"target_manifest:{target.manifest_snapshot.snapshot_sha256}",
                f"builder_profile:{source.builder_profile.profile_sha256}",
            ],
        }
        operation_payload["operation_sha256"] = _canonical_sha256(operation_payload)
        operations.append(AssemblyOperation.model_validate(operation_payload))
    plan.operations = operations
    plan.compilation_status = "resolved"
    return plan


def _resolved_instance_parameters(
    connection_id: str,
    sector: SectorSpec | None,
) -> dict[str, float | int | bool | str]:
    if connection_id != "radio-to-mount" or sector is None:
        return {}
    profile = sector.radio_geometry_profile
    if profile is None:
        raise ValueError(f"ASSEMBLY_RADIO_PROFILE_MISSING:{sector.sector_id}")
    return {
        "vertical_offset_m": float(profile.vertical_offset_m),
        "radial_inset_m": float(profile.radial_inset_m),
    }


def _adapt_radio_target_frame(
    target_frame: AssemblyFrame,
    sector: SectorSpec,
    parameters: dict[str, float | int | bool | str],
) -> AssemblyFrame:
    azimuth = math.radians(float(sector.azimuth_deg))
    radial_inset = float(parameters["radial_inset_m"])
    vertical_offset = float(parameters["vertical_offset_m"])
    return target_frame.model_copy(
        update={
            "position_m": (
                target_frame.position_m[0] - math.sin(azimuth) * radial_inset,
                target_frame.position_m[1] - math.cos(azimuth) * radial_inset,
                float(sector.install_height_m) - vertical_offset,
            )
        }
    )


def _connection_instances(scene: SceneSpec, source, target) -> list[SectorSpec | None]:
    per_sector = any(
        component.builder_profile and component.builder_profile.instance_strategy == "per_sector"
        for component in (source, target)
    )
    return list(scene.sectors) if per_sector else [None]


def _validate_connector_pair(
    kind: str,
    source: AssetConnector,
    target: AssetConnector,
) -> None:
    if source.kind != kind or target.kind != kind:
        raise ValueError(
            f"ASSEMBLY_CONNECTOR_KIND_MISMATCH:{source.connector_id}:{target.connector_id}"
        )
    if target.kind not in source.compatible_connector_kinds or source.kind not in (
        target.compatible_connector_kinds
    ):
        raise ValueError(
            f"ASSEMBLY_CONNECTOR_INCOMPATIBLE:{source.connector_id}:{target.connector_id}"
        )
    allowed = {
        ("source", "target"),
        ("male", "female"),
        ("female", "male"),
    }
    if (
        source.gender != "bidirectional"
        and target.gender != "bidirectional"
        and (source.gender, target.gender) not in allowed
    ):
        raise ValueError(
            f"ASSEMBLY_CONNECTOR_GENDER_INCOMPATIBLE:{source.connector_id}:{target.connector_id}"
        )


def _resolved_anchor_frame(
    scene: SceneSpec,
    role_id: str,
    anchor: AssetAnchor,
    sector: SectorSpec | None,
    transforms: dict[tuple[str, str], tuple[list[list[float]], tuple[float, float, float]]],
) -> AssemblyFrame:
    instance_id = sector.sector_id if sector is not None else "global"
    if anchor.placement_policy == "sector_tower_surface":
        if sector is None:
            raise ValueError("ASSEMBLY_SECTOR_ANCHOR_REQUIRES_SECTOR")
        azimuth = math.radians(float(sector.azimuth_deg))
        radius = _tower_radius_at_height(scene, sector.install_height_m, azimuth)
        outward = _normalize((math.sin(azimuth), math.cos(azimuth), 0.0))
        return AssemblyFrame(
            position_m=(
                outward[0] * radius,
                outward[1] * radius,
                float(sector.install_height_m),
            ),
            normal=outward,
            up=(0.0, 0.0, 1.0),
        )
    if anchor.placement_policy == "ground_route":
        return AssemblyFrame(
            position_m=(0.0, 0.0, 0.2),
            normal=(0.0, 0.0, 1.0),
            up=(0.0, 1.0, 0.0),
        )
    transform = transforms.get((role_id, instance_id))
    if transform is None and sector is not None:
        transform = _declared_scene_transform(scene, role_id, sector)
    if transform is None:
        transform = _declared_global_transform(scene, role_id)
    if transform is None:
        raise ValueError(f"ASSEMBLY_TARGET_FRAME_UNRESOLVED:{role_id}:{instance_id}")
    return _transform_anchor(anchor, *transform)


def _declared_scene_transform(
    scene: SceneSpec,
    role_id: str,
    sector: SectorSpec,
) -> tuple[list[list[float]], tuple[float, float, float]] | None:
    if role_id == "sector_antenna":
        return _sector_pose_transform(
            sector.azimuth_deg, sector.mechanical_tilt_deg, (0.0, 0.0, sector.install_height_m)
        )
    if role_id == "remote_radio":
        profile = sector.radio_geometry_profile
        offset = float(profile.vertical_offset_m if profile else 1.0)
        return _sector_pose_transform(
            sector.azimuth_deg,
            0.0,
            (0.0, 0.0, sector.install_height_m - offset),
        )
    return None


def _declared_global_transform(
    scene: SceneSpec,
    role_id: str,
) -> tuple[list[list[float]], tuple[float, float, float]] | None:
    if role_id == "support_structure":
        return _identity_matrix(), (0.0, 0.0, 0.0)
    asset_type = {
        "ground_equipment": "cabinet",
        "timing_antenna": "gps",
    }.get(role_id)
    if asset_type:
        accessory = next(
            (item for item in scene.accessory_assets if item.asset_type == asset_type),
            None,
        )
        if accessory:
            return _euler_xyz_matrix(accessory.rotation_deg), tuple(accessory.position)
    return None


def _solve_attachment_transform(
    source_anchor: AssetAnchor,
    target_frame: AssemblyFrame,
) -> tuple[list[list[float]], tuple[float, float, float]]:
    source_basis = _frame_basis(source_anchor.normal, source_anchor.up)
    target_basis = _frame_basis(
        tuple(-component for component in target_frame.normal),
        target_frame.up,
    )
    rotation = _matrix_multiply(target_basis, _transpose(source_basis))
    rotated_source = _matrix_vector(rotation, source_anchor.position_m)
    translation = tuple(
        target_frame.position_m[index] - rotated_source[index] for index in range(3)
    )
    return rotation, translation


def _transform_anchor(
    anchor: AssetAnchor,
    rotation: list[list[float]],
    translation: tuple[float, float, float],
) -> AssemblyFrame:
    position = _matrix_vector(rotation, anchor.position_m)
    return AssemblyFrame(
        position_m=tuple(position[index] + translation[index] for index in range(3)),
        normal=_normalize(_matrix_vector(rotation, anchor.normal)),
        up=_normalize(_matrix_vector(rotation, anchor.up)),
    )


def _route_points(
    source: tuple[float, float, float],
    target: tuple[float, float, float],
) -> list[tuple[float, float, float]]:
    if math.dist(source, target) <= 1e-9:
        return [source, target]
    bend_z = min(source[2], target[2]) + abs(source[2] - target[2]) * 0.35
    return [source, (source[0], source[1], bend_z), (target[0], target[1], bend_z), target]


def _tower_radius_at_height(scene: SceneSpec, height_m: float, azimuth_rad: float) -> float:
    characteristics = scene.tower.characteristics
    base_width = float(characteristics.base_width_m or 4.0)
    top_ratio = {
        "lattice": 0.25,
        "monopole": 0.35,
        "rooftop_mast": 0.4,
        "small_cell_pole": 0.6,
    }.get(characteristics.structure, 0.5)
    top_width = float(characteristics.top_width_m or (base_width * top_ratio))
    ratio = min(max(float(height_m) / max(float(scene.tower.height_m), 1e-6), 0.0), 1.0)
    half_width = max((base_width + (top_width - base_width) * ratio) * 0.5, 0.02)
    if characteristics.structure == "lattice" and characteristics.leg_count != 3:
        direction = max(abs(math.sin(azimuth_rad)), abs(math.cos(azimuth_rad)), 1e-6)
        return half_width / direction
    return half_width


def _frame_basis(
    normal: Iterable[float],
    up: Iterable[float],
) -> list[list[float]]:
    x_axis = _normalize(tuple(normal))
    raw_up = _normalize(tuple(up))
    y_axis = _normalize(_cross(raw_up, x_axis))
    z_axis = _normalize(_cross(x_axis, y_axis))
    return [
        [x_axis[0], y_axis[0], z_axis[0]],
        [x_axis[1], y_axis[1], z_axis[1]],
        [x_axis[2], y_axis[2], z_axis[2]],
    ]


def _sector_pose_transform(
    azimuth_deg: float,
    tilt_deg: float,
    translation: tuple[float, float, float],
) -> tuple[list[list[float]], tuple[float, float, float]]:
    yaw = _rotation_z(-math.radians(float(azimuth_deg)))
    tilt = _rotation_x(-math.radians(float(tilt_deg)))
    return _matrix_multiply(yaw, tilt), translation


def _euler_xyz_matrix(rotation_deg: list[float]) -> list[list[float]]:
    x, y, z = (math.radians(float(value)) for value in rotation_deg)
    return _matrix_multiply(_matrix_multiply(_rotation_z(z), _rotation_y(y)), _rotation_x(x))


def _matrix_to_euler_xyz_deg(matrix: list[list[float]]) -> tuple[float, float, float]:
    sy = max(-1.0, min(1.0, -matrix[2][0]))
    y = math.asin(sy)
    if abs(math.cos(y)) > 1e-8:
        x = math.atan2(matrix[2][1], matrix[2][2])
        z = math.atan2(matrix[1][0], matrix[0][0])
    else:
        x = math.atan2(-matrix[1][2], matrix[1][1])
        z = 0.0
    return tuple(round(math.degrees(value), 9) for value in (x, y, z))


def _rotation_x(angle: float) -> list[list[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[1.0, 0.0, 0.0], [0.0, cosine, -sine], [0.0, sine, cosine]]


def _rotation_y(angle: float) -> list[list[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[cosine, 0.0, sine], [0.0, 1.0, 0.0], [-sine, 0.0, cosine]]


def _rotation_z(angle: float) -> list[list[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]


def _identity_matrix() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _matrix_multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[row][index] * b[index][column] for index in range(3)) for column in range(3)]
        for row in range(3)
    ]


def _matrix_vector(
    matrix: list[list[float]], vector: Iterable[float]
) -> tuple[float, float, float]:
    values = tuple(vector)
    return tuple(
        sum(matrix[row][column] * values[column] for column in range(3)) for row in range(3)
    )


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[column][row] for column in range(3)] for row in range(3)]


def _cross(a: Iterable[float], b: Iterable[float]) -> tuple[float, float, float]:
    left, right = tuple(a), tuple(b)
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _normalize(vector: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(value) for value in vector)
    length = math.sqrt(sum(value * value for value in values))
    if length <= 1e-9:
        raise ValueError("ASSEMBLY_ZERO_LENGTH_FRAME_VECTOR")
    return tuple(value / length for value in values)
