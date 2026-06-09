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
    asset_imports: list[dict] = []
    asset_warnings: list[str] = []
    _reset_scene(bpy)
    _configure_scene(bpy, scene)
    _create_ground_plane(bpy, scene)
    _create_tower(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    _create_height_marker(bpy, scene, procedural_objects)
    _create_sectors(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    if scene["visual_elements"].get("include_power_cabinet", False):
        _create_power_cabinet(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    if scene["visual_elements"].get("include_gps_antenna", False):
        _create_gps_antenna(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    camera_metadata = _create_camera_and_light(bpy, scene)

    glb_path = output_dir / "design.glb"
    preview_path = output_dir / "preview.png"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB")
    _create_preview_backdrop(bpy, scene)
    camera_metadata["render_backdrop"] = "preview_only_light_plane"
    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    _write_metadata(
        scene,
        output_dir,
        "real_blender",
        procedural_objects,
        asset_warnings,
        camera_metadata,
        asset_imports,
    )
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
    for engine in ("BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if engine in engines:
            bpy.context.scene.render.engine = engine
            break
    width, height = scene["preview"]["resolution"]
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.94, 0.96, 0.98)
    bpy.context.scene.render.film_transparent = False
    if bpy.context.scene.render.engine == "BLENDER_WORKBENCH":
        shading = bpy.context.scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "COLOR"
        shading.background_color = (0.94, 0.96, 0.98)
    if hasattr(bpy.context.scene, "eevee"):
        if hasattr(bpy.context.scene.eevee, "use_gtao"):
            bpy.context.scene.eevee.use_gtao = True
        if hasattr(bpy.context.scene.eevee, "gtao_distance"):
            bpy.context.scene.eevee.gtao_distance = 4
        if hasattr(bpy.context.scene.eevee, "gtao_factor"):
            bpy.context.scene.eevee.gtao_factor = 0.8
    bpy.context.scene.view_settings.view_transform = "Standard"
    try:
        bpy.context.scene.view_settings.look = "None"
    except TypeError:
        bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 0.25
    bpy.context.scene.view_settings.gamma = 1


def _create_ground_plane(bpy, scene: dict) -> None:
    height = float(scene["tower"]["height_m"])
    size = max(14.0, height * 0.6)
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.02))
    ground = bpy.context.object
    ground.name = "technical_ground_plane"
    ground.data.materials.append(_material(bpy, "matte_ground", (0.72, 0.74, 0.74, 1)))


def _create_tower(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    height = float(scene["tower"]["height_m"])
    characteristics = scene["tower"].get("characteristics", {})
    tower_type = scene["tower"]["asset_id"].lower()
    base_width = float(characteristics.get("base_width_m") or 4.0)
    tower_mode = _try_import_glb_asset(
        bpy=bpy,
        asset_id=scene["tower"]["asset_id"],
        asset_file=scene["tower"].get("asset_file"),
        asset_source=scene["tower"].get("asset_source"),
        asset_metadata=scene["tower"].get("asset_metadata"),
        fallback_allowed=scene["tower"].get("import_fallback_allowed", True),
        object_role="tower",
        object_name=f"tower_{scene['tower']['asset_id']}",
        location=(0.0, 0.0, height / 2),
        rotation=(0.0, 0.0, 0.0),
        dimensions=scene["tower"].get("dimensions_m")
        or {
            "width": base_width,
            "depth": base_width,
            "height": height,
        },
        asset_imports=asset_imports,
        warnings=asset_warnings,
    )
    if tower_mode != "imported_glb" and scene["tower"].get("import_fallback_allowed", True):
        if "lattice" in tower_type:
            _create_lattice_tower(bpy, height, characteristics)
            procedural_objects.append("tower:lattice_procedural")
        elif "monopole" in tower_type:
            radius = base_width / 2
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=32, radius=radius, depth=height, location=(0, 0, height / 2)
            )
            obj = bpy.context.object
            obj.name = f"tower_{scene['tower']['asset_id']}"
            obj.data.materials.append(_material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1)))
            procedural_objects.append("tower:monopole_procedural")
        else:
            radius = base_width / 2
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=12, radius=radius, depth=height, location=(0, 0, height / 2)
            )
            obj = bpy.context.object
            obj.name = f"tower_{scene['tower']['asset_id']}"
            obj.data.materials.append(_material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1)))
            procedural_objects.append("tower:generic_procedural")
    _create_foundation(bpy, characteristics, procedural_objects)
    _create_tower_accessories(bpy, height, characteristics, procedural_objects)


