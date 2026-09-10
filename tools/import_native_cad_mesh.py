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


def _render(bpy, output, objects):
    from mathutils import Vector

    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    lower = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    upper = Vector(tuple(max(point[i] for point in points) for i in range(3)))
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
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.62, 0.67, 0.72)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("InspectionWorld")
    scene.world.color = (0.07, 0.07, 0.07)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    for name, direction in (("preview", (1, -1, 0.8)), ("preview_front", (0, -1, 0.05))):
        camera.location = center + Vector(direction).normalized() * radius * 4
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(output / f"{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    import bpy

    extraction_path, output_path = sys.argv[sys.argv.index("--") + 1 :]
    document = json.loads(Path(extraction_path).read_text())
    output = Path(output_path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = {}
    for node in document["nodes"]:
        mesh = None
        if node["kind"] == "mesh":
            mesh = bpy.data.meshes.new(node["node_id"])
            mesh.from_pydata(node["vertices_m"], [], node["faces"])
            if mesh.validate(verbose=False):
                raise ValueError("CAD_SOURCE_MESH_REQUIRED_REPAIR")
            mesh.update()
        obj = bpy.data.objects.new(node["node_id"], mesh)
        obj["cad_node_id"] = node["node_id"]
        obj["cad_entity_handle"] = node["entity_handle"]
        obj["cad_layer"] = node["layer"]
        obj["cad_source_sha256"] = document["source"]["sha256"]
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
    _render(bpy, output, [obj for obj in bpy.context.scene.objects if obj.type == "MESH"])
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source_mesh.blend"))
    (output / "blender_validation.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
