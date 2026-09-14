"""Controlled Blender worker for SceneSpec-based telecom scene generation.

Usage:
    blender -b --python apps/blender_worker/generate_scene.py -- scene_spec.json output_dir

The script is intentionally SceneSpec-driven. It does not execute LLM-generated code.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

# Prefer the immutable sibling snapshot prepared by BlenderRunner. Normal
# repository execution resolves the same sibling module. No worker dependency
# is imported later from a mutable project-root package.
_WORKER_ROOT = Path(__file__).resolve().parent
if str(_WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKER_ROOT))

import component_proofs  # noqa: E402
import geometry_program_compiler  # noqa: E402
import parametric_builder  # noqa: E402
import trusted_assembly  # noqa: E402


def main() -> int:
    scene_spec_path, output_dir = _parse_args(sys.argv)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = json.loads(scene_spec_path.read_text(encoding="utf-8"))
    project_root = Path.cwd().resolve()
    assembly_validation = trusted_assembly.validate_trusted_assembly(scene, project_root)

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
    if scene.get("tower") is not None:
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
    _create_geometry_programs(
        bpy,
        scene,
        procedural_objects,
        asset_imports,
        asset_warnings,
    )
    _create_remaining_assembly_routes(
        bpy,
        scene,
        procedural_objects,
        asset_imports,
        asset_warnings,
    )
    _create_assembly_constraint_anchors(bpy, scene)
    camera_metadata = _create_camera_and_light(bpy, scene)
    segment_connectivity = _validate_parametric_segment_connectivity(bpy)
    component_proof_report = None
    component_proof_metadata = None
    if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0" or scene.get(
        "geometry_programs"
    ):
        component_proof_report = component_proofs.build_component_proof_report(
            bpy,
            scene,
            asset_imports,
            assembly_validation,
        )
        component_proofs.verify_component_proof_report(component_proof_report, scene)
        component_proof_path = output_dir / "component_proofs.json"
        component_proof_path.write_text(
            json.dumps(component_proof_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        component_proof_metadata = {
            "file_name": component_proof_path.name,
            "sha256": _sha256_file(component_proof_path),
            "report_sha256": component_proof_report["report_sha256"],
            "component_count": len(component_proof_report["components"]),
            "geometry_program_count": len(component_proof_report["geometry_programs"]),
            "passed": True,
        }

    glb_path = output_dir / "design.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", export_extras=True)
    bounding_box_m = _compute_scene_bounding_box(bpy)
    camera_metadata["render_backdrop"] = "preview_only_light_plane"
    camera_metadata["preview_views"] = _render_preview_views(
        bpy,
        scene,
        output_dir,
    )
    camera_metadata["sector_preview_views"] = _render_sector_preview_views(
        bpy,
        scene,
        output_dir,
    )
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
        assembly_validation,
        component_proof_metadata,
    )
    return 0


def _create_geometry_programs(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    programs = list(scene.get("geometry_programs") or [])
    if not programs:
        return
    records = geometry_program_compiler.compile_geometry_programs(bpy, programs)
    for program, record in zip(programs, records, strict=True):
        if record.get("exact_asset_evidence"):
            evidence = record["exact_asset_evidence"][0]
            manifest = evidence["manifest"]
            limitations = list((manifest.get("qualification") or {}).get("limitations", []))
            asset_imports.append(
                {
                    "asset_id": evidence["asset_id"],
                    "asset_file": evidence["asset_file"],
                    "asset_source": manifest.get("source"),
                    "object_role": record["semantic_role"],
                    "object_name": record["object_name"],
                    "asset_file_exists": True,
                    "asset_import_success": True,
                    "generation_success": True,
                    "asset_import_attempted": True,
                    "import_fallback_allowed": False,
                    "import_mode": "imported_glb_exact",
                    "effective_generation_mode": "imported_glb_exact",
                    "effective_geometry_source": "imported_glb_exact",
                    "scale_factors": [1.0, 1.0, 1.0],
                    "asset_dimensions_checked": False,
                    "warnings": limitations,
                    "generated_object_names": record["generated_object_names"],
                    "source_provenance": {
                        key: value for key, value in evidence.items() if key != "manifest"
                    },
                    "geometry_fidelity": manifest.get("geometry_fidelity", "technical_generic"),
                    "asset_metadata": {
                        "qualification_status": "qualified_for_generation",
                        "qualification_limitations": limitations,
                        "license": manifest.get("license"),
                        "attribution": manifest.get("attribution"),
                    },
                }
            )
            asset_warnings.extend(limitations)
            continue
        geometry_program_profile = (
            "typed_geometry_program_v2"
            if str(program.get("schema_version")) == "2.0.0"
            else "typed_geometry_program_v1"
        )
        program_payload = json.dumps(
            program,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        program_sha256 = hashlib.sha256(program_payload).hexdigest()
        _record_asset_generation(
            asset_imports,
            asset_warnings,
            asset_id=f"GEOMETRY_PROGRAM_{record['program_id'].upper()}",
            asset_file=None,
            asset_source="llm_geometry_program"
            if record["authorship"] == "llm_generated"
            else "deterministic_geometry_program",
            asset_metadata={
                "geometry_fidelity": "technical_generic",
                "qualification_status": "validated_geometry_program",
                "allowed_generation_modes": ["internal_project_generated"],
                "qualification_method": geometry_program_profile,
                "geometry_program_schema_version": record["schema_version"],
                "qualification_limitations": record["limitations"],
                "program_sha256": program_sha256,
                "program_authorship": record["authorship"],
                "requested_quantity": record["requested_quantity"],
                "generator_provider": record["generator_provider"],
                "generator_model": record["generator_model"],
                "structured_output_mode": record["structured_output_mode"],
                "source_prompt_sha256": record["source_prompt_sha256"],
                "deterministic_adjustments": record["deterministic_adjustments"],
            },
            object_role=record["semantic_role"],
            object_name=record["object_name"],
            dimensions=None,
            location=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
            generation_strategy="internal_project_generated",
            generated_object_names=record["generated_object_names"],
        )
        procedural_objects.append(f"geometry_program:{record['program_id']}")


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


def _select_render_engine(available_engines: set[str], requested_engine: str | None) -> str:
    supported = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH")
    requested = (requested_engine or "").strip()
    if requested:
        if requested not in supported:
            raise RuntimeError(f"Unsupported governed Blender render engine: {requested}")
        if requested not in available_engines:
            raise RuntimeError(f"Requested Blender render engine is unavailable: {requested}")
        return requested
    for engine in supported:
        if engine in available_engines:
            return engine
    raise RuntimeError("No governed Blender render engine is available")


def _governed_eevee_render_samples(raw_value: str | None) -> int | None:
    requested = (raw_value or "").strip()
    if not requested:
        return None
    try:
        samples = int(requested)
    except ValueError as exc:
        raise RuntimeError("EEVEE render samples must be an integer") from exc
    if samples < 1 or samples > 64:
        raise RuntimeError("EEVEE render samples must be between 1 and 64")
    return samples


def _configure_scene(bpy, scene: dict) -> None:
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    engines = {
        item.identifier for item in bpy.context.scene.render.bl_rna.properties["engine"].enum_items
    }
    bpy.context.scene.render.engine = _select_render_engine(
        engines,
        os.getenv("TELECOM_STUDIO_BLENDER_RENDER_ENGINE"),
    )
    eevee_samples = _governed_eevee_render_samples(
        os.getenv("TELECOM_STUDIO_BLENDER_EEVEE_RENDER_SAMPLES")
    )
    if eevee_samples is not None:
        if not hasattr(bpy.context.scene, "eevee") or not hasattr(
            bpy.context.scene.eevee, "taa_render_samples"
        ):
            raise RuntimeError("Governed EEVEE render samples are unavailable")
        bpy.context.scene.eevee.taa_render_samples = eevee_samples
    width, height = scene["preview"]["resolution"]
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world.color = (0.04, 0.055, 0.072)
    bpy.context.scene.world.use_nodes = True
    world_background = bpy.context.scene.world.node_tree.nodes.get("Background")
    if world_background is not None:
        world_background.inputs["Color"].default_value = (0.04, 0.055, 0.072, 1)
        world_background.inputs["Strength"].default_value = 0.48
    bpy.context.scene.render.film_transparent = False
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.resolution_percentage = 100
    if bpy.context.scene.render.engine == "BLENDER_WORKBENCH":
        shading = bpy.context.scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "COLOR"
        shading.background_color = (0.04, 0.055, 0.072)
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
    bpy.context.scene.view_settings.exposure = 0.75
    bpy.context.scene.view_settings.gamma = 1


def _create_ground_plane(bpy, scene: dict) -> None:
    has_terrain = any(
        node.get("kind") == "terrain"
        for program in scene.get("geometry_programs", [])
        for node in program.get("nodes", [])
    )
    if has_terrain:
        return
    tower = scene.get("tower")
    # A generic cognitive scene must contain only planned/programmed geometry.
    # Adding an undeclared floor would be a hardcoded design component and would
    # also pollute framing QA. Telecom V1 retains its established technical pad.
    if tower is None:
        return
    size = max(14.0, float(tower["height_m"]) * 0.6)
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.02))
    ground = bpy.context.object
    ground.name = "technical_ground_plane"
    ground.data.materials.append(_material(bpy, "matte_ground", (0.12, 0.16, 0.20, 1)))


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
    paint_color_hex = characteristics.get("paint_color_hex") or None
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
            paint_color_hex=paint_color_hex,
        )
        tower_root = _create_semantic_group(
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
        if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
            _stamp_component_execution(
                tower_root,
                scene,
                "support_structure",
                "global",
                expected_handler="tower_structure",
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
        exact_boundary = trusted_assembly.exact_asset_boundary(
            scene,
            role_id="support_structure",
            asset_id=scene["tower"]["asset_id"],
            project_root=Path.cwd().resolve(),
        )
        tower_location = _asset_placement_location(
            (0.0, 0.0, height / 2),
            scene["tower"].get("asset_metadata"),
            "tower",
        )
        tower_mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=scene["tower"]["asset_id"],
            asset_file=exact_boundary["asset_file"],
            asset_source=scene["tower"].get("asset_source"),
            asset_metadata={
                **(scene["tower"].get("asset_metadata") or {}),
                "verified_file_sha256": exact_boundary["verified_file_sha256"],
            },
            fallback_allowed=False,
            object_role="tower",
            object_name=semantic_root,
            location=tower_location,
            rotation=(0.0, 0.0, 0.0),
            dimensions=exact_boundary.get("dimensions_m")
            or scene["tower"].get("dimensions_m")
            or {
                "width": base_width,
                "depth": base_width,
                "height": height,
            },
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={
                "tower_material": material_name,
                **_component_execution_properties(
                    scene,
                    "support_structure",
                    "global",
                    expected_handler="tower_structure",
                ),
            },
            exact_boundary=exact_boundary,
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
                paint_color_hex=paint_color_hex,
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
    _create_tower_accessories(bpy, scene, height, characteristics, procedural_objects)


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


def _platform_support_segments(
    scene: dict,
    *,
    face: float,
    level: float,
    width: float,
    thickness: float,
    support_radius: float,
    support_offset: float,
    support_drop: float,
    deck_center_radius: float,
) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    """Return two visible struts from tower legs to the deck underside.

    These remain bounded, project-authored access geometry.  Their placement
    proves geometric continuity only; it does not claim a structural design.
    """

    start_z = level - support_drop
    if start_z <= support_radius:
        raise RuntimeError("TOWER_ACCESS_PLATFORM_SUPPORT_BELOW_GROUND")
    end_z = level - thickness - support_radius
    tower_radius = _tower_radius_at_height(scene, start_z, face)
    start_radius = tower_radius + support_radius
    start_tangent = min(tower_radius, width / 2 - support_radius)
    outward = (math.sin(face), math.cos(face))
    tangent = (math.cos(face), -math.sin(face))

    def point(radial: float, tangential: float, z: float) -> tuple[float, float, float]:
        return (
            outward[0] * radial + tangent[0] * tangential,
            outward[1] * radial + tangent[1] * tangential,
            z,
        )

    return tuple(
        (
            point(start_radius, sign * start_tangent, start_z),
            point(deck_center_radius, sign * support_offset, end_z),
        )
        for sign in (-1.0, 1.0)
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


def _canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _create_tower_accessories(
    bpy,
    scene: dict,
    height: float,
    characteristics: dict,
    procedural_objects: list[str],
) -> None:
    """Create bounded tower access from a manifest-authored profile when present.

    Legacy scenes intentionally retain the prior accessory geometry.  A profile
    only activates when the user actually requested access and the tower is a
    lattice structure; it is internal technical procedural geometry, never a
    manufacturer installation or safety certification.
    """

    profile = scene["tower"].get("tower_access_geometry_profile")
    profile_active = (
        isinstance(profile, dict)
        and characteristics.get("structure") == "lattice"
        and bool(characteristics.get("has_ladder") or characteristics.get("has_platform"))
    )
    if profile_active:
        _create_profiled_tower_access_assembly(
            bpy,
            scene,
            height,
            characteristics,
            profile,
            procedural_objects,
        )
        _create_non_access_tower_accessories(bpy, height, characteristics, procedural_objects)
        return
    _create_legacy_tower_accessories(bpy, height, characteristics, procedural_objects)


def _create_legacy_tower_accessories(
    bpy,
    height: float,
    characteristics: dict,
    procedural_objects: list[str],
) -> None:
    """Keep the pre-profile output stable for persisted legacy SceneSpecs."""

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
    _create_non_access_tower_accessories(bpy, height, characteristics, procedural_objects)


def _create_non_access_tower_accessories(
    bpy,
    height: float,
    characteristics: dict,
    procedural_objects: list[str],
) -> None:
    steel = _material(bpy, "accessory_steel", (0.42, 0.44, 0.46, 1))
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


def _create_profiled_tower_access_assembly(
    bpy,
    scene: dict,
    height: float,
    characteristics: dict,
    profile: dict,
    procedural_objects: list[str],
) -> None:
    """Build one side-mounted, measurable access assembly from profile values."""

    asset_id = str(scene["tower"]["asset_id"])
    semantic_root = f"tower_access_{asset_id}"
    family = str(profile["family"])
    profile_sha256 = _canonical_json_sha256(profile)
    face = math.radians(float(profile["access_face_azimuth_deg"]))
    outward = (math.sin(face), math.cos(face))
    tangent = (math.cos(face), -math.sin(face))
    steel = _material(bpy, "tower_access_steel", (0.34, 0.37, 0.40, 1))
    toe_material = _material(bpy, "tower_access_toe_board", (0.28, 0.31, 0.34, 1))
    access_objects: list = []

    def point(radial: float, tangential: float, z: float) -> tuple[float, float, float]:
        return (
            outward[0] * radial + tangent[0] * tangential,
            outward[1] * radial + tangent[1] * tangential,
            z,
        )

    def properties(
        feature: str,
        *,
        platform_index: int | None = None,
        level: float | None = None,
    ) -> dict:
        values = {
            "tower_access_feature": feature,
            "tower_access_profile_family": family,
            "tower_access_profile_sha256": profile_sha256,
        }
        if platform_index is not None:
            values["tower_access_platform_index"] = platform_index
        if level is not None:
            values["tower_access_requested_level_m"] = level
        return values

    def tag(
        obj,
        feature: str,
        *,
        platform_index: int | None = None,
        level: float | None = None,
    ) -> None:
        for key, value in properties(feature, platform_index=platform_index, level=level).items():
            obj[key] = value

    def cylinder(
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        radius: float,
        name: str,
        feature: str,
        *,
        platform_index: int | None = None,
        level: float | None = None,
    ):
        obj = _create_cylinder_between(bpy, start, end, radius, name, steel)
        tag(obj, feature, platform_index=platform_index, level=level)
        access_objects.append(obj)
        return obj

    def box(
        *,
        radial: float,
        tangential: float,
        z: float,
        dimensions: tuple[float, float, float],
        name: str,
        feature: str,
        material,
        platform_index: int,
        level: float,
    ):
        bpy.ops.mesh.primitive_cube_add(size=1, location=point(radial, tangential, z))
        obj = bpy.context.object
        obj.name = name
        obj.rotation_euler = (0.0, 0.0, -face)
        obj.dimensions = dimensions
        obj.data.materials.append(material)
        tag(obj, feature, platform_index=platform_index, level=level)
        access_objects.append(obj)
        return obj

    if characteristics.get("has_ladder"):
        base_z = float(profile["ladder_base_clearance_m"])
        top_z = height - float(profile["ladder_top_clearance_m"])
        ladder_width = float(profile["ladder_width_m"])
        clearance = float(profile["ladder_tower_clearance_m"])
        rail_radius = float(profile["ladder_rail_radius_m"])
        rail_start_radius = _tower_radius_at_height(scene, base_z, face) + clearance
        rail_top_radius = _tower_radius_at_height(scene, top_z, face) + clearance
        for side, tangential in (("left", -ladder_width / 2), ("right", ladder_width / 2)):
            cylinder(
                point(rail_start_radius, tangential, base_z),
                point(rail_top_radius, tangential, top_z),
                rail_radius,
                f"tower_access_ladder_rail_{side}",
                "ladder_rail",
            )
        spacing = float(profile["ladder_rung_spacing_m"])
        rung_count = max(2, int(math.floor((top_z - base_z) / spacing)) + 1)
        for index in range(rung_count):
            z = min(top_z, base_z + index * spacing)
            radius = _tower_radius_at_height(scene, z, face) + clearance
            cylinder(
                point(radius, -ladder_width / 2, z),
                point(radius, ladder_width / 2, z),
                float(profile["ladder_rung_radius_m"]),
                f"tower_access_ladder_rung_{index + 1}",
                "ladder_rung",
            )
        procedural_objects.append("tower_access:ladder")

    if characteristics.get("has_platform"):
        count = max(1, int(characteristics.get("platform_count") or 1))
        explicit_levels = characteristics.get("platform_levels_m")
        levels = (
            [float(value) for value in explicit_levels]
            if isinstance(explicit_levels, list) and explicit_levels
            else [
                height
                * (
                    float(profile["legacy_platform_start_height_ratio"])
                    + float(profile["legacy_platform_span_height_ratio"]) * index / max(count, 1)
                )
                for index in range(count)
            ]
        )
        width = float(profile["platform_width_m"])
        depth = float(profile["platform_depth_m"])
        thickness = float(profile["platform_thickness_m"])
        guardrail_height = float(profile["platform_guardrail_height_m"])
        guardrail_radius = float(profile["platform_guardrail_radius_m"])
        toe_height = float(profile["platform_toe_board_height_m"])
        toe_thickness = float(profile["platform_toe_board_thickness_m"])
        deck_clearance = float(profile["platform_tower_clearance_m"])
        support_radius = float(profile["platform_support_radius_m"])
        support_offset = width * float(profile["platform_support_tangent_offset_ratio"])
        for platform_index, level in enumerate(levels, start=1):
            tower_radius = _tower_radius_at_height(scene, level, face)
            center_radius = tower_radius + deck_clearance + depth / 2
            inner_radius = center_radius - depth / 2
            outer_radius = center_radius + depth / 2
            deck_center_z = level - thickness / 2
            box(
                radial=center_radius,
                tangential=0.0,
                z=deck_center_z,
                dimensions=(width, depth, thickness),
                name=f"tower_access_platform_deck_{platform_index}",
                feature="platform_deck",
                material=steel,
                platform_index=platform_index,
                level=level,
            )
            # Top rails around the three exposed sides; the inward face remains
            # open for ladder/tower access and does not claim a compliant gate.
            rail_z = level + guardrail_height
            cylinder(
                point(outer_radius, -width / 2, rail_z),
                point(outer_radius, width / 2, rail_z),
                guardrail_radius,
                f"tower_access_guardrail_outer_{platform_index}",
                "guardrail",
                platform_index=platform_index,
                level=level,
            )
            for side, tangential in (("left", -width / 2), ("right", width / 2)):
                cylinder(
                    point(inner_radius, tangential, rail_z),
                    point(outer_radius, tangential, rail_z),
                    guardrail_radius,
                    f"tower_access_guardrail_{side}_{platform_index}",
                    "guardrail",
                    platform_index=platform_index,
                    level=level,
                )
            for radial, tangential in (
                (inner_radius, -width / 2),
                (inner_radius, width / 2),
                (outer_radius, -width / 2),
                (outer_radius, width / 2),
            ):
                cylinder(
                    point(radial, tangential, level),
                    point(radial, tangential, rail_z),
                    guardrail_radius,
                    f"tower_access_guardrail_post_{platform_index}_{radial:.3f}_{tangential:.3f}",
                    "guardrail",
                    platform_index=platform_index,
                    level=level,
                )
            toe_center_z = level + toe_height / 2
            box(
                radial=outer_radius - toe_thickness / 2,
                tangential=0.0,
                z=toe_center_z,
                dimensions=(width, toe_thickness, toe_height),
                name=f"tower_access_toe_board_outer_{platform_index}",
                feature="toe_board",
                material=toe_material,
                platform_index=platform_index,
                level=level,
            )
            for side, tangential in (("left", -width / 2), ("right", width / 2)):
                box(
                    radial=center_radius,
                    tangential=tangential,
                    z=toe_center_z,
                    dimensions=(toe_thickness, depth, toe_height),
                    name=f"tower_access_toe_board_{side}_{platform_index}",
                    feature="toe_board",
                    material=toe_material,
                    platform_index=platform_index,
                    level=level,
                )
            support_drop = profile.get("platform_support_drop_m")
            if support_drop is not None:
                support_segments = _platform_support_segments(
                    scene,
                    face=face,
                    level=level,
                    width=width,
                    thickness=thickness,
                    support_radius=support_radius,
                    support_offset=support_offset,
                    support_drop=float(support_drop),
                    deck_center_radius=center_radius,
                )
                for support_index, (start, end) in enumerate(support_segments, start=1):
                    cylinder(
                        start,
                        end,
                        support_radius,
                        f"tower_access_platform_support_{platform_index}_{support_index}",
                        "platform_support",
                        platform_index=platform_index,
                        level=level,
                    )
            else:
                # Preserve the established geometry for historical profiles.
                for tangential in (-support_offset, support_offset):
                    cylinder(
                        point(tower_radius + 0.02, tangential, deck_center_z),
                        point(inner_radius, tangential, deck_center_z),
                        support_radius,
                        f"tower_access_platform_support_{platform_index}_{tangential:.3f}",
                        "platform_support",
                        platform_index=platform_index,
                        level=level,
                    )
            procedural_objects.append(f"tower_access:platform:{platform_index}")

    if access_objects:
        _create_semantic_group(
            bpy,
            semantic_root,
            access_objects,
            role="tower_access",
            properties={
                "tower_access_profile_family": family,
                "tower_access_profile_sha256": profile_sha256,
                "tower_access_generation": "manifest_bounded_procedural",
                **_classification_properties("parametric_generated"),
            },
        )


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

        # The bracket is built in its manifest-local frame and then placed by
        # the connector compiler.  Legacy SceneSpecs keep the previous bounded
        # geometric placement path.
        bracket_instance = _assembly_operation_instance(
            scene,
            "mount-to-support",
            sector_id,
        )
        if bracket_instance is not None:
            bracket_component = trusted_assembly.component_boundary(scene, "antenna_mount")
            bracket_snapshot = bracket_component["manifest_snapshot"]
            anchors = {anchor["anchor_id"]: anchor for anchor in bracket_snapshot["anchors"]}
            clamp = tuple(anchors["tower_clamp"]["position_m"])
            rail = tuple(anchors["antenna_rail"]["position_m"])
            bracket_part = _create_cylinder_between(
                bpy,
                clamp,
                rail,
                0.035,
                f"mount_bracket_{sector_id}_arm",
                _material(bpy, "mount_steel", (0.42, 0.44, 0.46, 1)),
            )
            bracket = _create_semantic_group(
                bpy,
                f"mount_bracket_{sector_id}",
                [bracket_part],
                role="mount_bracket",
                sector_id=sector_id,
                properties={
                    "requested_azimuth_deg": azimuth_deg,
                    "requested_hba_m": z,
                    **_classification_properties("internal_project_generated"),
                },
            )
            _apply_resolved_instance_transform(bracket, bracket_instance)
            radio_mount_instance = _assembly_operation_instance(
                scene,
                "radio-to-mount",
                sector_id,
            )
            if radio_mount_instance is not None:
                radio_mount_operation = _assembly_operation(scene, "radio-to-mount")
                support_contract = _resolved_support_anchor_contract(
                    radio_mount_operation,
                    anchors,
                    endpoint="target",
                )
                _create_radio_adapter_geometry(
                    bpy,
                    bracket,
                    support_contract,
                    radio_mount_instance,
                    sector_id,
                )
            bracket_operation_ids = ["assembly:mount-to-support"]
            if radio_mount_instance is not None:
                bracket_operation_ids.append("assembly:radio-to-mount")
        else:
            bracket_part = _create_mounting_bracket(
                bpy,
                tower_radius,
                mount_radius,
                azimuth,
                z,
            )
            bracket = _create_semantic_group(
                bpy,
                f"mount_bracket_{sector_id}",
                [bracket_part],
                role="mount_bracket",
                sector_id=sector_id,
                properties={
                    "requested_azimuth_deg": azimuth_deg,
                    "requested_hba_m": z,
                    **_classification_properties("internal_project_generated"),
                },
            )
            bracket_operation_ids = []
        if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
            _stamp_component_execution(
                bracket,
                scene,
                "antenna_mount",
                sector_id,
                expected_handler="mount_bracket",
                operation_ids=bracket_operation_ids,
            )
        bracket_plan = _assembly_component(scene, "antenna_mount")
        if bracket_plan:
            _record_asset_generation(
                asset_imports,
                asset_warnings,
                asset_id=bracket_plan.get("selected_asset_id"),
                asset_file=None,
                asset_source="internal_project_generated",
                asset_metadata=None,
                object_role="mount_bracket",
                object_name=f"mount_bracket_{sector_id}",
                dimensions=None,
                location=tuple(bracket.location),
                rotation=tuple(bracket.rotation_euler),
                generation_strategy="internal_project_generated",
                generated_object_names=_semantic_tree_names(bracket),
            )
        procedural_objects.append(f"mount_bracket:{sector_id}")

        electrical_tilt_deg = float(sector.get("electrical_tilt_deg") or 0.0)
        beam_downtilt_deg = tilt_deg + electrical_tilt_deg
        antenna_strategy = sector.get("antenna_generation_strategy", "internal_project_generated")
        antenna_instance = _assembly_operation_instance(
            scene,
            "antenna-to-mount",
            sector_id,
        )
        antenna_location = (
            tuple(float(value) for value in antenna_instance["translation_m"])
            if antenna_instance is not None
            else (x, y, z)
        )
        # The record uses equivalent engineering angles. The actual transform
        # is quaternion yaw(Z) followed by downtilt(local X).
        antenna_rotation = (math.radians(-tilt_deg), 0.0, -azimuth)
        if antenna_instance is not None:
            antenna_rotation = tuple(
                math.radians(float(value)) for value in antenna_instance["rotation_deg"]
            )
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
        if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
            antenna_properties.update(
                _component_execution_properties(
                    scene,
                    "sector_antenna",
                    sector_id,
                    expected_handler="sector_equipment",
                    operation_ids=["assembly:antenna-to-mount"],
                )
            )
        if antenna_strategy == "imported_glb_exact":
            antenna_boundary = trusted_assembly.exact_asset_boundary(
                scene,
                role_id="sector_antenna",
                asset_id=sector["antenna_asset_id"],
                project_root=Path.cwd().resolve(),
            )
            antenna_mode = _try_import_glb_asset(
                bpy=bpy,
                asset_id=sector["antenna_asset_id"],
                asset_file=antenna_boundary["asset_file"],
                asset_source=sector.get("antenna_asset_source"),
                asset_metadata={
                    **(sector.get("antenna_asset_metadata") or {}),
                    "verified_file_sha256": antenna_boundary["verified_file_sha256"],
                },
                fallback_allowed=False,
                object_role="antenna",
                object_name=antenna_object_name,
                location=antenna_location,
                rotation=antenna_rotation,
                # Compiled assembly rotations are an XYZ Euler decomposition.
                # Legacy scenes retain the historical ZXY sector convention.
                rotation_mode="XYZ" if antenna_instance is not None else "ZXY",
                dimensions=antenna_boundary.get("dimensions_m")
                or sector.get("antenna_dimensions_m"),
                asset_imports=asset_imports,
                warnings=asset_warnings,
                semantic_properties=antenna_properties,
                exact_boundary=antenna_boundary,
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
            if antenna_instance is not None:
                _apply_resolved_instance_transform(antenna_root, antenna_instance)
            if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
                _stamp_component_execution(
                    antenna_root,
                    scene,
                    "sector_antenna",
                    sector_id,
                    expected_handler="sector_equipment",
                    operation_ids=["assembly:antenna-to-mount"],
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
            radio_profile = sector.get("radio_geometry_profile") or {}
            radio_vertical_offset = float(radio_profile.get("vertical_offset_m") or 1.0)
            radio_radial_inset = float(radio_profile.get("radial_inset_m") or 0.0)
            radio_location = (
                x - (math.sin(azimuth) * radio_radial_inset),
                y - (math.cos(azimuth) * radio_radial_inset),
                z - radio_vertical_offset,
            )
            radio_instance = _assembly_operation_instance(
                scene,
                "radio-to-mount",
                sector_id,
            )
            if radio_instance is not None:
                radio_location = tuple(float(value) for value in radio_instance["translation_m"])
            radio_rotation = (
                tuple(math.radians(float(value)) for value in radio_instance["rotation_deg"])
                if radio_instance is not None
                else (0.0, 0.0, 0.0)
            )
            radio_object_name = f"radio_{sector_id}_{sector['radio_asset_id']}"
            radio_properties = {
                "sector_id": sector_id,
                "install_height_m": radio_location[2],
                "requested_azimuth_deg": azimuth_deg,
                "requested_hba_m": z,
            }
            if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
                radio_properties.update(
                    _component_execution_properties(
                        scene,
                        "remote_radio",
                        sector_id,
                        expected_handler="radio_enclosure",
                        operation_ids=["assembly:radio-to-mount"],
                    )
                )
            if radio_strategy == "imported_glb_exact":
                radio_boundary = trusted_assembly.exact_asset_boundary(
                    scene,
                    role_id="remote_radio",
                    asset_id=sector["radio_asset_id"],
                    project_root=Path.cwd().resolve(),
                )
                radio_mode = _try_import_glb_asset(
                    bpy=bpy,
                    asset_id=sector["radio_asset_id"],
                    asset_file=radio_boundary["asset_file"],
                    asset_source=sector.get("radio_asset_source"),
                    asset_metadata={
                        **(sector.get("radio_asset_metadata") or {}),
                        "verified_file_sha256": radio_boundary["verified_file_sha256"],
                    },
                    fallback_allowed=False,
                    object_role="radio",
                    object_name=radio_object_name,
                    location=radio_location,
                    rotation=radio_rotation,
                    rotation_mode="XYZ",
                    dimensions=radio_boundary.get("dimensions_m")
                    or sector.get("radio_dimensions_m"),
                    asset_imports=asset_imports,
                    warnings=asset_warnings,
                    semantic_properties=radio_properties,
                    exact_boundary=radio_boundary,
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
                            "install_height_m": radio_location[2],
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
                if radio_instance is not None:
                    _apply_resolved_instance_transform(radio_root, radio_instance)
                if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
                    _stamp_component_execution(
                        radio_root,
                        scene,
                        "remote_radio",
                        sector_id,
                        expected_handler="radio_enclosure",
                        operation_ids=["assembly:radio-to-mount"],
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
                    rotation=radio_rotation,
                    generation_strategy=radio_strategy,
                    generated_object_names=_semantic_tree_names(radio_root),
                )

        if sector.get("include_cable"):
            tower_entry_radius = max(tower_radius * 0.82, 0.18)
            route_points = [
                (x, y, z - 0.65),
                radio_location
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
            cable_instance = _assembly_operation_instance(
                scene,
                "radio-to-base-route",
                sector_id,
            )
            if cable_instance is not None:
                route_points = [
                    tuple(float(value) for value in point)
                    for point in cable_instance["route_points_m"]
                ]
            cable_plan = _assembly_component(scene, "sector_cable_route")
            cable_diameter = float(
                ((cable_plan or {}).get("parameter_values") or {}).get(
                    "cable_diameter_m",
                    0.05,
                )
            )
            cable = _create_cable(
                bpy,
                sector_id,
                route_points,
                diameter_m=cable_diameter,
            )
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
            if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
                _stamp_component_execution(
                    cable,
                    scene,
                    "sector_cable_route",
                    sector_id,
                    expected_handler="cable_route",
                    operation_ids=["assembly:radio-to-base-route"],
                )
            procedural_objects.append(f"cable:{sector_id}")
            if cable_plan:
                _record_asset_generation(
                    asset_imports,
                    asset_warnings,
                    asset_id=cable_plan.get("selected_asset_id") or "PROCEDURAL_CABLE_ROUTE",
                    asset_file=None,
                    asset_source="internal_project_generated",
                    asset_metadata=None,
                    object_role="cable",
                    object_name=f"cable_{sector_id}",
                    dimensions=None,
                    location=route_points[0],
                    rotation=(0.0, 0.0, 0.0),
                    generation_strategy=str(
                        cable_plan.get("generation_strategy") or "internal_project_generated"
                    ),
                    generated_object_names=[cable.name],
                )

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
            geometry_profile=sector.get("antenna_geometry_profile"),
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
        geometry_profile=sector.get("radio_geometry_profile"),
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
    metadata = sector.get("antenna_asset_metadata") or {}
    builder = trusted_assembly.resolve_component_builder(
        scene,
        role_id="sector_antenna",
        runtime_builder_profile_id=metadata.get("builder_profile_id"),
        project_root=Path.cwd().resolve(),
    )
    if builder.get("worker_handler") != "sector_equipment":
        raise RuntimeError("ASSEMBLY_ANTENNA_BUILDER_HANDLER_INVALID")
    family = builder.get("geometry_family")
    if family not in {"panel", "microwave_dish"}:
        raise RuntimeError(f"ASSEMBLY_ANTENNA_GEOMETRY_FAMILY_UNSUPPORTED:{family}")
    return str(family)


def _create_cable(
    bpy,
    sector_id: str,
    route_points: list[tuple[float, float, float]],
    *,
    diameter_m: float = 0.05,
    name_prefix: str = "cable",
) -> object:
    curve = bpy.data.curves.new(f"{name_prefix}_{sector_id}", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 8
    curve.bevel_depth = max(0.0025, float(diameter_m) / 2.0)
    spline = curve.splines.new("POLY")
    spline.points.add(len(route_points) - 1)
    for point, coordinate in zip(spline.points, route_points, strict=True):
        point.co = (*coordinate, 1)
    obj = bpy.data.objects.new(f"{name_prefix}_{sector_id}", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(_material(bpy, "cable_sheath_black", (0.035, 0.045, 0.055, 1)))
    return obj


def _assembly_component(scene: dict, role_id: str) -> dict | None:
    plan = scene.get("assembly_plan") or {}
    return next(
        (item for item in plan.get("components", []) if item.get("role_id") == role_id),
        None,
    )


def _assembly_operation_instance(
    scene: dict,
    connection_id: str,
    instance_id: str,
) -> dict | None:
    plan = scene.get("assembly_plan") or {}
    if plan.get("schema_version") != "1.1.0":
        return None
    return trusted_assembly.operation_instance(
        scene,
        connection_id=connection_id,
        instance_id=instance_id,
    )


def _assembly_operation(scene: dict, connection_id: str) -> dict:
    operation = next(
        (
            item
            for item in (scene.get("assembly_plan") or {}).get("operations", [])
            if item.get("connection_id") == connection_id
        ),
        None,
    )
    if not isinstance(operation, dict):
        raise RuntimeError(f"ASSEMBLY_OPERATION_MISSING:{connection_id}")
    return operation


def _resolved_support_anchor_contract(
    operation: dict,
    anchors: dict[str, dict],
    *,
    endpoint: str,
) -> dict:
    """Resolve a physical support only from the immutable operation snapshot."""

    if endpoint not in {"source", "target"}:
        raise RuntimeError(f"ASSEMBLY_RESOLVED_SUPPORT_ENDPOINT_INVALID:{endpoint}")
    anchor = operation.get(f"{endpoint}_anchor")
    role_id = operation.get(f"{endpoint}_role_id")
    connection_id = str(operation.get("connection_id") or "")
    operation_id = str(operation.get("operation_id") or "")
    if not isinstance(anchor, dict) or anchor.get("placement_policy") != "resolved_from_operation":
        raise RuntimeError(
            f"ASSEMBLY_RESOLVED_SUPPORT_POLICY_INVALID:{operation.get('connection_id')}:{endpoint}"
        )
    resolved_anchor_id = str(anchor.get("anchor_id") or "")
    support_anchor_id = str(anchor.get("resolved_support_anchor_id") or "")
    support_anchor = anchors.get(support_anchor_id)
    if (
        not resolved_anchor_id
        or not support_anchor_id
        or not connection_id
        or not operation_id
        or not isinstance(role_id, str)
        or not role_id
        or not isinstance(support_anchor, dict)
        or support_anchor.get("anchor_id") != support_anchor_id
        or support_anchor.get("placement_policy", "fixed") != "fixed"
    ):
        raise RuntimeError(
            f"ASSEMBLY_RESOLVED_SUPPORT_ANCHOR_INVALID:{operation.get('connection_id')}:{endpoint}"
        )
    return {
        "connection_id": connection_id,
        "operation_id": operation_id,
        "endpoint": endpoint,
        "role_id": str(role_id or ""),
        "resolved_anchor_id": resolved_anchor_id,
        "support_anchor_id": support_anchor_id,
        "support_position_m": tuple(float(value) for value in support_anchor["position_m"]),
    }


def _create_radio_adapter_geometry(
    bpy,
    bracket_root,
    support_contract: dict,
    radio_instance: dict,
    sector_id: str,
) -> None:
    """Build a bounded mount member up to the resolved RRU anchor.

    RRU vertical/radial placement is a public edit capability. This member
    makes that placement physical in the exported model instead of leaving a
    plan-only offset between the bracket and the radio. It remains a
    project-authored technical-generic component, not a load or vendor claim.
    """

    from mathutils import Vector  # type: ignore[import-not-found]

    bpy.context.view_layer.update()
    start_world = bracket_root.matrix_world @ Vector(support_contract["support_position_m"])
    target_world = Vector(
        tuple(float(value) for value in radio_instance["target_frame_world"]["position_m"])
    )
    adapter = _create_cylinder_between(
        bpy,
        tuple(float(value) for value in start_world),
        tuple(float(value) for value in target_world),
        0.025,
        f"mount_bracket_{sector_id}_radio_adapter",
        _material(bpy, "mount_steel", (0.42, 0.44, 0.46, 1)),
    )
    adapter["role"] = "radio_mount_adapter"
    adapter["semantic_root"] = adapter.name
    adapter["sector_id"] = sector_id
    adapter["assembly_connection_id"] = "radio-to-mount"
    adapter["assembly_constraint_support"] = True
    adapter["constraint_connection_id"] = support_contract["connection_id"]
    adapter["constraint_operation_id"] = support_contract["operation_id"]
    adapter["constraint_instance_id"] = sector_id
    adapter["constraint_endpoint"] = support_contract["endpoint"]
    adapter["constraint_role_id"] = support_contract["role_id"]
    adapter["constraint_anchor_id"] = support_contract["resolved_anchor_id"]
    adapter["constraint_support_anchor_id"] = support_contract["support_anchor_id"]
    adapter["qualification_scope"] = "technical_generic_not_engineering_qualified"


def _create_assembly_constraint_anchors(bpy, scene: dict) -> None:
    """Export resolved anchor frames as independently measurable glTF nodes."""

    plan = scene.get("assembly_plan") or {}
    if plan.get("schema_version") != "1.1.0" or plan.get("compilation_status") != "resolved":
        return
    required_mechanical = {
        str(connection["connection_id"])
        for connection in plan.get("connections") or []
        if connection.get("required") is True and connection.get("kind") == "mechanical"
    }
    for operation in plan.get("operations") or []:
        connection_id = str(operation.get("connection_id") or "")
        if operation.get("kind") != "mechanical" or connection_id not in required_mechanical:
            continue
        operation_id = str(operation.get("operation_id") or "")
        endpoints = (
            (
                "source",
                str(operation.get("source_role_id") or ""),
                operation.get("source_anchor") or {},
                "source_frame_world",
            ),
            (
                "target",
                str(operation.get("target_role_id") or ""),
                operation.get("target_anchor") or {},
                "target_frame_world",
            ),
        )
        for instance in operation.get("instances") or []:
            instance_id = str(instance.get("instance_id") or "")
            for endpoint, role_id, anchor, frame_key in endpoints:
                if anchor.get("placement_policy", "fixed") == "fixed":
                    continue
                _create_assembly_constraint_anchor(
                    bpy,
                    frame=instance.get(frame_key) or {},
                    connection_id=connection_id,
                    operation_id=operation_id,
                    instance_id=instance_id,
                    endpoint=endpoint,
                    role_id=role_id,
                    anchor_id=str(anchor.get("anchor_id") or ""),
                )


def _create_assembly_constraint_anchor(
    bpy,
    *,
    frame: dict,
    connection_id: str,
    operation_id: str,
    instance_id: str,
    endpoint: str,
    role_id: str,
    anchor_id: str,
) -> None:
    from mathutils import Matrix, Vector  # type: ignore[import-not-found]

    position = Vector(tuple(float(value) for value in frame["position_m"]))
    normal = Vector(tuple(float(value) for value in frame["normal"])).normalized()
    up = Vector(tuple(float(value) for value in frame["up"])).normalized()
    lateral = up.cross(normal).normalized()
    corrected_up = normal.cross(lateral).normalized()
    marker = bpy.data.objects.new(
        f"assembly_anchor_{connection_id}_{instance_id}_{endpoint}",
        None,
    )
    bpy.context.collection.objects.link(marker)
    marker.empty_display_type = "ARROWS"
    marker.empty_display_size = 0.08
    marker.matrix_world = Matrix(
        (
            (normal.x, lateral.x, corrected_up.x, position.x),
            (normal.y, lateral.y, corrected_up.y, position.y),
            (normal.z, lateral.z, corrected_up.z, position.z),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    marker["assembly_constraint_anchor"] = True
    marker["constraint_connection_id"] = connection_id
    marker["constraint_operation_id"] = operation_id
    marker["constraint_instance_id"] = instance_id
    marker["constraint_endpoint"] = endpoint
    marker["constraint_role_id"] = role_id
    marker["constraint_anchor_id"] = anchor_id


def _component_execution_properties(
    scene: dict,
    role_id: str,
    instance_id: str,
    *,
    expected_handler: str,
    operation_ids: list[str] | None = None,
) -> dict:
    component = trusted_assembly.component_boundary(scene, role_id)
    builder = component.get("builder_profile") or {}
    snapshot = component.get("manifest_snapshot") or {}
    if builder.get("worker_handler") != expected_handler:
        raise RuntimeError(
            f"ASSEMBLY_BUILDER_HANDLER_DISPATCH_MISMATCH:{role_id}:{expected_handler}"
        )
    return {
        "assembly_role_id": role_id,
        "assembly_instance_id": instance_id,
        "assembly_operation_ids": ",".join(sorted(operation_ids or [])),
        "builder_profile_id": component["builder_profile_id"],
        "worker_handler": expected_handler,
        "manifest_snapshot_sha256": snapshot["snapshot_sha256"],
        "source_manifest_sha256": snapshot["source_manifest_sha256"],
        "selected_asset_id": component["selected_asset_id"],
    }


def _stamp_component_execution(
    root,
    scene: dict,
    role_id: str,
    instance_id: str,
    *,
    expected_handler: str,
    operation_ids: list[str] | None = None,
) -> None:
    semantic_root = str(root.get("semantic_root") or root.name)
    role = str(root.get("role") or role_id)
    _set_semantic_tree(
        root,
        role=role,
        semantic_root=semantic_root,
        sector_id=instance_id if instance_id != "global" else None,
        properties=_component_execution_properties(
            scene,
            role_id,
            instance_id,
            expected_handler=expected_handler,
            operation_ids=operation_ids,
        ),
    )


def _apply_resolved_instance_transform(root, instance: dict) -> None:
    from mathutils import Vector  # type: ignore[import-not-found]

    root.location = tuple(float(value) for value in instance["translation_m"])
    root.rotation_mode = "XYZ"
    root.rotation_euler = tuple(math.radians(float(value)) for value in instance["rotation_deg"])
    root.scale = tuple(float(value) for value in instance.get("scale") or [1.0, 1.0, 1.0])
    # Segment builders store their requested endpoints for hard geometric QA.
    # Once their semantic root receives the compiled placement, keep those QA
    # targets in the same world frame as the evaluated geometry.
    rotation = root.rotation_euler.to_matrix()
    translation = Vector(root.location)
    scale = Vector(root.scale)

    def resolved_point(values) -> tuple[float, float, float]:
        local = Vector(tuple(values))
        scaled = Vector((local.x * scale.x, local.y * scale.y, local.z * scale.z))
        return tuple(rotation @ scaled + translation)

    for obj in root.children_recursive:
        if "segment_start_m" not in obj or "segment_end_m" not in obj:
            continue
        obj["segment_start_m"] = resolved_point(obj["segment_start_m"])
        obj["segment_end_m"] = resolved_point(obj["segment_end_m"])


def _create_remaining_assembly_routes(
    bpy,
    scene: dict,
    procedural_objects: list[str],
    asset_imports: list[dict],
    asset_warnings: list[str],
) -> None:
    del asset_imports, asset_warnings
    plan = scene.get("assembly_plan") or {}
    if plan.get("schema_version") != "1.1.0":
        return
    for operation in plan.get("operations", []):
        if operation.get("operation_type") != "route_connection":
            continue
        if operation.get("connection_id") == "radio-to-base-route":
            # Executed by the selected cable-route handler in _create_sectors.
            continue
        operation_id = str(operation["operation_id"])
        for instance in operation.get("instances", []):
            route_points = [tuple(point) for point in instance.get("route_points_m", [])]
            if len(route_points) < 2:
                raise RuntimeError(f"ASSEMBLY_ROUTE_POINTS_MISSING:{operation['connection_id']}")
            instance_id = str(instance["instance_id"])
            connection_kind = str(operation["kind"])
            name = f"{operation['connection_id']}_{instance_id}"
            semantic_name, semantic_role = _assembly_route_object_identity(
                connection_kind,
                str(operation["connection_id"]),
                instance_id,
            )
            connection = _create_cable(
                bpy,
                name,
                route_points,
                diameter_m=0.018,
                name_prefix=semantic_role,
            )
            _set_semantic_properties(
                connection,
                role=semantic_role,
                semantic_root=semantic_name,
                sector_id=instance_id if instance_id != "global" else None,
                properties={
                    "assembly_operation_ids": operation_id,
                    "assembly_connection_id": operation["connection_id"],
                    "connection_kind": operation["kind"],
                    **_classification_properties("parametric_generated"),
                },
            )
            procedural_objects.append(
                f"assembly_connection:{operation['connection_id']}:{instance_id}"
            )


def _assembly_route_object_identity(
    connection_kind: str,
    connection_id: str,
    instance_id: str,
) -> tuple[str, str]:
    """Keep non-cable assembly links out of the product cable count."""

    if connection_kind not in {"power", "fiber", "rf", "grounding", "routing"}:
        raise RuntimeError(f"ASSEMBLY_ROUTE_KIND_UNSUPPORTED:{connection_kind}")
    semantic_role = f"{connection_kind}_connection"
    return f"{semantic_role}_{connection_id}_{instance_id}", semantic_role


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
    if accessory and strategy == "imported_glb_exact":
        import_attempted = True
        cabinet_boundary = trusted_assembly.exact_asset_boundary(
            scene,
            role_id="ground_equipment",
            asset_id=accessory["asset_id"],
            project_root=Path.cwd().resolve(),
        )
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=cabinet_boundary["asset_file"],
            asset_source=accessory.get("asset_source"),
            asset_metadata={
                **(accessory.get("asset_metadata") or {}),
                "verified_file_sha256": cabinet_boundary["verified_file_sha256"],
            },
            fallback_allowed=False,
            object_role="cabinet",
            object_name=cabinet_object_name,
            location=cabinet_location,
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=cabinet_boundary.get("dimensions_m") or accessory.get("dimensions_m"),
            placement_scale=tuple(accessory.get("scale") or [1.0, 1.0, 1.0]),
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={
                "ground_datum_z": 0.0,
                **_component_execution_properties(
                    scene,
                    "ground_equipment",
                    "global",
                    expected_handler="ground_cabinet",
                ),
            },
            exact_boundary=cabinet_boundary,
        )
        if _is_imported_mode(mode) or not accessory.get("import_fallback_allowed", True):
            return
    cabinet = parametric_builder.build_parametric_accessory_cabinet(
        bpy=bpy,
        name=cabinet_object_name,
        location=cabinet_location,
        width=float((accessory.get("dimensions_m") or {}).get("width", 1.0)) if accessory else 1.0,
        depth=float((accessory.get("dimensions_m") or {}).get("depth", 0.45))
        if accessory
        else 0.45,
        height=float((accessory.get("dimensions_m") or {}).get("height", 1.6))
        if accessory
        else 1.6,
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
    if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
        _stamp_component_execution(
            cabinet,
            scene,
            "ground_equipment",
            "global",
            expected_handler="ground_cabinet",
        )
    if accessory and import_attempted:
        _mark_fallback_generated(
            asset_imports,
            object_role="cabinet",
            object_name=cabinet_object_name,
            generated_object_names=_semantic_tree_names(cabinet),
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
            dimensions=accessory.get("dimensions_m")
            if accessory
            else {"width": 1.0, "depth": 0.45, "height": 1.6},
            location=cabinet_location,
            rotation=(0.0, 0.0, 0.0),
            generation_strategy=strategy,
            generated_object_names=_semantic_tree_names(cabinet),
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
    # The fallback procedural radome is 0.32 m deep.  Offset its centre by the
    # half-depth as well as the clearance so the mesh stays outside the tower.
    mount_radius = _tower_radius_at_height(scene, z) + 0.16 + 0.1
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
        gps_boundary = (
            trusted_assembly.exact_asset_boundary(
                scene,
                role_id="timing_antenna",
                asset_id=accessory["asset_id"],
                project_root=Path.cwd().resolve(),
            )
            if strategy == "imported_glb_exact"
            else None
        )
        mode = _try_import_glb_asset(
            bpy=bpy,
            asset_id=accessory["asset_id"],
            asset_file=(gps_boundary or {}).get("asset_file") or accessory.get("asset_file"),
            asset_source=accessory.get("asset_source"),
            asset_metadata={
                **(accessory.get("asset_metadata") or {}),
                **(
                    {"verified_file_sha256": gps_boundary["verified_file_sha256"]}
                    if gps_boundary
                    else {}
                ),
            },
            fallback_allowed=False
            if gps_boundary
            else accessory.get("import_fallback_allowed", True),
            object_role="gps",
            object_name=gps_object_name,
            location=gps_location,
            rotation=_rotation_deg_to_rad(accessory.get("rotation_deg") or [0.0, 0.0, 0.0]),
            dimensions=(gps_boundary or {}).get("dimensions_m") or accessory.get("dimensions_m"),
            placement_scale=tuple(accessory.get("scale") or [1.0, 1.0, 1.0]),
            asset_imports=asset_imports,
            warnings=asset_warnings,
            semantic_properties={
                "install_height_m": z,
                **(
                    _component_execution_properties(
                        scene,
                        "timing_antenna",
                        "global",
                        expected_handler="gps_radome",
                    )
                    if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0"
                    else {}
                ),
            },
            exact_boundary=gps_boundary,
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
    if (scene.get("assembly_plan") or {}).get("schema_version") == "1.1.0":
        _stamp_component_execution(
            gps,
            scene,
            "timing_antenna",
            "global",
            expected_handler="gps_radome",
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
    exact_boundary: dict | None = None,
) -> str:
    path = _resolve_asset_path(asset_file)
    record_asset_file = asset_file
    if exact_boundary is not None:
        if fallback_allowed:
            raise RuntimeError(f"EXACT_IMPORT_FALLBACK_NOT_FAIL_CLOSED:{asset_id}")
        public_asset_file = exact_boundary.get("asset_file")
        resolved_asset_path = exact_boundary.get("resolved_asset_path")
        if (
            not isinstance(public_asset_file, str)
            or not public_asset_file
            or Path(public_asset_file).is_absolute()
        ):
            raise RuntimeError(f"EXACT_IMPORT_ASSET_PATH_INVALID:{asset_id}")
        if asset_file != public_asset_file:
            raise RuntimeError(f"EXACT_IMPORT_PUBLIC_ASSET_FILE_MISMATCH:{asset_id}")
        if not isinstance(resolved_asset_path, str) or not Path(resolved_asset_path).is_absolute():
            raise RuntimeError(f"EXACT_IMPORT_RESOLVED_PATH_MISMATCH:{asset_id}")
        public_resolved_path = _resolve_asset_path(public_asset_file)
        internal_resolved_path = Path(resolved_asset_path).resolve()
        if public_resolved_path is None or public_resolved_path.resolve() != internal_resolved_path:
            raise RuntimeError(f"EXACT_IMPORT_RESOLVED_PATH_MISMATCH:{asset_id}")
        path = internal_resolved_path
        record_asset_file = public_asset_file
        if tuple(float(value) for value in placement_scale) != (1.0, 1.0, 1.0):
            raise RuntimeError(f"EXACT_IMPORT_SCALE_NOT_AUTHORIZED:{asset_id}")
    record = _base_asset_import_record(
        asset_id=asset_id,
        asset_file=record_asset_file,
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
        if exact_boundary is not None:
            raise RuntimeError(f"EXACT_IMPORT_ASSET_FILE_MISSING:{asset_id}")
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            "ASSET_FILE_MISSING",
            fallback_allowed=fallback_allowed,
        )

    expected_sha256 = str(
        (exact_boundary or {}).get("verified_file_sha256")
        or (asset_metadata or {}).get("verified_file_sha256")
        or ""
    )
    if exact_boundary is not None and not expected_sha256:
        raise RuntimeError(f"EXACT_IMPORT_PINNED_HASH_MISSING:{asset_id}")
    if expected_sha256 and _sha256_file(path) != expected_sha256:
        if exact_boundary is not None:
            raise RuntimeError(f"EXACT_IMPORT_ASSET_HASH_MISMATCH:{asset_id}")
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            "ASSET_QUALIFIED_HASH_MISMATCH",
            fallback_allowed=fallback_allowed,
        )

    before_object_ids = {id(obj) for obj in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=str(path))
    except Exception as exc:
        _remove_partial_import_objects(bpy, before_object_ids)
        if exact_boundary is not None:
            raise RuntimeError(
                f"EXACT_IMPORT_BLENDER_IMPORT_FAILED:{asset_id}:{type(exc).__name__}"
            ) from exc
        return _record_asset_import_fallback(
            record,
            asset_imports,
            warnings,
            f"ASSET_IMPORT_FAILED:{type(exc).__name__}",
            fallback_allowed=fallback_allowed,
        )

    imported = [obj for obj in bpy.data.objects if id(obj) not in before_object_ids]
    if not imported:
        if exact_boundary is not None:
            raise RuntimeError(f"EXACT_IMPORT_EMPTY:{asset_id}")
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
        if exact_boundary is not None:
            for index, axis in enumerate(("width", "depth", "height")):
                actual = float(source_size[index])
                expected = float(target_size[index])
                tolerance = max(0.01, expected * 0.05)
                if abs(actual - expected) > tolerance:
                    _remove_partial_import_objects(bpy, before_object_ids)
                    raise RuntimeError(
                        "EXACT_IMPORT_DIMENSIONS_MISMATCH:"
                        f"{asset_id}:{axis}:{actual:.6f}:{expected:.6f}"
                    )
        else:
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
    if exact_boundary is not None and any(
        abs(float(value) - 1.0) > 1e-9 for value in scale_factors
    ):
        raise RuntimeError(f"EXACT_IMPORT_SCALE_NOT_AUTHORIZED:{asset_id}")
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


def _remove_partial_import_objects(bpy, before_object_ids: set[int]) -> None:
    """Remove every scene object created by a failed, non-transactional importer."""

    created = [obj for obj in bpy.data.objects if id(obj) not in before_object_ids]
    for obj in created:
        bpy.data.objects.remove(obj, do_unlink=True)


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
    if generation_strategy == "procedural_fallback":
        _append_warning(record["warnings"], "PROCEDURAL_FALLBACK_USED")
        _append_warning(warnings, f"PROCEDURAL_FALLBACK_USED:{asset_id}")
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

    tower = scene.get("tower")
    tower_height = float(tower["height_m"]) if tower is not None else 0.0
    base_width = (
        float(tower.get("characteristics", {}).get("base_width_m") or 4.0)
        if tower is not None
        else 4.0
    )
    subject_corners = _subject_world_corners(bpy)
    subject_bounds = _bounds_from_vectors(subject_corners)
    if subject_bounds:
        minimum, maximum = subject_bounds
        target_vector = (minimum + maximum) * 0.5
        subject_size = maximum - minimum
    else:
        fallback_height = max(tower_height, 4.0)
        target_vector = Vector((0.0, 0.0, fallback_height * 0.5))
        subject_size = Vector((base_width, base_width, fallback_height))
    reference_height = max(float(subject_size.z), tower_height, 4.0)
    distance = max(12.0, subject_size.length * 1.45)
    camera_mode = str(scene.get("preview", {}).get("camera") or "isometric")
    view_direction = Vector(_camera_view_direction(camera_mode)).normalized()
    camera_location_vector = target_vector + (view_direction * distance)
    target = tuple(float(value) for value in target_vector)
    camera_location = tuple(float(value) for value in camera_location_vector)

    bpy.ops.object.light_add(type="SUN", location=(8, -6, reference_height + 12))
    sun = bpy.context.object
    sun.name = "sun_key"
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-32))
    bpy.ops.object.light_add(
        type="AREA",
        location=(-distance * 0.35, -distance * 0.45, reference_height * 0.82),
    )
    fill = bpy.context.object
    fill.name = "area_fill"
    fill.data.energy = 1550
    fill.data.size = max(5, reference_height * 0.42)
    _point_object_at(fill, target)
    bpy.ops.object.light_add(
        type="AREA",
        location=(distance * 0.58, distance * 0.32, reference_height * 0.7),
    )
    rim = bpy.context.object
    rim.name = "area_rim"
    rim.data.energy = 1750
    rim.data.size = max(4, reference_height * 0.3)
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
        "side": (1.0, 0.0, 0.04),
        "top": (0.0, 0.0, 1.0),
    }[camera_mode]


def _render_preview_views(bpy, scene: dict, output_dir: Path) -> list[dict]:
    """Render the governed preview set without changing exported scene geometry.

    The primary view preserves ``SceneSpec.preview.camera`` and its historical
    filename. The other views are deterministic inspection aids. They are not
    presented as independent semantic or engineering QA.
    """

    camera = bpy.context.scene.camera
    subject_corners = _subject_world_corners(bpy)
    closeup_corners, closeup_focus = _closeup_subject_world_corners(bpy, subject_corners)
    requested_camera = str(scene.get("preview", {}).get("camera") or "isometric")
    views = (
        ("primary", "preview.png", requested_camera, subject_corners, "complete_scene"),
        ("front", "preview_front.png", "front", subject_corners, "complete_scene"),
        ("side", "preview_side.png", "side", subject_corners, "complete_scene"),
        ("top", "preview_top.png", "top", subject_corners, "complete_scene"),
        ("closeup", "preview_closeup.png", "isometric", closeup_corners, closeup_focus),
    )
    rendered: list[dict] = []
    for view_id, file_name, camera_mode, view_corners, focus in views:
        _remove_preview_backdrops(bpy)
        framing = _position_preview_camera(
            bpy,
            camera,
            view_corners,
            scene,
            camera_mode=camera_mode,
        )
        if view_id == "closeup" and focus == "complete_scene":
            # Generic scenes may not expose telecom role names. Preserve the
            # deterministic scene centre and create an honest inspection crop
            # instead of duplicating the primary overview under another name.
            camera.data.ortho_scale *= 0.62
        _create_preview_backdrop(bpy, scene)
        preview_path = output_dir / file_name
        bpy.context.scene.render.filepath = str(preview_path)
        annotation_states = _set_preview_annotations_hidden(bpy, hidden=view_id == "closeup")
        try:
            bpy.ops.render.render(write_still=True)
        finally:
            _restore_preview_annotation_states(annotation_states)
        rendered.append(
            {
                "view_id": view_id,
                "file_name": file_name,
                "camera_mode": camera_mode,
                "focus": focus,
                "inspection_only": view_id != "primary",
                "camera_location": [round(float(value), 3) for value in camera.location],
                "target": [round(float(value), 3) for value in framing["target"]],
                "ortho_scale": round(float(camera.data.ortho_scale), 3),
                "subject_bounds_m": framing["subject_bounds_m"],
                "sha256": _sha256_file(preview_path),
                "size_bytes": preview_path.stat().st_size,
            }
        )
    return rendered


def _render_sector_preview_views(bpy, scene: dict, output_dir: Path) -> list[dict]:
    """Render one inspection image per real telecom sector.

    The images are deliberately narrow: they show local mechanical equipment
    associated with a sector (panel, bracket and radio). They are not a second
    scene, nor an illustration assembled outside Blender. The full cable route
    is verified from the exported GLB but excluded from the close-up because
    its descent to the tower base would destroy the local mechanical framing.
    """

    assembly = scene.get("assembly_plan") or {}
    if assembly.get("schema_version") != "1.1.0" or not scene.get("sectors"):
        return []
    camera = bpy.context.scene.camera
    rendered: list[dict] = []
    for sector in scene["sectors"]:
        sector_id = str(sector["sector_id"])
        framed_roles = ["antenna", "mount_bracket"]
        if sector.get("radio_asset_id"):
            framed_roles.append("radio")
        # The previous overview view leaves a temporary backdrop in the
        # scene. Remove it before snapshotting visibility so restoration never
        # holds a reference to a Blender object that this loop deletes.
        _remove_preview_backdrops(bpy)
        visible_states = _set_sector_preview_visibility(bpy, sector_id, set(framed_roles))
        try:
            subject_corners = _subject_world_corners(bpy)
            if not subject_corners:
                raise RuntimeError(f"SECTOR_PREVIEW_SUBJECT_MISSING:{sector_id}")
            framing = _position_preview_camera(
                bpy,
                camera,
                subject_corners,
                scene,
                camera_mode="isometric",
            )
            _create_preview_backdrop(bpy, scene)
            preview_id = _sector_preview_id(sector_id)
            file_name = f"preview_sector_{preview_id}.png"
            preview_path = output_dir / file_name
            bpy.context.scene.render.filepath = str(preview_path)
            bpy.ops.render.render(write_still=True)
            rendered.append(
                {
                    "preview_id": preview_id,
                    "sector_id": sector_id,
                    "file_name": file_name,
                    "camera_mode": "isometric",
                    "focus": "sector_equipment",
                    "framed_roles": framed_roles,
                    "inspection_only": True,
                    "camera_location": [round(float(value), 3) for value in camera.location],
                    "target": [round(float(value), 3) for value in framing["target"]],
                    "ortho_scale": round(float(camera.data.ortho_scale), 3),
                    "subject_bounds_m": framing["subject_bounds_m"],
                    "sha256": _sha256_file(preview_path),
                    "size_bytes": preview_path.stat().st_size,
                }
            )
        finally:
            _remove_preview_backdrops(bpy)
            _restore_preview_visibility(visible_states)
    return rendered


def _sector_preview_id(sector_id: str) -> str:
    return hashlib.sha256(sector_id.encode("utf-8")).hexdigest()[:16]


def _set_sector_preview_visibility(
    bpy,
    sector_id: str,
    framed_roles: set[str],
) -> list[tuple[object, bool]]:
    """Show only sector-owned equipment while preserving the export scene."""

    visible_states = []
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE"}:
            continue
        visible_states.append((obj, bool(obj.hide_render)))
        role = str(obj.get("role") or obj.get("object_role") or "").strip().lower()
        obj_sector_id = str(obj.get("sector_id") or "")
        obj.hide_render = not (role in framed_roles and obj_sector_id == sector_id)
    return visible_states


def _restore_preview_visibility(states: list[tuple[object, bool]]) -> None:
    for obj, hide_render in states:
        obj.hide_render = hide_render


def _position_preview_camera(
    bpy,
    camera,
    subject_corners: list,
    scene: dict,
    *,
    camera_mode: str,
) -> dict:
    from mathutils import Vector  # type: ignore[import-not-found]

    subject_bounds = _bounds_from_vectors(subject_corners)
    if subject_bounds:
        minimum, maximum = subject_bounds
        target = (minimum + maximum) * 0.5
        subject_size = maximum - minimum
    else:
        tower = scene.get("tower")
        fallback_height = float(tower["height_m"]) if tower is not None else 10.0
        target = Vector((0.0, 0.0, fallback_height * 0.5))
        subject_size = Vector((4.0, 4.0, fallback_height))
    distance = max(12.0, subject_size.length * 1.45)
    direction = Vector(_camera_view_direction(camera_mode)).normalized()
    camera.location = target + (direction * distance)
    _point_object_at(camera, tuple(float(value) for value in target))
    return _fit_orthographic_camera(bpy, camera, subject_corners, scene)


def _closeup_subject_world_corners(bpy, fallback_corners: list) -> tuple[list, str]:
    """Prefer mounted/ground equipment for telecom and remain generic otherwise."""

    from mathutils import Vector  # type: ignore[import-not-found]

    preferred_roles = {
        "antenna",
        "radio",
        "rru",
        "gps",
        "equipment",
        "component",
    }
    corners = []
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE"} or obj.hide_render:
            continue
        role = str(obj.get("role") or obj.get("component_role") or "").strip().lower()
        if role not in preferred_roles:
            continue
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    if corners:
        return corners, "primary_equipment"
    return fallback_corners, "complete_scene"


def _remove_preview_backdrops(bpy) -> None:
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith("technical_preview_backdrop"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _set_preview_annotations_hidden(bpy, *, hidden: bool) -> list[tuple[object, bool]]:
    if not hidden:
        return []
    states = []
    annotation_roles = {"label", "beam", "azimuth_arrow", "height_marker"}
    annotation_prefixes = ("label_", "sector_beam_", "azimuth_arrow_", "height_marker")
    for obj in bpy.context.scene.objects:
        role = str(obj.get("role") or "").strip().lower()
        if role not in annotation_roles and not obj.name.startswith(annotation_prefixes):
            continue
        states.append((obj, bool(obj.hide_render)))
        obj.hide_render = True
    return states


def _restore_preview_annotation_states(states: list[tuple[object, bool]]) -> None:
    for obj, hide_render in states:
        obj.hide_render = hide_render


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
        "sector_beam_",
        "azimuth_arrow_",
        "height_marker",
        "label_",
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
        tower = scene.get("tower")
        reference_height = float(tower["height_m"]) if tower is not None else 10.0
        camera.data.ortho_scale = max(reference_height * 1.28, 12.0)
        camera.data.clip_start = 0.1
        camera.data.clip_end = max(reference_height * 6.0, 120.0)
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
    tower = scene.get("tower")
    reference_height = float(tower["height_m"]) if tower is not None else width
    backdrop_distance = max(reference_height * 2.2, 40.0)
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
        _emission_material(bpy, "preview_backdrop_dark", (0.04, 0.055, 0.072, 1), 0.52)
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
    assembly_validation: dict | None = None,
    component_proof: dict | None = None,
) -> None:
    asset_imports = asset_imports or _fallback_asset_import_records(scene)
    public_asset_imports = _public_asset_import_records(asset_imports)
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
        "design_domain": scene.get("design_domain") or "telecom",
        "design_intent_id": scene.get("design_intent_id"),
        "component_graph_id": scene.get("component_graph_id"),
        "asset_decision_plan_id": scene.get("asset_decision_plan_id"),
        "specialist_route_id": scene.get("specialist_route_id"),
        "cognitive_plan_sha256": scene.get("cognitive_plan_sha256"),
        "generation_mode": generation_mode,
        "assets_used": _assets_used(scene),
        "geometry_program_ids": [
            str(program["program_id"]) for program in scene.get("geometry_programs", [])
        ],
        "procedural_objects_created": procedural_objects,
        "asset_imports": public_asset_imports,
        "asset_import_summary": _asset_import_summary(asset_imports),
        "sector_count": len(scene.get("sectors", [])),
        "network_type": scene.get("network_type"),
        "tower_height_m": (scene.get("tower") or {}).get("height_m"),
        "tower_characteristics": (scene.get("tower") or {}).get("characteristics", {}),
        "azimuths_deg": [sector["azimuth_deg"] for sector in scene.get("sectors", [])],
        "antenna_heights_m": [sector["install_height_m"] for sector in scene.get("sectors", [])],
        "mechanical_tilts_deg": [
            sector.get("mechanical_tilt_deg", 0.0) for sector in scene.get("sectors", [])
        ],
        "visual_elements": scene.get("visual_elements", {}),
        "accessory_assets": scene.get("accessory_assets", []),
        "assembly_plan": scene.get("assembly_plan"),
        "assembly_validation": assembly_validation,
        "component_proof": component_proof,
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


def _public_asset_import_records(asset_imports: list[dict]) -> list[dict]:
    """Strip worker-local paths before asset evidence is persisted or exposed."""

    public_records: list[dict] = []
    for record in asset_imports:
        public_record = dict(record)
        public_record.pop("resolved_path", None)
        asset_file = public_record.get("asset_file")
        if isinstance(asset_file, str) and Path(asset_file).is_absolute():
            asset_id = str(public_record.get("asset_id") or "unknown")
            raise RuntimeError(f"PUBLIC_ASSET_FILE_ABSOLUTE_PATH:{asset_id}")
        public_records.append(public_record)
    return public_records


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
    assets = []
    tower = scene.get("tower")
    if tower is not None:
        assets.append(tower["asset_id"])
    for sector in scene.get("sectors", []):
        assets.append(sector["antenna_asset_id"])
        if sector.get("radio_asset_id"):
            assets.append(sector["radio_asset_id"])
    for accessory in scene.get("accessory_assets", []):
        assets.append(accessory["asset_id"])
    for program in scene.get("geometry_programs", []):
        assets.append(f"GEOMETRY_PROGRAM_{str(program['program_id']).upper()}")
        assets.extend(
            node["asset_id"]
            for node in program.get("nodes", [])
            if node.get("kind") == "exact_asset"
        )
    return sorted(set(assets))


def _fallback_asset_import_records(scene: dict) -> list[dict]:
    records = []
    tower = scene.get("tower")
    if tower is not None:
        records.append(
            _fallback_asset_import_record(
                asset_id=tower["asset_id"],
                asset_file=tower.get("asset_file"),
                asset_source=tower.get("asset_source"),
                asset_metadata=tower.get("asset_metadata"),
                object_role="tower",
                object_name=f"tower_{tower['asset_id']}",
                fallback_allowed=tower.get("import_fallback_allowed", True),
                dimensions=tower.get("dimensions_m")
                or {
                    "height": tower.get("height_m"),
                    "width": tower.get("characteristics", {}).get("base_width_m"),
                    "depth": tower.get("characteristics", {}).get("base_width_m"),
                },
            )
        )
    for sector in scene.get("sectors", []):
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
        "imported_glb_count": modes.get("imported_glb", 0) + modes.get("imported_glb_exact", 0),
        "imported_glb_exact_count": modes.get("imported_glb_exact", 0),
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
    tower = scene.get("tower")
    tower_height = float(tower["height_m"]) if tower is not None else 10.0
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