def _create_lattice_tower(bpy, height: float, characteristics: dict) -> None:
    material = _material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1))
    base = float(characteristics.get("base_width_m") or 4.0)
    top = float(characteristics.get("top_width_m") or 1.0)
    leg_count = int(characteristics.get("leg_count") or 4)
    levels = 8
    for index in range(levels):
        z0 = height * index / levels
        z1 = height * (index + 1) / levels
        width0 = base - (base - top) * index / levels
        width1 = base - (base - top) * (index + 1) / levels
        corners0 = _tower_corners(width0, z0, leg_count)
        corners1 = _tower_corners(width1, z1, leg_count)
        for c0, c1 in zip(corners0, corners1, strict=True):
            _create_cylinder_between(bpy, c0, c1, 0.045, "tower_leg", material)
        for side in range(len(corners0)):
            _create_cylinder_between(
                bpy,
                corners0[side],
                corners1[(side + 1) % len(corners1)],
                0.025,
                "tower_brace",
                material,
            )
            _create_cylinder_between(
                bpy,
                corners0[(side + 1) % len(corners0)],
                corners1[side],
                0.025,
                "tower_brace",
                material,
            )


def _tower_corners(width: float, z: float, leg_count: int) -> list[tuple[float, float, float]]:
    if leg_count == 3:
        radius = width / 2
        return [
            (
                math.sin((2 * math.pi * index) / 3) * radius,
                math.cos((2 * math.pi * index) / 3) * radius,
                z,
            )
            for index in range(3)
        ]
    half = width / 2
    return [(-half, -half, z), (half, -half, z), (half, half, z), (-half, half, z)]


def _create_tower_accessories(
    bpy,
    height: float,
    characteristics: dict,
    procedural_objects: list[str],
) -> None:
    steel = _material(bpy, "accessory_steel", (0.42, 0.44, 0.46, 1))
    base_width = float(characteristics.get("base_width_m") or 4.0)
    if characteristics.get("has_platform"):
        count = max(1, int(characteristics.get("platform_count") or 1))
        for index in range(count):
            z = height * (0.55 + (0.35 * index / max(count, 1)))
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, z))
            platform = bpy.context.object
            platform.name = f"tower_platform_{index + 1}"
            platform.dimensions = (2.2, 2.2, 0.08)
            platform.data.materials.append(steel)
            procedural_objects.append(f"tower_platform:{index + 1}")
    if characteristics.get("has_ladder"):
        ladder_offset = base_width / 2 + 0.15
        _create_cylinder_between(
            bpy,
            (-ladder_offset, 0, 0.5),
            (-ladder_offset, 0, height - 0.5),
            0.018,
            "tower_ladder",
            steel,
        )
        _create_cylinder_between(
            bpy,
            (-ladder_offset + 0.15, 0, 0.5),
            (-ladder_offset + 0.15, 0, height - 0.5),
            0.018,
            "tower_ladder",
            steel,
        )
        procedural_objects.append("tower_ladder")
    if characteristics.get("has_lightning_rod"):
        _create_cylinder_between(
            bpy, (0, 0, height), (0, 0, height + 1.2), 0.025, "tower_lightning_rod", steel
        )
        procedural_objects.append("tower_lightning_rod")
    if characteristics.get("has_aviation_light"):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=16,
            ring_count=8,
            radius=0.16,
            location=(0, 0, height + 0.25),
        )
        light = bpy.context.object
        light.name = "tower_aviation_light"
        light.data.materials.append(_material(bpy, "aviation_red", (1.0, 0.02, 0.02, 1)))
        procedural_objects.append("tower_aviation_light")


