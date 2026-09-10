"""Blender-only consumer of inspected native CAD faces; never qualifies an asset.

Run through scripts/inspect_native_cad.py. The extraction contains world-space
vertices, so hierarchy nodes deliberately have identity transforms.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _snapshot(bpy):
    result = {}
    for obj in bpy.context.scene.objects:
        identity = obj.get("cad_node_id")
        if not identity:
            continue
        record = {"parent_id": obj.parent.get("cad_node_id") if obj.parent else None}
        if obj.type == "MESH":
            obj.data.calc_loop_triangles()
            used = {index for polygon in obj.data.polygons for index in polygon.vertices}
            record.update(
                vertices=[tuple(obj.matrix_world @ obj.data.vertices[i].co) for i in used],
                triangles=len(obj.data.loop_triangles),
                area=sum(triangle.area for triangle in obj.data.loop_triangles),
            )
        result[identity] = record
    return result


def _verify(source, exported):
    from mathutils.kdtree import KDTree

    if source.keys() != exported.keys():
        raise ValueError("CAD_EXPORT_NODE_IDENTITIES_CHANGED")
    maximum_error = 0.0
    mesh_count = 0
    triangles = 0
    for identity, before in source.items():
        after = exported[identity]
        if before["parent_id"] != after["parent_id"]:
            raise ValueError("CAD_EXPORT_HIERARCHY_CHANGED")
        if "vertices" not in before:
            continue
        mesh_count += 1
        triangles += before["triangles"]
        if before["triangles"] != after["triangles"]:
            raise ValueError("CAD_EXPORT_TRIANGLES_CHANGED")
        if not math.isclose(before["area"], after["area"], rel_tol=1e-5, abs_tol=1e-9):
            raise ValueError("CAD_EXPORT_SURFACE_AREA_CHANGED")
        # glTF may duplicate vertices at normal seams. Compare both directions
        # spatially rather than requiring storage-level vertex-count equality.
        for left, right in ((before, after), (after, before)):
            tree = KDTree(len(right["vertices"]))
            for index, point in enumerate(right["vertices"]):
                tree.insert(point, index)
            tree.balance()
            for point in left["vertices"]:
                maximum_error = max(maximum_error, tree.find(point)[2])
        if maximum_error > 1e-5:
            raise ValueError("CAD_EXPORT_VERTEX_POSITION_CHANGED")
    return {
        "passed": True,
        "mesh_count": mesh_count,
        "triangles": triangles,
        "maximum_vertex_error_m": maximum_error,
        "tolerance_m": 1e-5,
        "hierarchy_preserved": True,
        "method": (
            "GLB reimport, identities, hierarchy, triangle count, area, bidirectional vertices"
        ),
    }


def _material_for_component(bpy, component_name, materials):
    """Return a restrained inspection material keyed by source part semantics."""

    name = str(component_name or "").upper()
    if any(token in name for token in ("CABLE", "RG174", "XLPE", "SHRUNK")):
        key, color, metallic = "cable", (0.035, 0.045, 0.055, 1.0), 0.0
    elif "SMA" in name:
        key, color, metallic = "connector", (0.42, 0.46, 0.5, 1.0), 0.85
    elif any(token in name for token in ("THREAD", "SF2", "SF3", "SP8-0463", "SR7")):
        key, color, metallic = "mount", (0.18, 0.21, 0.24, 1.0), 0.65
    else:
        key, color, metallic = "housing", (0.32, 0.37, 0.43, 1.0), 0.15
    material = materials.get(key)
    if material is None:
        material = bpy.data.materials.new(f"CAD inspection · {key}")
        material.diffuse_color = color
        material.metallic = metallic
        material.roughness = 0.34 if metallic else 0.48
        materials[key] = material
    return material


def _is_cable_component(component_name):
    name = str(component_name or "").upper()
    return any(token in name for token in ("CABLE", "RG174", "XLPE", "SHRUNK"))


def _bounds_for_objects(objects):
    from mathutils import Vector

    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise ValueError("CAD_RENDER_OBJECTS_EMPTY")
    lower = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    upper = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return lower, upper


def _render(bpy, output, objects):
    from mathutils import Vector

    lower, upper = _bounds_for_objects(objects)
    center = (lower + upper) / 2
    radius = max((upper - lower).length / 2, 1e-8)
    camera_data = bpy.data.cameras.new("InspectionCamera")
    camera = bpy.data.objects.new("InspectionCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = radius * 2.4
    camera_data.clip_end = radius * 20 + 100
    camera_data.clip_start = min(0.001, radius / 100)
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("InspectionWorld")
    scene.world.color = (0.07, 0.07, 0.07)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    # Imported mesh origins are intentionally kept at the assembly origin so
    # that the source transform is not rewritten.  Use world-space bounds for
    # framing and subject selection rather than object origins/dimensions.
    object_bounds = {id(obj): _bounds_for_objects([obj]) for obj in objects}

    def bound_volume(obj):
        obj_lower, obj_upper = object_bounds[id(obj)]
        extent = obj_upper - obj_lower
        return max(extent.x * extent.y * extent.z, 0.0)

    subject = max(objects, key=bound_volume)
    subject_lower, subject_upper = object_bounds[id(subject)]
    subject_center = (subject_lower + subject_upper) / 2
    subject_radius = max((subject_upper - subject_lower).length / 2, 1e-8)
    views = (
        ("preview", center, radius, (1, -1, 0.8), objects),
        ("preview_front", center, radius, (0, -1, 0.05), objects),
        ("preview_side", center, radius, (1, 0, 0.05), objects),
        ("preview_top", center, radius, (0.05, 0.05, 1), objects),
    )
    # A close-up is deliberately a separate evidence view.  It keeps the
    # housing and nearby mount hardware in frame while hiding the metres-long
    # cables that would otherwise make the actual equipment unreadable.
    closeup_objects = []
    for obj in objects:
        # Keep the equipment and its connector/mounting hardware legible.  A
        # cable is a valid part of the assembly but its long span must not
        # dictate the close-up evidence frame.
        if _is_cable_component(obj.get("cad_component_name")):
            continue
        obj_lower, obj_upper = object_bounds[id(obj)]
        obj_center = (obj_lower + obj_upper) / 2
        distance = (obj_center - subject_center).length
        if distance <= max(subject_radius * 3.0, 0.18):
            closeup_objects.append(obj)
    if not closeup_objects:
        closeup_objects = [subject]
    closeup_lower, closeup_upper = _bounds_for_objects(closeup_objects)
    closeup_center = (closeup_lower + closeup_upper) / 2
    closeup_radius = max((closeup_upper - closeup_lower).length / 2, 1e-8)
    views += (("preview_closeup", closeup_center, closeup_radius, (1, -1, 0.8), closeup_objects),)
    for view_name, view_center, view_radius, direction, visible_objects in views:
        hidden = []
        if view_name == "preview_closeup":
            visible_ids = {id(obj) for obj in visible_objects}
            for obj in objects:
                if id(obj) not in visible_ids and not obj.hide_render:
                    obj.hide_render = True
                    hidden.append(obj)
        camera.location = view_center + Vector(direction).normalized() * view_radius * 4
        camera_data.ortho_scale = view_radius * 2.4
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        if view_name == "preview_closeup":
            camera.rotation_euler = (
                view_center - camera.location
            ).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(output / f"{view_name}.png")
        bpy.ops.render.render(write_still=True)
        for obj in hidden:
            obj.hide_render = False
    return [view_name for view_name, *_ in views]


def main():
    import bpy

    extraction_path, output_path = sys.argv[sys.argv.index("--") + 1 :]
    document = json.loads(Path(extraction_path).read_text())
    output = Path(output_path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = {}
    materials = {}
    for node in document["nodes"]:
        mesh = None
        if node["kind"] == "mesh":
            mesh = bpy.data.meshes.new(node["node_id"])
            mesh.from_pydata(node["vertices_m"], [], node["faces"])
            if mesh.validate(verbose=False):
                raise ValueError("CAD_SOURCE_MESH_REQUIRED_REPAIR")
            mesh.update()
        readable_name = str(node.get("name") or "STEP component")
        occurrence = str(node.get("occurrence_name") or node["node_id"].rsplit("/", 1)[-1])
        readable_name = f"{readable_name} [{occurrence}]"
        obj = bpy.data.objects.new(readable_name, mesh)
        obj["cad_node_id"] = node["node_id"]
        obj["cad_entity_handle"] = node["entity_handle"]
        obj["cad_layer"] = node["layer"]
        obj["cad_source_sha256"] = document["source"]["sha256"]
        obj["cad_component_name"] = node.get("name") or "STEP component"
        obj["cad_definition_entry"] = node.get("definition_entry") or node["entity_handle"]
        if mesh is not None:
            mesh.materials.append(_material_for_component(bpy, node.get("name"), materials))
        bpy.context.scene.collection.objects.link(obj)
        objects[node["node_id"]] = obj
    for node in document["nodes"]:
        if node["parent_id"]:
            objects[node["node_id"]].parent = objects[node["parent_id"]]
    bpy.context.view_layer.update()
    before = _snapshot(bpy)
    bpy.ops.export_scene.gltf(
        filepath=str(output / "source_mesh.glb"),
        export_format="GLB",
        export_extras=True,
        export_yup=True,
        export_apply=False,
    )
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(output / "source_mesh.glb"))
    bpy.context.view_layer.update()
    validation = _verify(before, _snapshot(bpy))
    report = {
        "blender_version": bpy.app.version_string,
        "blender_executed": True,
        "geometry_roundtrip": validation,
        "generation_eligible": False,
        "professional_qualified": False,
        "limitations": [
            "Native mesh inspection only; engineering accuracy and rights are not certified.",
            "CAD materials are not reconstructed; previews use a neutral inspection material.",
            "Triangle counts and vertex distances do not prove manifoldness or fitness for use.",
        ],
    }
    preview_views = _render(
        bpy,
        output,
        [obj for obj in bpy.context.scene.objects if obj.type == "MESH"],
    )
    report["preview_views"] = [
        {
            "view": view_name.removeprefix("preview_") if view_name != "preview" else "perspective",
            "file": f"{view_name}.png",
        }
        for view_name in preview_views
    ]
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source_mesh.blend"))
    (output / "blender_validation.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
