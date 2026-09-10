"""Pinned catalog imports, shared by admission, worker execution and build evidence."""

import hashlib
import json
import math
from pathlib import Path


def validate_exact_program(program: dict, project_root: Path) -> list[dict]:
    nodes = program.get("nodes", [])
    exact = [node for node in nodes if node.get("kind") == "exact_asset"]
    if not exact:
        return []
    if (
        len(nodes) != 1
        or program.get("requested_quantity") != 1
        or program.get("authorship") != "deterministic_generated"
        or any(
            program.get(field)
            for field in (
                "materials",
                "anchors",
                "connectors",
                "semantic_groups",
                "construction_node_ids",
            )
        )
    ):
        raise ValueError("EXACT_ASSET_PROGRAM_SCOPE_INVALID")
    node = exact[0]
    if node.get("parent_id") or node.get("material_id"):
        raise ValueError("EXACT_ASSET_PARENT_OR_MATERIAL_FORBIDDEN")
    transform = node.get("transform") or {}
    if any(float((transform.get("scale") or {}).get(axis, 1)) != 1 for axis in "xyz"):
        raise ValueError("EXACT_ASSET_SCALE_FORBIDDEN")
    root = project_root.resolve()
    name = node["manifest_file_name"]
    if Path(name).name != name or not name.endswith(".json"):
        raise ValueError("EXACT_ASSET_MANIFEST_PATH_INVALID")
    manifest_path = (root / "assets" / "manifests" / name).resolve()
    manifest_path.relative_to((root / "assets" / "manifests").resolve())
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != node["manifest_sha256"]:
        raise ValueError("EXACT_ASSET_MANIFEST_HASH_MISMATCH")
    manifest = json.loads(raw)
    qualification = manifest.get("qualification") or {}
    if (
        manifest.get("asset_id") != node["asset_id"]
        or manifest.get("cognitive_reuse_enabled") is not True
        or manifest.get("status") != "validated"
        or qualification.get("status") != "qualified_for_generation"
        or "imported_glb_exact" not in qualification.get("allowed_generation_modes", [])
        or qualification.get("units") != "meters"
        or manifest.get("import_fallback_allowed") is not False
        or not all(
            qualification.get(check) is True
            for check in (
                "mesh_integrity_verified",
                "dimensions_verified",
                "pivot_verified",
                "orientation_verified",
            )
        )
        or program.get("semantic_role")
        not in (manifest.get("compatibility_rules") or {}).get("compatible_roles", [])
    ):
        raise ValueError("EXACT_ASSET_QUALIFICATION_INVALID")
    dimensions = manifest.get("dimensions_m") or {}
    source_dimensions = node.get("source_dimensions_m") or {}
    if any(
        float(source_dimensions.get(axis, 0)) != float(dimensions.get(key, -1))
        for axis, key in zip("xyz", ("width", "depth", "height"), strict=True)
    ):
        raise ValueError("EXACT_ASSET_SOURCE_DIMENSIONS_MISMATCH")
    permissions = manifest.get("transform_permissions")
    if not isinstance(permissions, dict):
        raise ValueError("EXACT_ASSET_TRANSFORM_PERMISSIONS_MISSING")
    for field, axes, maximum in (
        ("translation_m", "translation_axes", "maximum_translation_m"),
        ("rotation_deg", "rotation_axes", "maximum_rotation_deg"),
    ):
        values = transform.get(field) or {}
        for axis in "xyz":
            value = float(values.get(axis, 0))
            if not math.isfinite(value) or (value and axis not in permissions.get(axes, [])):
                raise ValueError("EXACT_ASSET_TRANSFORM_NOT_AUTHORIZED")
            if abs(value) > float(permissions.get(maximum, 0)):
                raise ValueError("EXACT_ASSET_TRANSFORM_OUT_OF_BOUNDS")
    asset_file = node["asset_file"]
    relative = Path(asset_file)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".glb":
        raise ValueError("EXACT_ASSET_PATH_INVALID")
    path = (root / relative).resolve()
    path.relative_to((root / "assets").resolve())
    if manifest.get("file") != asset_file:
        raise ValueError("EXACT_ASSET_MANIFEST_FILE_MISMATCH")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != node["asset_sha256"] or digest != qualification.get("verified_file_sha256"):
        raise ValueError("EXACT_ASSET_FILE_HASH_MISMATCH")
    return [
        {
            "asset_id": node["asset_id"],
            "asset_file": asset_file,
            "manifest_file_name": name,
            "manifest_sha256": node["manifest_sha256"],
            "asset_sha256": digest,
            "units": "meters",
            "manifest": manifest,
        }
    ]


def import_exact_node(bpy, name: str, spec: dict):
    # Validation of the whole program has already pinned this source immediately
    # before dispatch. Import preserves source meshes/materials/local transforms.
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str((Path.cwd() / spec["asset_file"]).resolve()))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not any(obj.type == "MESH" for obj in imported):
        raise RuntimeError("EXACT_ASSET_IMPORTED_MESH_MISSING")
    group = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(group)
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            world = obj.matrix_world.copy()
            obj.parent = group
            obj.matrix_world = world
    group["exact_asset_id"] = spec["asset_id"]
    group["exact_asset_sha256"] = spec["asset_sha256"]
    return group