def _create_sectors(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    characteristics = scene["tower"].get("characteristics", {})
    base_width = float(characteristics.get("base_width_m") or 4.0)
    mount_radius = base_width / 2 + 0.35
    for sector in scene["sectors"]:
        azimuth = math.radians(float(sector["azimuth_deg"]))
        x = math.sin(azimuth) * mount_radius
        y = math.cos(azimuth) * mount_radius
        z = float(sector["install_height_m"])
        tilt_deg = float(sector.get("mechanical_tilt_deg") or 0.0)

        # Mounting bracket arm
        _create_mounting_bracket(bpy, mount_radius, azimuth, z)
        procedural_objects.append(f"mount_bracket:{sector['sector_id']}")

        total_tilt = tilt_deg + float(sector.get("electrical_tilt_deg") or 0.0)
        antenna_mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=sector["antenna_asset_id"],
            asset_file=sector.get("antenna_asset_file"),
            asset_source=sector.get("antenna_asset_source"),
            asset_metadata=sector.get("antenna_asset_metadata"),
            fallback_allowed=sector.get("antenna_import_fallback_allowed", True),
            object_role="antenna",
            object_name=f"antenna_{sector['sector_id']}_{sector['antenna_asset_id']}",
            location=(x, y, z),
            rotation=(-azimuth, math.radians(total_tilt), 0.0),
            rotation_mode="ZXY",
            dimensions=sector.get("antenna_dimensions_m"),
            asset_imports=asset_imports,
            warnings=asset_warnings,
        )
        if antenna_mode != "imported_glb" and sector.get("antenna_import_fallback_allowed", True):
            if "dish" in sector["antenna_asset_id"].lower():
                _create_dish(bpy, sector, x, y, z, azimuth, tilt_deg)
                procedural_objects.append(f"antenna_dish:{sector['sector_id']}")
            else:
                _create_panel_antenna(bpy, sector, x, y, z, azimuth, tilt_deg)
                procedural_objects.append(f"antenna_panel:{sector['sector_id']}")

        if sector.get("radio_asset_id"):
            radio_mode = _try_import_glb_asset(
                bpy=bpy,
                asset_id=sector["radio_asset_id"],
                asset_file=sector.get("radio_asset_file"),
                asset_source=sector.get("radio_asset_source"),
                asset_metadata=sector.get("radio_asset_metadata"),
                fallback_allowed=sector.get("radio_import_fallback_allowed", True),
                object_role="radio",
                object_name=f"radio_{sector['sector_id']}_{sector['radio_asset_id']}",
                location=(x * 0.92, y * 0.92, z - 1.0),
                rotation=(0.0, 0.0, 0.0),
                rotation_mode="XYZ",
                dimensions=sector.get("radio_dimensions_m"),
                asset_imports=asset_imports,
                warnings=asset_warnings,
            )
            if radio_mode != "imported_glb" and sector.get("radio_import_fallback_allowed", True):
                _create_radio(bpy, sector, x * 0.92, y * 0.92, z - 1.0)
                procedural_objects.append(f"radio:{sector['sector_id']}")

        if sector.get("include_cable"):
            _create_cable(bpy, sector["sector_id"], (x, y, z - 0.8), (0, 0, 0.5))
            procedural_objects.append(f"cable:{sector['sector_id']}")

        if scene["visual_elements"].get("include_sector_beams"):
            beamwidth = float(sector.get("beamwidth_deg") or 65.0)
            _create_beam(
                bpy, sector["sector_id"], azimuth, z, float(sector["beam_radius_m"]), beamwidth
            )
            procedural_objects.append(f"sector_beam:{sector['sector_id']}")

        if scene["visual_elements"].get("include_azimuth_arrows"):
            _create_azimuth_arrow(bpy, sector["sector_id"], azimuth, z + 1.2)
            procedural_objects.append(f"azimuth_arrow:{sector['sector_id']}")


def _create_panel_antenna(
    bpy, sector: dict, x: float, y: float, z: float, azimuth: float, tilt_deg: float
) -> None:
    dims = sector.get("antenna_dimensions_m") or {}
    width = float(dims.get("width") or 0.35)
    depth = float(dims.get("depth") or 0.12)
    height = float(dims.get("height") or 1.55)
    total_tilt = tilt_deg + float(sector.get("electrical_tilt_deg") or 0.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    antenna = bpy.context.object
    antenna.name = f"antenna_{sector['sector_id']}_{sector['antenna_asset_id']}"
    antenna.dimensions = (width, depth, height)
    antenna.rotation_mode = "ZXY"
    antenna.rotation_euler = (-azimuth, math.radians(total_tilt), 0)
    antenna.data.materials.append(_material(bpy, "antenna_white", (0.9, 0.9, 0.86, 1)))


def _create_dish(
    bpy, sector: dict, x: float, y: float, z: float, azimuth: float, tilt_deg: float
) -> None:
    dims = sector.get("antenna_dimensions_m") or {}
    width = float(dims.get("width") or 0.9)
    depth = float(dims.get("depth") or 0.35)
    radius = width / 2
    total_tilt = tilt_deg + float(sector.get("electrical_tilt_deg") or 0.0)
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=16, radius=radius, location=(x, y, z)
    )
    dish = bpy.context.object
    dish.name = f"dish_{sector['sector_id']}_{sector['antenna_asset_id']}"
    dish.scale = (1.0, depth / width, 1.0)
    dish.rotation_mode = "ZXY"
    dish.rotation_euler = (-azimuth, math.radians(total_tilt), 0)
    dish.data.materials.append(_material(bpy, "dish_light_gray", (0.78, 0.8, 0.82, 1)))
    # Feed horn
    horn_dir = (
        math.sin(azimuth) * (radius * 0.35),
        math.cos(azimuth) * (radius * 0.35),
        z + math.sin(math.radians(total_tilt)) * (radius * 0.35),
    )
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=radius * 0.06, depth=radius * 0.25, location=horn_dir
    )
    horn = bpy.context.object
    horn.name = f"dish_horn_{sector['sector_id']}"
    horn.rotation_mode = "ZXY"
    horn.rotation_euler = (-azimuth, math.radians(total_tilt), 0)
    horn.data.materials.append(_material(bpy, "dish_feed", (0.2, 0.22, 0.24, 1)))


