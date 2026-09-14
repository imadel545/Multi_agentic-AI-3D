"""Prepare a CAD-derived GLB for inspection without changing its mesh geometry.

This script runs inside Blender.  It applies one rigid transform above the
imported hierarchy, recentres the published viewer bounds, and delegates GLB
buffer packing to Blender's GLB exporter. Quantization, compression and mesh
simplification are deliberately disabled so the neutral-CAD tessellation is not
approximated a second time.  Cameras, lights and animation data are omitted from
the inspection derivative. This preparation alone never grants generation
admission or establishes physical mounting and electrical interfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("report")
    parser.add_argument("--rotation-x-deg", type=float, default=0.0)
    parser.add_argument("--rotation-y-deg", type=float, default=0.0)
    parser.add_argument("--rotation-z-deg", type=float, default=0.0)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounds(objects: list[bpy.types.Object], transform: Matrix | None = None) -> dict:
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            points.append(transform @ point if transform is not None else point)
    if not points:
        raise RuntimeError("QUALIFIED_ASSET_MESH_MISSING")
    minimum = [min(point[index] for point in points) for index in range(3)]
    maximum = [max(point[index] for point in points) for index in range(3)]
    return {
        "minimum": minimum,
        "maximum": maximum,
        "dimensions": [maximum[index] - minimum[index] for index in range(3)],
        "center": [(maximum[index] + minimum[index]) / 2 for index in range(3)],
    }


def _matrix_payload(matrix: Matrix) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _render_previews(output: Path) -> list[dict]:
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    bounds = _bounds(mesh_objects)
    lower = Vector(bounds["minimum"])
    upper = Vector(bounds["maximum"])
    center = (lower + upper) / 2
    radius = max((upper - lower).length / 2, 1e-8)

    camera_data = bpy.data.cameras.new("QualificationCamera")
    camera = bpy.data.objects.new("QualificationCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.clip_start = min(0.001, radius / 100)
    camera_data.clip_end = radius * 20 + 100
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("QualificationWorld")
    scene.world.color = (0.07, 0.07, 0.07)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100

    views = (
        ("perspective", "preview.png", (1.0, -1.0, 0.75), 2.35),
        ("front", "preview_front.png", (0.0, -1.0, 0.0), 2.35),
        ("side", "preview_side.png", (1.0, 0.0, 0.0), 2.35),
        ("top", "preview_top.png", (0.0, 0.0, 1.0), 2.35),
        ("closeup", "preview_closeup.png", (0.8, -1.0, 0.35), 1.85),
    )
    records = []
    for view, filename, direction, scale in views:
        camera.location = center + Vector(direction).normalized() * radius * 4
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.ortho_scale = radius * scale
        path = output.parent / filename
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        records.append(
            {
                "view": view,
                "file": filename,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "width_px": 1200,
                "height_px": 1000,
            }
        )
    return records


def main() -> None:
    args = _arguments()
    source = Path(args.source).resolve(strict=True)
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects = list(bpy.context.scene.objects)
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError("QUALIFIED_ASSET_MESH_MISSING")

    input_bounds = _bounds(objects)
    rotation = (
        Matrix.Rotation(math.radians(args.rotation_z_deg), 4, "Z")
        @ Matrix.Rotation(math.radians(args.rotation_y_deg), 4, "Y")
        @ Matrix.Rotation(math.radians(args.rotation_x_deg), 4, "X")
    )
    rotated_bounds = _bounds(objects, rotation)
    center = Vector(rotated_bounds["center"])
    normalization = Matrix.Translation(-center) @ rotation

    normalization_root = bpy.data.objects.new("QualifiedAssetRoot", None)
    bpy.context.collection.objects.link(normalization_root)
    for obj in objects:
        if obj.parent is None:
            obj.parent = normalization_root
    normalization_root.matrix_world = normalization
    normalization_root["normalization"] = "rigid_rotation_and_bounds_center"
    normalization_root["source_glb_sha256"] = _sha256(source)
    triangle_count = sum(
        sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)
        for obj in mesh_objects
    )

    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        use_selection=False,
        export_apply=False,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_extras=True,
    )
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(output))
    bpy.context.view_layer.update()
    preview_records = _render_previews(output)

    report = {
        "schema_version": "qualified_asset_viewer_preparation.v1",
        "status": "passed",
        "blender_version": bpy.app.version_string,
        "source": {
            "file": source.name,
            "sha256": _sha256(source),
            "size_bytes": source.stat().st_size,
        },
        "output": {
            "file": output.name,
            "sha256": _sha256(output),
            "size_bytes": output.stat().st_size,
        },
        "mesh_count": len(mesh_objects),
        "triangle_count": triangle_count,
        "input_bounds_m": input_bounds,
        "rotation_deg": [
            args.rotation_x_deg,
            args.rotation_y_deg,
            args.rotation_z_deg,
        ],
        "normalization_matrix": _matrix_payload(normalization),
        "expected_output_bounds_m": {
            "minimum": [
                rotated_bounds["minimum"][index] - rotated_bounds["center"][index]
                for index in range(3)
            ],
            "maximum": [
                rotated_bounds["maximum"][index] - rotated_bounds["center"][index]
                for index in range(3)
            ],
            "dimensions": rotated_bounds["dimensions"],
        },
        "optimization": {
            "engine": "Blender indexed GLB export",
            "position_quantization": False,
            "mesh_compression": False,
            "mesh_simplification": False,
            "geometry_transform": "rigid_only",
            "omitted_scene_data": ["cameras", "lights", "animations"],
        },
        "previews": preview_records,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
