"""Parametric telecom geometry builders for Blender.

This module is executed inside Blender (it imports bpy). It provides
constructors for towers, sector components, and accessories driven by
SceneSpec parameters rather than fixed GLB assets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # type: ignore[import-not-found]


def _material(
    bpy,
    name: str,
    color: tuple[float, float, float, float],
    *,
    roughness: float = 0.55,
    metallic: float = 0.0,
) -> object:
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = color
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = roughness
        principled.inputs["Metallic"].default_value = metallic
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


@dataclass(frozen=True)
class SegmentGeometry:
    midpoint: tuple[float, float, float]
    direction: tuple[float, float, float]
    length: float


def segment_geometry(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> SegmentGeometry | None:
    """Return the canonical geometry of a segment in Blender's Z-up frame."""

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return None
    return SegmentGeometry(
        midpoint=(
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2,
            (start[2] + end[2]) / 2,
        ),
        direction=(dx / length, dy / length, dz / length),
        length=length,
    )


def create_cylinder_between(
    bpy,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    name: str,
    material: object,
    *,
    vertices: int = 32,
) -> object:
    """Create a cylinder whose local +Z axis joins ``start`` and ``end`` exactly."""

    geometry = segment_geometry(start, end)
    if geometry is None:
        return None
    from mathutils import Vector  # type: ignore[import-not-found]

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=geometry.length,
        location=geometry.midpoint,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector(geometry.direction).to_track_quat("Z", "Y")
    obj["segment_start_m"] = list(start)
    obj["segment_end_m"] = list(end)
    obj["segment_length_m"] = geometry.length
    obj.data.materials.append(material)
    # Do not leak an active segment into later context-sensitive bpy operators.
    obj.select_set(False)
    if bpy.context.view_layer.objects.active is obj:
        bpy.context.view_layer.objects.active = None
    return obj