def _create_radio(bpy, sector: dict, x: float, y: float, z: float) -> None:
    dims = sector.get("radio_dimensions_m") or {}
    width = float(dims.get("width") or 0.35)
    depth = float(dims.get("depth") or 0.18)
    height = float(dims.get("height") or 0.55)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    radio = bpy.context.object
    radio.name = f"radio_{sector['sector_id']}_{sector['radio_asset_id']}"
    radio.dimensions = (width, depth, height)
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


def _create_beam(
    bpy, sector_id: str, azimuth: float, z: float, radius: float, beamwidth_deg: float = 65.0
) -> None:
    visual_length = min(radius, 4.5)
    start_radius = 1.55
    start = (
        math.sin(azimuth) * start_radius,
        math.cos(azimuth) * start_radius,
        z + 0.15,
    )
    end = (
        math.sin(azimuth) * (start_radius + visual_length),
        math.cos(azimuth) * (start_radius + visual_length),
        z + 0.15,
    )
    material = _material(bpy, "beam_direction_blue", (0.05, 0.45, 1.0, 0.62))
    _create_cylinder_between(bpy, start, end, 0.035, f"sector_beam_{sector_id}", material)
    # Cone head scaled by beamwidth (narrower beam = sharper cone)
    cone_radius = max(0.08, 0.14 * (65.0 / max(beamwidth_deg, 10.0)))
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=cone_radius, depth=0.3, location=end)
    head = bpy.context.object
    head.name = f"sector_beam_head_{sector_id}"
    head.rotation_euler = _direction_to_euler(
        end[0] - start[0],
        end[1] - start[1],
        end[2] - start[2],
    )
    head.data.materials.append(material)


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


def _create_power_cabinet(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    base_width = float(scene["tower"].get("characteristics", {}).get("base_width_m") or 4.0)
    # Place cabinet a few meters away from tower base
    offset = max(3.0, base_width * 1.2)
    accessory = _accessory_asset(scene, "cabinet")
    if accessory:
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=accessory.get("asset_file"),
            asset_source=accessory.get("asset_source"),
            asset_metadata=accessory.get("asset_metadata"),
            fallback_allowed=accessory.get("import_fallback_allowed", True),
            object_role="cabinet",
            object_name=f"power_cabinet_{accessory['asset_id']}",
            location=tuple(accessory.get("position") or [offset, 0.0, 0.8]),
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=accessory.get("dimensions_m"),
            asset_imports=asset_imports,
            warnings=asset_warnings,
        )
        if mode == "imported_glb" or not accessory.get("import_fallback_allowed", True):
            return
    bpy.ops.mesh.primitive_cube_add(size=1, location=(offset, 0, 0.9))
    cabinet = bpy.context.object
    cabinet.name = "power_cabinet_dc"
    cabinet.dimensions = (1.5, 0.8, 1.8)
    cabinet.data.materials.append(_material(bpy, "cabinet_gray", (0.35, 0.37, 0.39, 1)))
    # Small detail: door outline hint
    bpy.ops.mesh.primitive_cube_add(size=1, location=(offset + 0.76, 0, 0.9))
    door = bpy.context.object
    door.name = "power_cabinet_door"
    door.dimensions = (0.04, 0.72, 1.6)
    door.data.materials.append(_material(bpy, "cabinet_door", (0.28, 0.30, 0.32, 1)))
    procedural_objects.append("power_cabinet")


def _create_gps_antenna(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    height = float(scene["tower"]["height_m"])
    # GPS typically mounted near tower top
    z = height - 0.5
    base_width = float(scene["tower"].get("characteristics", {}).get("base_width_m") or 4.0)
    mount_radius = base_width / 2 + 0.1
    accessory = _accessory_asset(scene, "gps")
    if accessory:
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=accessory.get("asset_file"),
            asset_source=accessory.get("asset_source"),
            asset_metadata=accessory.get("asset_metadata"),
            fallback_allowed=accessory.get("import_fallback_allowed", True),
            object_role="gps",
            object_name=f"gps_antenna_{accessory['asset_id']}",
            location=tuple(accessory.get("position") or [0.0, mount_radius, z + 0.64]),
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=accessory.get("dimensions_m"),
            asset_imports=asset_imports,
            warnings=asset_warnings,
        )
        if mode == "imported_glb" or not accessory.get("import_fallback_allowed", True):
            return
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=0.04, depth=0.6, location=(0, mount_radius, z + 0.3)
    )
    pole = bpy.context.object
    pole.name = "gps_mount_pole"
    pole.data.materials.append(_material(bpy, "gps_pole", (0.5, 0.5, 0.52, 1)))
    # Radome: flattened sphere instead of flat disc
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=16, ring_count=8, radius=0.12, location=(0, mount_radius, z + 0.64)
    )
    radome = bpy.context.object
    radome.name = "gps_antenna_radome"
    radome.scale = (1.0, 1.0, 0.55)
    radome.data.materials.append(_material(bpy, "gps_white", (0.92, 0.92, 0.9, 1)))
    procedural_objects.append("gps_antenna")


