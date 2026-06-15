"""Generate internal tower GLB assets using Blender.

Usage:
    blender -b --python tools/generate_internal_tower_assets.py

Outputs:
    assets/towers/tower_monopole_30m.glb
    assets/towers/tower_rooftop_12m.glb
    assets/towers/tower_small_cell_10m.glb

These are project-authored procedural assets intended to replace runtime
procedural fallbacks with stable, importable GLB files.
"""

from __future__ import annotations

from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "towers"


def main() -> int:
    try:
        import bpy  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("This script must be run inside Blender: " + str(exc)) from exc

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _generate_monopole(bpy, OUTPUT_DIR / "tower_monopole_30m.glb")
    _generate_rooftop_mast(bpy, OUTPUT_DIR / "tower_rooftop_12m.glb")
    _generate_small_cell_pole(bpy, OUTPUT_DIR / "tower_small_cell_10m.glb")

    print("Generated internal tower assets in", OUTPUT_DIR)
    return 0


def _reset_scene(bpy) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for material in bpy.data.materials:
        bpy.data.materials.remove(material)


def _material(bpy, name: str, color: tuple[float, float, float, float]) -> object:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
        principled.inputs["Metallic"].default_value = 0.6
    return mat


def _center_origin_to_geometry(bpy, obj) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.select_set(False)


def _export_glb(bpy, path: Path, objects: list) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
    )
    bpy.ops.object.select_all(action="DESELECT")


def _create_cylinder(
    bpy,
    name: str,
    radius_bottom: float,
    radius_top: float,
    height: float,
    location: tuple[float, float, float],
    vertices: int = 32,
) -> object:
    if abs(radius_bottom - radius_top) < 1e-6:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=vertices,
            radius=radius_bottom,
            depth=height,
            location=location,
        )
    else:
        # Blender 5.x cylinder is uniform; use cone for tapered forms.
        bpy.ops.mesh.primitive_cone_add(
            vertices=vertices,
            radius1=radius_bottom,
            radius2=radius_top,
            depth=height,
            location=location,
        )
    obj = bpy.context.object
    obj.name = name
    return obj


def _create_box(
    bpy,
    name: str,
    width: float,
    depth: float,
    height: float,
    location: tuple[float, float, float],
) -> object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (width, depth, height)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def _generate_monopole(bpy, path: Path) -> None:
    _reset_scene(bpy)
    height = 30.0
    base_radius = 0.6
    top_radius = 0.25
    steel = _material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1))

    pole = _create_cylinder(
        bpy,
        name="tower_monopole_pole",
        radius_bottom=base_radius,
        radius_top=top_radius,
        height=height,
        location=(0.0, 0.0, height / 2),
        vertices=32,
    )
    pole.data.materials.append(steel)

    # Reinforcing rings every 5 m
    ring_material = _material(bpy, "monopole_ring", (0.40, 0.43, 0.46, 1))
    for z in [5.0, 10.0, 15.0, 20.0, 25.0]:
        ring = _create_cylinder(
            bpy,
            name=f"monopole_ring_{int(z)}",
            radius_bottom=base_radius + 0.04,
            radius_top=base_radius + 0.04,
            height=0.15,
            location=(0.0, 0.0, z),
            vertices=32,
        )
        ring.data.materials.append(ring_material)

    _center_origin_to_geometry(bpy, pole)
    _export_glb(bpy, path, bpy.data.objects)
    print("Exported", path)


def _generate_rooftop_mast(bpy, path: Path) -> None:
    _reset_scene(bpy)
    height = 12.0
    base_radius = 0.5
    top_radius = 0.2
    steel = _material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1))

    mast = _create_cylinder(
        bpy,
        name="tower_rooftop_mast",
        radius_bottom=base_radius,
        radius_top=top_radius,
        height=height,
        location=(0.0, 0.0, height / 2),
        vertices=24,
    )
    mast.data.materials.append(steel)

    # Mounting flange at the base
    flange = _create_cylinder(
        bpy,
        name="rooftop_flange",
        radius_bottom=base_radius + 0.15,
        radius_top=base_radius + 0.15,
        height=0.25,
        location=(0.0, 0.0, 0.125),
        vertices=24,
    )
    flange.data.materials.append(_material(bpy, "rooftop_flange", (0.38, 0.40, 0.42, 1)))

    _center_origin_to_geometry(bpy, mast)
    _export_glb(bpy, path, bpy.data.objects)
    print("Exported", path)


def _generate_small_cell_pole(bpy, path: Path) -> None:
    _reset_scene(bpy)
    height = 10.0
    base_radius = 0.15
    top_radius = 0.10
    steel = _material(bpy, "galvanized_steel", (0.48, 0.51, 0.54, 1))

    pole = _create_cylinder(
        bpy,
        name="tower_small_cell_pole",
        radius_bottom=base_radius,
        radius_top=top_radius,
        height=height,
        location=(0.0, 0.0, height / 2),
        vertices=16,
    )
    pole.data.materials.append(steel)

    # Mounting arm near the top
    arm_height = 0.12
    arm_length = 0.9
    arm = _create_box(
        bpy,
        name="small_cell_mount_arm",
        width=arm_length,
        depth=arm_height,
        height=arm_height,
        location=(arm_length / 2, 0.0, height - 0.6),
    )
    arm.data.materials.append(steel)

    # Small equipment box on the pole
    box = _create_box(
        bpy,
        name="small_cell_equipment_box",
        width=0.35,
        depth=0.25,
        height=0.55,
        location=(0.0, base_radius + 0.13, 2.0),
    )
    box.data.materials.append(_material(bpy, "small_cell_box", (0.30, 0.32, 0.34, 1)))

    _center_origin_to_geometry(bpy, pole)
    _export_glb(bpy, path, bpy.data.objects)
    print("Exported", path)


if __name__ == "__main__":
    raise SystemExit(main())
