"""Controlled Blender worker for SceneSpec-based telecom scene generation.

Usage:
    blender -b --python apps/blender_worker/generate_scene.py -- scene_spec.json output_dir

The script is intentionally SceneSpec-driven. It does not execute LLM-generated code.
"""

from __future__ import annotations

import json
import math
import sys
import zlib
from binascii import crc32
from pathlib import Path


def main() -> int:
    scene_spec_path, output_dir = _parse_args(sys.argv)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = json.loads(scene_spec_path.read_text(encoding="utf-8"))

    try:
        import bpy  # type: ignore[import-not-found]
    except ImportError:
        _write_non_blender_fallback(scene, output_dir)
        return 0

    procedural_objects: list[str] = []
    _reset_scene(bpy)
    _configure_scene(bpy, scene)
    _create_tower(bpy, scene, procedural_objects)
    _create_height_marker(bpy, scene, procedural_objects)
    _create_sectors(bpy, scene, procedural_objects)
    _create_camera_and_light(bpy, scene)

    glb_path = output_dir / "design.glb"
    preview_path = output_dir / "preview.png"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB")
    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    _write_metadata(scene, output_dir, "real_blender", procedural_objects, [])
    return 0


def _parse_args(argv: list[str]) -> tuple[Path, Path]:
    if "--" not in argv:
        raise SystemExit("Expected '-- scene_spec.json output_dir'")
    args = argv[argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("Expected exactly: scene_spec.json output_dir")
    return Path(args[0]), Path(args[1])


def _reset_scene(bpy) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def _configure_scene(bpy, scene: dict) -> None:
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    engines = {
        item.identifier for item in bpy.context.scene.render.bl_rna.properties["engine"].enum_items
    }
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if engine in engines:
            bpy.context.scene.render.engine = engine
            break
    width, height = scene["preview"]["resolution"]
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)


def _create_tower(bpy, scene: dict, procedural_objects: list[str]) -> None:
    height = float(scene["tower"]["height_m"])
    tower_type = scene["tower"]["asset_id"].lower()
    if "lattice" in tower_type:
        _create_lattice_tower(bpy, height)
        procedural_objects.append("tower:lattice_procedural")
    elif "monopole" in tower_type:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=0.35, depth=height, location=(0, 0, height / 2)
        )
        obj = bpy.context.object
        obj.name = f"tower_{scene['tower']['asset_id']}"
        obj.data.materials.append(_material(bpy, "galvanized_steel", (0.55, 0.58, 0.6, 1)))
        procedural_objects.append("tower:monopole_procedural")
    else:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=12, radius=0.5, depth=height, location=(0, 0, height / 2)
        )
        obj = bpy.context.object
        obj.name = f"tower_{scene['tower']['asset_id']}"
        obj.data.materials.append(_material(bpy, "galvanized_steel", (0.55, 0.58, 0.6, 1)))
        procedural_objects.append("tower:generic_procedural")


def _create_lattice_tower(bpy, height: float) -> None:
    material = _material(bpy, "galvanized_steel", (0.55, 0.58, 0.6, 1))
    base = 2.0
    top = 0.8
    levels = 8
    for index in range(levels):
        z0 = height * index / levels
        z1 = height * (index + 1) / levels
        width0 = base - (base - top) * index / levels
        width1 = base - (base - top) * (index + 1) / levels
        corners0 = _square_corners(width0, z0)
        corners1 = _square_corners(width1, z1)
        for c0, c1 in zip(corners0, corners1, strict=True):
            _create_cylinder_between(bpy, c0, c1, 0.045, "tower_leg", material)
        for side in range(4):
            _create_cylinder_between(
                bpy, corners0[side], corners1[(side + 1) % 4], 0.025, "tower_brace", material
            )
            _create_cylinder_between(
                bpy, corners0[(side + 1) % 4], corners1[side], 0.025, "tower_brace", material
            )


def _square_corners(width: float, z: float) -> list[tuple[float, float, float]]:
    half = width / 2
    return [(-half, -half, z), (half, -half, z), (half, half, z), (-half, half, z)]


