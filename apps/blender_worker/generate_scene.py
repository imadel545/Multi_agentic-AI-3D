"""Controlled Blender worker for SceneSpec-based telecom scene generation.

Usage:
    blender -b --python apps/blender_worker/generate_scene.py -- scene_spec.json output_dir

The script is intentionally SceneSpec-driven. It does not execute LLM-generated code.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

# Make project root importable when this script is executed inside Blender.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apps.blender_worker import parametric_builder  # noqa: E402


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
    if scene["visual_elements"].get("include_height_markers", False):
        _create_height_marker(bpy, scene, procedural_objects)
    _create_sectors(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    if scene["visual_elements"].get("include_power_cabinet", False):
        _create_power_cabinet(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    if scene["visual_elements"].get("include_gps_antenna", False):
        _create_gps_antenna(bpy, scene, procedural_objects, asset_imports, asset_warnings)
    if scene["visual_elements"].get("include_labels", False):
        _create_labels(bpy, scene, procedural_objects)
    camera_metadata = _create_camera_and_light(bpy, scene)
    segment_connectivity = _validate_parametric_segment_connectivity(bpy)

    glb_path = output_dir / "design.glb"
    preview_path = output_dir / "preview.png"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", export_extras=True)
    bounding_box_m = _compute_scene_bounding_box(bpy)
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
        bounding_box_m,
        segment_connectivity,
        _blender_runtime_metadata(bpy),
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
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if engine in engines:
            bpy.context.scene.render.engine = engine
            break
    width, height = scene["preview"]["resolution"]
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.025, 0.038, 0.052)
    bpy.context.scene.world.use_nodes = True
    world_background = bpy.context.scene.world.node_tree.nodes.get("Background")
    if world_background is not None:
        world_background.inputs["Color"].default_value = (0.025, 0.038, 0.052, 1)
        world_background.inputs["Strength"].default_value = 0.28
    bpy.context.scene.render.film_transparent = False
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.resolution_percentage = 100
    if bpy.context.scene.render.engine == "BLENDER_WORKBENCH":
        shading = bpy.context.scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "COLOR"
        shading.background_color = (0.025, 0.038, 0.052)
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
    bpy.context.scene.view_settings.exposure = 0.45
    bpy.context.scene.view_settings.gamma = 1


def _create_ground_plane(bpy, scene: dict) -> None:
    height = float(scene["tower"]["height_m"])
    size = max(14.0, height * 0.6)
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.02))
    ground = bpy.context.object
    ground.name = "technical_ground_plane"
    ground.data.materials.append(_material(bpy, "matte_ground", (0.08, 0.12, 0.15, 1)))


def _create_tower(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    height = float(scene["tower"]["height_m"])
    characteristics = scene["tower"].get("characteristics", {})
    base_width = float(characteristics.get("base_width_m") or 4.0)
    strategy = scene["tower"].get("generation_strategy", "parametric_generated")
    material_name = str(characteristics.get("material") or "galvanized_steel")
    semantic_root = f"tower_{scene['tower']['asset_id']}"

    if strategy == "parametric_generated":
        structure = characteristics.get("structure", "lattice")
        created = parametric_builder.build_parametric_tower(
            bpy=bpy,
            asset_id=scene["tower"]["asset_id"],
            height=height,
            structure=structure,
            base_width=base_width,
            top_width=characteristics.get("top_width_m"),
            leg_count=int(characteristics.get("leg_count") or 4),
            material_name=material_name,
        )
        _create_semantic_group(
            bpy,
            semantic_root,
            created,
            role="tower",
            properties={
                "tower_material": material_name,
                **_classification_properties(
                    "parametric_generated",
                    str(scene["tower"].get("geometry_source") or "parametric_generated"),
                ),
            },
        )
        procedural_objects.append(f"tower:{structure}_parametric")
        _record_asset_generation(
            asset_imports,
            asset_warnings,
            asset_id=scene["tower"]["asset_id"],
            asset_file=scene["tower"].get("asset_file"),
            asset_source=scene["tower"].get("asset_source"),
            asset_metadata=scene["tower"].get("asset_metadata"),
            object_role="tower",
            object_name=semantic_root,
            dimensions=scene["tower"].get("dimensions_m"),
            location=(0.0, 0.0, height / 2),
            rotation=(0.0, 0.0, 0.0),
            generation_strategy=strategy,
            generated_object_names=[semantic_root, *[obj.name for obj in created]],
        )
    else:
        tower_location = _asset_placement_location(
            (0.0, 0.0, height / 2),
            scene["tower"].get("asset_metadata"),
            "tower",
        )
        tower_mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=scene["tower"]["asset_id"],
            asset_file=scene["tower"].get("asset_file"),
            asset_source=scene["tower"].get("asset_source"),
            asset_metadata=scene["tower"].get("asset_metadata"),
            fallback_allowed=scene["tower"].get("import_fallback_allowed", True),
            object_role="tower",
            object_name=semantic_root,
            location=tower_location,
            rotation=(0.0, 0.0, 0.0),
            dimensions=scene["tower"].get("dimensions_m")
            or {
                "width": base_width,
                "depth": base_width,
                "height": height,
            },
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={"tower_material": material_name},
        )
        if not _is_imported_mode(tower_mode) and scene["tower"].get(
            "import_fallback_allowed", True
        ):
            structure = characteristics.get("structure", "lattice")
            created = parametric_builder.build_parametric_tower(
                bpy=bpy,
                asset_id=scene["tower"]["asset_id"],
                height=height,
                structure=structure,
                base_width=base_width,
                top_width=characteristics.get("top_width_m"),
                leg_count=int(characteristics.get("leg_count") or 4),
                material_name=material_name,
            )
            _create_semantic_group(
                bpy,
                semantic_root,
                created,
                role="tower",
                properties={
                    "tower_material": material_name,
                    **_classification_properties("procedural_fallback"),
                },
            )
            procedural_objects.append(f"tower:{structure}_procedural_fallback")
            _mark_fallback_generated(
                asset_imports,
                object_role="tower",
                object_name=semantic_root,
                generated_object_names=[semantic_root, *[obj.name for obj in created]],
            )
    if characteristics.get("foundation_type") == "unknown":
        asset_warnings.append("FOUNDATION_UNKNOWN_NO_GEOMETRY_GENERATED")
    _create_foundation(bpy, characteristics, procedural_objects)
    _create_tower_accessories(bpy, height, characteristics, procedural_objects)


def _tower_radius_at_height(scene: dict, height_m: float, azimuth_rad: float = 0.0) -> float:
    characteristics = scene["tower"].get("characteristics", {})
    base_width = float(characteristics.get("base_width_m") or 4.0)
    return parametric_builder.tower_envelope_radius_at_height(
        height_m=height_m,
        tower_height_m=float(scene["tower"]["height_m"]),
        base_width_m=base_width,
        top_width_m=characteristics.get("top_width_m"),
        structure=str(characteristics.get("structure") or "lattice"),
        leg_count=int(characteristics.get("leg_count") or 4),
        azimuth_rad=azimuth_rad,
    )


def _create_semantic_group(
    bpy,
    name: str,
    objects: list,
    *,
    role: str,
    sector_id: str | None = None,
    properties: dict | None = None,
):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    # Flush all pending object transforms before preserving world matrices while parenting.
    # Without this, Blender can expose a stale identity matrix for the last generated member.
    bpy.context.view_layer.update()
    for obj in objects:
        world_matrix = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world_matrix
    _set_semantic_tree(
        root,
        role=role,
        semantic_root=name,
        sector_id=sector_id,
        properties=properties,
    )
    return root


def _set_semantic_tree(
    root,
    *,
    role: str,
    semantic_root: str,
    sector_id: str | None = None,
    properties: dict | None = None,
) -> None:
    _set_semantic_properties(
        root,
        role=role,
        semantic_root=semantic_root,
        sector_id=sector_id,
        properties=properties,
    )
    for child in root.children_recursive:
        _set_semantic_properties(
            child,
            role=role,
            semantic_root=semantic_root,
            sector_id=sector_id,
            properties=properties,
        )


def _set_semantic_properties(
    obj,
    *,
    role: str,
    semantic_root: str,
    sector_id: str | None = None,
    properties: dict | None = None,
) -> None:
    obj["role"] = role
    obj["semantic_root"] = semantic_root
    if sector_id is not None:
        obj["sector_id"] = sector_id
    for key, value in (properties or {}).items():
        if value is not None:
            obj[key] = value


def _classification_properties(
    generation_strategy: str,
    geometry_source: str | None = None,
) -> dict[str, str]:
    """Return canonical exported provenance for mesh-level QA.

    Blender's asset import report uses ``imported_glb`` for a successful
    operation, while the public QA contract calls the resulting geometry
    ``imported_glb_exact``. Normalize that internal operation name before it is
    written to glTF extras so downstream QA never has to infer provenance from
    object names.
    """

    aliases = {
        "imported_glb": "imported_glb_exact",
        "imported_glb_exact": "imported_glb_exact",
        "stretched_imported_asset": "stretched_imported_glb",
        "stretched_imported_glb": "stretched_imported_glb",
        "parametric_generated": "parametric_generated",
        "internal_project_generated": "internal_project_generated",
        "procedural_fallback": "procedural_fallback",
        "degraded": "degraded",
        "unknown": "unknown",
    }
    normalized_strategy = aliases.get(str(generation_strategy), "unknown")
    source_value = str(geometry_source or "unknown")
    if source_value == "unknown":
        source_value = str(generation_strategy)
    normalized_source = aliases.get(source_value, "unknown")
    return {
        "generation_strategy": normalized_strategy,
        "geometry_source": normalized_source,
    }


def _semantic_tree_names(root) -> list[str]:
    return [root.name, *[child.name for child in root.children_recursive]]


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
    for sector in scene["sectors"]:
        azimuth_deg = float(sector["azimuth_deg"])
        azimuth = math.radians(azimuth_deg)
        z = float(sector["install_height_m"])
        tower_radius = _tower_radius_at_height(scene, z, azimuth)
        mount_radius = tower_radius + 0.35
        x = math.sin(azimuth) * mount_radius
        y = math.cos(azimuth) * mount_radius
        tilt_deg = float(sector.get("mechanical_tilt_deg") or 0.0)
        sector_id = str(sector["sector_id"])

        # Mounting bracket arm
        bracket = _create_mounting_bracket(bpy, tower_radius, mount_radius, azimuth, z)
        _set_semantic_properties(
            bracket,
            role="mount_bracket",
            semantic_root=f"mount_bracket_{sector_id}",
            sector_id=sector_id,
            properties={
                "requested_azimuth_deg": azimuth_deg,
                "requested_hba_m": z,
            },
        )
        procedural_objects.append(f"mount_bracket:{sector_id}")

        electrical_tilt_deg = float(sector.get("electrical_tilt_deg") or 0.0)
        beam_downtilt_deg = tilt_deg + electrical_tilt_deg
        antenna_strategy = sector.get("antenna_generation_strategy", "internal_project_generated")
        antenna_location = (x, y, z)
        # The record uses equivalent engineering angles. The actual transform
        # is quaternion yaw(Z) followed by downtilt(local X).
        antenna_rotation = (math.radians(-tilt_deg), 0.0, -azimuth)
        antenna_object_name = f"antenna_{sector_id}_{sector['antenna_asset_id']}"
        antenna_front_axis = str(
            (sector.get("antenna_asset_metadata") or {}).get("front_axis") or "+Y"
        )
        antenna_properties = {
            "sector_id": sector_id,
            "azimuth_deg": azimuth_deg,
            "requested_azimuth_deg": azimuth_deg,
            "mechanical_tilt_deg": tilt_deg,
            "electrical_tilt_deg": electrical_tilt_deg,
            "install_height_m": z,
            "requested_hba_m": z,
            "front_axis": antenna_front_axis,
            "geometry_family": _antenna_geometry_family(scene, sector),
        }
        if antenna_strategy == "imported_glb_exact":
            antenna_mode = _try_import_glb_asset(
                bpy=bpy,
                asset_id=sector["antenna_asset_id"],
                asset_file=sector.get("antenna_asset_file"),
                asset_source=sector.get("antenna_asset_source"),
                asset_metadata=sector.get("antenna_asset_metadata"),
                fallback_allowed=sector.get("antenna_import_fallback_allowed", True),
                object_role="antenna",
                object_name=antenna_object_name,
                location=antenna_location,
                rotation=antenna_rotation,
                rotation_mode="ZXY",
                dimensions=sector.get("antenna_dimensions_m"),
                asset_imports=asset_imports,
                warnings=asset_warnings,
                semantic_properties=antenna_properties,
                sector_pose=(azimuth_deg, tilt_deg, antenna_front_axis),
            )
            if not _is_imported_mode(antenna_mode) and sector.get(
                "antenna_import_fallback_allowed", True
            ):
                antenna_root = _build_generated_antenna(
                    bpy,
                    scene,
                    sector,
                    antenna_object_name,
                    antenna_location,
                    azimuth_deg,
                    tilt_deg,
                )
                _set_semantic_tree(
                    antenna_root,
                    role="antenna",
                    semantic_root=antenna_object_name,
                    sector_id=sector_id,
                    properties={
                        **antenna_properties,
                        **_classification_properties("procedural_fallback"),
                    },
                )
                procedural_objects.append(
                    f"antenna_{_antenna_geometry_family(scene, sector)}:{sector_id}:fallback"
                )
                _mark_fallback_generated(
                    asset_imports,
                    object_role="antenna",
                    object_name=antenna_object_name,
                    generated_object_names=_semantic_tree_names(antenna_root),
                )
        else:
            antenna_root = _build_generated_antenna(
                bpy,
                scene,
                sector,
                antenna_object_name,
                antenna_location,
                azimuth_deg,
                tilt_deg,
            )
            procedural_objects.append(
                f"antenna_{_antenna_geometry_family(scene, sector)}:{sector_id}"
            )
            _record_asset_generation(
                asset_imports,
                asset_warnings,
                asset_id=sector["antenna_asset_id"],
                asset_file=sector.get("antenna_asset_file"),
                asset_source=sector.get("antenna_asset_source"),
                asset_metadata=sector.get("antenna_asset_metadata"),
                object_role="antenna",
                object_name=antenna_object_name,
                dimensions=sector.get("antenna_dimensions_m"),
                location=antenna_location,
                rotation=antenna_rotation,
                generation_strategy=antenna_strategy,
                generated_object_names=_semantic_tree_names(antenna_root),
            )

        if sector.get("radio_asset_id"):
            radio_strategy = sector.get("radio_generation_strategy", "internal_project_generated")
            radio_location = (x * 0.92, y * 0.92, z - 1.0)
            radio_object_name = f"radio_{sector_id}_{sector['radio_asset_id']}"
            if radio_strategy == "imported_glb_exact":
                radio_mode = _try_import_glb_asset(
                    bpy=bpy,
                    asset_id=sector["radio_asset_id"],
                    asset_file=sector.get("radio_asset_file"),
                    asset_source=sector.get("radio_asset_source"),
                    asset_metadata=sector.get("radio_asset_metadata"),
                    fallback_allowed=sector.get("radio_import_fallback_allowed", True),
                    object_role="radio",
                    object_name=radio_object_name,
                    location=radio_location,
                    rotation=(0.0, 0.0, 0.0),
                    rotation_mode="XYZ",
                    dimensions=sector.get("radio_dimensions_m"),
                    asset_imports=asset_imports,
                    warnings=asset_warnings,
                    semantic_properties={
                        "sector_id": sector_id,
                        "install_height_m": z - 1.0,
                        "requested_azimuth_deg": azimuth_deg,
                        "requested_hba_m": z,
                    },
                    sector_pose=(
                        azimuth_deg,
                        0.0,
                        str((sector.get("radio_asset_metadata") or {}).get("front_axis") or "+Y"),
                    ),
                )
                if not _is_imported_mode(radio_mode) and sector.get(
                    "radio_import_fallback_allowed", True
                ):
                    radio_root = _build_generated_radio(
                        bpy,
                        sector,
                        radio_object_name,
                        radio_location,
                        sector_id,
                        azimuth_deg,
                        z,
                    )
                    _set_semantic_tree(
                        radio_root,
                        role="radio",
                        semantic_root=radio_object_name,
                        sector_id=sector_id,
                        properties={
                            "install_height_m": z - 1.0,
                            "requested_azimuth_deg": azimuth_deg,
                            "requested_hba_m": z,
                            **_classification_properties("procedural_fallback"),
                        },
                    )
                    procedural_objects.append(f"radio:{sector_id}:fallback")
                    _mark_fallback_generated(
                        asset_imports,
                        object_role="radio",
                        object_name=radio_object_name,
                        generated_object_names=_semantic_tree_names(radio_root),
                    )
            else:
                radio_root = _build_generated_radio(
                    bpy,
                    sector,
                    radio_object_name,
                    radio_location,
                    sector_id,
                    azimuth_deg,
                    z,
                )
                procedural_objects.append(f"radio:{sector_id}")
                _record_asset_generation(
                    asset_imports,
                    asset_warnings,
                    asset_id=sector["radio_asset_id"],
                    asset_file=sector.get("radio_asset_file"),
                    asset_source=sector.get("radio_asset_source"),
                    asset_metadata=sector.get("radio_asset_metadata"),
                    object_role="radio",
                    object_name=radio_object_name,
                    dimensions=sector.get("radio_dimensions_m"),
                    location=radio_location,
                    rotation=(0.0, 0.0, 0.0),
                    generation_strategy=radio_strategy,
                    generated_object_names=_semantic_tree_names(radio_root),
                )

        if sector.get("include_cable"):
            tower_entry_radius = max(tower_radius * 0.82, 0.18)
            route_points = [
                (x, y, z - 0.65),
                (x * 0.92, y * 0.92, z - 1.0)
                if sector.get("radio_asset_id")
                else (
                    math.sin(azimuth) * tower_entry_radius,
                    math.cos(azimuth) * tower_entry_radius,
                    z - 0.8,
                ),
                (
                    math.sin(azimuth) * tower_entry_radius,
                    math.cos(azimuth) * tower_entry_radius,
                    max(z - 1.4, 0.8),
                ),
                (
                    math.sin(azimuth) * tower_entry_radius,
                    math.cos(azimuth) * tower_entry_radius,
                    0.5,
                ),
            ]
            cable = _create_cable(bpy, sector_id, route_points)
            _set_semantic_properties(
                cable,
                role="cable",
                semantic_root=f"cable_{sector_id}",
                sector_id=sector_id,
                properties={
                    "requested_azimuth_deg": azimuth_deg,
                    "requested_hba_m": z,
                    "source_role": "antenna_port",
                    "via_role": "radio_port" if sector.get("radio_asset_id") else "tower_entry",
                    "target_role": "base_termination",
                    "route_point_count": len(route_points),
                    "route_topology": "antenna_to_radio_to_tower_base"
                    if sector.get("radio_asset_id")
                    else "antenna_to_tower_base",
                    **_classification_properties("parametric_generated"),
                },
            )
            procedural_objects.append(f"cable:{sector_id}")

        if scene["visual_elements"].get("include_sector_beams"):
            beamwidth = float(sector.get("beamwidth_deg") or 65.0)
            _create_beam(
                bpy,
                sector["sector_id"],
                azimuth,
                z,
                float(sector["beam_radius_m"]),
                beamwidth,
                beam_downtilt_deg,
            )
            procedural_objects.append(f"sector_beam:{sector_id}")

        if scene["visual_elements"].get("include_azimuth_arrows"):
            _create_azimuth_arrow(
                bpy,
                sector["sector_id"],
                azimuth,
                z + 1.2,
                azimuth_deg=azimuth_deg,
            )
            procedural_objects.append(f"azimuth_arrow:{sector_id}")


def _build_generated_antenna(
    bpy,
    scene: dict,
    sector: dict,
    object_name: str,
    location: tuple[float, float, float],
    azimuth_deg: float,
    tilt_deg: float,
):
    dims = sector.get("antenna_dimensions_m") or {}
    geometry_family = _antenna_geometry_family(scene, sector)
    if geometry_family == "microwave_dish":
        root = parametric_builder.build_parametric_microwave_dish(
            bpy=bpy,
            name=object_name,
            width=float(dims.get("width") or 0.9),
            depth=float(dims.get("depth") or 0.35),
            height=float(dims.get("height") or dims.get("width") or 0.9),
            location=location,
        )
    else:
        root = parametric_builder.build_parametric_panel_antenna(
            bpy=bpy,
            name=object_name,
            width=float(dims.get("width") or 0.45),
            depth=float(dims.get("depth") or 0.18),
            height=float(dims.get("height") or 1.6),
            location=location,
            rotation=(0.0, 0.0, 0.0),
        )
    parametric_builder.apply_sector_pose(
        root,
        azimuth_deg=azimuth_deg,
        mechanical_tilt_deg=tilt_deg,
        front_axis="+Y",
    )
    sector_id = str(sector["sector_id"])
    _set_semantic_tree(
        root,
        role="antenna",
        semantic_root=object_name,
        sector_id=sector_id,
        properties={
            "azimuth_deg": azimuth_deg,
            "requested_azimuth_deg": azimuth_deg,
            "mechanical_tilt_deg": tilt_deg,
            "electrical_tilt_deg": float(sector.get("electrical_tilt_deg") or 0.0),
            "install_height_m": float(sector["install_height_m"]),
            "requested_hba_m": float(sector["install_height_m"]),
            "front_axis": "+Y",
            "geometry_family": geometry_family,
            **_classification_properties(
                str(sector.get("antenna_generation_strategy") or "internal_project_generated"),
                str(sector.get("antenna_geometry_source") or "internal_project_generated"),
            ),
        },
    )
    return root


def _build_generated_radio(
    bpy,
    sector: dict,
    object_name: str,
    location: tuple[float, float, float],
    sector_id: str,
    azimuth_deg: float,
    requested_hba_m: float,
):
    dims = sector.get("radio_dimensions_m") or {}
    root = parametric_builder.build_parametric_radio(
        bpy=bpy,
        name=object_name,
        width=float(dims.get("width") or 0.35),
        depth=float(dims.get("depth") or 0.18),
        height=float(dims.get("height") or 0.6),
        location=location,
        rotation=(0.0, 0.0, 0.0),
    )
    parametric_builder.apply_sector_pose(
        root,
        azimuth_deg=azimuth_deg,
        mechanical_tilt_deg=0.0,
        front_axis="+Y",
    )
    _set_semantic_properties(
        root,
        role="radio",
        semantic_root=object_name,
        sector_id=sector_id,
        properties={
            "install_height_m": float(location[2]),
            "requested_azimuth_deg": azimuth_deg,
            "requested_hba_m": requested_hba_m,
            **_classification_properties(
                str(sector.get("radio_generation_strategy") or "internal_project_generated"),
                str(sector.get("radio_geometry_source") or "internal_project_generated"),
            ),
        },
    )
    return root


def _antenna_geometry_family(scene: dict, sector: dict) -> str:
    asset_id = str(sector.get("antenna_asset_id") or "").lower()
    if scene.get("network_type") == "MW" or "microwave" in asset_id or "dish" in asset_id:
        return "microwave_dish"
    return "panel"


def _create_cable(bpy, sector_id: str, route_points: list[tuple[float, float, float]]) -> object:
    curve = bpy.data.curves.new(f"cable_{sector_id}", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 8
    curve.bevel_depth = 0.025
    spline = curve.splines.new("POLY")
    spline.points.add(len(route_points) - 1)
    for point, coordinate in zip(spline.points, route_points, strict=True):
        point.co = (*coordinate, 1)
    obj = bpy.data.objects.new(f"cable_{sector_id}", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(_material(bpy, "cable_sheath_black", (0.035, 0.045, 0.055, 1)))
    return obj


def _create_beam(
    bpy,
    sector_id: str,
    azimuth: float,
    z: float,
    radius: float,
    beamwidth_deg: float = 65.0,
    downtilt_deg: float = 0.0,
) -> object:
    visual_length = min(radius, 4.5)
    start_radius = 1.55
    horizontal_length = visual_length * math.cos(math.radians(downtilt_deg))
    start = (
        math.sin(azimuth) * start_radius,
        math.cos(azimuth) * start_radius,
        z + 0.15,
    )
    end = (
        math.sin(azimuth) * (start_radius + horizontal_length),
        math.cos(azimuth) * (start_radius + horizontal_length),
        z + 0.15 - (visual_length * math.sin(math.radians(downtilt_deg))),
    )
    material = _material(bpy, "beam_direction_blue", (0.05, 0.45, 1.0, 0.62))
    shaft = _create_cylinder_between(bpy, start, end, 0.035, f"sector_beam_{sector_id}", material)
    # The visible aperture must widen monotonically with the requested HPBW.
    half_angle = math.radians(min(max(beamwidth_deg, 1.0), 175.0) / 2.0)
    cone_radius = min(0.55, max(0.08, 0.22 * math.tan(half_angle)))
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=cone_radius, depth=0.3, location=end)
    head = bpy.context.object
    head.name = f"sector_beam_head_{sector_id}"
    head.rotation_euler = _direction_to_euler(
        end[0] - start[0],
        end[1] - start[1],
        end[2] - start[2],
    )
    head.data.materials.append(material)
    return _create_semantic_group(
        bpy,
        f"sector_beam_{sector_id}",
        [item for item in (shaft, head) if item is not None],
        role="beam",
        sector_id=str(sector_id),
        properties={
            "requested_azimuth_deg": math.degrees(azimuth) % 360.0,
            "requested_hba_m": z,
            "beamwidth_deg": beamwidth_deg,
            "downtilt_deg": downtilt_deg,
            **_classification_properties("parametric_generated"),
        },
    )


def _create_azimuth_arrow(
    bpy,
    sector_id: str,
    azimuth: float,
    z: float,
    *,
    azimuth_deg: float,
) -> object:
    start = (0, 0, z)
    end = (math.sin(azimuth) * 3.0, math.cos(azimuth) * 3.0, z)
    material = _material(bpy, f"azimuth_arrow_red_{sector_id}", (1.0, 0.15, 0.1, 1))
    shaft = _create_cylinder_between(bpy, start, end, 0.035, f"azimuth_arrow_{sector_id}", material)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.16, depth=0.35, location=end)
    head = bpy.context.object
    head.name = f"azimuth_arrow_head_{sector_id}"
    head.rotation_euler = _direction_to_euler(
        end[0] - start[0],
        end[1] - start[1],
        end[2] - start[2],
    )
    head.data.materials.append(material)
    return _create_semantic_group(
        bpy,
        f"azimuth_arrow_{sector_id}",
        [item for item in (shaft, head) if item is not None],
        role="azimuth_arrow",
        sector_id=str(sector_id),
        properties={
            "requested_azimuth_deg": azimuth_deg,
            **_classification_properties("parametric_generated"),
        },
    )


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
    strategy = (
        accessory.get("generation_strategy", "internal_project_generated")
        if accessory
        else "procedural_fallback"
    )
    cabinet_object_name = (
        f"power_cabinet_{accessory['asset_id']}" if accessory else "power_cabinet_procedural"
    )
    cabinet_location = (
        tuple(accessory.get("position") or [offset, 0.0, 0.0]) if accessory else (offset, 0.0, 0.0)
    )
    import_attempted = False
    if accessory and strategy in {"imported_glb_exact", "internal_project_generated"}:
        import_attempted = True
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=accessory.get("asset_file"),
            asset_source=accessory.get("asset_source"),
            asset_metadata=accessory.get("asset_metadata"),
            fallback_allowed=accessory.get("import_fallback_allowed", True),
            object_role="cabinet",
            object_name=cabinet_object_name,
            location=cabinet_location,
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=accessory.get("dimensions_m"),
            placement_scale=tuple(accessory.get("scale") or [1.0, 1.0, 1.0]),
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={"ground_datum_z": 0.0},
        )
        if _is_imported_mode(mode) or not accessory.get("import_fallback_allowed", True):
            return
    cabinet = parametric_builder.build_parametric_accessory_cabinet(
        bpy=bpy,
        name=cabinet_object_name,
        location=cabinet_location,
    )
    if accessory:
        cabinet.rotation_euler = _rotation_deg_to_rad(
            accessory.get("rotation_deg") or [0.0, 0.0, 0.0]
        )
        cabinet.scale = tuple(accessory.get("scale") or [1.0, 1.0, 1.0])
    actual_strategy = "procedural_fallback" if import_attempted else str(strategy)
    actual_source = (
        "procedural_fallback"
        if import_attempted or not accessory
        else str(accessory.get("geometry_source") or strategy)
    )
    _set_semantic_properties(
        cabinet,
        role="cabinet",
        semantic_root=cabinet_object_name,
        properties={
            "ground_datum_z": 0.0,
            **_classification_properties(actual_strategy, actual_source),
        },
    )
    if accessory and import_attempted:
        _mark_fallback_generated(
            asset_imports,
            object_role="cabinet",
            object_name=cabinet_object_name,
            generated_object_names=[cabinet.name],
        )
    else:
        _record_asset_generation(
            asset_imports,
            asset_warnings,
            asset_id=accessory["asset_id"] if accessory else "POWER_CABINET_PROCEDURAL",
            asset_file=accessory.get("asset_file") if accessory else None,
            asset_source=accessory.get("asset_source")
            if accessory
            else "internal_project_generated",
            asset_metadata=accessory.get("asset_metadata") if accessory else None,
            object_role="cabinet",
            object_name=cabinet_object_name,
            dimensions={"width": 1.0, "depth": 0.45, "height": 1.6},
            location=cabinet_location,
            rotation=(0.0, 0.0, 0.0),
            generation_strategy=strategy,
            generated_object_names=[cabinet.name],
        )
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
    mount_radius = _tower_radius_at_height(scene, z) + 0.1
    accessory = _accessory_asset(scene, "gps")
    strategy = (
        accessory.get("generation_strategy", "internal_project_generated")
        if accessory
        else "procedural_fallback"
    )
    gps_object_name = (
        f"gps_antenna_{accessory['asset_id']}" if accessory else "gps_antenna_procedural"
    )
    gps_location = (
        tuple(accessory.get("position") or [0.0, mount_radius, z])
        if accessory
        else (0.0, mount_radius, z)
    )
    import_attempted = False
    if accessory and strategy in {"imported_glb_exact", "internal_project_generated"}:
        import_attempted = True
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=accessory.get("asset_file"),
            asset_source=accessory.get("asset_source"),
            asset_metadata=accessory.get("asset_metadata"),
            fallback_allowed=accessory.get("import_fallback_allowed", True),
            object_role="gps",
            object_name=gps_object_name,
            location=gps_location,
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=accessory.get("dimensions_m"),
            placement_scale=tuple(accessory.get("scale") or [1.0, 1.0, 1.0]),
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={"install_height_m": z},
        )
        if _is_imported_mode(mode) or not accessory.get("import_fallback_allowed", True):
            return
    gps = parametric_builder.build_parametric_accessory_gps(
        bpy=bpy,
        name=gps_object_name,
        location=gps_location,
    )
    if accessory:
        gps.rotation_euler = _rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0])
        gps.scale = tuple(accessory.get("scale") or [1.0, 1.0, 1.0])
    actual_strategy = "procedural_fallback" if import_attempted else str(strategy)
    actual_source = (
        "procedural_fallback"
        if import_attempted or not accessory
        else str(accessory.get("geometry_source") or strategy)
    )
    _set_semantic_tree(
        gps,
        role="gps",
        semantic_root=gps_object_name,
        properties={
            "install_height_m": z,
            **_classification_properties(actual_strategy, actual_source),
        },
    )
    if accessory and import_attempted:
        _mark_fallback_generated(
            asset_imports,
            object_role="gps",
            object_name=gps_object_name,
            generated_object_names=_semantic_tree_names(gps),
        )
    else:
        _record_asset_generation(
            asset_imports,
            asset_warnings,
            asset_id=accessory["asset_id"] if accessory else "GPS_ANTENNA_PROCEDURAL",
            asset_file=accessory.get("asset_file") if accessory else None,
            asset_source=accessory.get("asset_source")
            if accessory
            else "internal_project_generated",
            asset_metadata=accessory.get("asset_metadata") if accessory else None,
            object_role="gps",
            object_name=gps_object_name,
            dimensions={"width": 0.32, "depth": 0.32, "height": 0.82},
            location=gps_location,
            rotation=(0.0, 0.0, 0.0),
            generation_strategy=strategy,
            generated_object_names=_semantic_tree_names(gps),
        )
    procedural_objects.append("gps_antenna")


def _create_labels(bpy, scene: dict, procedural_objects: list[str]) -> None:
    characteristics = scene["tower"].get("characteristics", {})
    base_width = float(characteristics.get("base_width_m") or 4.0)
    for sector in scene["sectors"]:
        if not sector.get("include_label", True):
            continue
        azimuth_deg = float(sector["azimuth_deg"])
        azimuth = math.radians(azimuth_deg)
        z = float(sector["install_height_m"]) + 1.05
        mount_radius = _tower_radius_at_height(scene, z, azimuth) + 1.25
        x = math.sin(azimuth) * mount_radius
        y = math.cos(azimuth) * mount_radius
        label_name = f"label_sector_{sector['sector_id']}_{_azimuth_label(azimuth_deg)}"
        label_text = (
            f"{sector['sector_id']} {azimuth_deg:g}° HBA {float(sector['install_height_m']):g}m"
        )
        label = _create_text_label(bpy, label_name, label_text, (x, y, z))
        _set_semantic_properties(
            label,
            role="label",
            semantic_root=label_name,
            sector_id=str(sector["sector_id"]),
            properties={
                "requested_azimuth_deg": azimuth_deg,
                "requested_hba_m": float(sector["install_height_m"]),
                **_classification_properties("parametric_generated"),
            },
        )
        procedural_objects.append(f"label:{sector['sector_id']}")
    if scene["visual_elements"].get("include_power_cabinet", False):
        offset = max(3.0, base_width * 1.2)
        label = _create_text_label(
            bpy,
            "label_power_cabinet",
            "Power cabinet",
            (offset, -0.55, 1.75),
            size=0.28,
        )
        _set_semantic_properties(
            label,
            role="label",
            semantic_root="label_power_cabinet",
            properties=_classification_properties("parametric_generated"),
        )
        procedural_objects.append("label:power_cabinet")
    if scene["visual_elements"].get("include_gps_antenna", False):
        height = float(scene["tower"]["height_m"])
        mount_radius = _tower_radius_at_height(scene, height - 0.5) + 0.65
        label = _create_text_label(
            bpy,
            "label_gps_antenna",
            "GPS",
            (0.0, mount_radius, height + 0.55),
            size=0.26,
        )
        _set_semantic_properties(
            label,
            role="label",
            semantic_root="label_gps_antenna",
            properties=_classification_properties("parametric_generated"),
        )
        procedural_objects.append("label:gps_antenna")


def _create_text_label(
    bpy,
    name: str,
    text: str,
    location: tuple[float, float, float],
    *,
    size: float = 0.32,
) -> object:
    bpy.ops.object.text_add(location=location, rotation=(math.radians(75), 0.0, 0.0))
    label = bpy.context.object
    label.name = name
    label.data.name = f"{name}_text"
    label.data.body = text
    label.data.align_x = "CENTER"
    label.data.align_y = "CENTER"
    label.data.size = size
    label.data.extrude = 0.006
    label.data.materials.append(_material(bpy, "label_technical_cyan", (0.18, 0.78, 0.92, 1)))
    bpy.ops.object.convert(target="MESH")
    label_mesh = bpy.context.object
    label_mesh.name = name
    return label_mesh


def _azimuth_label(value: float) -> str:
    return f"{int(value)}deg" if float(value).is_integer() else f"{value:g}deg".replace(".", "p")


def _accessory_asset(scene: dict, asset_type: str) -> dict | None:
    for accessory in scene.get("accessory_assets", []):
        if accessory.get("asset_type") == asset_type:
            return accessory
    return None


def _rotation_deg_to_rad(values: list[float]) -> tuple[float, float, float]:
    return tuple(math.radians(float(value)) for value in values[:3])


def _create_foundation(bpy, characteristics: dict, procedural_objects: list[str]) -> None:
    foundation_type = characteristics.get("foundation_type", "concrete_pad")
    base_width = float(characteristics.get("base_width_m") or 4.0)
    if foundation_type == "concrete_pad":
        size = max(base_width * 1.6, 3.0)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.15))
        pad = bpy.context.object
        pad.name = "foundation_concrete_pad"
        pad.dimensions = (size, size, 0.3)
        pad.data.materials.append(_material(bpy, "concrete_gray", (0.62, 0.64, 0.66, 1)))
        _set_semantic_properties(
            pad,
            role="foundation",
            semantic_root="foundation_concrete_pad",
            properties={
                "foundation_type": foundation_type,
                **_classification_properties("parametric_generated"),
            },
        )
        procedural_objects.append("foundation_concrete_pad")
        return
    if foundation_type == "rooftop_anchored":
        steel = _material(bpy, "foundation_anchor_steel", (0.38, 0.42, 0.46, 1))
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, 0.0, 0.06))
        plate = bpy.context.object
        plate.name = "foundation_rooftop_anchored"
        plate.dimensions = (max(base_width * 2.2, 1.1), max(base_width * 2.2, 1.1), 0.12)
        plate.data.materials.append(steel)
        created = [plate]
        anchor_offset = max(base_width * 0.75, 0.28)
        for index, (x, y) in enumerate(
            (
                (-anchor_offset, -anchor_offset),
                (anchor_offset, -anchor_offset),
                (anchor_offset, anchor_offset),
                (-anchor_offset, anchor_offset),
            ),
            start=1,
        ):
            anchor = _create_cylinder_between(
                bpy,
                (x, y, -0.18),
                (x, y, 0.24),
                0.035,
                f"foundation_rooftop_anchor_{index}",
                steel,
            )
            created.append(anchor)
        _create_semantic_group(
            bpy,
            "foundation_rooftop_anchored_root",
            created,
            role="foundation",
            properties={
                "foundation_type": foundation_type,
                **_classification_properties("parametric_generated"),
            },
        )
        procedural_objects.append("foundation_rooftop_anchored")
        return
    if foundation_type == "pole_base":
        concrete = _material(bpy, "foundation_pole_concrete", (0.58, 0.60, 0.61, 1))
        radius = max(base_width * 0.85, 0.45)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32,
            radius=radius,
            depth=0.8,
            location=(0.0, 0.0, -0.35),
        )
        base = bpy.context.object
        base.name = "foundation_pole_base"
        base.data.materials.append(concrete)
        _set_semantic_properties(
            base,
            role="foundation",
            semantic_root="foundation_pole_base",
            properties={
                "foundation_type": foundation_type,
                **_classification_properties("parametric_generated"),
            },
        )
        procedural_objects.append("foundation_pole_base")
        return
    if foundation_type == "unknown":
        return
    raise RuntimeError(f"Unsupported foundation_type for Blender generation: {foundation_type!r}")


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
    placement_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    asset_imports: list[dict],
    warnings: list[str],
    semantic_properties: dict | None = None,
    sector_pose: tuple[float, float, str] | None = None,
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

    expected_sha256 = str((asset_metadata or {}).get("verified_file_sha256") or "")
    if expected_sha256 and _sha256_file(path) != expected_sha256:
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            "ASSET_QUALIFIED_HASH_MISMATCH",
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

    imported_set = set(imported)
    imported_roots = [obj for obj in imported if obj.parent not in imported_set]
    container = bpy.data.objects.new(object_name, None)
    bpy.context.collection.objects.link(container)
    for root in imported_roots:
        root.parent = container
    for index, obj in enumerate(imported):
        obj.name = f"{object_name}_part_{index + 1}"

    source_bounds = _objects_world_bounds(imported)
    pivot_policy = str((asset_metadata or {}).get("pivot_policy") or "").lower()
    if source_bounds and pivot_policy.startswith("base_center"):
        minimum, maximum = source_bounds
        pivot_offset = (
            -((minimum.x + maximum.x) * 0.5),
            -((minimum.y + maximum.y) * 0.5),
            -minimum.z,
        )
        for root in imported_roots:
            root.location.x += pivot_offset[0]
            root.location.y += pivot_offset[1]
            root.location.z += pivot_offset[2]

    dimensions_checked = False
    scale_factors = (1.0, 1.0, 1.0)
    if dimensions and source_bounds:
        minimum, maximum = source_bounds
        source_size = maximum - minimum
        target_size = (
            float(dimensions.get("width") or source_size.x),
            float(dimensions.get("depth") or source_size.y),
            float(dimensions.get("height") or source_size.z),
        )
        scale_factors = tuple(
            target_size[index] / max(float(source_size[index]), 1e-6) for index in range(3)
        )
        dimensions_checked = True
    scale_factors = tuple(
        float(scale_factors[index]) * float(placement_scale[index]) for index in range(3)
    )
    container.scale = scale_factors
    container.location = location
    if sector_pose is not None:
        parametric_builder.apply_sector_pose(
            container,
            azimuth_deg=sector_pose[0],
            mechanical_tilt_deg=sector_pose[1],
            front_axis=sector_pose[2],
        )
    else:
        container.rotation_mode = rotation_mode
        container.rotation_euler = rotation
    sector_id = str((semantic_properties or {}).get("sector_id") or "") or None
    _set_semantic_tree(
        container,
        role=object_role,
        semantic_root=object_name,
        sector_id=sector_id,
        properties=semantic_properties,
    )
    bpy.context.view_layer.update()

    non_uniform_scale = max(scale_factors) - min(scale_factors) > 0.01
    import_mode = "stretched_imported_glb" if non_uniform_scale else "imported_glb"
    geometry_source = "stretched_imported_glb" if non_uniform_scale else "imported_glb_exact"
    _set_semantic_tree(
        container,
        role=object_role,
        semantic_root=object_name,
        sector_id=sector_id,
        properties={
            **(semantic_properties or {}),
            **_classification_properties(geometry_source, geometry_source),
        },
    )
    if non_uniform_scale:
        _append_warning(record["warnings"], "IMPORTED_ASSET_NONUNIFORM_SCALE_APPLIED")
        _append_warning(warnings, f"IMPORTED_ASSET_NONUNIFORM_SCALE_APPLIED:{asset_id}")

    record.update(
        {
            "asset_file_exists": True,
            "asset_import_success": True,
            "generation_success": False,
            "asset_dimensions_checked": dimensions_checked,
            "import_mode": import_mode,
            "effective_generation_mode": import_mode,
            "effective_geometry_source": geometry_source,
            "scale_factors": [round(float(value), 6) for value in scale_factors],
            "imported_object_count": len(imported),
            "imported_object_names": [container.name, *[obj.name for obj in imported]],
            "import_root_name": container.name,
            "generated_object_count": 0,
            "generated_object_names": [],
        }
    )
    for source_warning in _asset_source_warnings(asset_source, asset_metadata):
        _append_warning(record["warnings"], source_warning)
        _append_warning(warnings, f"{source_warning}:{asset_id}")
    asset_imports.append(record)
    return import_mode


def _asset_placement_location(
    default: tuple[float, float, float],
    asset_metadata: dict | None,
    object_role: str,
) -> tuple[float, float, float]:
    pivot_policy = str((asset_metadata or {}).get("pivot_policy") or "").lower()
    if object_role == "tower" and pivot_policy == "base_center_ground":
        return (0.0, 0.0, 0.0)
    return default


def _objects_world_bounds(objects: list):
    from mathutils import Vector  # type: ignore[import-not-found]

    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return _bounds_from_vectors(corners)


def _resolve_asset_path(asset_file: str | None) -> Path | None:
    if not asset_file:
        return None
    path = Path(asset_file)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "generation_success": False,
        "asset_dimensions_checked": False,
        "manifest_dimensions_m": dimensions,
        "placement_location": [round(float(value), 5) for value in location],
        "placement_rotation_rad": [round(float(value), 5) for value in rotation],
        "placement_rotation_deg": [round(math.degrees(float(value)), 5) for value in rotation],
        "import_fallback_allowed": fallback_allowed,
        "import_mode": "not_attempted",
        "effective_generation_mode": "not_attempted",
        "effective_geometry_source": "unknown",
        "imported_object_count": 0,
        "imported_object_names": [],
        "generated_object_count": 0,
        "generated_object_names": [],
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
            "effective_geometry_source": "missing_file",
            "asset_import_success": False,
            "generation_success": False,
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


def _record_asset_generation(
    asset_imports: list[dict],
    warnings: list[str],
    *,
    asset_id: str,
    asset_file: str | None,
    asset_source: str | None,
    asset_metadata: dict | None,
    object_role: str,
    object_name: str,
    dimensions: dict | None,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
    generation_strategy: str,
    generated_object_names: list[str] | None = None,
) -> None:
    """Record a parametric/internal-project-generated asset placement."""
    record = _base_asset_import_record(
        asset_id=asset_id,
        asset_file=asset_file,
        asset_source=asset_source,
        asset_metadata=asset_metadata,
        object_role=object_role,
        object_name=object_name,
        path=_resolve_asset_path(asset_file),
        fallback_allowed=True,
        dimensions=dimensions,
        location=location,
        rotation=rotation,
    )
    for source_warning in _asset_source_warnings(asset_source, asset_metadata):
        _append_warning(record["warnings"], source_warning)
        _append_warning(warnings, f"{source_warning}:{asset_id}")
    resolved = Path(record["resolved_path"]) if record.get("resolved_path") else None
    record.update(
        {
            "asset_file_exists": bool(resolved and resolved.exists()),
            "asset_import_success": False,
            "generation_success": True,
            "asset_dimensions_checked": False,
            "import_mode": generation_strategy,
            "effective_generation_mode": generation_strategy,
            "effective_geometry_source": generation_strategy,
            "imported_object_count": 0,
            "imported_object_names": [],
            "generated_object_count": len(generated_object_names or [object_name]),
            "generated_object_names": generated_object_names or [object_name],
        }
    )
    asset_imports.append(record)


def _mark_fallback_generated(
    asset_imports: list[dict],
    *,
    object_role: str,
    object_name: str,
    generated_object_names: list[str],
) -> None:
    record = next(
        (
            item
            for item in reversed(asset_imports)
            if item.get("object_role") == object_role
            and item.get("object_name") == object_name
            and item.get("import_mode") == "procedural_fallback"
        ),
        None,
    )
    if record is None:
        raise RuntimeError(f"Missing fallback import record for {object_role}:{object_name}")
    record.update(
        {
            "generation_success": True,
            "effective_generation_mode": "procedural_fallback",
            "effective_geometry_source": "procedural_fallback",
            "generated_object_count": len(generated_object_names),
            "generated_object_names": generated_object_names,
        }
    )


def _is_imported_mode(mode: str) -> bool:
    return mode in {"imported_glb", "stretched_imported_glb"}


def _create_mounting_bracket(
    bpy,
    tower_radius: float,
    mount_radius: float,
    azimuth: float,
    z: float,
):
    steel = _material(bpy, "mount_steel", (0.42, 0.44, 0.46, 1))
    start = (
        math.sin(azimuth) * tower_radius,
        math.cos(azimuth) * tower_radius,
        z,
    )
    end = (math.sin(azimuth) * (mount_radius + 0.05), math.cos(azimuth) * (mount_radius + 0.05), z)
    return _create_cylinder_between(bpy, start, end, 0.035, "mount_bracket", steel)


def _create_height_marker(bpy, scene: dict, procedural_objects: list[str]) -> None:
    height = float(scene["tower"]["height_m"])
    material = _material(bpy, "height_marker_yellow", (1.0, 0.82, 0.1, 1))
    _create_cylinder_between(bpy, (2.7, 0, 0), (2.7, 0, height), 0.025, "height_marker", material)
    procedural_objects.append("height_marker")


def _create_camera_and_light(bpy, scene: dict) -> dict:
    from mathutils import Vector  # type: ignore[import-not-found]

    tower_height = float(scene["tower"]["height_m"])
    base_width = float(scene["tower"].get("characteristics", {}).get("base_width_m") or 4.0)
    subject_corners = _subject_world_corners(bpy)
    subject_bounds = _bounds_from_vectors(subject_corners)
    if subject_bounds:
        minimum, maximum = subject_bounds
        target_vector = (minimum + maximum) * 0.5
        subject_size = maximum - minimum
    else:
        target_vector = Vector((0.0, 0.0, tower_height * 0.5))
        subject_size = Vector((base_width, base_width, tower_height))
    distance = max(34.0, subject_size.length * 1.45)
    camera_mode = str(scene.get("preview", {}).get("camera") or "isometric")
    view_direction = Vector(_camera_view_direction(camera_mode)).normalized()
    camera_location_vector = target_vector + (view_direction * distance)
    target = tuple(float(value) for value in target_vector)
    camera_location = tuple(float(value) for value in camera_location_vector)

    bpy.ops.object.light_add(type="SUN", location=(8, -6, tower_height + 12))
    sun = bpy.context.object
    sun.name = "sun_key"
    sun.data.energy = 2.2
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-32))
    bpy.ops.object.light_add(
        type="AREA",
        location=(-distance * 0.35, -distance * 0.45, tower_height * 0.82),
    )
    fill = bpy.context.object
    fill.name = "area_fill"
    fill.data.energy = 950
    fill.data.size = max(7, tower_height * 0.42)
    _point_object_at(fill, target)
    bpy.ops.object.light_add(
        type="AREA",
        location=(distance * 0.58, distance * 0.32, tower_height * 0.7),
    )
    rim = bpy.context.object
    rim.name = "area_rim"
    rim.data.energy = 1200
    rim.data.size = max(5, tower_height * 0.3)
    _point_object_at(rim, target)

    bpy.ops.object.camera_add(
        location=camera_location,
    )
    camera = bpy.context.object
    camera.name = {
        "isometric": "camera_technical_three_quarter_full_tower",
        "front": "camera_technical_front_full_tower",
        "top": "camera_technical_top_full_tower",
    }[camera_mode]
    camera.data.type = "ORTHO"
    _point_object_at(camera, target)
    framing = _fit_orthographic_camera(bpy, camera, subject_corners, scene)
    bpy.context.scene.camera = camera
    return {
        "camera": camera.name,
        "camera_type": "ORTHO",
        "requested_camera": camera_mode,
        "camera_location": [round(float(value), 3) for value in camera.location],
        "target": [round(float(value), 3) for value in framing["target"]],
        "ortho_scale": round(float(camera.data.ortho_scale), 3),
        "subject_bounds_m": framing["subject_bounds_m"],
        "projected_subject_width_m": framing["projected_subject_width_m"],
        "projected_subject_height_m": framing["projected_subject_height_m"],
        "frame_margin_ratio": framing["frame_margin_ratio"],
        "background": "dark_technical_studio",
        "framing": {
            "isometric": "geometry_bounds_three_quarter",
            "front": "geometry_bounds_front",
            "top": "geometry_bounds_top",
        }[camera_mode],
    }


def _camera_view_direction(camera_mode: str) -> tuple[float, float, float]:
    return {
        "isometric": (0.62, -1.0, 0.28),
        "front": (0.0, -1.0, 0.04),
        "top": (0.0, 0.0, 1.0),
    }[camera_mode]


def _subject_world_corners(bpy) -> list:
    from mathutils import Vector  # type: ignore[import-not-found]

    bpy.context.view_layer.update()
    corners = []
    excluded_prefixes = (
        "technical_ground_plane",
        "technical_preview_backdrop",
        "camera_",
        "sun_",
        "area_",
    )
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE"}:
            continue
        if obj.hide_render or obj.name.lower().startswith(excluded_prefixes):
            continue
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    return corners


def _bounds_from_vectors(vectors: list):
    if not vectors:
        return None
    from mathutils import Vector  # type: ignore[import-not-found]

    minimum = Vector(tuple(min(point[axis] for point in vectors) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in vectors) for axis in range(3)))
    return minimum, maximum


def _fit_orthographic_camera(bpy, camera, subject_corners: list, scene: dict) -> dict:
    from mathutils import Vector  # type: ignore[import-not-found]

    margin_ratio = 0.09
    width, height = scene["preview"]["resolution"]
    aspect_ratio = max(float(width) / max(float(height), 1.0), 0.1)
    if not subject_corners:
        tower_height = float(scene["tower"]["height_m"])
        camera.data.ortho_scale = max(tower_height * 1.28, 18.0)
        camera.data.clip_start = 0.1
        camera.data.clip_end = max(tower_height * 6.0, 250.0)
        return {
            "target": list(camera.location),
            "subject_bounds_m": None,
            "projected_subject_width_m": None,
            "projected_subject_height_m": None,
            "frame_margin_ratio": margin_ratio,
        }

    bpy.context.view_layer.update()
    camera_inverse = camera.matrix_world.inverted()
    camera_points = [camera_inverse @ point for point in subject_corners]
    min_x = min(point.x for point in camera_points)
    max_x = max(point.x for point in camera_points)
    min_y = min(point.y for point in camera_points)
    max_y = max(point.y for point in camera_points)
    projected_center = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, 0.0))
    world_offset = camera.matrix_world.to_quaternion() @ projected_center
    camera.location += world_offset
    target = Vector(camera.location) + (camera.matrix_world.to_quaternion() @ Vector((0, 0, -1)))
    projected_width = max_x - min_x
    projected_height = max_y - min_y
    # In Blender's camera projection used here, ortho_scale behaves as the
    # horizontal span and the visible vertical span is scale / aspect ratio.
    required_horizontal_span = max(projected_width, projected_height * aspect_ratio, 1.0)
    camera.data.ortho_scale = required_horizontal_span / (1.0 - (2.0 * margin_ratio))
    depth_values = [-point.z for point in camera_points]
    camera.data.clip_start = max(0.05, min(depth_values) * 0.25)
    camera.data.clip_end = max(max(depth_values) * 1.5, camera.data.clip_start + 100.0)
    bpy.context.view_layer.update()

    world_bounds = _bounds_from_vectors(subject_corners)
    minimum, maximum = world_bounds
    return {
        "target": [float(value) for value in target],
        "subject_bounds_m": {
            "min": [round(float(value), 4) for value in minimum],
            "max": [round(float(value), 4) for value in maximum],
        },
        "projected_subject_width_m": round(projected_width, 4),
        "projected_subject_height_m": round(projected_height, 4),
        "frame_margin_ratio": margin_ratio,
    }


def _create_preview_backdrop(bpy, scene: dict) -> None:
    from mathutils import Vector  # type: ignore[import-not-found]

    camera = bpy.context.scene.camera
    preview_width, preview_height = scene["preview"]["resolution"]
    aspect_ratio = max(float(preview_width) / max(float(preview_height), 1.0), 0.1)
    width = float(camera.data.ortho_scale) * 1.3
    height = (width / aspect_ratio) * 1.3
    view_direction = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    backdrop_distance = max(float(scene["tower"]["height_m"]) * 2.2, 70.0)
    location = Vector(camera.location) + (view_direction * backdrop_distance)
    bpy.ops.mesh.primitive_plane_add(
        size=1,
        location=location,
        rotation=camera.rotation_euler,
    )
    backdrop = bpy.context.object
    backdrop.name = "technical_preview_backdrop"
    backdrop.dimensions = (width, height, 1)
    backdrop.data.materials.append(
        _emission_material(bpy, "preview_backdrop_dark", (0.025, 0.04, 0.055, 1), 0.42)
    )


def _point_object_at(obj, target: tuple[float, float, float]) -> None:
    from mathutils import Vector  # type: ignore[import-not-found]

    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _create_cylinder_between(
    bpy,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    name: str,
    material,
):
    return parametric_builder.create_cylinder_between(
        bpy,
        start,
        end,
        radius,
        name,
        material,
        vertices=12,
    )


def _direction_to_euler(dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    yaw = math.atan2(dy, dx)
    horizontal = math.sqrt(dx * dx + dy * dy)
    pitch = math.atan2(horizontal, dz)
    return (pitch, 0, yaw + math.pi / 2)


def _material(bpy, name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = _first_node_by_type(material, "ShaderNodeBsdfPrincipled")
    if principled:
        base_color = principled.inputs.get("Base Color")
        if base_color is not None:
            base_color.default_value = color
        alpha = principled.inputs.get("Alpha")
        if alpha is not None:
            alpha.default_value = color[3]
        roughness = principled.inputs.get("Roughness")
        if roughness is not None:
            roughness.default_value = _material_roughness(name)
        metallic = principled.inputs.get("Metallic")
        if metallic is not None:
            metallic.default_value = _material_metallic(name)
    if color[3] < 1:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
        material.show_transparent_back = False
    return material


def _material_roughness(name: str) -> float:
    normalized = name.lower()
    if "concrete" in normalized or "ground" in normalized:
        return 0.78
    if any(token in normalized for token in ("steel", "metal", "mount", "pole", "gray")):
        return 0.32
    if any(token in normalized for token in ("antenna", "gps", "label")):
        return 0.42
    return 0.5


def _material_metallic(name: str) -> float:
    normalized = name.lower()
    if any(token in normalized for token in ("steel", "metal", "mount", "pole")):
        return 0.68
    return 0.05


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
    _write_metadata(
        scene,
        output_dir,
        "fallback_no_blender",
        [],
        [
            "Blender Python API not available; no GLB or preview was generated.",
            "NO_GEOMETRY_GENERATED",
        ],
        _fallback_camera_metadata(scene),
        _fallback_asset_import_records(scene),
        segment_connectivity={
            "status": "not_available",
            "passed": False,
            "evaluated_segment_count": 0,
            "failed_segment_count": 0,
            "maximum_endpoint_error_m": None,
            "tolerance_m": 0.001,
        },
    )


def _validate_parametric_segment_connectivity(bpy, tolerance_m: float = 0.001) -> dict:
    """Hard-fail when generated cylindrical members miss their requested endpoints."""

    bpy.context.view_layer.update()
    evaluated = 0
    failures: list[dict] = []
    maximum_error = 0.0
    for obj in bpy.context.scene.objects:
        if "segment_start_m" not in obj or "segment_end_m" not in obj:
            continue
        evaluated += 1
        endpoint_errors = parametric_builder.measure_segment_endpoint_errors(obj)
        if endpoint_errors is None:
            failures.append({"object": obj.name, "reason": "endpoint_measurement_unavailable"})
            continue
        start_error, end_error = endpoint_errors
        object_error = max(start_error, end_error)
        maximum_error = max(maximum_error, object_error)
        if object_error > tolerance_m:
            failures.append(
                {
                    "object": obj.name,
                    "start_error_m": round(start_error, 9),
                    "end_error_m": round(end_error, 9),
                    "requested_start_m": [
                        round(float(value), 6) for value in obj["segment_start_m"]
                    ],
                    "requested_end_m": [round(float(value), 6) for value in obj["segment_end_m"]],
                    "rotation_quaternion": [
                        round(float(value), 6) for value in obj.rotation_quaternion
                    ],
                    "scale": [round(float(value), 6) for value in obj.scale],
                }
            )
    report = {
        "status": "passed" if not failures else "failed",
        "passed": not failures,
        "evaluated_segment_count": evaluated,
        "failed_segment_count": len(failures),
        "maximum_endpoint_error_m": round(maximum_error, 9),
        "tolerance_m": tolerance_m,
        "failures": failures,
    }
    if failures:
        sample = "; ".join(
            ",".join(f"{key}={value}" for key, value in failure.items()) for failure in failures[:5]
        )
        raise RuntimeError(
            "PARAMETRIC_SEGMENT_CONNECTIVITY_FAILED: "
            f"{len(failures)} segment(s), max_error_m={maximum_error:.9f}: {sample}"
        )
    return report


def _compute_scene_bounding_box(bpy) -> dict:
    """Compute world-space bounding box of all mesh objects in the scene."""
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.data.vertices:
            continue
        for vertex in obj.bound_box:
            world_coord = obj.matrix_world @ obj.location.__class__(vertex)
            x, y, z = world_coord.x, world_coord.y, world_coord.z
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            min_z, max_z = min(min_z, z), max(max_z, z)
            found = True
    if not found:
        return {
            "min_x": 0.0,
            "min_y": 0.0,
            "min_z": 0.0,
            "max_x": 0.0,
            "max_y": 0.0,
            "max_z": 0.0,
            "width": 0.0,
            "depth": 0.0,
            "height": 0.0,
        }
    return {
        "min_x": min_x,
        "min_y": min_y,
        "min_z": min_z,
        "max_x": max_x,
        "max_y": max_y,
        "max_z": max_z,
        "width": max_x - min_x,
        "depth": max_y - min_y,
        "height": max_z - min_z,
    }


def _write_metadata(
    scene: dict,
    output_dir: Path,
    generation_mode: str,
    procedural_objects: list[str],
    warnings: list[str],
    camera_metadata: dict,
    asset_imports: list[dict] | None = None,
    bounding_box_m: dict | None = None,
    segment_connectivity: dict | None = None,
    blender_runtime: dict | None = None,
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
    payload = {
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
        "segment_connectivity": segment_connectivity
        or {
            "status": "not_available",
            "passed": False,
            "evaluated_segment_count": 0,
            "failed_segment_count": 0,
            "maximum_endpoint_error_m": None,
            "tolerance_m": 0.001,
        },
        "blender_runtime": blender_runtime,
        "warnings": all_warnings,
    }
    if bounding_box_m is not None:
        payload["bounding_box_m"] = bounding_box_m
    (output_dir / "scene_metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _blender_runtime_metadata(bpy) -> dict:
    build_hash = getattr(bpy.app, "build_hash", b"")
    if isinstance(build_hash, bytes):
        build_hash = build_hash.decode("utf-8", errors="replace")
    return {
        "version": str(bpy.app.version_string),
        "version_tuple": [int(value) for value in bpy.app.version],
        "build_hash": str(build_hash),
        "background": bool(bpy.app.background),
        "factory_startup": True,
    }


def _assets_used(scene: dict) -> list[str]:
    assets = [scene["tower"]["asset_id"]]
    for sector in scene["sectors"]:
        assets.append(sector["antenna_asset_id"])
        if sector.get("radio_asset_id"):
            assets.append(sector["radio_asset_id"])
    for accessory in scene.get("accessory_assets", []):
        assets.append(accessory["asset_id"])
    return sorted(set(assets))


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
    mode = "not_generated_no_blender"
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
        "generation_success": False,
        "asset_dimensions_checked": False,
        "manifest_dimensions_m": dimensions,
        "import_fallback_allowed": fallback_allowed,
        "import_mode": mode,
        "effective_generation_mode": mode,
        "effective_geometry_source": "missing",
        "imported_object_count": 0,
        "imported_object_names": [],
        "generated_object_count": 0,
        "generated_object_names": [],
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
        "stretched_imported_glb_count": modes.get("stretched_imported_glb", 0),
        "procedural_fallback_count": modes.get("procedural_fallback", 0),
        "not_generated_no_blender_count": modes.get("not_generated_no_blender", 0),
        "missing_file_count": modes.get("missing_file", 0),
        "parametric_generated_count": modes.get("parametric_generated", 0),
        "internal_project_generated_count": modes.get("internal_project_generated", 0),
        "import_success_count": sum(
            1 for record in asset_imports if record.get("asset_import_success") is True
        ),
        "generation_success_count": sum(
            1 for record in asset_imports if record.get("generation_success") is True
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
    if asset_source == "internal_project_generated":
        warnings.append("INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE")
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
        "camera": "not_rendered",
        "camera_type": "not_rendered",
        "requested_camera": scene.get("preview", {}).get("camera", "isometric"),
        "target": [0.0, 0.0, round(tower_height * 0.52, 3)],
        "ortho_scale": round(max(tower_height * 1.28, 18.0), 3),
        "background": "not_rendered",
    }


if __name__ == "__main__":
    raise SystemExit(main())
