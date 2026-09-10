"""Measure one exported GLB in a fresh Blender process.

This is intentionally separate from the import/export command that produced
the file.  It observes the persisted GLB after re-import, including world
space bounds, mesh counts and the component identities carried as glTF extras.

Example (normally launched by ``scripts.qualify_step_asset``)::

    blender --background --factory-startup --python scripts/inspect_exported_glb.py -- \
        /tmp/evidence/source_mesh.glb /tmp/evidence/post_blender_measurement.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _measure(bpy, glb_path: Path) -> dict:
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    bpy.context.view_layer.update()
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    records = []
    points = []
    for obj in meshes:
        world_points = [obj.matrix_world @ Vector(vertex.co) for vertex in obj.data.vertices]
        if not world_points:
            continue
        points.extend(world_points)
        lower = [min(point[index] for point in world_points) for index in range(3)]
        upper = [max(point[index] for point in world_points) for index in range(3)]
        obj.data.calc_loop_triangles()
        records.append(
            {
                "name": obj.name,
                "component_name": obj.get("cad_component_name"),
                "cad_node_id": obj.get("cad_node_id"),
                "cad_definition_entry": obj.get("cad_definition_entry"),
                "vertex_count": len(obj.data.vertices),
                "triangle_count": len(obj.data.loop_triangles),
                "bounding_box_m": {"minimum": lower, "maximum": upper},
            }
        )
    if not points:
        raise ValueError("POST_BLENDER_GLB_HAS_NO_MESH_VERTICES")
    lower = [min(point[index] for point in points) for index in range(3)]
    upper = [max(point[index] for point in points) for index in range(3)]
    if not all(math.isfinite(value) for value in (*lower, *upper)):
        raise ValueError("POST_BLENDER_GLB_HAS_NON_FINITE_BOUNDS")
    return {
        "schema_version": "1.0.0",
        "status": "passed",
        "file": glb_path.name,
        "blender_version": bpy.app.version_string,
        "mesh_count": len(meshes),
        "vertex_count": sum(record["vertex_count"] for record in records),
        "triangle_count": sum(record["triangle_count"] for record in records),
        "bounding_box_m": {"minimum": lower, "maximum": upper},
        "dimensions_m": {
            axis: upper[index] - lower[index]
            for index, axis in enumerate(("x", "y", "z"))
        },
        "component_identity_count": sum(
            bool(record["component_name"] or record["cad_node_id"]) for record in records
        ),
        "components": records,
        "method": "fresh Blender GLB import and world-space vertex measurement",
    }


def main() -> None:
    import bpy

    try:
        glb_arg, report_arg = sys.argv[sys.argv.index("--") + 1 :]
    except (ValueError, IndexError) as exc:
        raise SystemExit("Usage: inspect_exported_glb.py -- GLB REPORT_JSON") from exc
    glb_path = Path(glb_arg).resolve(strict=True)
    report_path = Path(report_arg).resolve()
    result = _measure(bpy, glb_path)
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
