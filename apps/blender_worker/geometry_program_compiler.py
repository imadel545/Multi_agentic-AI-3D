"""Deterministic compiler for validated declarative geometry programs.

The module runs inside Blender's isolated worker snapshot. It accepts data
already validated by ``core.contracts.geometry_program`` and never evaluates
Python, expressions, file paths, URLs or arbitrary operators supplied by a
model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import exact_asset

_SCHEMA_NODE_KINDS = {
    "1.0.0": {"primitive", "curve", "instance"},
    "2.0.0": {
        "exact_asset",
        "primitive",
        "curve",
        "instance",
        "profile",
        "extrude",
        "revolve",
        "sweep",
        "array",
        "boolean",
        "modifier",
        "terrain",
    },
}
_BOOLEAN_OPERATIONS = {"union", "difference", "intersection"}
_MODIFIER_OPERATIONS = {"bevel", "solidify", "mirror"}


def compile_geometry_programs(bpy, programs: list[dict]) -> list[dict]:
    if not isinstance(programs, list) or len(programs) > 32:
        raise RuntimeError("GEOMETRY_PROGRAM_COLLECTION_INVALID")
    return [_compile_program(bpy, program) for program in programs]


def _compile_program(bpy, program: dict) -> dict:
    _validate_closed_program(program)
    exact_evidence = exact_asset.validate_exact_program(program, Path.cwd())
    program_id = str(program["program_id"])
    semantic_role = str(program["semantic_role"])
    root_name = f"program_{program_id}"
    root = bpy.data.objects.new(root_name, None)
    bpy.context.collection.objects.link(root)
    _set_program_metadata(root, program)

    materials = {
        material["material_id"]: _compile_material(bpy, program_id, material)
        for material in program.get("materials", [])
    }
    node_specs = {node["node_id"]: node for node in program["nodes"]}
    semantic_groups_by_node: dict[str, list[str]] = {}
    for group in program.get("semantic_groups", []):
        for node_id in group["node_ids"]:
            semantic_groups_by_node.setdefault(node_id, []).append(group["group_id"])
    construction_node_ids = set(program.get("construction_node_ids", []))
    objects: dict[str, object] = {}
    pending = set(node_specs)
    while pending:
        ready = sorted(
            node_id
            for node_id in pending
            if (
                not node_specs[node_id].get("parent_id")
                or node_specs[node_id]["parent_id"] in objects
            )
            and _node_dependencies(node_specs[node_id]).issubset(objects)
        )
        if not ready:
            raise RuntimeError(f"GEOMETRY_PROGRAM_UNRESOLVED_GRAPH:{program_id}")
        for node_id in ready:
            spec = node_specs[node_id]
            obj = _compile_node(bpy, program_id, spec, node_specs, objects)
            parent_id = spec.get("parent_id")
            obj.parent = objects[parent_id] if parent_id else root
            _apply_local_transform(obj, spec.get("transform") or {})
            material_id = spec.get("material_id")
            if material_id:
                _assign_material(obj, materials[material_id])
            if spec["kind"] == "exact_asset":
                for descendant in obj.children_recursive:
                    descendant["geometry_program_id"] = program_id
                    descendant["exact_asset_id"] = spec["asset_id"]
                    descendant["exact_asset_sha256"] = spec["asset_sha256"]
            obj["geometry_program_id"] = program_id
            obj["geometry_program_node_id"] = node_id
            groups = sorted(semantic_groups_by_node.get(node_id, []))
            if groups:
                obj["geometry_program_semantic_groups"] = json.dumps(groups, separators=(",", ":"))
            if node_id in construction_node_ids:
                obj["geometry_program_construction_only"] = True
                obj.hide_render = True
            if spec.get("semantic_role"):
                node_role = str(spec["semantic_role"])
                obj["role"] = node_role
                obj["component_role"] = node_role
                obj["semantic_root"] = obj.name
                obj["semantic_id"] = f"{program_id}:{node_id}"
            objects[node_id] = obj
            pending.remove(node_id)

    anchor_names = _compile_anchors_and_connectors(bpy, program_id, program, objects)

    return {
        "exact_asset_evidence": exact_evidence,
        "program_id": program_id,
        "semantic_role": semantic_role,
        "requested_quantity": int(program["requested_quantity"]),
        "object_name": root_name,
        "generated_object_names": [
            root_name,
            *[objects[node_id].name for node_id in sorted(objects)],
            *anchor_names,
        ],
        "schema_version": str(program["schema_version"]),
        "authorship": str(program["authorship"]),
        "generator_provider": str(program["generator_provider"]),
        "generator_model": str(program["generator_model"]),
        "structured_output_mode": str(program["structured_output_mode"]),
        "source_prompt_sha256": str(program["source_prompt_sha256"]),
        "limitations": list(program.get("limitations", [])),
        "deterministic_adjustments": list(program.get("deterministic_adjustments", [])),
    }


def _compile_node(
    bpy,
    program_id: str,
    spec: dict,
    node_specs: dict[str, dict],
    objects: dict[str, object],
):
    name = f"{program_id}_{spec['node_id']}"
    kind = spec["kind"]
    if kind == "exact_asset":
        return exact_asset.import_exact_node(bpy, name, spec)
    if kind == "primitive":
        return _compile_primitive(bpy, name, spec)
    if kind == "curve":
        return _compile_curve(bpy, name, spec)
    if kind == "instance":
        source = objects[spec["source_node_id"]]
        instance = source.copy()
        if getattr(source, "data", None) is not None:
            instance.data = source.data
        instance.name = name
        bpy.context.collection.objects.link(instance)
        return instance
    if kind == "profile":
        return _compile_profile_definition(bpy, name, spec)
    if kind == "extrude":
        return _compile_extrude(bpy, name, spec, node_specs[spec["profile_node_id"]])
    if kind == "revolve":
        return _compile_revolve(bpy, name, spec, node_specs[spec["profile_node_id"]])
    if kind == "sweep":
        return _compile_sweep(bpy, name, spec, node_specs[spec["profile_node_id"]])
    if kind == "array":
        return _compile_array(bpy, name, spec, objects[spec["source_node_id"]])
    if kind == "boolean":
        return _compile_boolean(
            bpy,
            name,
            spec,
            objects[spec["left_node_id"]],
            objects[spec["right_node_id"]],
        )
    if kind == "modifier":
        return _compile_modifier(bpy, name, spec, objects[spec["source_node_id"]])
    if kind == "terrain":
        return _compile_terrain(bpy, name, spec)
    raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_NODE_KIND:{kind}")


def _compile_primitive(bpy, name: str, spec: dict):
    primitive = spec["primitive"]
    if primitive == "box":
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.object
        obj.dimensions = _vector_tuple(spec["size_m"])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    elif primitive == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=int(spec["vertices"]),
            radius=float(spec["radius_m"]),
            depth=float(spec["height_m"]),
        )
        obj = bpy.context.object
    elif primitive == "cone":
        bpy.ops.mesh.primitive_cone_add(
            vertices=int(spec["vertices"]),
            radius1=float(spec["radius_m"]),
            radius2=float(spec["top_radius_m"]),
            depth=float(spec["height_m"]),
        )
        obj = bpy.context.object
    elif primitive == "uv_sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=int(spec["vertices"]),
            ring_count=max(8, int(spec["vertices"]) // 2),
            radius=float(spec["radius_m"]),
        )
        obj = bpy.context.object
    else:
        raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_PRIMITIVE:{primitive}")
    obj.name = name
    bevel = float(spec.get("bevel_m") or 0.0)
    if bevel > 0:
        modifier = obj.modifiers.new(name=f"{name}_bounded_bevel", type="BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def _compile_curve(bpy, name: str, spec: dict):
    curve_data = bpy.data.curves.new(name=name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.bevel_depth = float(spec["bevel_depth_m"])
    curve_data.bevel_resolution = 2
    spline = curve_data.splines.new("POLY")
    points = spec["points_m"]
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points, strict=True):
        point.co = (*_vector_tuple(coordinate), 1.0)
    spline.use_cyclic_u = bool(spec.get("cyclic", False))
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    return obj


def _compile_profile_definition(bpy, name: str, spec: dict):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj["geometry_program_profile"] = True
    obj["geometry_program_profile_closed"] = bool(spec["closed"])
    obj["geometry_program_profile_points"] = json.dumps(
        spec["points_m"], sort_keys=True, separators=(",", ":")
    )
    obj.hide_render = True
    return obj


def _compile_extrude(bpy, name: str, spec: dict, profile: dict):
    points = [(float(point["x"]), float(point["y"])) for point in profile["points_m"]]
    count = len(points)
    half_depth = float(spec["depth_m"]) / 2.0
    vertices = [
        *((x, y, -half_depth) for x, y in points),
        *((x, y, half_depth) for x, y in points),
    ]
    faces = [
        tuple(reversed(range(count))),
        tuple(range(count, count * 2)),
        *(
            (index, (index + 1) % count, count + (index + 1) % count, count + index)
            for index in range(count)
        ),
    ]
    return _compile_mesh(bpy, name, vertices, faces)


def _compile_revolve(bpy, name: str, spec: dict, profile: dict):
    profile_points = [(float(point["x"]), float(point["y"])) for point in profile["points_m"]]
    segments = int(spec["segments"])
    angle_deg = float(spec["angle_deg"])
    full = math.isclose(angle_deg, 360.0, rel_tol=0.0, abs_tol=1e-9)
    ring_count = segments if full else segments + 1
    vertices = []
    for ring_index in range(ring_count):
        angle = math.radians(angle_deg * ring_index / segments)
        vertices.extend(
            (radius * math.cos(angle), radius * math.sin(angle), z) for radius, z in profile_points
        )
    profile_count = len(profile_points)
    profile_edge_count = profile_count if profile.get("closed", True) else profile_count - 1
    angular_edge_count = ring_count if full else ring_count - 1
    faces = []
    for ring_index in range(angular_edge_count):
        next_ring = (ring_index + 1) % ring_count
        for profile_index in range(profile_edge_count):
            next_profile = (profile_index + 1) % profile_count
            faces.append(
                (
                    ring_index * profile_count + profile_index,
                    next_ring * profile_count + profile_index,
                    next_ring * profile_count + next_profile,
                    ring_index * profile_count + next_profile,
                )
            )
    if not full and profile.get("closed", True):
        faces.extend(
            [
                tuple(reversed(range(profile_count))),
                tuple((ring_count - 1) * profile_count + index for index in range(profile_count)),
            ]
        )
    return _compile_mesh(bpy, name, vertices, faces)


def _compile_sweep(bpy, name: str, spec: dict, profile: dict):
    from mathutils import Vector

    profile_points = [(float(point["x"]), float(point["y"])) for point in profile["points_m"]]
    path = [Vector(_vector_tuple(point)) for point in spec["path_points_m"]]
    cyclic = bool(spec.get("cyclic", False))
    vertices = []
    for index, center in enumerate(path):
        previous = path[index - 1] if index > 0 else (path[-1] if cyclic else path[index])
        following = (
            path[(index + 1) % len(path)] if index + 1 < len(path) or cyclic else path[index]
        )
        tangent = (following - previous).normalized()
        reference = Vector((0.0, 0.0, 1.0))
        if abs(tangent.dot(reference)) > 0.95:
            reference = Vector((1.0, 0.0, 0.0))
        normal = tangent.cross(reference).normalized()
        binormal = tangent.cross(normal).normalized()
        vertices.extend(tuple(center + normal * x + binormal * y) for x, y in profile_points)
    profile_count = len(profile_points)
    ring_edge_count = len(path) if cyclic else len(path) - 1
    faces = []
    for ring_index in range(ring_edge_count):
        next_ring = (ring_index + 1) % len(path)
        for profile_index in range(profile_count):
            next_profile = (profile_index + 1) % profile_count
            faces.append(
                (
                    ring_index * profile_count + profile_index,
                    next_ring * profile_count + profile_index,
                    next_ring * profile_count + next_profile,
                    ring_index * profile_count + next_profile,
                )
            )
    if not cyclic:
        faces.extend(
            [
                tuple(reversed(range(profile_count))),
                tuple((len(path) - 1) * profile_count + index for index in range(profile_count)),
            ]
        )
    return _compile_mesh(bpy, name, vertices, faces)


def _compile_array(bpy, name: str, spec: dict, source):
    obj = _copy_mesh_object(bpy, name, source)
    modifier = obj.modifiers.new(name=f"{name}_array", type="ARRAY")
    modifier.count = int(spec["count"])
    modifier.use_relative_offset = False
    modifier.use_constant_offset = True
    modifier.constant_offset_displace = _vector_tuple(spec["offset_m"])
    _apply_modifier(bpy, obj, modifier.name, "ARRAY")
    return obj


def _compile_boolean(bpy, name: str, spec: dict, left, right):
    operation = str(spec["operation"])
    if operation not in _BOOLEAN_OPERATIONS:
        raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_BOOLEAN:{operation}")
    # Boolean operands are spatial inputs, unlike modifier/array source
    # definitions. Bake each evaluated operand in the common program/world
    # frame before applying the exact Boolean. Resetting the copies to the
    # identity without baking their matrices silently moves translated or
    # parented operands back to the origin.
    obj = _copy_evaluated_mesh_in_world_space(bpy, name, left)
    operand = _copy_evaluated_mesh_in_world_space(bpy, f"{name}_operand", right)
    modifier = obj.modifiers.new(name=f"{name}_boolean", type="BOOLEAN")
    modifier.operation = operation.upper()
    modifier.solver = "EXACT"
    modifier.object = operand
    try:
        _apply_modifier(bpy, obj, modifier.name, "BOOLEAN")
    finally:
        operand_mesh = operand.data
        bpy.data.objects.remove(operand, do_unlink=True)
        if operand_mesh.users == 0:
            bpy.data.meshes.remove(operand_mesh)
    return obj


def _compile_modifier(bpy, name: str, spec: dict, source):
    operation = str(spec["modifier"])
    if operation not in _MODIFIER_OPERATIONS:
        raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_MODIFIER:{operation}")
    obj = _copy_mesh_object(bpy, name, source)
    if operation == "bevel":
        modifier = obj.modifiers.new(name=f"{name}_bevel", type="BEVEL")
        modifier.width = float(spec["width_m"])
        modifier.segments = int(spec["segments"])
    elif operation == "solidify":
        modifier = obj.modifiers.new(name=f"{name}_solidify", type="SOLIDIFY")
        modifier.thickness = float(spec["thickness_m"])
    else:
        modifier = obj.modifiers.new(name=f"{name}_mirror", type="MIRROR")
        axes = set(spec["mirror_axes"])
        modifier.use_axis = tuple(axis in axes for axis in ("x", "y", "z"))
        modifier.use_mirror_merge = True
        modifier.merge_threshold = float(spec["merge_distance_m"])
    _apply_modifier(bpy, obj, modifier.name, operation.upper())
    return obj


def _compile_terrain(bpy, name: str, spec: dict):
    columns = int(spec["columns"])
    rows = int(spec["rows"])
    width = float(spec["width_m"])
    depth = float(spec["depth_m"])
    heights = [float(value) for value in spec["heights_m"]]
    vertices = [
        (
            -width / 2.0 + width * column / (columns - 1),
            -depth / 2.0 + depth * row / (rows - 1),
            heights[row * columns + column],
        )
        for row in range(rows)
        for column in range(columns)
    ]
    faces = [
        (
            row * columns + column,
            row * columns + column + 1,
            (row + 1) * columns + column + 1,
            (row + 1) * columns + column,
        )
        for row in range(rows - 1)
        for column in range(columns - 1)
    ]
    return _compile_mesh(bpy, name, vertices, faces)


def _compile_mesh(bpy, name: str, vertices, faces):
    mesh = bpy.data.meshes.new(name=f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    if not mesh.vertices or not mesh.polygons:
        raise RuntimeError(f"GEOMETRY_PROGRAM_EMPTY_MESH:{name}")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _copy_mesh_object(bpy, name: str, source):
    if getattr(source, "type", None) != "MESH" or getattr(source, "data", None) is None:
        raise RuntimeError(f"GEOMETRY_PROGRAM_MESH_SOURCE_REQUIRED:{source.name}")
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = name
    obj.parent = None
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(obj)
    return obj


def _copy_evaluated_mesh_in_world_space(bpy, name: str, source):
    """Copy a mesh operand with its evaluated world transform baked in.

    Exact booleans need both operands in one coordinate system. This helper is
    deliberately boolean-specific: instance, array and modifier nodes keep
    their existing source-definition semantics.
    """

    if getattr(source, "type", None) != "MESH" or getattr(source, "data", None) is None:
        raise RuntimeError(f"GEOMETRY_PROGRAM_MESH_SOURCE_REQUIRED:{source.name}")
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated,
        preserve_all_data_layers=True,
        depsgraph=depsgraph,
    )
    if not mesh.vertices or not mesh.polygons:
        bpy.data.meshes.remove(mesh)
        raise RuntimeError(f"GEOMETRY_PROGRAM_EMPTY_MESH:{name}")
    mesh.name = f"{name}_mesh"
    mesh.transform(source.matrix_world)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _apply_modifier(bpy, obj, modifier_name: str, operation: str) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier=modifier_name)
    except Exception as exc:
        raise RuntimeError(f"GEOMETRY_PROGRAM_MODIFIER_FAILED:{operation}") from exc
    finally:
        obj.select_set(False)


def _compile_anchors_and_connectors(
    bpy,
    program_id: str,
    program: dict,
    objects: dict[str, object],
) -> list[str]:
    connectors_by_anchor: dict[str, list[dict]] = {}
    for connector in program.get("connectors", []):
        connectors_by_anchor.setdefault(connector["anchor_id"], []).append(connector)
    names = []
    for anchor in program.get("anchors", []):
        name = f"{program_id}_anchor_{anchor['anchor_id']}"
        obj = bpy.data.objects.new(name, None)
        bpy.context.collection.objects.link(obj)
        obj.parent = objects[anchor["node_id"]]
        obj.location = _vector_tuple(anchor["position_m"])
        obj["geometry_program_anchor"] = True
        obj["geometry_program_id"] = program_id
        obj["geometry_program_anchor_id"] = str(anchor["anchor_id"])
        obj["geometry_program_anchor_node_id"] = str(anchor["node_id"])
        obj["geometry_program_anchor_normal"] = list(_vector_tuple(anchor["normal"]))
        obj["geometry_program_anchor_up"] = list(_vector_tuple(anchor["up"]))
        connector_payload = sorted(
            connectors_by_anchor.get(anchor["anchor_id"], []),
            key=lambda item: item["connector_id"],
        )
        if connector_payload:
            obj["geometry_program_connectors"] = json.dumps(
                connector_payload,
                sort_keys=True,
                separators=(",", ":"),
            )
        names.append(name)
    return names


def _node_dependencies(spec: dict) -> set[str]:
    kind = spec["kind"]
    if kind in {"instance", "array", "modifier"}:
        return {str(spec["source_node_id"])}
    if kind in {"extrude", "revolve", "sweep"}:
        return {str(spec["profile_node_id"])}
    if kind == "boolean":
        return {str(spec["left_node_id"]), str(spec["right_node_id"])}
    return set()


def _validate_closed_program(program: object) -> None:
    if not isinstance(program, dict):
        raise RuntimeError("GEOMETRY_PROGRAM_INVALID")
    schema_version = program.get("schema_version")
    allowed_kinds = _SCHEMA_NODE_KINDS.get(schema_version)
    if allowed_kinds is None:
        raise RuntimeError(f"GEOMETRY_PROGRAM_SCHEMA_UNSUPPORTED:{schema_version}")
    nodes = program.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 512:
        raise RuntimeError("GEOMETRY_PROGRAM_NODES_INVALID")
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise RuntimeError("GEOMETRY_PROGRAM_NODE_INVALID")
        node_id = node.get("node_id")
        kind = node.get("kind")
        if not isinstance(node_id, str) or not node_id or node_id in node_ids:
            raise RuntimeError("GEOMETRY_PROGRAM_NODE_ID_INVALID")
        if kind not in allowed_kinds:
            raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_NODE_KIND:{kind}")
        if kind == "boolean" and node.get("operation") not in _BOOLEAN_OPERATIONS:
            raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_BOOLEAN:{node.get('operation')}")
        if kind == "modifier" and node.get("modifier") not in _MODIFIER_OPERATIONS:
            raise RuntimeError(f"GEOMETRY_PROGRAM_UNKNOWN_MODIFIER:{node.get('modifier')}")
        node_ids.add(node_id)
    if schema_version == "1.0.0" and any(
        program.get(field)
        for field in ("anchors", "connectors", "semantic_groups", "construction_node_ids")
    ):
        raise RuntimeError("GEOMETRY_PROGRAM_V2_FEATURE_IN_V1")
    for node in nodes:
        references = _node_dependencies(node)
        parent_id = node.get("parent_id")
        if parent_id:
            references.add(str(parent_id))
        if not references.issubset(node_ids) or node["node_id"] in references:
            raise RuntimeError(f"GEOMETRY_PROGRAM_REFERENCE_INVALID:{node['node_id']}")
    construction_node_ids = program.get("construction_node_ids", [])
    if (
        not isinstance(construction_node_ids, list)
        or len(construction_node_ids) != len(set(construction_node_ids))
        or not set(construction_node_ids).issubset(node_ids)
    ):
        raise RuntimeError("GEOMETRY_PROGRAM_CONSTRUCTION_NODES_INVALID")
    profile_node_ids = {node["node_id"] for node in nodes if node["kind"] == "profile"}
    if not profile_node_ids.issubset(construction_node_ids):
        raise RuntimeError("GEOMETRY_PROGRAM_PROFILE_NOT_CONSTRUCTION_ONLY")
    anchor_ids = {
        anchor.get("anchor_id") for anchor in program.get("anchors", []) if isinstance(anchor, dict)
    }
    if len(anchor_ids) != len(program.get("anchors", [])):
        raise RuntimeError("GEOMETRY_PROGRAM_ANCHOR_ID_INVALID")
    if any(
        not isinstance(anchor, dict) or anchor.get("node_id") not in node_ids
        for anchor in program.get("anchors", [])
    ):
        raise RuntimeError("GEOMETRY_PROGRAM_ANCHOR_REFERENCE_INVALID")
    if any(
        not isinstance(connector, dict) or connector.get("anchor_id") not in anchor_ids
        for connector in program.get("connectors", [])
    ):
        raise RuntimeError("GEOMETRY_PROGRAM_CONNECTOR_REFERENCE_INVALID")
    connector_ids = [
        connector.get("connector_id")
        for connector in program.get("connectors", [])
        if isinstance(connector, dict)
    ]
    if len(connector_ids) != len(set(connector_ids)):
        raise RuntimeError("GEOMETRY_PROGRAM_CONNECTOR_ID_INVALID")
    group_ids: set[str] = set()
    for group in program.get("semantic_groups", []):
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("group_id"), str)
            or group["group_id"] in group_ids
            or not isinstance(group.get("node_ids"), list)
            or not set(group["node_ids"]).issubset(node_ids)
        ):
            raise RuntimeError("GEOMETRY_PROGRAM_SEMANTIC_GROUP_INVALID")
        group_ids.add(group["group_id"])


def _compile_material(bpy, program_id: str, spec: dict):
    name = f"program_{program_id}_{spec['material_id']}"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    rgba = spec["base_color_rgba"]
    color = (rgba["r"], rgba["g"], rgba["b"], rgba["a"])
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Metallic"].default_value = float(spec["metallic"])
        principled.inputs["Roughness"].default_value = float(spec["roughness"])
    return material


def _assign_material(obj, material) -> None:
    data = getattr(obj, "data", None)
    if data is not None and hasattr(data, "materials"):
        data.materials.append(material)


def _apply_local_transform(obj, transform: dict) -> None:
    obj.location = _vector_tuple(transform.get("translation_m") or {"x": 0.0, "y": 0.0, "z": 0.0})
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = tuple(
        math.radians(float(value))
        for value in _vector_tuple(transform.get("rotation_deg") or {"x": 0.0, "y": 0.0, "z": 0.0})
    )
    obj.scale = _vector_tuple(transform.get("scale") or {"x": 1.0, "y": 1.0, "z": 1.0})


def _vector_tuple(value: dict) -> tuple[float, float, float]:
    return (float(value["x"]), float(value["y"]), float(value["z"]))


def _set_program_metadata(root, program: dict) -> None:
    root["geometry_program_group"] = True
    exact = any(node.get("kind") == "exact_asset" for node in program.get("nodes", []))
    root["geometry_generation_strategy"] = (
        "imported_glb_exact" if exact else "internal_project_generated"
    )
    root["geometry_source"] = "imported_glb_exact" if exact else "internal_project_generated"
    root["geometry_program_id"] = str(program["program_id"])
    root["geometry_program_requested_quantity"] = int(program["requested_quantity"])
    root["geometry_program_schema_version"] = str(program["schema_version"])
    root["geometry_program_authorship"] = str(program["authorship"])
    root["geometry_program_generator"] = (
        f"{program['generator_provider']}:{program['generator_model']}"
    )
    root["geometry_program_structured_output_mode"] = str(program["structured_output_mode"])
    root["geometry_program_deterministic_adjustment_count"] = len(
        program.get("deterministic_adjustments", [])
    )
    root["geometry_program_anchor_count"] = len(program.get("anchors", []))
    root["geometry_program_connector_count"] = len(program.get("connectors", []))
    root["geometry_program_semantic_group_count"] = len(program.get("semantic_groups", []))
    root["geometry_program_registry"] = (
        "generic_cognitive_3d_core_v1"
        if str(program.get("schema_version")) == "2.0.0"
        else "geometry_program_v1"
    )
