"""Mesh-level QA for exported GLB files.

This module parses glTF 2.0 accessors/bufferViews/buffers to compute real
world-space bounding boxes and compare them against the SceneSpec. It does not
depend on Blender and can run in the standard Python interpreter.
"""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.contracts.parametric import (
    BoundingBoxM,
    GenerationStrategy,
    GeometrySource,
    MeshCheckResult,
    MeshQAReport,
)
from core.contracts.scene import SceneSpec

SemanticInspectionMode = Literal[
    "semantic_extras",
    "mixed_semantic_name_based",
    "name_based",
    "not_available",
]

_PER_SECTOR_ROLES = {"antenna", "rru", "cable", "beam", "azimuth_arrow"}
_ROLE_ALIASES = {
    "antenna": "antenna",
    "antenna_panel": "antenna",
    "antenna_dish": "antenna",
    "dish": "antenna",
    "radio": "rru",
    "rru": "rru",
    "cable": "cable",
    "sector_beam": "beam",
    "beam": "beam",
    "azimuth_arrow": "azimuth_arrow",
    "power_cabinet": "power_cabinet",
    "cabinet": "power_cabinet",
    "gps_antenna": "gps",
    "gps": "gps",
    "foundation_concrete_pad": "foundation",
    "foundation": "foundation",
    "label": "label",
    "tower": "tower",
}


@dataclass(frozen=True)
class _SemanticEntity:
    identity: str
    role: str
    sector_id: str | None
    root_index: int
    node_indices: tuple[int, ...]
    extras: dict[str, Any]
    evidence_source: Literal["extras", "name"]


@dataclass(frozen=True)
class _SemanticIndex:
    mode: SemanticInspectionMode
    entities: tuple[_SemanticEntity, ...]

    @property
    def extras_root_count(self) -> int:
        return sum(entity.evidence_source == "extras" for entity in self.entities)

    @property
    def extras_coverage_ratio(self) -> float:
        if not self.entities:
            return 0.0
        return self.extras_root_count / len(self.entities)


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
        if not isinstance(m, list) or len(m) != 16:
            return _identity_matrix()
        # glTF stores matrices column-major. Internally we use row-major matrices.
        return [
            [m[0], m[4], m[8], m[12]],
            [m[1], m[5], m[9], m[13]],
            [m[2], m[6], m[10], m[14]],
            [m[3], m[7], m[11], m[15]],
        ]
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


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matrix_multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[row][index] * b[index][column] for index in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _world_node_transforms(payload: dict[str, Any]) -> dict[int, list[list[float]]]:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return {}
    parent_by_child: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        for child in node.get("children", []):
            if isinstance(child, int) and 0 <= child < len(nodes):
                parent_by_child[child] = parent_index

    cache: dict[int, list[list[float]]] = {}

    def resolve(index: int, visiting: set[int]) -> list[list[float]]:
        if index in cache:
            return cache[index]
        if index in visiting or not isinstance(nodes[index], dict):
            return _identity_matrix()
        local = _node_transform(nodes[index])
        parent_index = parent_by_child.get(index)
        if parent_index is None:
            world = local
        else:
            world = _matrix_multiply(resolve(parent_index, {*visiting, index}), local)
        cache[index] = world
        return world

    for node_index in range(len(nodes)):
        resolve(node_index, set())
    return cache


