"""Parametric telecom geometry builders for Blender.

This module is executed inside Blender (it imports bpy). It provides
constructors for towers, sector components, and accessories driven by
SceneSpec parameters rather than fixed GLB assets.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # type: ignore[import-not-found]


def _material(bpy, name: str, color: tuple[float, float, float, float]) -> object:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
        principled.inputs["Metallic"].default_value = 0.6
    return mat


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
        # Blender 5.x uniform cylinder; use cone for tapered forms.
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


def _create_cylinder_between(
    bpy,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    name: str,
    material: object,
) -> object:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return None
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2)
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (
        math.atan2(math.sqrt(dx * dx + dy * dy), dz),
        0,
        math.atan2(dy, dx),
    )
    obj.data.materials.append(material)
    return obj


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


def build_parametric_tower(
    bpy,
    *,
    asset_id: str,
    height: float,
    structure: str,
    base_width: float,
    top_width: float | None,
    leg_count: int,
    material_name: str = "galvanized_steel",
) -> list[object]:
    """Generate a tower mesh from engineering parameters.

    Returns the list of created objects.
    """
    steel = _material(bpy, material_name, (0.48, 0.51, 0.54, 1))
    created: list[object] = []

    if structure == "lattice":
        top = top_width if top_width is not None else base_width * 0.25
        levels = max(4, int(height / 4))
        for index in range(levels):
            z0 = height * index / levels
            z1 = height * (index + 1) / levels
            width0 = base_width - (base_width - top) * index / levels
            width1 = base_width - (base_width - top) * (index + 1) / levels
            corners0 = _tower_corners(width0, z0, leg_count)
            corners1 = _tower_corners(width1, z1, leg_count)
            for c0, c1 in zip(corners0, corners1, strict=True):
                leg = _create_cylinder_between(bpy, c0, c1, 0.045, "tower_leg", steel)
                if leg is not None:
                    created.append(leg)
            for side in range(len(corners0)):
                brace = _create_cylinder_between(
                    bpy,
                    corners0[side],
                    corners1[(side + 1) % len(corners1)],
                    0.025,
                    "tower_brace",
                    steel,
                )
                if brace is not None:
                    created.append(brace)
                brace = _create_cylinder_between(
                    bpy,
                    corners0[(side + 1) % len(corners0)],
                    corners1[side],
                    0.025,
                    "tower_brace",
                    steel,
                )
                if brace is not None:
                    created.append(brace)

    elif structure == "monopole":
        base_radius = base_width / 2
        top_radius = (top_width if top_width is not None else base_width * 0.35) / 2
        pole = _create_cylinder(
            bpy,
            name=f"tower_{asset_id}_pole",
            radius_bottom=base_radius,
            radius_top=top_radius,
            height=height,
            location=(0.0, 0.0, height / 2),
            vertices=32,
        )
        pole.data.materials.append(steel)
        created.append(pole)
        # Reinforcing rings every 5 m
        ring_mat = _material(bpy, "monopole_ring", (0.40, 0.43, 0.46, 1))
        ring_count = max(1, int(height // 5))
        for i in range(1, ring_count + 1):
            z = i * 5.0
            if z >= height:
                continue
            ring = _create_cylinder(
                bpy,
                name=f"tower_{asset_id}_ring_{i}",
                radius_bottom=base_radius + 0.04,
                radius_top=base_radius + 0.04,
                height=0.15,
                location=(0.0, 0.0, z),
                vertices=32,
            )
            ring.data.materials.append(ring_mat)
            created.append(ring)

    elif structure == "rooftop_mast":
        base_radius = base_width / 2
        top_radius = (top_width if top_width is not None else base_width * 0.4) / 2
        mast = _create_cylinder(
            bpy,
            name=f"tower_{asset_id}_mast",
            radius_bottom=base_radius,
            radius_top=top_radius,
            height=height,
            location=(0.0, 0.0, height / 2),
            vertices=24,
        )
        mast.data.materials.append(steel)
        created.append(mast)
        flange = _create_cylinder(
            bpy,
            name=f"tower_{asset_id}_flange",
            radius_bottom=base_radius + 0.15,
            radius_top=base_radius + 0.15,
            height=0.25,
            location=(0.0, 0.0, 0.125),
            vertices=24,
        )
        flange.data.materials.append(_material(bpy, "rooftop_flange", (0.38, 0.40, 0.42, 1)))
        created.append(flange)

    else:  # small_cell_pole and fallback
        base_radius = base_width / 2
        top_radius = (top_width if top_width is not None else base_width * 0.6) / 2
        pole = _create_cylinder(
            bpy,
            name=f"tower_{asset_id}_pole",
            radius_bottom=base_radius,
            radius_top=top_radius,
            height=height,
            location=(0.0, 0.0, height / 2),
            vertices=16,
        )
        pole.data.materials.append(steel)
        created.append(pole)

    return created


def build_parametric_panel_antenna(
    bpy,
    *,
    name: str,
    width: float,
    depth: float,
    height: float,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> object:
    """Generate a simple rectangular panel antenna primitive."""
    box = _create_box(bpy, name, width, depth, height, location)
    box.rotation_mode = "ZXY"
    box.rotation_euler = rotation
    box.data.materials.append(_material(bpy, "antenna_white", (0.88, 0.88, 0.90, 1)))
    return box


def build_parametric_radio(
    bpy,
    *,
    name: str,
    width: float,
    depth: float,
    height: float,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> object:
    """Generate a simple RRU box primitive."""
    box = _create_box(bpy, name, width, depth, height, location)
    box.rotation_mode = "XYZ"
    box.rotation_euler = rotation
    box.data.materials.append(_material(bpy, "radio_gray", (0.32, 0.34, 0.36, 1)))
    return box


def build_parametric_cable(
    bpy,
    *,
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    sag: float = 0.5,
) -> object:
    """Generate a curved cable between two points."""
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2 - sag)
    curve_data = bpy.data.curves.new(name=name, type="CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("NURBS")
    spline.points.add(2)
    for point, coord in zip(spline.points, [start, mid, end], strict=True):
        point.co = (*coord, 1)
    spline.resolution_u = 8
    curve_data.bevel_depth = 0.02
    curve_data.bevel_resolution = 2
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(_material(bpy, "cable_black", (0.08, 0.08, 0.09, 1)))
    return obj


def build_parametric_beam(
    bpy,
    *,
    name: str,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    length: float,
    radius: float = 0.08,
) -> object:
    """Generate a sector beam visualization."""
    end = (
        origin[0] + direction[0] * length,
        origin[1] + direction[1] * length,
        origin[2] + direction[2] * length,
    )
    beam = _create_cylinder_between(
        bpy, origin, end, radius, name, _material(bpy, "beam_blue", (0.25, 0.55, 0.95, 0.35))
    )
    return beam


def build_parametric_accessory_cabinet(
    bpy,
    *,
    name: str,
    location: tuple[float, float, float],
) -> object:
    """Generate a simple outdoor cabinet primitive."""
    box = _create_box(bpy, name, 1.0, 0.45, 1.6, location)
    box.data.materials.append(_material(bpy, "cabinet_green", (0.25, 0.42, 0.28, 1)))
    return box


def build_parametric_accessory_gps(
    bpy,
    *,
    name: str,
    location: tuple[float, float, float],
) -> object:
    """Generate a simple GPS radome on a short pole."""
    pole = _create_cylinder(
        bpy,
        f"{name}_pole",
        0.02,
        0.02,
        0.6,
        (location[0], location[1], location[2] + 0.3),
        vertices=8,
    )
    pole.data.materials.append(_material(bpy, "gps_pole", (0.42, 0.44, 0.46, 1)))
    radome = _create_cylinder(
        bpy, name, 0.16, 0.16, 0.22, (location[0], location[1], location[2] + 0.7), vertices=16
    )
    radome.data.materials.append(_material(bpy, "gps_white", (0.92, 0.92, 0.94, 1)))
    return radome