def _create_sectors(bpy, scene: dict, procedural_objects: list[str]) -> None:
    for sector in scene["sectors"]:
        azimuth = math.radians(float(sector["azimuth_deg"]))
        radius = 1.35
        x = math.sin(azimuth) * radius
        y = math.cos(azimuth) * radius
        z = float(sector["install_height_m"])

        if "dish" in sector["antenna_asset_id"].lower():
            _create_dish(bpy, sector, x, y, z, azimuth)
            procedural_objects.append(f"antenna_dish:{sector['sector_id']}")
        else:
            _create_panel_antenna(bpy, sector, x, y, z, azimuth)
            procedural_objects.append(f"antenna_panel:{sector['sector_id']}")

        if sector.get("radio_asset_id"):
            _create_radio(bpy, sector, x * 0.9, y * 0.9, z - 1.0)
            procedural_objects.append(f"radio:{sector['sector_id']}")

        if sector.get("include_cable"):
            _create_cable(bpy, sector["sector_id"], (x, y, z - 0.8), (0, 0, 0.5))
            procedural_objects.append(f"cable:{sector['sector_id']}")

        if scene["visual_elements"].get("include_sector_beams"):
            _create_beam(bpy, sector["sector_id"], azimuth, z, float(sector["beam_radius_m"]))
            procedural_objects.append(f"sector_beam:{sector['sector_id']}")

        if scene["visual_elements"].get("include_azimuth_arrows"):
            _create_azimuth_arrow(bpy, sector["sector_id"], azimuth, z + 1.2)
            procedural_objects.append(f"azimuth_arrow:{sector['sector_id']}")


def _create_panel_antenna(bpy, sector: dict, x: float, y: float, z: float, azimuth: float) -> None:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    antenna = bpy.context.object
    antenna.name = f"antenna_{sector['sector_id']}_{sector['antenna_asset_id']}"
    antenna.dimensions = (0.35, 0.12, 1.55)
    antenna.rotation_euler[2] = -azimuth
    antenna.data.materials.append(_material(bpy, "antenna_white", (0.9, 0.9, 0.86, 1)))


def _create_dish(bpy, sector: dict, x: float, y: float, z: float, azimuth: float) -> None:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=16, radius=0.45, location=(x, y, z)
    )
    dish = bpy.context.object
    dish.name = f"dish_{sector['sector_id']}_{sector['antenna_asset_id']}"
    dish.scale = (1.0, 0.22, 1.0)
    dish.rotation_euler[2] = -azimuth
    dish.data.materials.append(_material(bpy, "dish_light_gray", (0.78, 0.8, 0.82, 1)))


def _create_radio(bpy, sector: dict, x: float, y: float, z: float) -> None:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    radio = bpy.context.object
    radio.name = f"radio_{sector['sector_id']}_{sector['radio_asset_id']}"
    radio.dimensions = (0.35, 0.18, 0.55)
    radio.data.materials.append(_material(bpy, "rru_gray", (0.25, 0.27, 0.29, 1)))


def _create_cable(
    bpy, sector_id: str, start: tuple[float, float, float], end: tuple[float, float, float]
) -> None:
    curve = bpy.data.curves.new(f"cable_{sector_id}", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 8
    curve.bevel_depth = 0.025
    spline = curve.splines.new("POLY")
    spline.points.add(2)
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, start[2] - 2.0)
    spline.points[0].co = (*start, 1)
    spline.points[1].co = (*mid, 1)
    spline.points[2].co = (*end, 1)
    obj = bpy.data.objects.new(f"cable_{sector_id}", curve)
    bpy.context.collection.objects.link(obj)


def _create_beam(bpy, sector_id: str, azimuth: float, z: float, radius: float) -> None:
    x = math.sin(azimuth) * radius / 2
    y = math.cos(azimuth) * radius / 2
    bpy.ops.mesh.primitive_cone_add(
        vertices=32, radius1=radius / 2, radius2=0.1, depth=radius, location=(x, y, z)
    )
    beam = bpy.context.object
    beam.name = f"sector_beam_{sector_id}"
    beam.rotation_euler[0] = math.radians(90)
    beam.rotation_euler[2] = -azimuth
    beam.data.materials.append(_material(bpy, "beam_translucent", (0.1, 0.5, 1.0, 0.22)))


def _create_azimuth_arrow(bpy, sector_id: str, azimuth: float, z: float) -> None:
    start = (0, 0, z)
    end = (math.sin(azimuth) * 3.0, math.cos(azimuth) * 3.0, z)
    material = _material(bpy, f"azimuth_arrow_red_{sector_id}", (1.0, 0.15, 0.1, 1))
    _create_cylinder_between(bpy, start, end, 0.035, f"azimuth_arrow_{sector_id}", material)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.16, depth=0.35, location=end)
    head = bpy.context.object
    head.name = f"azimuth_arrow_head_{sector_id}"
    head.rotation_euler[0] = math.radians(90)
    head.rotation_euler[2] = -azimuth
    head.data.materials.append(material)