def _node_extras(payload: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Merge mesh and node extras, with node-level semantics taking precedence."""
    extras: dict[str, Any] = {}
    meshes = payload.get("meshes", [])
    mesh_index = node.get("mesh")
    if (
        isinstance(mesh_index, int)
        and isinstance(meshes, list)
        and 0 <= mesh_index < len(meshes)
        and isinstance(meshes[mesh_index], dict)
        and isinstance(meshes[mesh_index].get("extras"), dict)
    ):
        extras.update(meshes[mesh_index]["extras"])
    if isinstance(node.get("extras"), dict):
        extras.update(node["extras"])
    return extras


def _build_semantic_index(payload: dict[str, Any], scene: SceneSpec) -> _SemanticIndex:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return _SemanticIndex(mode="not_available", entities=())

    explicit_groups: dict[tuple[str, str], list[int]] = {}
    explicit_metadata: dict[tuple[str, str], tuple[str | None, dict[str, Any]]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        extras = _node_extras(payload, node)
        semantic_root = extras.get("semantic_root")
        if semantic_root is not True and not (
            isinstance(semantic_root, str) and semantic_root.strip()
        ):
            continue
        role = _canonical_role(extras.get("role") or extras.get("object_role"), node.get("name"))
        if role is None:
            continue
        sector_id = _canonical_sector_id(extras.get("sector_id"), scene)
        if sector_id is None:
            sector_id = _sector_id_from_name(str(node.get("name") or ""), scene)
        identity_value = extras.get("semantic_id") or extras.get("object_id")
        if not identity_value and isinstance(semantic_root, str):
            identity_value = semantic_root
        identity = str(identity_value or _entity_identity(role, sector_id, node.get("name"), scene))
        key = (role, identity)
        explicit_groups.setdefault(key, []).append(index)
        explicit_metadata[key] = (sector_id, extras)

    explicitly_covered: set[int] = set()
    entities: list[_SemanticEntity] = []
    all_explicit_indices = {index for indices in explicit_groups.values() for index in indices}
    for (role, identity), grouped_indices in explicit_groups.items():
        sector_id, _ = explicit_metadata[(role, identity)]
        root_index = _semantic_group_root_index(nodes, grouped_indices, identity)
        descendants = _descendant_indices(
            nodes,
            root_index,
            stop_roots=all_explicit_indices - set(grouped_indices),
        )
        grouped_node_indices = set(grouped_indices) | descendants
        explicitly_covered.update(grouped_node_indices)
        root_node = nodes[root_index] if isinstance(nodes[root_index], dict) else {}
        extras = _node_extras(payload, root_node)
        entities.append(
            _SemanticEntity(
                identity=identity,
                role=role,
                sector_id=sector_id,
                root_index=root_index,
                node_indices=tuple(sorted(grouped_node_indices)),
                extras=extras,
                evidence_source="extras",
            )
        )

    fallback_groups: dict[tuple[str, str], list[int]] = {}
    fallback_meta: dict[tuple[str, str], tuple[str | None, str]] = {}
    explicit_roles = {role for role, _ in explicit_groups}
    for index, node in enumerate(nodes):
        if index in explicitly_covered or not isinstance(node, dict):
            continue
        name = str(node.get("name") or "")
        normalized = _normalize_object_name(name)
        if not normalized or _is_auxiliary_object(normalized):
            continue
        role = _canonical_role(None, name)
        if role is None:
            continue
        if role == "tower" and _is_tower_accessory(normalized):
            continue
        # Once a tower semantic root exists, ungrouped tower-prefixed nodes are
        # accessories (lights, rods, markers), never additional tower geometry.
        if role == "tower" and role in explicit_roles:
            continue
        sector_id = _sector_id_from_name(name, scene)
        identity = _entity_identity(role, sector_id, name, scene)
        key = (role, identity)
        fallback_groups.setdefault(key, []).append(index)
        fallback_meta[key] = (sector_id, identity)

    for (role, _), indices in fallback_groups.items():
        sector_id, identity = fallback_meta[(role, _)]
        root_index = _topmost_index(nodes, indices)
        entities.append(
            _SemanticEntity(
                identity=identity,
                role=role,
                sector_id=sector_id,
                root_index=root_index,
                node_indices=tuple(sorted(set(indices))),
                extras={},
                evidence_source="name",
            )
        )

    merged_entities: dict[tuple[str, str], _SemanticEntity] = {}
    for entity in entities:
        key = (entity.role, entity.identity)
        current = merged_entities.get(key)
        if current is None:
            merged_entities[key] = entity
            continue
        preferred = entity if entity.evidence_source == "extras" else current
        merged_entities[key] = _SemanticEntity(
            identity=preferred.identity,
            role=preferred.role,
            sector_id=preferred.sector_id or current.sector_id,
            root_index=preferred.root_index,
            node_indices=tuple(sorted(set(current.node_indices) | set(entity.node_indices))),
            extras=preferred.extras,
            evidence_source=preferred.evidence_source,
        )
    entities = sorted(
        merged_entities.values(),
        key=lambda item: (item.role, item.sector_id or "", item.identity),
    )
    has_extras = any(entity.evidence_source == "extras" for entity in entities)
    has_names = any(entity.evidence_source == "name" for entity in entities)
    if has_extras and has_names:
        mode: SemanticInspectionMode = "mixed_semantic_name_based"
    elif has_extras:
        mode = "semantic_extras"
    elif has_names:
        mode = "name_based"
    else:
        mode = "not_available"
    return _SemanticIndex(mode=mode, entities=tuple(entities))


def _semantic_group_root_index(nodes: list[Any], indices: list[int], identity: str) -> int:
    normalized_identity = _normalize_object_name(identity)
    exact_name_matches = [
        index
        for index in indices
        if isinstance(nodes[index], dict)
        and _normalize_object_name(str(nodes[index].get("name") or "")) == normalized_identity
    ]
    if exact_name_matches:
        return _topmost_index(nodes, exact_name_matches)
    return _topmost_index(nodes, indices)


def _descendant_indices(
    nodes: list[Any],
    root_index: int,
    *,
    stop_roots: set[int],
) -> set[int]:
    found: set[int] = set()
    stack = [root_index]
    while stack:
        index = stack.pop()
        if index in found or not 0 <= index < len(nodes):
            continue
        found.add(index)
        node = nodes[index]
        if not isinstance(node, dict):
            continue
        for child in node.get("children", []):
            if not isinstance(child, int) or child in stop_roots:
                continue
            stack.append(child)
    return found


def _topmost_index(nodes: list[Any], indices: list[int]) -> int:
    candidates = set(indices)
    children = {
        child
        for index in candidates
        if isinstance(nodes[index], dict)
        for child in nodes[index].get("children", [])
        if isinstance(child, int) and child in candidates
    }
    return min(candidates - children or candidates)


def _canonical_role(value: object, name: object = None) -> str | None:
    if isinstance(value, str):
        normalized_value = _normalize_object_name(value)
        if normalized_value in _ROLE_ALIASES:
            return _ROLE_ALIASES[normalized_value]
    normalized_name = _normalize_object_name(str(name or ""))
    role_prefixes = (
        "power_cabinet",
        "gps_antenna",
        "azimuth_arrow",
        "sector_beam",
        "foundation_concrete_pad",
        "antenna_dish",
        "antenna_panel",
        "antenna",
        "dish",
        "radio",
        "rru",
        "cable",
        "foundation",
        "label",
        "tower",
        "cabinet",
        "gps",
        "beam",
    )
    for prefix in role_prefixes:
        if normalized_name == prefix or normalized_name.startswith(f"{prefix}_"):
            return _ROLE_ALIASES[prefix]
    return None


def _canonical_sector_id(value: object, scene: SceneSpec) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_token(value)
    for sector in scene.sectors:
        if _normalize_token(sector.sector_id) == normalized:
            return sector.sector_id
    return None


def _sector_id_from_name(name: str, scene: SceneSpec) -> str | None:
    tokens = _tokenize(name)
    for sector in sorted(
        scene.sectors, key=lambda item: len(_tokenize(item.sector_id)), reverse=True
    ):
        sector_tokens = _tokenize(sector.sector_id)
        if sector_tokens and _contains_token_sequence(tokens, sector_tokens):
            return sector.sector_id
    return None


def _contains_token_sequence(tokens: list[str], expected: list[str]) -> bool:
    width = len(expected)
    return any(
        tokens[index : index + width] == expected for index in range(len(tokens) - width + 1)
    )


def _tokenize(value: object) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value).lower())


def _normalize_token(value: object) -> str:
    return "_".join(_tokenize(value))


def _entity_identity(
    role: str,
    sector_id: str | None,
    name: object,
    scene: SceneSpec,
) -> str:
    if sector_id and role in _PER_SECTOR_ROLES | {"label"}:
        return f"{role}:{_normalize_token(sector_id)}"
    normalized_name = _normalize_object_name(str(name or ""))
    if role == "label":
        if "power_cabinet" in normalized_name or "cabinet" in _tokenize(normalized_name):
            return "label:power_cabinet"
        if "gps" in _tokenize(normalized_name):
            return "label:gps"
    if role in {"tower", "power_cabinet", "gps", "foundation"}:
        return f"{role}:global"
    stripped = re.sub(r"(?:_part)?_\d+$", "", normalized_name)
    expected_sector = _sector_id_from_name(normalized_name, scene)
    if expected_sector:
        return f"{role}:{_normalize_token(expected_sector)}"
    return f"{role}:{stripped or 'unnamed'}"


def _semantic_object_counts(index: _SemanticIndex) -> dict[str, int]:
    counts = {role: 0 for role in _ROLE_ALIASES.values()}
    for entity in index.entities:
        counts[entity.role] = counts.get(entity.role, 0) + 1
    return counts


def _semantic_sector_ids(index: _SemanticIndex) -> dict[str, list[str]]:
    by_role: dict[str, set[str]] = {}
    for entity in index.entities:
        if entity.sector_id:
            by_role.setdefault(entity.role, set()).add(entity.sector_id)
    return {role: sorted(values) for role, values in sorted(by_role.items())}


def _semantic_counts_from_names(object_names: list[str], scene: SceneSpec) -> dict[str, int]:
    payload = {"nodes": [{"name": name} for name in object_names]}
    return _semantic_object_counts(_build_semantic_index(payload, scene))


def _semantic_sector_ids_from_names(
    object_names: list[str], scene: SceneSpec
) -> dict[str, list[str]]:
    payload = {"nodes": [{"name": name} for name in object_names]}
    return _semantic_sector_ids(_build_semantic_index(payload, scene))


def _apply_matrix(
    m: list[list[float]], v: tuple[float, float, float]
) -> tuple[float, float, float]:
    x = m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2] + m[0][3]
    y = m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2] + m[1][3]
    z = m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] + m[2][3]
    return (x, y, z)


def _compute_glb_bounding_box(
    glb_path: Path,
    payload: dict[str, Any] | None = None,
    *,
    node_indices: set[int] | None = None,
) -> BoundingBoxM | None:
    payload = payload or _read_glb_json(glb_path)
    if payload is None:
        return None
    nodes = payload.get("nodes", [])
    meshes = payload.get("meshes", [])
    accessors = payload.get("accessors", [])
    if (
        not isinstance(nodes, list)
        or not isinstance(meshes, list)
        or not isinstance(accessors, list)
    ):
        return None
    world_transforms = _world_node_transforms(payload)
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False

    for node_index, node in enumerate(nodes):
        if node_indices is not None and node_index not in node_indices:
            continue
        if not isinstance(node, dict):
            continue
        mesh_index = node.get("mesh")
        if not isinstance(mesh_index, int):
            continue
        if not 0 <= mesh_index < len(meshes) or not isinstance(meshes[mesh_index], dict):
            continue
        mesh = meshes[mesh_index]
        transform = world_transforms.get(node_index, _node_transform(node))
        for primitive in mesh.get("primitives", []):
            if not isinstance(primitive, dict):
                continue
            accessor_index = primitive.get("attributes", {}).get("POSITION")
            if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
                continue
            # Use accessor min/max when available (fast path)
            accessor = accessors[accessor_index]
            if not isinstance(accessor, dict):
                continue
            amin = accessor.get("min")
            amax = accessor.get("max")
            if amin and amax and len(amin) >= 3 and len(amax) >= 3:
                for corner in _bounding_box_corners(amin, amax):
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


def _tower_bounding_box(
    glb_path: Path,
    payload: dict[str, Any],
    semantic_index: _SemanticIndex,
) -> BoundingBoxM | None:
    tower_indices = {
        node_index
        for entity in semantic_index.entities
        if entity.role == "tower"
        for node_index in entity.node_indices
    }
    if not tower_indices:
        return None
    return _compute_glb_bounding_box(glb_path, payload, node_indices=tower_indices)


def _bounding_box_corners(amin: list[float], amax: list[float]):
    return [
        (x, y, z)
        for x in (amin[0], amax[0])
        for y in (amin[1], amax[1])
        for z in (amin[2], amax[2])
    ]


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
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return re.sub(r"_+", "_", normalized)


def _is_auxiliary_object(normalized_name: str) -> bool:
    tokens = _tokenize(normalized_name)
    return "head" in tokens or "marker" in tokens


def _is_tower_accessory(normalized_name: str) -> bool:
    return any(
        normalized_name.startswith(prefix)
        for prefix in (
            "tower_accessory_",
            "tower_aviation_light",
            "tower_ladder",
            "tower_lightning_rod",
            "tower_platform",
        )
    )


def _aggregate_actual_classification(
    semantic_index: _SemanticIndex,
    field_name: Literal["geometry_source", "generation_strategy"],
) -> tuple[str, bool]:
    """Return actual provenance and whether semantic evidence is incomplete."""
    aliases = {
        "geometry_source": ("geometry_source", "effective_geometry_source"),
        "generation_strategy": ("generation_strategy", "effective_generation_mode"),
    }[field_name]
    values = [
        str(next((entity.extras.get(key) for key in aliases if entity.extras.get(key)), "unknown"))
        for entity in semantic_index.entities
        if entity.evidence_source == "extras"
    ]
    if len(values) != len(semantic_index.entities) or not values:
        return "unknown", True
    unique = set(values)
    allowed = {
        "parametric_generated",
        "imported_glb_exact",
        "stretched_imported_glb",
        "internal_project_generated",
        "procedural_fallback",
        "mixed",
        "degraded",
    }
    if "unknown" in unique or not unique.issubset(allowed):
        return "unknown", True
    if "degraded" in unique:
        return "degraded", False
    if "procedural_fallback" in unique:
        return "procedural_fallback", False
    if len(unique) == 1:
        return unique.pop(), False
    return "mixed", False


def _guess_geometry_source(semantic_index: _SemanticIndex) -> tuple[GeometrySource, bool]:
    value, mixed = _aggregate_actual_classification(semantic_index, "geometry_source")
    return value, mixed  # type: ignore[return-value]


def _guess_generation_strategy(
    semantic_index: _SemanticIndex,
) -> tuple[GenerationStrategy, bool]:
    value, mixed = _aggregate_actual_classification(semantic_index, "generation_strategy")
    return value, mixed  # type: ignore[return-value]


class MeshQA:
    """Bounded mesh QA using semantic GLB roots when the exporter provides them."""

    def validate(self, glb_path: Path, scene: SceneSpec) -> MeshQAReport:
        payload = _read_glb_json(glb_path)
        semantic_index = _build_semantic_index(payload or {}, scene)
        bounding_box = _compute_glb_bounding_box(glb_path, payload)
        tower_bbox = _tower_bounding_box(glb_path, payload or {}, semantic_index)
        geometry_source, geometry_source_incomplete = _guess_geometry_source(semantic_index)
        generation_strategy, generation_strategy_incomplete = _guess_generation_strategy(
            semantic_index
        )
        checks: list[MeshCheckResult] = []
        warnings: list[str] = []
        critical_errors: list[str] = []

        parse_ok = payload is not None and bounding_box is not None
        checks.append(MeshCheckResult(name="glb_parse_ok", passed=parse_ok))
        if not parse_ok:
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

        if geometry_source_incomplete:
            warnings.append("MESH_GEOMETRY_SOURCE_INCOMPLETE")
        if generation_strategy_incomplete:
            warnings.append("MESH_GENERATION_STRATEGY_INCOMPLETE")
        if semantic_index.mode == "name_based":
            warnings.append("MESH_QA_NAME_BASED_DEGRADED")
        elif semantic_index.mode == "mixed_semantic_name_based":
            warnings.append("MESH_QA_SEMANTIC_EXTRAS_PARTIAL")
        elif semantic_index.mode == "not_available":
            warnings.append("MESH_QA_SEMANTIC_OBJECTS_NOT_AVAILABLE")

        semantic_counts = _semantic_object_counts(semantic_index)
        expected_counts = _expected_semantic_counts(scene)
        semantic_coverage_ok = all(
            semantic_counts.get(role, 0) >= expected for role, expected in expected_counts.items()
        )
        checks.append(
            MeshCheckResult(
                name="semantic_object_coverage",
                passed=semantic_coverage_ok,
                detail=(
                    f"mode={semantic_index.mode}; expected={expected_counts}; "
                    f"observed={semantic_counts}"
                ),
            )
        )

        # Tower height is isolated to semantic tower roots. Scene accessories cannot mask it.
        expected_height = scene.tower.height_m
        actual_height = tower_bbox.height if tower_bbox is not None else None
        height_ok = actual_height is not None and abs(actual_height - expected_height) <= max(
            expected_height * 0.05, 0.75
        )
        checks.append(
            MeshCheckResult(
                name="tower_height_approx",
                passed=height_ok,
                detail=(
                    f"semantic_mode={semantic_index.mode}; expected={expected_height:.2f}m; "
                    f"tower_only={actual_height:.2f}m"
                    if actual_height is not None
                    else f"semantic_mode={semantic_index.mode}; no tower-only mesh bounds"
                ),
            )
        )
        if not height_ok:
            actual_label = f"{actual_height:.2f}m" if actual_height is not None else "unavailable"
            warnings.append(
                f"MESH_TOWER_HEIGHT_MISMATCH: expected {expected_height:.2f}m, got {actual_label}"
            )

        # Ground check: glTF is Y-up in exported coordinates.
        if bounding_box.min_y < -1.0 or bounding_box.max_y <= 0:
            critical_errors.append("MESH_SCENE_BELOW_GROUND")
            checks.append(MeshCheckResult(name="scene_above_ground", passed=False))
        else:
            checks.append(MeshCheckResult(name="scene_above_ground", passed=True))

        # Reasonable scale check
        if bounding_box.height > 300:
            warnings.append("MESH_SCENE_HEIGHT_UNREALISTIC")
            checks.append(MeshCheckResult(name="scale_realistic", passed=False))
        else:
            checks.append(MeshCheckResult(name="scale_realistic", passed=True))

        expected_antennas = len(scene.sectors)
        antenna_count = semantic_counts.get("antenna", 0)
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

        transform_checks = _transform_checks(payload, scene, semantic_index)
        checks.extend(transform_checks["checks"])
        warnings.extend(transform_checks["warnings"])
        mesh_level = (
            "mesh_level_transform_basic"
            if transform_checks["semantic_transform_checks_complete"]
            else "mesh_level_basic"
        )

        limitations = [
            "Mesh-level QA v1 does not perform collision detection.",
            "Mesh-level QA v1 does not validate RF propagation or structural wind/load.",
        ]
        if transform_checks["semantic_transform_checks_complete"]:
            limitations.append(
                "mesh_level_transform_basic verifies semantic-root transforms, per-sector HBA and "
                "basic azimuth orientation; it does not verify per-vertex panel normals."
            )
        else:
            limitations.append(
                f"Semantic GLB transform proof is incomplete ({semantic_index.mode}); checks are "
                "limited to mesh bounds and unique name-based roots where necessary."
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
            "semantic_object_coverage",
            "semantic_extras_complete",
            "scene_above_ground",
            "scale_realistic",
            "antenna_sector_transforms_present",
        }
        if semantic_index.mode in {"semantic_extras", "mixed_semantic_name_based"}:
            required_check_names.update(
                {
                    "antenna_hba_transform_approx",
                    "antenna_azimuth_transform_approx",
                }
            )
        if scene.visual_elements.include_labels:
            required_check_names.add("label_transforms_present")
        if scene.tower.characteristics.foundation_type != "unknown":
            required_check_names.add("foundation_transform_present")
        if scene.visual_elements.include_power_cabinet:
            required_check_names.add("power_cabinet_transform_present")
        if scene.visual_elements.include_gps_antenna:
            required_check_names.add("gps_transform_present")

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


def _expected_semantic_counts(scene: SceneSpec) -> dict[str, int]:
    return {
        "tower": 1,
        "antenna": len(scene.sectors),
        "rru": sum(1 for sector in scene.sectors if sector.radio_asset_id),
        "cable": sum(1 for sector in scene.sectors if sector.include_cable),
        "beam": len(scene.sectors) if scene.visual_elements.include_sector_beams else 0,
        "azimuth_arrow": (
            len(scene.sectors) if scene.visual_elements.include_azimuth_arrows else 0
        ),
        "power_cabinet": 1 if scene.visual_elements.include_power_cabinet else 0,
        "gps": 1 if scene.visual_elements.include_gps_antenna else 0,
        "foundation": int(scene.tower.characteristics.foundation_type != "unknown"),
        "label": _expected_label_count(scene),
    }


def _expected_label_count(scene: SceneSpec) -> int:
    if not scene.visual_elements.include_labels:
        return 0
    return (
        len(scene.sectors)
        + int(scene.visual_elements.include_power_cabinet)
        + int(scene.visual_elements.include_gps_antenna)
    )


def _transform_checks(
    payload: dict[str, Any] | None,
    scene: SceneSpec,
    semantic_index: _SemanticIndex | None = None,
) -> dict[str, Any]:
    checks: list[MeshCheckResult] = []
    warnings: list[str] = []
    if not payload:
        return {
            "checks": checks,
            "warnings": warnings,
            "semantic_transform_checks_complete": False,
        }
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return {
            "checks": checks,
            "warnings": warnings,
            "semantic_transform_checks_complete": False,
        }
    semantic_index = semantic_index or _build_semantic_index(payload, scene)
    if not semantic_index.entities:
        checks.append(
            MeshCheckResult(
                name="object_transforms_readable",
                passed=False,
                detail="no semantic or name-based object roots are available",
            )
        )
        return {
            "checks": checks,
            "warnings": warnings,
            "semantic_transform_checks_complete": False,
        }

    world_transforms = _world_node_transforms(payload)
    checks.append(
        MeshCheckResult(
            name="object_transforms_readable",
            passed=True,
            detail=(
                f"{len(semantic_index.entities)} unique semantic object root transforms readable"
            ),
        )
    )
    extras_complete, extras_detail = _semantic_extras_complete(semantic_index, scene)
    checks.append(
        MeshCheckResult(
            name="semantic_extras_complete",
            passed=extras_complete,
            detail=extras_detail,
        )
    )

    antennas = [entity for entity in semantic_index.entities if entity.role == "antenna"]
    expected_sector_ids = {sector.sector_id for sector in scene.sectors}
    sectors_with_antenna = {entity.sector_id for entity in antennas if entity.sector_id}
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

    hba_check = _antenna_hba_transform_check(antennas, scene, world_transforms)
    checks.append(
        MeshCheckResult(
            name="antenna_hba_transform_approx",
            passed=hba_check["passed"],
            detail=hba_check["detail"],
        )
    )
    if not hba_check["passed"]:
        warnings.append("MESH_ANTENNA_HBA_TRANSFORM_APPROX_FAILED")

    azimuth_check = _antenna_azimuth_transform_check(antennas, scene, world_transforms)
    checks.append(
        MeshCheckResult(
            name="antenna_azimuth_transform_approx",
            passed=azimuth_check["passed"],
            detail=azimuth_check["detail"],
        )
    )
    if not azimuth_check["passed"]:
        warnings.append("MESH_ANTENNA_AZIMUTH_TRANSFORM_APPROX_FAILED")

    if scene.visual_elements.include_labels:
        label_entities = [entity for entity in semantic_index.entities if entity.role == "label"]
        checks.append(
            MeshCheckResult(
                name="label_transforms_present",
                passed=len(label_entities) >= _expected_label_count(scene),
                detail=f"expected >= {_expected_label_count(scene)}, found {len(label_entities)}",
            )
        )
    if scene.tower.characteristics.foundation_type != "unknown":
        foundation_entities = [
            entity for entity in semantic_index.entities if entity.role == "foundation"
        ]
        checks.append(
            MeshCheckResult(
                name="foundation_transform_present",
                passed=bool(foundation_entities),
                detail=f"found {len(foundation_entities)} unique foundation root(s)",
            )
        )
    if scene.visual_elements.include_power_cabinet:
        cabinet_entities = [
            entity for entity in semantic_index.entities if entity.role == "power_cabinet"
        ]
        checks.append(
            MeshCheckResult(
                name="power_cabinet_transform_present",
                passed=bool(cabinet_entities),
                detail=f"found {len(cabinet_entities)} unique cabinet root(s)",
            )
        )
    if scene.visual_elements.include_gps_antenna:
        gps_entities = [entity for entity in semantic_index.entities if entity.role == "gps"]
        checks.append(
            MeshCheckResult(
                name="gps_transform_present",
                passed=bool(gps_entities),
                detail=f"found {len(gps_entities)} unique gps root(s)",
            )
        )
    semantic_transform_checks_complete = (
        extras_complete
        and sector_transforms_present
        and hba_check["passed"]
        and azimuth_check["passed"]
    )
    return {
        "checks": checks,
        "warnings": warnings,
        "semantic_transform_checks_complete": semantic_transform_checks_complete,
    }


def _semantic_extras_complete(
    semantic_index: _SemanticIndex,
    scene: SceneSpec,
) -> tuple[bool, str]:
    expected = _expected_semantic_counts(scene)
    actual = _semantic_object_counts(semantic_index)
    missing_roles = [
        f"{role}:{expected_count - actual.get(role, 0)}"
        for role, expected_count in expected.items()
        if actual.get(role, 0) < expected_count
    ]
    core_name_based = [
        entity.identity
        for entity in semantic_index.entities
        if entity.evidence_source == "name" and entity.role in {"tower", "antenna"}
    ]
    explicit_towers = [
        entity
        for entity in semantic_index.entities
        if entity.role == "tower" and entity.evidence_source == "extras"
    ]
    incomplete_antennas = [
        entity.identity
        for entity in semantic_index.entities
        if entity.role == "antenna"
        and (
            entity.sector_id is None
            or _number(entity.extras.get("requested_hba_m")) is None
            or _number(entity.extras.get("requested_azimuth_deg")) is None
            or _forward_axis_vector(entity.extras) is None
        )
    ]
    explicit_antenna_sectors = {
        entity.sector_id
        for entity in semantic_index.entities
        if entity.role == "antenna" and entity.evidence_source == "extras" and entity.sector_id
    }
    expected_antenna_sectors = {sector.sector_id for sector in scene.sectors}
    complete = (
        not missing_roles
        and not core_name_based
        and bool(explicit_towers)
        and explicit_antenna_sectors == expected_antenna_sectors
        and not incomplete_antennas
    )
    return (
        complete,
        f"missing_roles={missing_roles}; core_name_based={core_name_based}; "
        f"explicit_tower_roots={len(explicit_towers)}; "
        f"explicit_antenna_sectors={sorted(explicit_antenna_sectors)}; "
        f"incomplete_antennas={incomplete_antennas}",
    )


def _entity_position(
    entity: _SemanticEntity,
    world_transforms: dict[int, list[list[float]]],
) -> tuple[float, float, float] | None:
    matrix = world_transforms.get(entity.root_index)
    if matrix is None:
        return None
    return matrix[0][3], matrix[1][3], matrix[2][3]


def _antenna_hba_transform_check(
    antenna_entities: list[_SemanticEntity],
    scene: SceneSpec,
    world_transforms: dict[int, list[list[float]]],
) -> dict[str, Any]:
    entities_by_sector = {
        entity.sector_id: entity for entity in antenna_entities if entity.sector_id
    }
    results: list[str] = []
    passed = True
    for sector in scene.sectors:
        entity = entities_by_sector.get(sector.sector_id)
        if entity is None:
            passed = False
            results.append(f"{sector.sector_id}=missing")
            continue
        position = _entity_position(entity, world_transforms)
        requested = _number(entity.extras.get("requested_hba_m"))
        if position is None or requested is None:
            passed = False
            results.append(f"{sector.sector_id}=semantic_hba_unavailable")
            continue
        requested_ok = abs(requested - sector.install_height_m) <= 0.05
        actual_ok = abs(position[1] - sector.install_height_m) <= max(
            0.75, sector.install_height_m * 0.03
        )
        passed = passed and requested_ok and actual_ok
        results.append(
            f"{sector.sector_id}:requested={requested:.2f},actual_y={position[1]:.2f},"
            f"target={sector.install_height_m:.2f}"
        )
    return {"passed": passed, "detail": "; ".join(results)}


def _antenna_azimuth_transform_check(
    antenna_entities: list[_SemanticEntity],
    scene: SceneSpec,
    world_transforms: dict[int, list[list[float]]],
) -> dict[str, Any]:
    entities_by_sector = {
        entity.sector_id: entity for entity in antenna_entities if entity.sector_id
    }
    results: list[str] = []
    passed = True
    for sector in scene.sectors:
        entity = entities_by_sector.get(sector.sector_id)
        if entity is None:
            passed = False
            results.append(f"{sector.sector_id}=missing")
            continue
        matrix = world_transforms.get(entity.root_index)
        requested = _number(entity.extras.get("requested_azimuth_deg"))
        local_forward = _forward_axis_vector(entity.extras)
        if matrix is None or requested is None or local_forward is None:
            passed = False
            results.append(f"{sector.sector_id}=semantic_orientation_unavailable")
            continue
        world_forward = _apply_direction(matrix, local_forward)
        horizontal_norm = math.hypot(world_forward[0], world_forward[2])
        if horizontal_norm <= 1e-8:
            passed = False
            results.append(f"{sector.sector_id}=vertical_or_zero_forward_axis")
            continue
        actual = math.degrees(math.atan2(world_forward[0], -world_forward[2])) % 360.0
        requested_ok = _angular_delta(requested, sector.azimuth_deg) <= 0.05
        actual_ok = _angular_delta(actual, sector.azimuth_deg) <= 5.0
        passed = passed and requested_ok and actual_ok
        results.append(
            f"{sector.sector_id}:requested={requested:.2f},actual={actual:.2f},"
            f"target={sector.azimuth_deg:.2f}"
        )
    return {"passed": passed, "detail": "; ".join(results)}


def _forward_axis_vector(extras: dict[str, Any]) -> tuple[float, float, float] | None:
    semantic_value = extras.get("semantic_forward_axis")
    value = semantic_value or extras.get("front_axis")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("gltf:", "").replace(" ", "")
    gltf_axes = {
        "+x": (1.0, 0.0, 0.0),
        "x": (1.0, 0.0, 0.0),
        "-x": (-1.0, 0.0, 0.0),
        "+y": (0.0, 1.0, 0.0),
        "y": (0.0, 1.0, 0.0),
        "-y": (0.0, -1.0, 0.0),
        "+z": (0.0, 0.0, 1.0),
        "z": (0.0, 0.0, 1.0),
        "-z": (0.0, 0.0, -1.0),
    }
    if semantic_value:
        return gltf_axes.get(normalized)
    # Blender custom asset metadata uses Blender axes. Convert them to glTF Y-up.
    return {
        "+x": (1.0, 0.0, 0.0),
        "x": (1.0, 0.0, 0.0),
        "-x": (-1.0, 0.0, 0.0),
        "+y": (0.0, 0.0, -1.0),
        "y": (0.0, 0.0, -1.0),
        "-y": (0.0, 0.0, 1.0),
        "+z": (0.0, 1.0, 0.0),
        "z": (0.0, 1.0, 0.0),
        "-z": (0.0, -1.0, 0.0),
    }.get(normalized)


def _apply_direction(
    matrix: list[list[float]],
    direction: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        matrix[0][0] * direction[0] + matrix[0][1] * direction[1] + matrix[0][2] * direction[2],
        matrix[1][0] * direction[0] + matrix[1][1] * direction[1] + matrix[1][2] * direction[2],
        matrix[2][0] * direction[0] + matrix[2][1] * direction[1] + matrix[2][2] * direction[2],
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _angular_delta(actual: float, expected: float) -> float:
    delta = abs((actual - expected) % 360.0)
    return min(delta, 360.0 - delta)