def _accessory_asset(scene: dict, asset_type: str) -> dict | None:
    for accessory in scene.get("accessory_assets", []):
        if accessory.get("asset_type") == asset_type:
            return accessory
    return None


def _rotation_deg_to_rad(values: list[float]) -> tuple[float, float, float]:
    return tuple(math.radians(float(value)) for value in values[:3])


def _create_foundation(bpy, characteristics: dict, procedural_objects: list[str]) -> None:
    foundation_type = characteristics.get("foundation_type", "concrete_pad")
    if foundation_type == "concrete_pad":
        base_width = float(characteristics.get("base_width_m") or 4.0)
        size = max(base_width * 1.6, 3.0)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.15))
        pad = bpy.context.object
        pad.name = "foundation_concrete_pad"
        pad.dimensions = (size, size, 0.3)
        pad.data.materials.append(_material(bpy, "concrete_gray", (0.62, 0.64, 0.66, 1)))
        procedural_objects.append("foundation_concrete_pad")


def _try_import_glb_asset(
    *,
    bpy,
    asset_id: str,
    asset_file: str | None,
    asset_source: str | None,
    asset_metadata: dict | None,
    fallback_allowed: bool,
    object_role: str,
    object_name: str,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
    rotation_mode: str = "XYZ",
    dimensions: dict | None = None,
    asset_imports: list[dict],
    warnings: list[str],
) -> str:
    path = _resolve_asset_path(asset_file)
    record = _base_asset_import_record(
        asset_id=asset_id,
        asset_file=asset_file,
        asset_source=asset_source,
        asset_metadata=asset_metadata,
        object_role=object_role,
        object_name=object_name,
        path=path,
        fallback_allowed=fallback_allowed,
        dimensions=dimensions,
        location=location,
        rotation=rotation,
    )
    if path is None or not path.exists():
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            "ASSET_FILE_MISSING",
            fallback_allowed=fallback_allowed,
        )

    before_names = {obj.name for obj in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=str(path))
    except Exception as exc:
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            f"ASSET_IMPORT_FAILED:{type(exc).__name__}",
            fallback_allowed=fallback_allowed,
        )

    imported = [obj for obj in bpy.data.objects if obj.name not in before_names]
    if not imported:
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            "ASSET_IMPORT_EMPTY",
            fallback_allowed=fallback_allowed,
        )

    for index, obj in enumerate(imported):
        obj.name = object_name if len(imported) == 1 else f"{object_name}_{index + 1}"
        obj.location = location
        obj.rotation_mode = rotation_mode
        obj.rotation_euler = rotation

    dimensions_checked = False
    if dimensions and len(imported) == 1:
        imported_obj = imported[0]
        imported_obj.dimensions = (
            float(dimensions.get("width") or imported_obj.dimensions.x),
            float(dimensions.get("depth") or imported_obj.dimensions.y),
            float(dimensions.get("height") or imported_obj.dimensions.z),
        )
        bpy.ops.object.select_all(action="DESELECT")
        imported_obj.select_set(True)
        bpy.context.view_layer.objects.active = imported_obj
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        imported_obj.select_set(False)
        dimensions_checked = True

    record.update(
        {
            "asset_file_exists": True,
            "asset_import_success": True,
            "asset_dimensions_checked": dimensions_checked,
            "import_mode": "imported_glb",
            "effective_generation_mode": "imported_glb",
            "imported_object_count": len(imported),
            "imported_object_names": [obj.name for obj in imported],
        }
    )
    for source_warning in _asset_source_warnings(asset_source, asset_metadata):
        _append_warning(record["warnings"], source_warning)
        _append_warning(warnings, f"{source_warning}:{asset_id}")
    asset_imports.append(record)
    return "imported_glb"


