from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK_TYPE = 0x4E4F534A
GLB_BIN_CHUNK_TYPE = 0x004E4942

_COMPONENT_FORMATS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
_TYPE_COMPONENT_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


@dataclass(frozen=True)
class GltfIntegrityResult:
    payload: dict[str, Any] | None
    container_valid: bool
    binary_chunk_count: int
    buffer_count: int
    buffer_view_count: int
    primitive_count: int
    valid_primitive_count: int
    valid_position_accessor_count: int
    valid_mesh_indices: frozenset[int]
    errors: tuple[str, ...]


def inspect_gltf_integrity(path: Path) -> GltfIntegrityResult:
    errors: list[str] = []
    payload, binary_chunks = _load_document(path, errors)
    if payload is None:
        return GltfIntegrityResult(
            payload=None,
            container_valid=False,
            binary_chunk_count=len(binary_chunks),
            buffer_count=0,
            buffer_view_count=0,
            primitive_count=0,
            valid_primitive_count=0,
            valid_position_accessor_count=0,
            valid_mesh_indices=frozenset(),
            errors=tuple(_unique(errors or ["GLB_FORMAT_INVALID"])),
        )

    asset = payload.get("asset")
    if not isinstance(asset, dict) or str(asset.get("version")) != "2.0":
        errors.append("GLTF_ASSET_VERSION_INVALID")

    buffers = _load_buffers(path, payload, binary_chunks, errors)
    buffer_views = payload.get("bufferViews", [])
    accessors = payload.get("accessors", [])
    meshes = payload.get("meshes", [])
    nodes = payload.get("nodes", [])
    if not isinstance(buffer_views, list):
        errors.append("GLTF_BUFFERVIEWS_INVALID")
        buffer_views = []
    if not isinstance(accessors, list):
        errors.append("GLTF_ACCESSORS_INVALID")
        accessors = []
    if not isinstance(meshes, list):
        errors.append("GLTF_MESHES_INVALID")
        meshes = []
    if not isinstance(nodes, list):
        errors.append("GLTF_NODES_INVALID")
        nodes = []
    if meshes and not buffers:
        errors.append("GLB_BINARY_CHUNK_MISSING")

    _validate_buffer_views(buffer_views, buffers, errors)
    _validate_nodes(nodes, meshes, errors)
    primitive_count = 0
    valid_primitive_count = 0
    valid_position_accessors: set[int] = set()
    valid_mesh_indices: set[int] = set()
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives"), list):
            errors.append("GLTF_MESH_PRIMITIVES_INVALID")
            continue
        mesh_valid = False
        for primitive in mesh["primitives"]:
            primitive_count += 1
            if not isinstance(primitive, dict):
                errors.append("GLTF_PRIMITIVE_INVALID")
                continue
            attributes = primitive.get("attributes")
            position_index = attributes.get("POSITION") if isinstance(attributes, dict) else None
            positions = _read_accessor(
                accessors,
                buffer_views,
                buffers,
                position_index,
                expected_type="VEC3",
                expected_component_type=5126,
                error_prefix="GLTF_POSITION",
                errors=errors,
            )
            position_valid = bool(positions) and all(
                all(math.isfinite(float(component)) for component in value) for value in positions
            )
            if not position_valid:
                errors.append("GLTF_POSITION_DATA_INVALID")
                continue
            valid_position_accessors.add(int(position_index))

            indices_valid = True
            indices_index = primitive.get("indices")
            if indices_index is not None:
                indices = _read_accessor(
                    accessors,
                    buffer_views,
                    buffers,
                    indices_index,
                    expected_type="SCALAR",
                    allowed_component_types={5121, 5123, 5125},
                    error_prefix="GLTF_INDEX",
                    errors=errors,
                )
                flat_indices = [int(value[0]) for value in indices or []]
                indices_valid = (
                    bool(flat_indices)
                    and min(flat_indices) >= 0
                    and max(flat_indices) < len(positions)
                )
                if not indices_valid:
                    errors.append("GLTF_INDEX_DATA_INVALID")
            if position_valid and indices_valid:
                valid_primitive_count += 1
                mesh_valid = True
        if mesh_valid:
            valid_mesh_indices.add(mesh_index)

    if primitive_count == 0:
        errors.append("GLB_MESH_PRIMITIVES_MISSING")
    if valid_primitive_count != primitive_count:
        errors.append("GLTF_PRIMITIVE_DATA_INCOMPLETE")
    if not valid_position_accessors:
        errors.append("GLB_POSITION_ACCESSORS_EMPTY")

    return GltfIntegrityResult(
        payload=payload,
        container_valid=not any(
            error.startswith(("GLB_HEADER", "GLB_CHUNK", "GLB_JSON", "GLTF_DOCUMENT"))
            for error in errors
        ),
        binary_chunk_count=len(binary_chunks),
        buffer_count=len(payload.get("buffers", []))
        if isinstance(payload.get("buffers"), list)
        else 0,
        buffer_view_count=len(buffer_views),
        primitive_count=primitive_count,
        valid_primitive_count=valid_primitive_count,
        valid_position_accessor_count=len(valid_position_accessors),
        valid_mesh_indices=frozenset(valid_mesh_indices),
        errors=tuple(_unique(errors)),
    )


