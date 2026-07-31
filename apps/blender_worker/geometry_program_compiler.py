"""Deterministic compiler for validated declarative geometry programs.

The module runs inside Blender's isolated worker snapshot. It accepts data
already validated by ``core.contracts.geometry_program`` and never evaluates
Python, expressions, file paths, URLs or arbitrary operators supplied by a
model.
"""

from __future__ import annotations

import math


def compile_geometry_programs(bpy, programs: list[dict]) -> list[dict]:
    return [_compile_program(bpy, program) for program in programs]


def _compile_program(bpy, program: dict) -> dict:
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
            and (
                node_specs[node_id]["kind"] != "instance"
                or node_specs[node_id]["source_node_id"] in objects
            )
        )
        if not ready:
            raise RuntimeError(f"GEOMETRY_PROGRAM_UNRESOLVED_GRAPH:{program_id}")
        for node_id in ready:
            spec = node_specs[node_id]
            obj = _compile_node(bpy, program_id, spec, objects)
            parent_id = spec.get("parent_id")
            obj.parent = objects[parent_id] if parent_id else root
            _apply_local_transform(obj, spec.get("transform") or {})
            material_id = spec.get("material_id")
            if material_id:
                _assign_material(obj, materials[material_id])
            obj["geometry_program_id"] = program_id
            obj["geometry_program_node_id"] = node_id
            if spec.get("semantic_role"):
                node_role = str(spec["semantic_role"])
                obj["role"] = node_role
                obj["component_role"] = node_role
                obj["semantic_root"] = obj.name
                obj["semantic_id"] = f"{program_id}:{node_id}"
            objects[node_id] = obj
            pending.remove(node_id)

    return {
        "program_id": program_id,
        "semantic_role": semantic_role,
        "requested_quantity": int(program["requested_quantity"]),
        "object_name": root_name,
        "generated_object_names": [
            root_name,
            *[objects[node_id].name for node_id in sorted(objects)],
        ],
        "authorship": str(program["authorship"]),
        "generator_provider": str(program["generator_provider"]),
        "generator_model": str(program["generator_model"]),
        "structured_output_mode": str(program["structured_output_mode"]),
        "source_prompt_sha256": str(program["source_prompt_sha256"]),
        "limitations": list(program.get("limitations", [])),
        "deterministic_adjustments": list(program.get("deterministic_adjustments", [])),
    }


def _compile_node(bpy, program_id: str, spec: dict, objects: dict[str, object]):
    name = f"{program_id}_{spec['node_id']}"
    kind = spec["kind"]
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
    root["geometry_generation_strategy"] = "internal_project_generated"
    root["geometry_source"] = "internal_project_generated"
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