def _resolve_asset_path(asset_file: str | None) -> Path | None:
    if not asset_file:
        return None
    path = Path(asset_file)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _base_asset_import_record(
    *,
    asset_id: str,
    asset_file: str | None,
    asset_source: str | None,
    asset_metadata: dict | None,
    object_role: str,
    object_name: str,
    path: Path | None,
    fallback_allowed: bool,
    dimensions: dict | None,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> dict:
    return {
        "asset_id": asset_id,
        "asset_file": asset_file,
        "asset_source": asset_source or "vendor_expected",
        "asset_metadata": asset_metadata or {},
        "object_role": object_role,
        "object_name": object_name,
        "resolved_path": str(path) if path else None,
        "asset_file_exists": bool(path and path.exists()),
        "asset_import_success": False,
        "asset_dimensions_checked": False,
        "manifest_dimensions_m": dimensions,
        "placement_location": [round(float(value), 5) for value in location],
        "placement_rotation_rad": [round(float(value), 5) for value in rotation],
        "placement_rotation_deg": [round(math.degrees(float(value)), 5) for value in rotation],
        "import_fallback_allowed": fallback_allowed,
        "import_mode": "not_attempted",
        "effective_generation_mode": "not_attempted",
        "imported_object_count": 0,
        "imported_object_names": [],
        "warnings": [],
    }


def _record_asset_import_fallback(
    record: dict,
    asset_imports: list[dict],
    warnings: list[str],
    warning_code: str,
    *,
    fallback_allowed: bool,
) -> str:
    mode = "procedural_fallback" if fallback_allowed else "missing_file"
    record.update(
        {
            "import_mode": mode,
            "effective_generation_mode": mode,
            "asset_import_success": False,
        }
    )
    _append_warning(record["warnings"], warning_code)
    _append_warning(warnings, f"{warning_code}:{record['asset_id']}")
    if fallback_allowed:
        _append_warning(record["warnings"], "PROCEDURAL_FALLBACK_USED")
        _append_warning(warnings, f"PROCEDURAL_FALLBACK_USED:{record['asset_id']}")
    else:
        _append_warning(record["warnings"], "PROCEDURAL_FALLBACK_NOT_ALLOWED")
        _append_warning(warnings, f"PROCEDURAL_FALLBACK_NOT_ALLOWED:{record['asset_id']}")
    asset_imports.append(record)
    return mode


def _create_mounting_bracket(bpy, mount_radius: float, azimuth: float, z: float) -> None:
    steel = _material(bpy, "mount_steel", (0.42, 0.44, 0.46, 1))
    start = (
        math.sin(azimuth) * (mount_radius - 0.25),
        math.cos(azimuth) * (mount_radius - 0.25),
        z,
    )
    end = (math.sin(azimuth) * (mount_radius + 0.05), math.cos(azimuth) * (mount_radius + 0.05), z)
    _create_cylinder_between(bpy, start, end, 0.035, "mount_bracket", steel)


def _create_height_marker(bpy, scene: dict, procedural_objects: list[str]) -> None:
    height = float(scene["tower"]["height_m"])
    material = _material(bpy, "height_marker_yellow", (1.0, 0.82, 0.1, 1))
    _create_cylinder_between(bpy, (2.7, 0, 0), (2.7, 0, height), 0.025, "height_marker", material)
    procedural_objects.append("height_marker")


def _create_camera_and_light(bpy, scene: dict) -> dict:
    tower_height = float(scene["tower"]["height_m"])
    base_width = float(scene["tower"].get("characteristics", {}).get("base_width_m") or 4.0)
    target = (0.0, 0.0, tower_height * 0.52)
    distance = max(38.0, tower_height * 1.55)
    camera_location = (0.0, -distance, target[2])
    preview_width, preview_height = scene["preview"]["resolution"]
    aspect_ratio = float(preview_width) / max(float(preview_height), 1.0)

    bpy.ops.object.light_add(type="SUN", location=(8, -6, tower_height + 12))
    sun = bpy.context.object
    sun.name = "sun_key"
    sun.data.energy = 1.8
    bpy.ops.object.light_add(
        type="AREA",
        location=(distance * 0.25, -distance * 0.45, tower_height),
    )
    fill = bpy.context.object
    fill.name = "area_fill"
    fill.data.energy = 650
    fill.data.size = max(6, tower_height * 0.35)

    bpy.ops.object.camera_add(
        location=camera_location,
    )
    camera = bpy.context.object
    camera.name = "camera_technical_front_full_tower"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(tower_height * 1.5 * aspect_ratio, base_width * 6.0, 24.0)
    camera.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.camera = camera
    return {
        "camera": camera.name,
        "camera_type": "ORTHO",
        "camera_location": [round(value, 3) for value in camera_location],
        "target": [round(value, 3) for value in target],
        "ortho_scale": round(float(camera.data.ortho_scale), 3),
        "background": "light_technical_world",
        "framing": "full_tower_front",
    }


def _create_preview_backdrop(bpy, scene: dict) -> None:
    tower_height = float(scene["tower"]["height_m"])
    width = max(tower_height * 2.8, 70.0)
    height = max(tower_height * 1.9, 48.0)
    bpy.ops.mesh.primitive_plane_add(
        size=1,
        location=(0, 9.0, tower_height * 0.52),
        rotation=(math.radians(90), 0, 0),
    )
    backdrop = bpy.context.object
    backdrop.name = "technical_preview_backdrop"
    backdrop.dimensions = (width, height, 1)
    backdrop.data.materials.append(
        _emission_material(bpy, "preview_backdrop_light", (0.9, 0.93, 0.96, 1), 0.65)
    )


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
    if color[3] < 1:
        material.use_nodes = True
        material.blend_method = "BLEND"
        material.show_transparent_back = False
        principled = _first_node_by_type(material, "ShaderNodeBsdfPrincipled")
        if principled:
            principled.inputs["Base Color"].default_value = color
            principled.inputs["Alpha"].default_value = color[3]
    return material


def _emission_material(
    bpy,
    name: str,
    color: tuple[float, float, float, float],
    strength: float,
):
    material = _material(bpy, name, color)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    emission = nodes.new(type="ShaderNodeEmission")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _first_node_by_type(material, bl_idname: str):
    return next(
        (node for node in material.node_tree.nodes if node.bl_idname == bl_idname),
        None,
    )


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
        _fallback_camera_metadata(scene),
        _fallback_asset_import_records(scene),
    )