def _load_document(
    path: Path,
    errors: list[str],
) -> tuple[dict[str, Any] | None, list[bytes]]:
    try:
        if path.suffix.lower() == ".gltf":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return (payload if isinstance(payload, dict) else None), []
        data = path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("GLTF_DOCUMENT_UNREADABLE")
        return None, []
    if len(data) < 20:
        errors.append("GLB_HEADER_TRUNCATED")
        return None, []
    try:
        magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    except struct.error:
        errors.append("GLB_HEADER_TRUNCATED")
        return None, []
    if magic != GLB_MAGIC or version != 2:
        errors.append("GLB_HEADER_INVALID")
        return None, []
    if declared_length != len(data):
        errors.append("GLB_HEADER_LENGTH_MISMATCH")
        return None, []

    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset < declared_length:
        if offset + 8 > declared_length:
            errors.append("GLB_CHUNK_HEADER_TRUNCATED")
            return None, []
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if chunk_length % 4 != 0 or offset + chunk_length > declared_length:
            errors.append("GLB_CHUNK_LENGTH_INVALID")
            return None, []
        chunks.append((chunk_type, data[offset : offset + chunk_length]))
        offset += chunk_length
    if not chunks or chunks[0][0] != GLB_JSON_CHUNK_TYPE:
        errors.append("GLB_JSON_CHUNK_MISSING")
        return None, []
    if sum(chunk_type == GLB_JSON_CHUNK_TYPE for chunk_type, _ in chunks) != 1:
        errors.append("GLB_JSON_CHUNK_COUNT_INVALID")
        return None, []
    binary_chunks = [chunk for chunk_type, chunk in chunks if chunk_type == GLB_BIN_CHUNK_TYPE]
    if len(binary_chunks) > 1:
        errors.append("GLB_BINARY_CHUNK_COUNT_INVALID")
    try:
        payload = json.loads(chunks[0][1].decode("utf-8").rstrip(" \t\r\n\0"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append("GLB_JSON_INVALID")
        return None, binary_chunks
    if not isinstance(payload, dict):
        errors.append("GLTF_DOCUMENT_INVALID")
        return None, binary_chunks
    return payload, binary_chunks


def _load_buffers(
    path: Path,
    payload: dict[str, Any],
    binary_chunks: list[bytes],
    errors: list[str],
) -> list[bytes | None]:
    definitions = payload.get("buffers", [])
    if not isinstance(definitions, list):
        errors.append("GLTF_BUFFERS_INVALID")
        return []
    loaded: list[bytes | None] = []
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            errors.append("GLTF_BUFFER_INVALID")
            loaded.append(None)
            continue
        uri = definition.get("uri")
        data: bytes | None = None
        if uri is None:
            data = binary_chunks[0] if index == 0 and binary_chunks else None
            if data is None:
                errors.append("GLB_BINARY_CHUNK_MISSING")
        elif isinstance(uri, str) and uri.startswith("data:"):
            try:
                data = base64.b64decode(uri.split(",", 1)[1], validate=True)
            except (IndexError, ValueError):
                errors.append("GLTF_BUFFER_DATA_URI_INVALID")
        elif isinstance(uri, str):
            candidate = (path.parent / uri).resolve()
            try:
                candidate.relative_to(path.parent.resolve())
                data = candidate.read_bytes()
            except (ValueError, OSError):
                errors.append("GLTF_EXTERNAL_BUFFER_UNREADABLE")
        else:
            errors.append("GLTF_BUFFER_URI_INVALID")
        declared_length = definition.get("byteLength")
        if (
            not isinstance(declared_length, int)
            or declared_length < 0
            or data is None
            or len(data) < declared_length
            or len(data) - declared_length > 3
        ):
            errors.append("GLTF_BUFFER_LENGTH_INVALID")
        loaded.append(data)
    return loaded


def _validate_buffer_views(
    buffer_views: list[Any],
    buffers: list[bytes | None],
    errors: list[str],
) -> None:
    for view in buffer_views:
        if not isinstance(view, dict):
            errors.append("GLTF_BUFFERVIEW_INVALID")
            continue
        buffer_index = view.get("buffer")
        byte_offset = view.get("byteOffset", 0)
        byte_length = view.get("byteLength")
        if (
            not isinstance(buffer_index, int)
            or not 0 <= buffer_index < len(buffers)
            or buffers[buffer_index] is None
            or not isinstance(byte_offset, int)
            or byte_offset < 0
            or not isinstance(byte_length, int)
            or byte_length <= 0
            or byte_offset + byte_length > len(buffers[buffer_index] or b"")
        ):
            errors.append("GLTF_BUFFERVIEW_RANGE_INVALID")


def _validate_nodes(
    nodes: list[Any],
    meshes: list[Any],
    errors: list[str],
) -> None:
    parent_by_child: dict[int, int] = {}
    adjacency: dict[int, list[int]] = {}
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append("GLTF_NODE_INVALID")
            continue
        matrix = node.get("matrix")
        has_trs = any(field in node for field in ("translation", "rotation", "scale"))
        if matrix is not None:
            if has_trs or not _finite_vector(matrix, 16):
                errors.append("GLTF_NODE_TRANSFORM_INVALID")
        else:
            if "translation" in node and not _finite_vector(node["translation"], 3):
                errors.append("GLTF_NODE_TRANSFORM_INVALID")
            if "scale" in node and not _finite_vector(node["scale"], 3):
                errors.append("GLTF_NODE_TRANSFORM_INVALID")
            if "rotation" in node:
                rotation = node["rotation"]
                if not _finite_vector(rotation, 4):
                    errors.append("GLTF_NODE_TRANSFORM_INVALID")
                else:
                    norm = math.sqrt(sum(float(value) ** 2 for value in rotation))
                    if norm <= 1e-8 or abs(norm - 1.0) > 1e-3:
                        errors.append("GLTF_NODE_TRANSFORM_INVALID")

        mesh_index = node.get("mesh")
        if mesh_index is not None and (
            not isinstance(mesh_index, int)
            or isinstance(mesh_index, bool)
            or not 0 <= mesh_index < len(meshes)
        ):
            errors.append("GLTF_NODE_MESH_INVALID")

        children = node.get("children", [])
        if not isinstance(children, list):
            errors.append("GLTF_NODE_CHILDREN_INVALID")
            continue
        integer_children = [
            child for child in children if isinstance(child, int) and not isinstance(child, bool)
        ]
        if len(integer_children) != len(children) or len(integer_children) != len(
            set(integer_children)
        ):
            errors.append("GLTF_NODE_CHILDREN_INVALID")
        valid_children: list[int] = []
        for child in children:
            if (
                not isinstance(child, int)
                or isinstance(child, bool)
                or not 0 <= child < len(nodes)
                or child == node_index
                or child in parent_by_child
            ):
                errors.append("GLTF_NODE_GRAPH_INVALID")
                continue
            parent_by_child[child] = node_index
            valid_children.append(child)
        adjacency[node_index] = valid_children

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node_index: int) -> bool:
        if node_index in visiting:
            return False
        if node_index in visited:
            return True
        visiting.add(node_index)
        for child in adjacency.get(node_index, []):
            if not visit(child):
                return False
        visiting.remove(node_index)
        visited.add(node_index)
        return True

    if any(not visit(node_index) for node_index in range(len(nodes)) if node_index not in visited):
        errors.append("GLTF_NODE_GRAPH_INVALID")


def _finite_vector(value: object, length: int) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) == length
        and all(
            isinstance(component, (int, float))
            and not isinstance(component, bool)
            and math.isfinite(float(component))
            for component in value
        )
    )


