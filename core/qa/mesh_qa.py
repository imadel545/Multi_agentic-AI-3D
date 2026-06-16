"""Mesh-level QA for exported GLB files.

This module parses glTF 2.0 accessors/bufferViews/buffers to compute real
world-space bounding boxes and compare them against the SceneSpec. It does not
depend on Blender and can run in the standard Python interpreter.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from core.contracts.parametric import (
    BoundingBoxM,
    GenerationStrategy,
    GeometrySource,
    MeshCheckResult,
    MeshQAReport,
)
from core.contracts.scene import SceneSpec


def _read_glb_json(glb_path: Path) -> dict[str, Any] | None:
    try:
        data = glb_path.read_bytes()
    except Exception:
        return None
    if len(data) < 12:
        return None
    magic, version, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67 or version != 2:
        return None
    offset = 12
    json_data = None
    while offset < length:
        if offset + 8 > len(data):
            break
        chunk_length, chunk_type = struct.unpack("<II", data[offset : offset + 8])
        offset += 8
        if offset + chunk_length > len(data):
            break
        chunk_data = data[offset : offset + chunk_length]
        if chunk_type == 0x4E4F534A:
            json_data = json.loads(chunk_data)
        offset += chunk_length
        # Align to 4 bytes
        offset = (offset + 3) & ~3
    return json_data


def _get_buffer_bytes(glb_path: Path, payload: dict[str, Any], buffer_index: int) -> bytes | None:
    buffers = payload.get("buffers", [])
    if buffer_index >= len(buffers):
        return None
    buffer = buffers[buffer_index]
    uri = buffer.get("uri")
    if uri is None:
        # GLB binary chunk
        data = glb_path.read_bytes()
        offset = 12
        while offset < len(data):
            chunk_length, chunk_type = struct.unpack("<II", data[offset : offset + 8])
            offset += 8
            if chunk_type == 0x004E4942:
                return data[offset : offset + chunk_length]
            offset += chunk_length
            offset = (offset + 3) & ~3
        return None
    return None


def _read_accessor_floats(
    glb_path: Path,
    payload: dict[str, Any],
    accessor_index: int,
) -> list[tuple[float, float, float]] | None:
    accessors = payload.get("accessors", [])
    if accessor_index >= len(accessors):
        return None
    accessor = accessors[accessor_index]
    buffer_view_index = accessor.get("bufferView")
    if buffer_view_index is None:
        return None
    buffer_views = payload.get("bufferViews", [])
    if buffer_view_index >= len(buffer_views):
        return None
    buffer_view = buffer_views[buffer_view_index]
    buffer_index = buffer_view.get("buffer", 0)
    buffer_bytes = _get_buffer_bytes(glb_path, payload, buffer_index)
    if buffer_bytes is None:
        return None
    byte_offset = buffer_view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor.get("count", 0)
    component_type = accessor.get("componentType", 5126)
    byte_stride = buffer_view.get("byteStride", 0)

    type_format = accessor.get("type", "VEC3")
    if type_format != "VEC3":
        return None

    component_size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}.get(component_type)
    if component_size is None:
        return None

    if component_type == 5126:
        unpack_fmt = "<fff"
    elif component_type in {5122, 5123}:
        # unsigned short / short not handled for simplicity
        return None
    else:
        return None

    item_size = component_size * 3
    stride = byte_stride if byte_stride else item_size
    out: list[tuple[float, float, float]] = []
    for i in range(count):
        start = byte_offset + i * stride
        if start + item_size > len(buffer_bytes):
            break
        x, y, z = struct.unpack(unpack_fmt, buffer_bytes[start : start + item_size])
        out.append((x, y, z))
    return out


def _node_transform(node: dict[str, Any]) -> list[list[float]]:
    if "matrix" in node:
        m = node["matrix"]
        return [m[0:4], m[4:8], m[8:12], m[12:16]]
    t = node.get("translation", [0.0, 0.0, 0.0])
    r = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    s = node.get("scale", [1.0, 1.0, 1.0])
    # Convert quaternion to matrix (simplified; assume no rotation for v1 if complex)
    x, y, z, w = r
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    rot = [
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy), 0.0],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx), 0.0],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return [
        [rot[0][0] * s[0], rot[0][1] * s[1], rot[0][2] * s[2], t[0]],
        [rot[1][0] * s[0], rot[1][1] * s[1], rot[1][2] * s[2], t[1]],
        [rot[2][0] * s[0], rot[2][1] * s[1], rot[2][2] * s[2], t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _apply_matrix(
    m: list[list[float]], v: tuple[float, float, float]
) -> tuple[float, float, float]:
    x = m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2] + m[0][3]
    y = m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2] + m[1][3]
    z = m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] + m[2][3]
    return (x, y, z)


def _compute_glb_bounding_box(glb_path: Path) -> BoundingBoxM | None:
    payload = _read_glb_json(glb_path)
    if payload is None:
        return None
    nodes = payload.get("nodes", [])
    meshes = payload.get("meshes", [])
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False

    for node in nodes:
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        if mesh_index >= len(meshes):
            continue
        mesh = meshes[mesh_index]
        transform = _node_transform(node)
        for primitive in mesh.get("primitives", []):
            accessor_index = primitive.get("attributes", {}).get("POSITION")
            if accessor_index is None:
                continue
            # Use accessor min/max when available (fast path)
            accessor = payload.get("accessors", [])[accessor_index]
            amin = accessor.get("min")
            amax = accessor.get("max")
            if amin and amax and len(amin) >= 3 and len(amax) >= 3:
                for corner in [(amin[0], amin[1], amin[2]), (amax[0], amax[1], amax[2])]:
                    wx, wy, wz = _apply_matrix(transform, corner)
                    min_x, max_x = min(min_x, wx), max(max_x, wx)
                    min_y, max_y = min(min_y, wy), max(max_y, wy)
                    min_z, max_z = min(min_z, wz), max(max_z, wz)
                    found = True
            else:
                positions = _read_accessor_floats(glb_path, payload, accessor_index)
                if positions is None:
                    continue
                for v in positions:
                    wx, wy, wz = _apply_matrix(transform, v)
                    min_x, max_x = min(min_x, wx), max(max_x, wx)
                    min_y, max_y = min(min_y, wy), max(max_y, wy)
                    min_z, max_z = min(min_z, wz), max(max_z, wz)
                    found = True

    if not found:
        return None
    return BoundingBoxM(
        min_x=min_x,
        min_y=min_y,
        min_z=min_z,
        max_x=max_x,
        max_y=max_y,
        max_z=max_z,
    )


def _object_prefix_counts(object_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in object_names:
        normalized = _normalize_object_name(name)
        for prefix in (
            "tower",
            "antenna",
            "radio",
            "cable",
            "sector_beam",
            "azimuth_arrow",
            "power_cabinet",
            "gps",
            "foundation",
            "label",
        ):
            if normalized == prefix or normalized.startswith(f"{prefix}_"):
                counts[prefix] = counts.get(prefix, 0) + 1
                break
    return counts


def _normalize_object_name(name: str) -> str:
    return str(name).lower().replace(":", "_").replace("-", "_")


def _guess_geometry_source(scene: SceneSpec) -> GeometrySource:
    # Aggregate strategy from scene; default to parametric if tower is parametric.
    strategies = {scene.tower.generation_strategy}
    for sector in scene.sectors:
        strategies.add(sector.antenna_generation_strategy)
        if sector.radio_asset_id:
            strategies.add(sector.radio_generation_strategy)
    for accessory in scene.accessory_assets:
        strategies.add(accessory.generation_strategy)
    if "parametric_generated" in strategies:
        return "parametric_generated"
    if "imported_glb_exact" in strategies:
        return "imported_glb_exact"
    if "stretched_imported_glb" in strategies:
        return "stretched_imported_glb"
    if "internal_project_generated" in strategies:
        return "internal_project_generated"
    if "procedural_fallback" in strategies or "degraded" in strategies:
        return "procedural_fallback"
    return "unknown"


def _guess_generation_strategy(scene: SceneSpec) -> GenerationStrategy:
    # Mirror geometry source logic for strategy.
    source = _guess_geometry_source(scene)
    if source == "parametric_generated":
        return "parametric_generated"
    if source == "imported_glb_exact":
        return "imported_glb_exact"
    if source == "stretched_imported_glb":
        return "stretched_imported_glb"
    if source == "internal_project_generated":
        return "internal_project_generated"
    if source == "procedural_fallback":
        return "procedural_fallback"
    return "unknown"


class MeshQA:
    """Basic mesh-level QA for a generated GLB."""

    def validate(self, glb_path: Path, scene: SceneSpec) -> MeshQAReport:
        bounding_box = _compute_glb_bounding_box(glb_path)
        geometry_source = _guess_geometry_source(scene)
        generation_strategy = _guess_generation_strategy(scene)
        checks: list[MeshCheckResult] = []
        warnings: list[str] = []
        critical_errors: list[str] = []

        checks.append(MeshCheckResult(name="glb_parse_ok", passed=bounding_box is not None))
        if bounding_box is None:
            critical_errors.append("GLB_MESH_PARSE_FAILED")
            return MeshQAReport(
                level="mesh_level_basic",
                geometry_source=geometry_source,
                generation_strategy=generation_strategy,
                glb_parse_ok=False,
                checks=checks,
                warnings=warnings,
                critical_errors=critical_errors,
                mesh_qa_passed=False,
                limitations=["Mesh-level QA could not parse the GLB accessors."],
            )

        # Tower height check
        expected_height = scene.tower.height_m
        actual_height = bounding_box.height
        height_ok = abs(actual_height - expected_height) <= max(expected_height * 0.15, 1.0)
        checks.append(
            MeshCheckResult(
                name="tower_height_approx",
                passed=height_ok,
                detail=f"expected {expected_height:.2f}m, got {actual_height:.2f}m",
            )
        )
        if not height_ok:
            warnings.append(
                f"MESH_TOWER_HEIGHT_MISMATCH: expected {expected_height:.2f}m, "
                f"got {actual_height:.2f}m"
            )

        # Ground check: glTF is Y-up in exported coordinates.
        if bounding_box.max_y < 0:
            critical_errors.append("MESH_SCENE_BELOW_GROUND")
            checks.append(MeshCheckResult(name="scene_above_ground", passed=False))
        else:
            checks.append(MeshCheckResult(name="scene_above_ground", passed=True))

        # Reasonable scale check
        if actual_height > 300:
            warnings.append("MESH_SCENE_HEIGHT_UNREALISTIC")
            checks.append(MeshCheckResult(name="scale_realistic", passed=False))
        else:
            checks.append(MeshCheckResult(name="scale_realistic", passed=True))

        payload = _read_glb_json(glb_path) or {}
        object_names = [node.get("name", "") for node in payload.get("nodes", [])]
        prefix_counts = _object_prefix_counts(object_names)

        # Object count check (coarse)
        expected_antennas = len(scene.sectors)
        antenna_count = prefix_counts.get("antenna", 0)
        checks.append(
            MeshCheckResult(
                name="antenna_count",
                passed=antenna_count >= expected_antennas,
                detail=f"expected >= {expected_antennas}, found {antenna_count}",
            )
        )
        if antenna_count < expected_antennas:
            warnings.append(
                f"MESH_ANTENNA_COUNT_LOW: expected {expected_antennas}, found {antenna_count}"
            )

        transform_checks = _transform_checks(payload, scene)
        checks.extend(transform_checks["checks"])
        warnings.extend(transform_checks["warnings"])
        mesh_level = (
            "mesh_level_transform_basic"
            if transform_checks["transform_checks_available"]
            else "mesh_level_basic"
        )

        limitations = [
            "Mesh-level QA v1 does not perform collision detection.",
            "Mesh-level QA v1 does not validate RF propagation or structural wind/load.",
        ]
        if transform_checks["transform_checks_available"]:
            limitations.append(
                "mesh_level_transform_basic verifies object-role node transforms and approximate "
                "antenna height, not exact per-vertex antenna orientation."
            )
        else:
            limitations.append(
                "Mesh-level QA could not read role-specific transforms; individual antenna HBA "
                "and azimuth remain metadata/object-name based."
            )
        limitations.extend(
            [
                "Azimuth arrows are verified by object names/metadata, not vector orientation.",
                "Materials are not vendor-grade validated.",
            ]
        )

        required_check_names = {
            "tower_height_approx",
            "antenna_count",
            "scene_above_ground",
            "scale_realistic",
            "antenna_sector_transforms_present",
            "antenna_hba_transform_approx",
        }

        mesh_qa_passed = not critical_errors and not any(
            c.name in required_check_names and not c.passed for c in checks
        )

        return MeshQAReport(
            level=mesh_level,
            geometry_source=geometry_source,
            generation_strategy=generation_strategy,
            glb_parse_ok=True,
            bounding_box_m=bounding_box,
            checks=checks,
            warnings=warnings,
            critical_errors=critical_errors,
            mesh_qa_passed=mesh_qa_passed,
            limitations=limitations,
        )


def _transform_checks(payload: dict[str, Any] | None, scene: SceneSpec) -> dict[str, Any]:
    checks: list[MeshCheckResult] = []
    warnings: list[str] = []
    if not payload:
        return {"checks": checks, "warnings": warnings, "transform_checks_available": False}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return {"checks": checks, "warnings": warnings, "transform_checks_available": False}
    named_nodes = [node for node in nodes if isinstance(node, dict) and node.get("name")]
    transform_nodes = [node for node in named_nodes if "translation" in node or "matrix" in node]
    if not transform_nodes:
        checks.append(
            MeshCheckResult(
                name="object_transforms_readable",
                passed=False,
                detail="no named GLB nodes expose translation/matrix transforms",
            )
        )
        return {"checks": checks, "warnings": warnings, "transform_checks_available": False}

    checks.append(
        MeshCheckResult(
            name="object_transforms_readable",
            passed=True,
            detail=f"{len(transform_nodes)} named node transforms readable",
        )
    )
    antenna_positions = _role_positions(transform_nodes, "antenna")
    expected_sector_ids = {sector.sector_id for sector in scene.sectors}
    sectors_with_antenna = {
        sector_id
        for sector_id in expected_sector_ids
        if any(_normalize_object_name(sector_id) in name for name, _ in antenna_positions)
    }
    sector_transforms_present = sectors_with_antenna == expected_sector_ids
    checks.append(
        MeshCheckResult(
            name="antenna_sector_transforms_present",
            passed=sector_transforms_present,
            detail=f"expected {sorted(expected_sector_ids)}, found {sorted(sectors_with_antenna)}",
        )
    )
    if not sector_transforms_present:
        warnings.append("MESH_ANTENNA_SECTOR_TRANSFORMS_MISSING")

    expected_heights = [sector.install_height_m for sector in scene.sectors]
    hba_check = _antenna_hba_transform_check(antenna_positions, expected_heights)
    checks.append(
        MeshCheckResult(
            name="antenna_hba_transform_approx",
            passed=hba_check["passed"],
            detail=hba_check["detail"],
        )
    )
    if not hba_check["passed"]:
        warnings.append("MESH_ANTENNA_HBA_TRANSFORM_APPROX_FAILED")

    if scene.visual_elements.include_labels:
        label_positions = _role_positions(transform_nodes, "label")
        checks.append(
            MeshCheckResult(
                name="label_transforms_present",
                passed=len(label_positions) >= len(scene.sectors),
                detail=f"expected >= {len(scene.sectors)}, found {len(label_positions)}",
            )
        )
    if scene.tower.characteristics.foundation_type == "concrete_pad":
        foundation_positions = _role_positions(transform_nodes, "foundation")
        checks.append(
            MeshCheckResult(
                name="foundation_transform_present",
                passed=bool(foundation_positions),
                detail=f"found {len(foundation_positions)} foundation transform(s)",
            )
        )
    if scene.visual_elements.include_power_cabinet:
        cabinet_positions = _role_positions(transform_nodes, "power_cabinet")
        checks.append(
            MeshCheckResult(
                name="power_cabinet_transform_present",
                passed=bool(cabinet_positions),
                detail=f"found {len(cabinet_positions)} cabinet transform(s)",
            )
        )
    if scene.visual_elements.include_gps_antenna:
        gps_positions = _role_positions(transform_nodes, "gps")
        checks.append(
            MeshCheckResult(
                name="gps_transform_present",
                passed=bool(gps_positions),
                detail=f"found {len(gps_positions)} gps transform(s)",
            )
        )
    return {"checks": checks, "warnings": warnings, "transform_checks_available": True}


def _role_positions(
    nodes: list[dict[str, Any]],
    role_prefix: str,
) -> list[tuple[str, tuple[float, float, float]]]:
    positions = []
    for node in nodes:
        name = _normalize_object_name(str(node.get("name") or ""))
        if not (name == role_prefix or name.startswith(f"{role_prefix}_")):
            continue
        matrix = _node_transform(node)
        positions.append((name, (matrix[0][3], matrix[1][3], matrix[2][3])))
    return positions


def _antenna_hba_transform_check(
    antenna_positions: list[tuple[str, tuple[float, float, float]]],
    expected_heights: list[float],
) -> dict[str, Any]:
    if not antenna_positions:
        return {"passed": False, "detail": "no antenna transforms found"}
    expected = sum(expected_heights) / len(expected_heights)
    axes = {
        "y": [position[1] for _, position in antenna_positions],
        "z": [position[2] for _, position in antenna_positions],
    }
    axis, values = min(
        axes.items(),
        key=lambda item: sum(abs(value - expected) for value in item[1]) / max(len(item[1]), 1),
    )
    tolerance = max(2.0, expected * 0.15)
    near = [value for value in values if abs(value - expected) <= tolerance]
    passed = len(near) >= len(expected_heights)
    actual = sum(values) / len(values)
    return {
        "passed": passed,
        "detail": (
            f"axis={axis}, expected≈{expected:.2f}m, mean={actual:.2f}m, "
            f"within_tolerance={len(near)}/{len(expected_heights)}"
        ),
    }