def _write_metadata(
    scene: dict,
    output_dir: Path,
    generation_mode: str,
    procedural_objects: list[str],
    warnings: list[str],
    camera_metadata: dict,
    asset_imports: list[dict] | None = None,
) -> None:
    asset_imports = asset_imports or _fallback_asset_import_records(scene)
    all_warnings = _unique_strings(
        [
            *warnings,
            *[
                f"{warning}:{record['asset_id']}"
                for record in asset_imports
                for warning in record.get("warnings", [])
            ],
        ]
    )
    (output_dir / "scene_metadata.json").write_text(
        json.dumps(
            {
                "scene_id": scene["scene_id"],
                "schema_version": scene.get("schema_version"),
                "generation_mode": generation_mode,
                "assets_used": _assets_used(scene),
                "procedural_objects_created": procedural_objects,
                "asset_imports": asset_imports,
                "asset_import_summary": _asset_import_summary(asset_imports),
                "sector_count": len(scene["sectors"]),
                "network_type": scene["network_type"],
                "tower_height_m": scene["tower"]["height_m"],
                "tower_characteristics": scene["tower"].get("characteristics", {}),
                "azimuths_deg": [sector["azimuth_deg"] for sector in scene["sectors"]],
                "antenna_heights_m": [sector["install_height_m"] for sector in scene["sectors"]],
                "mechanical_tilts_deg": [
                    sector.get("mechanical_tilt_deg", 0.0) for sector in scene["sectors"]
                ],
                "visual_elements": scene.get("visual_elements", {}),
                "accessory_assets": scene.get("accessory_assets", []),
                "preview_camera": camera_metadata,
                "warnings": all_warnings,
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
    for accessory in scene.get("accessory_assets", []):
        assets.append(accessory["asset_id"])
    return sorted(set(assets))


def _procedural_objects_from_scene(scene: dict) -> list[str]:
    objects = ["tower"]
    characteristics = scene["tower"].get("characteristics", {})
    if characteristics.get("has_platform"):
        objects.extend(
            f"tower_platform:{index + 1}"
            for index in range(int(characteristics.get("platform_count") or 1))
        )
    if characteristics.get("has_ladder"):
        objects.append("tower_ladder")
    if characteristics.get("has_lightning_rod"):
        objects.append("tower_lightning_rod")
    if characteristics.get("has_aviation_light"):
        objects.append("tower_aviation_light")
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
    if scene["visual_elements"].get("include_power_cabinet"):
        objects.append("power_cabinet")
    if scene["visual_elements"].get("include_gps_antenna"):
        objects.append("gps_antenna")
    if scene["visual_elements"].get("include_labels"):
        objects.append("labels_metadata")
    return objects


def _fallback_asset_import_records(scene: dict) -> list[dict]:
    records = [
        _fallback_asset_import_record(
            asset_id=scene["tower"]["asset_id"],
            asset_file=scene["tower"].get("asset_file"),
            asset_source=scene["tower"].get("asset_source"),
            asset_metadata=scene["tower"].get("asset_metadata"),
            object_role="tower",
            object_name=f"tower_{scene['tower']['asset_id']}",
            fallback_allowed=scene["tower"].get("import_fallback_allowed", True),
            dimensions=scene["tower"].get("dimensions_m")
            or {
                "height": scene["tower"].get("height_m"),
                "width": scene["tower"].get("characteristics", {}).get("base_width_m"),
                "depth": scene["tower"].get("characteristics", {}).get("base_width_m"),
            },
        )
    ]
    for sector in scene["sectors"]:
        records.append(
            _fallback_asset_import_record(
                asset_id=sector["antenna_asset_id"],
                asset_file=sector.get("antenna_asset_file"),
                asset_source=sector.get("antenna_asset_source"),
                asset_metadata=sector.get("antenna_asset_metadata"),
                object_role="antenna",
                object_name=f"antenna_{sector['sector_id']}_{sector['antenna_asset_id']}",
                fallback_allowed=sector.get("antenna_import_fallback_allowed", True),
                dimensions=sector.get("antenna_dimensions_m"),
            )
        )
        if sector.get("radio_asset_id"):
            records.append(
                _fallback_asset_import_record(
                    asset_id=sector["radio_asset_id"],
                    asset_file=sector.get("radio_asset_file"),
                    asset_source=sector.get("radio_asset_source"),
                    asset_metadata=sector.get("radio_asset_metadata"),
                    object_role="radio",
                    object_name=f"radio_{sector['sector_id']}_{sector['radio_asset_id']}",
                    fallback_allowed=sector.get("radio_import_fallback_allowed", True),
                    dimensions=sector.get("radio_dimensions_m"),
                )
            )
    for accessory in scene.get("accessory_assets", []):
        records.append(
            _fallback_asset_import_record(
                asset_id=accessory["asset_id"],
                asset_file=accessory.get("asset_file"),
                asset_source=accessory.get("asset_source"),
                asset_metadata=accessory.get("asset_metadata"),
                object_role=accessory.get("asset_type", "accessory"),
                object_name=f"{accessory.get('asset_type', 'accessory')}_{accessory['asset_id']}",
                fallback_allowed=accessory.get("import_fallback_allowed", True),
                dimensions=accessory.get("dimensions_m"),
            )
        )
    return records


def _fallback_asset_import_record(
    *,
    asset_id: str,
    asset_file: str | None,
    asset_source: str | None,
    asset_metadata: dict | None,
    object_role: str,
    object_name: str,
    fallback_allowed: bool,
    dimensions: dict | None,
) -> dict:
    path = _resolve_asset_path(asset_file)
    file_exists = bool(path and path.exists())
    mode = "procedural_fallback" if fallback_allowed else "missing_file"
    warnings = ["BLENDER_FALLBACK_ASSET_IMPORT_SKIPPED"]
    if not file_exists:
        warnings.append("ASSET_FILE_MISSING")
    warnings.extend(_asset_source_warnings(asset_source, asset_metadata))
    if not fallback_allowed:
        warnings.append("PROCEDURAL_FALLBACK_NOT_ALLOWED")
    return {
        "asset_id": asset_id,
        "asset_file": asset_file,
        "asset_source": asset_source or "vendor_expected",
        "asset_metadata": asset_metadata or {},
        "object_role": object_role,
        "object_name": object_name,
        "resolved_path": str(path) if path else None,
        "asset_file_exists": file_exists,
        "asset_import_success": False,
        "asset_dimensions_checked": False,
        "manifest_dimensions_m": dimensions,
        "import_fallback_allowed": fallback_allowed,
        "import_mode": mode,
        "effective_generation_mode": mode,
        "imported_object_count": 0,
        "imported_object_names": [],
        "warnings": warnings,
    }


def _asset_import_summary(asset_imports: list[dict]) -> dict:
    modes: dict[str, int] = {}
    for record in asset_imports:
        mode = str(record.get("import_mode") or "unknown")
        modes[mode] = modes.get(mode, 0) + 1
    return {
        "asset_count": len(asset_imports),
        "imported_glb_count": modes.get("imported_glb", 0),
        "procedural_fallback_count": modes.get("procedural_fallback", 0),
        "missing_file_count": modes.get("missing_file", 0),
        "import_success_count": sum(
            1 for record in asset_imports if record.get("asset_import_success") is True
        ),
        "asset_file_exists_count": sum(
            1 for record in asset_imports if record.get("asset_file_exists") is True
        ),
        "modes": modes,
    }


def _asset_source_warnings(asset_source: str | None, asset_metadata: dict | None) -> list[str]:
    warnings = []
    if asset_source == "internal_test_minimal":
        warnings.append("INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE")
    if asset_source == "internal_cleaned":
        warnings.append("INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE")
    if asset_source == "cc_by":
        warnings.append("CC_BY_ASSET_NOT_VENDOR_GRADE")
    if isinstance(asset_metadata, dict) and asset_metadata.get("attribution_required"):
        warnings.append("ATTRIBUTION_REQUIRED")
    return warnings


def _append_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _fallback_camera_metadata(scene: dict) -> dict:
    tower_height = float(scene["tower"]["height_m"])
    return {
        "camera": "fallback_preview",
        "camera_type": "not_rendered",
        "target": [0.0, 0.0, round(tower_height * 0.52, 3)],
        "ortho_scale": round(max(tower_height * 1.28, 18.0), 3),
        "background": "fallback_png",
    }


def _minimal_png(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            gradient = 205 - int(42 * y / max(height - 1, 1)) + int(18 * x / max(width - 1, 1))
            row.extend((gradient, gradient, min(255, gradient + 8)))
        rows.append(bytes(row))
    image = zlib.compress(b"".join(rows), level=9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    raise SystemExit(main())