def _read_accessor(
    accessors: list[Any],
    buffer_views: list[Any],
    buffers: list[bytes | None],
    accessor_index: object,
    *,
    expected_type: str,
    error_prefix: str,
    errors: list[str],
    expected_component_type: int | None = None,
    allowed_component_types: set[int] | None = None,
) -> list[tuple[int | float, ...]] | None:
    if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
        errors.append(f"{error_prefix}_ACCESSOR_INVALID")
        return None
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or accessor.get("sparse") is not None:
        errors.append(f"{error_prefix}_ACCESSOR_INVALID")
        return None
    component_type = accessor.get("componentType")
    type_name = accessor.get("type")
    count = accessor.get("count")
    view_index = accessor.get("bufferView")
    if (
        type_name != expected_type
        or not isinstance(count, int)
        or count <= 0
        or not isinstance(view_index, int)
        or not 0 <= view_index < len(buffer_views)
        or component_type not in _COMPONENT_FORMATS
        or (expected_component_type is not None and component_type != expected_component_type)
        or (allowed_component_types is not None and component_type not in allowed_component_types)
    ):
        errors.append(f"{error_prefix}_ACCESSOR_INVALID")
        return None
    view = buffer_views[view_index]
    if not isinstance(view, dict):
        errors.append(f"{error_prefix}_BUFFERVIEW_INVALID")
        return None
    buffer_index = view.get("buffer")
    if not isinstance(buffer_index, int) or not 0 <= buffer_index < len(buffers):
        errors.append(f"{error_prefix}_BUFFER_INVALID")
        return None
    data = buffers[buffer_index]
    if data is None:
        errors.append(f"{error_prefix}_BUFFER_INVALID")
        return None

    format_char, component_size = _COMPONENT_FORMATS[component_type]
    component_count = _TYPE_COMPONENT_COUNTS[type_name]
    element_size = component_size * component_count
    stride = view.get("byteStride", element_size)
    accessor_offset = accessor.get("byteOffset", 0)
    view_offset = view.get("byteOffset", 0)
    view_length = view.get("byteLength", 0)
    if (
        not isinstance(stride, int)
        or stride < element_size
        or stride % component_size != 0
        or not isinstance(accessor_offset, int)
        or accessor_offset < 0
        or accessor_offset % component_size != 0
        or not isinstance(view_offset, int)
        or not isinstance(view_length, int)
    ):
        errors.append(f"{error_prefix}_ACCESSOR_LAYOUT_INVALID")
        return None
    required_end = accessor_offset + ((count - 1) * stride) + element_size
    absolute_start = view_offset + accessor_offset
    if required_end > view_length or absolute_start + required_end - accessor_offset > len(data):
        errors.append(f"{error_prefix}_ACCESSOR_RANGE_INVALID")
        return None

    unpack_format = "<" + (format_char * component_count)
    values: list[tuple[int | float, ...]] = []
    try:
        for item_index in range(count):
            start = absolute_start + item_index * stride
            values.append(struct.unpack_from(unpack_format, data, start))
    except struct.error:
        errors.append(f"{error_prefix}_ACCESSOR_RANGE_INVALID")
        return None
    return values


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