def measure_segment_endpoint_errors(obj) -> tuple[float, float] | None:
    """Measure endpoint errors from transformed mesh vertices, not object metadata alone."""

    start_value = obj.get("segment_start_m")
    end_value = obj.get("segment_end_m")
    try:
        start_coordinates = tuple(float(value) for value in start_value)
        end_coordinates = tuple(float(value) for value in end_value)
    except (TypeError, ValueError):
        return None
    if len(start_coordinates) != 3 or len(end_coordinates) != 3 or not getattr(obj, "data", None):
        return None
    geometry = segment_geometry(start_coordinates, end_coordinates)
    vertices = getattr(obj.data, "vertices", ())
    if geometry is None or not vertices:
        return None

    local_z_values = [float(vertex.co.z) for vertex in vertices]
    minimum = min(local_z_values)
    maximum = max(local_z_values)
    local_tolerance = max(1e-7, geometry.length * 1e-8)
    start_ring = [
        vertex.co for vertex in vertices if abs(float(vertex.co.z) - minimum) <= local_tolerance
    ]
    end_ring = [
        vertex.co for vertex in vertices if abs(float(vertex.co.z) - maximum) <= local_tolerance
    ]
    if not start_ring or not end_ring:
        return None

    local_start = tuple(
        sum(getattr(vertex, axis) for vertex in start_ring) / len(start_ring)
        for axis in ("x", "y", "z")
    )
    local_end = tuple(
        sum(getattr(vertex, axis) for vertex in end_ring) / len(end_ring)
        for axis in ("x", "y", "z")
    )
    measured_start_vector = obj.matrix_world @ vertices[0].co.__class__(local_start)
    measured_end_vector = obj.matrix_world @ vertices[0].co.__class__(local_end)
    measured_start = tuple(getattr(measured_start_vector, axis) for axis in ("x", "y", "z"))
    measured_end = tuple(getattr(measured_end_vector, axis) for axis in ("x", "y", "z"))
    return (
        math.dist(measured_start, start_coordinates),
        math.dist(measured_end, end_coordinates),
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


def sector_forward_vector(
    azimuth_deg: float,
    mechanical_tilt_deg: float,
) -> tuple[float, float, float]:
    """Return the world direction of an asset whose local front axis is +Y."""

    azimuth = math.radians(float(azimuth_deg))
    tilt = math.radians(float(mechanical_tilt_deg))
    horizontal = math.cos(tilt)
    return (
        math.sin(azimuth) * horizontal,
        math.cos(azimuth) * horizontal,
        -math.sin(tilt),
    )


def apply_sector_pose(
    obj,
    *,
    azimuth_deg: float,
    mechanical_tilt_deg: float,
    front_axis: str = "+Y",
) -> None:
    """Apply yaw around world Z followed by downtilt around the asset local X axis."""

    from mathutils import Matrix, Vector  # type: ignore[import-not-found]

    yaw = Matrix.Rotation(-math.radians(float(azimuth_deg)), 4, "Z")
    local_downtilt = Matrix.Rotation(-math.radians(float(mechanical_tilt_deg)), 4, "X")
    source_front = {
        "+X": Vector((1.0, 0.0, 0.0)),
        "-X": Vector((-1.0, 0.0, 0.0)),
        "+Y": Vector((0.0, 1.0, 0.0)),
        "-Y": Vector((0.0, -1.0, 0.0)),
    }.get(str(front_axis).upper())
    if source_front is None:
        raise ValueError(f"Unsupported horizontal asset front_axis: {front_axis!r}")
    front_correction = (
        source_front.rotation_difference(Vector((0.0, 1.0, 0.0))).to_matrix().to_4x4()
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (yaw @ local_downtilt @ front_correction).to_quaternion()


def tower_material_profile(
    material_name: str,
) -> tuple[tuple[float, float, float, float], float, float]:
    profiles = {
        "galvanized_steel": ((0.48, 0.53, 0.58, 1.0), 0.3, 0.72),
        "painted_steel": ((0.12, 0.24, 0.38, 1.0), 0.38, 0.52),
        "concrete": ((0.56, 0.57, 0.55, 1.0), 0.82, 0.0),
        "unknown": ((0.45, 0.47, 0.49, 1.0), 0.58, 0.2),
    }
    return profiles.get(material_name, profiles["unknown"])


def tower_envelope_radius_at_height(
    *,
    height_m: float,
    tower_height_m: float,
    base_width_m: float,
    top_width_m: float | None,
    structure: str,
    leg_count: int,
    azimuth_rad: float,
) -> float:
    """Return the tower envelope in a horizontal direction at a given height."""

    top_ratio = {
        "lattice": 0.25,
        "monopole": 0.35,
        "rooftop_mast": 0.4,
        "small_cell_pole": 0.6,
    }.get(structure, 0.5)
    top_width = float(top_width_m or (base_width_m * top_ratio))
    ratio = min(max(float(height_m) / max(float(tower_height_m), 1e-6), 0.0), 1.0)
    width = float(base_width_m) + ((top_width - float(base_width_m)) * ratio)
    half_width = max(width * 0.5, 0.02)
    if structure == "lattice" and leg_count != 3:
        direction = max(abs(math.sin(azimuth_rad)), abs(math.cos(azimuth_rad)), 1e-6)
        return half_width / direction
    return half_width


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
    color, roughness, metallic = tower_material_profile(material_name)
    steel = _material(
        bpy,
        f"tower_{material_name}",
        color,
        roughness=roughness,
        metallic=metallic,
    )
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
                leg = create_cylinder_between(bpy, c0, c1, 0.045, "tower_leg", steel)
                if leg is not None:
                    created.append(leg)
            for side in range(len(corners0)):
                brace = create_cylinder_between(
                    bpy,
                    corners0[side],
                    corners1[(side + 1) % len(corners1)],
                    0.025,
                    "tower_brace",
                    steel,
                )
                if brace is not None:
                    created.append(brace)
                brace = create_cylinder_between(
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
        ring_mat = _material(
            bpy,
            f"tower_{material_name}_ring",
            color,
            roughness=roughness,
            metallic=metallic,
        )
        ring_count = max(1, int(height // 5))
        for i in range(1, ring_count + 1):
            z = i * 5.0
            if z >= height:
                continue
            ring_radius = tower_envelope_radius_at_height(
                height_m=z,
                tower_height_m=height,
                base_width_m=base_width,
                top_width_m=top_width,
                structure=structure,
                leg_count=leg_count,
                azimuth_rad=0.0,
            )
            ring = _create_cylinder(
                bpy,
                name=f"tower_{asset_id}_ring_{i}",
                radius_bottom=ring_radius + 0.04,
                radius_top=ring_radius + 0.04,
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


def build_parametric_microwave_dish(
    bpy,
    *,
    name: str,
    width: float,
    depth: float,
    height: float,
    location: tuple[float, float, float],
) -> object:
    """Generate a parabolic dish whose local front axis is +Y."""

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = location

    radial_segments = 8
    angular_segments = 32
    radius_x = max(float(width) / 2, 0.05)
    radius_z = max(float(height) / 2, 0.05)
    bowl_depth = min(max(float(depth), 0.04), max(radius_x, radius_z) * 0.8)
    vertices: list[tuple[float, float, float]] = [(0.0, -bowl_depth, 0.0)]
    faces: list[tuple[int, ...]] = []
    for ring in range(1, radial_segments + 1):
        ratio = ring / radial_segments
        y = -bowl_depth * (1.0 - ratio * ratio)
        for segment in range(angular_segments):
            angle = 2 * math.pi * segment / angular_segments
            vertices.append(
                (
                    radius_x * ratio * math.cos(angle),
                    y,
                    radius_z * ratio * math.sin(angle),
                )
            )
    for segment in range(angular_segments):
        faces.append((0, 1 + ((segment + 1) % angular_segments), 1 + segment))
    for ring in range(1, radial_segments):
        previous_start = 1 + (ring - 1) * angular_segments
        current_start = 1 + ring * angular_segments
        for segment in range(angular_segments):
            next_segment = (segment + 1) % angular_segments
            faces.append(
                (
                    previous_start + next_segment,
                    current_start + next_segment,
                    current_start + segment,
                    previous_start + segment,
                )
            )

    mesh = bpy.data.meshes.new(f"{name}_surface_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    surface = bpy.data.objects.new(f"{name}_surface", mesh)
    bpy.context.collection.objects.link(surface)
    surface.parent = root
    surface.data.materials.append(
        _material(bpy, "microwave_dish_white", (0.78, 0.81, 0.84, 1.0), roughness=0.42)
    )
    solidify = surface.modifiers.new(name="dish_thickness", type="SOLIDIFY")
    solidify.thickness = 0.012

    feed_distance = max(bowl_depth * 1.7, radius_x * 0.35)
    feed = _create_cylinder(
        bpy,
        name=f"{name}_feed",
        radius_bottom=max(radius_x * 0.045, 0.015),
        radius_top=max(radius_x * 0.035, 0.012),
        height=max(radius_x * 0.18, 0.08),
        location=(0.0, feed_distance, 0.0),
        vertices=16,
    )
    feed.rotation_euler[0] = math.radians(90)
    feed.parent = root
    feed.data.materials.append(
        _material(bpy, "microwave_feed_dark", (0.12, 0.14, 0.16, 1.0), roughness=0.36)
    )
    return root


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
    beam = create_cylinder_between(
        bpy, origin, end, radius, name, _material(bpy, "beam_blue", (0.25, 0.55, 0.95, 0.35))
    )
    return beam


def build_parametric_accessory_cabinet(
    bpy,
    *,
    name: str,
    location: tuple[float, float, float],
    width: float = 1.0,
    depth: float = 0.45,
    height: float = 1.6,
) -> object:
    """Generate a cabinet from a base-center-ground datum."""
    box = _create_box(
        bpy,
        name,
        width,
        depth,
        height,
        (location[0], location[1], location[2] + height / 2),
    )
    box.data.materials.append(_material(bpy, "cabinet_green", (0.25, 0.42, 0.28, 1)))
    return box


def build_parametric_accessory_gps(
    bpy,
    *,
    name: str,
    location: tuple[float, float, float],
) -> object:
    """Generate a simple GPS radome on a short pole."""
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = location
    pole = _create_cylinder(
        bpy,
        f"{name}_pole",
        0.02,
        0.02,
        0.6,
        (0.0, 0.0, 0.3),
        vertices=8,
    )
    pole.data.materials.append(_material(bpy, "gps_pole", (0.42, 0.44, 0.46, 1)))
    pole.parent = root
    radome = _create_cylinder(
        bpy,
        f"{name}_radome",
        0.16,
        0.16,
        0.22,
        (0.0, 0.0, 0.7),
        vertices=16,
    )
    radome.data.materials.append(_material(bpy, "gps_white", (0.92, 0.92, 0.94, 1)))
    radome.parent = root
    return root