def _create_height_marker(bpy, scene: dict, procedural_objects: list[str]) -> None:
    height = float(scene["tower"]["height_m"])
    material = _material(bpy, "height_marker_yellow", (1.0, 0.82, 0.1, 1))
    _create_cylinder_between(bpy, (2.7, 0, 0), (2.7, 0, height), 0.025, "height_marker", material)
    procedural_objects.append("height_marker")


def _create_camera_and_light(bpy, scene: dict) -> None:
    tower_height = float(scene["tower"]["height_m"])
    bpy.ops.object.light_add(type="SUN", location=(5, -5, tower_height + 10))
    bpy.context.object.name = "sun_key"
    bpy.ops.object.camera_add(
        location=(tower_height, -tower_height, tower_height * 0.8), rotation=(1.1, 0, 0.78)
    )
    bpy.context.scene.camera = bpy.context.object


def _create_cylinder_between(
    bpy,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    name: str,
    material,
) -> None:
    sx, sy, sz = start
    ex, ey, ez = end
    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length == 0:
        return
    midpoint = ((sx + ex) / 2, (sy + ey) / 2, (sz + ez) / 2)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=length, location=midpoint)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = _direction_to_euler(dx, dy, dz)
    obj.data.materials.append(material)


def _direction_to_euler(dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    yaw = math.atan2(dy, dx)
    horizontal = math.sqrt(dx * dx + dy * dy)
    pitch = math.atan2(horizontal, dz)
    return (pitch, 0, yaw + math.pi / 2)


def _material(bpy, name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def _write_non_blender_fallback(scene: dict, output_dir: Path) -> None:
    (output_dir / "design.glb").write_bytes(
        b"glTF fallback artifact generated from SceneSpec: " + scene["scene_id"].encode()
    )
    width, height = scene["preview"]["resolution"]
    (output_dir / "preview.png").write_bytes(_minimal_png(int(width), int(height)))
    _write_metadata(
        scene,
        output_dir,
        "fallback_no_blender",
        _procedural_objects_from_scene(scene),
        ["Blender Python API not available; worker fallback artifact created."],
    )


def _write_metadata(
    scene: dict,
    output_dir: Path,
    generation_mode: str,
    procedural_objects: list[str],
    warnings: list[str],
) -> None:
    (output_dir / "scene_metadata.json").write_text(
        json.dumps(
            {
                "scene_id": scene["scene_id"],
                "schema_version": scene.get("schema_version"),
                "generation_mode": generation_mode,
                "assets_used": _assets_used(scene),
                "procedural_objects_created": procedural_objects,
                "sector_count": len(scene["sectors"]),
                "network_type": scene["network_type"],
                "azimuths_deg": [sector["azimuth_deg"] for sector in scene["sectors"]],
                "antenna_heights_m": [sector["install_height_m"] for sector in scene["sectors"]],
                "warnings": warnings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _assets_used(scene: dict) -> list[str]:
    assets = [scene["tower"]["asset_id"]]
    for sector in scene["sectors"]:
        assets.append(sector["antenna_asset_id"])
        if sector.get("radio_asset_id"):
            assets.append(sector["radio_asset_id"])
    return sorted(set(assets))


def _procedural_objects_from_scene(scene: dict) -> list[str]:
    objects = ["tower"]
    for sector in scene["sectors"]:
        objects.append(f"antenna:{sector['sector_id']}")
        if sector.get("radio_asset_id"):
            objects.append(f"radio:{sector['sector_id']}")
        if sector.get("include_cable"):
            objects.append(f"cable:{sector['sector_id']}")
        if scene["visual_elements"].get("include_sector_beams"):
            objects.append(f"sector_beam:{sector['sector_id']}")
        if scene["visual_elements"].get("include_azimuth_arrows"):
            objects.append(f"azimuth_arrow:{sector['sector_id']}")
    if scene["visual_elements"].get("include_height_markers"):
        objects.append("height_marker")
    if scene["visual_elements"].get("include_labels"):
        objects.append("labels_metadata")
    return objects


def _minimal_png(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    row = b"\x00" + (b"\xff\xff\xff" * width)
    image = zlib.compress(row * height, level=9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(
        b"IEND", b""
    )


if __name__ == "__main__":
    raise SystemExit(main())
