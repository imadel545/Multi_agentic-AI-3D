"""Build deterministic per-component evidence from the Blender scene.

This module runs inside the immutable worker bundle.  It never trusts object
names alone: catalog components must carry the assembly role, builder profile
and manifest snapshot that were stamped by the bounded worker handler.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

_OBJECT_ROLES = {
    "support_structure": "tower",
    "sector_antenna": "antenna",
    "antenna_mount": "mount_bracket",
    "remote_radio": "radio",
    "sector_cable_route": "cable",
    "ground_equipment": "cabinet",
    "timing_antenna": "gps",
}
_PROOF_STRATEGIES = {"reuse", "adapt", "compose", "procedural_generate"}


def build_component_proof_report(
    bpy,
    scene: dict,
    asset_imports: list[dict],
    assembly_evidence: dict,
) -> dict:
    plan = scene.get("assembly_plan") or {}
    components = [
        _catalog_component_proof(bpy, scene, component, asset_imports)
        for component in plan.get("components", [])
    ]
    programs = [
        _geometry_program_proof(bpy, program) for program in scene.get("geometry_programs", [])
    ]
    operation_ids = {str(operation.get("operation_id")) for operation in plan.get("operations", [])}
    executed_operation_ids = {
        operation_id for obj in bpy.context.scene.objects for operation_id in _operation_ids(obj)
    }
    missing_operations = sorted(operation_ids - executed_operation_ids)
    if missing_operations:
        raise RuntimeError("ASSEMBLY_OPERATION_NOT_EXECUTED:" + ",".join(missing_operations))
    if any(not proof["qa"]["passed"] for proof in [*components, *programs]):
        raise RuntimeError("COMPONENT_PROOF_QA_FAILED")
    payload = {
        "schema_version": "1.0.0",
        "scene_id": scene["scene_id"],
        "workflow_id": plan.get("workflow_id"),
        "assembly_plan_schema_version": plan.get("schema_version"),
        "manifest_catalog_sha256": plan.get("manifest_catalog_sha256"),
        "assembly_validation": assembly_evidence,
        "components": components,
        "geometry_programs": programs,
        "operation_execution": {
            "declared_operation_ids": sorted(operation_ids),
            "executed_operation_ids": sorted(executed_operation_ids),
            "missing_operation_ids": missing_operations,
            "passed": not missing_operations,
        },
    }
    payload["report_sha256"] = _canonical_sha256(payload)
    return payload


def verify_component_proof_report(payload: dict, scene: dict) -> None:
    expected = payload.get("report_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "report_sha256"}
    if not isinstance(expected, str) or _canonical_sha256(unsigned) != expected:
        raise RuntimeError("COMPONENT_PROOF_REPORT_HASH_MISMATCH")
    if payload.get("scene_id") != scene.get("scene_id"):
        raise RuntimeError("COMPONENT_PROOF_SCENE_MISMATCH")
    if payload.get("operation_execution", {}).get("passed") is not True:
        raise RuntimeError("COMPONENT_PROOF_OPERATION_EXECUTION_FAILED")
    proofs = [
        *payload.get("components", []),
        *payload.get("geometry_programs", []),
    ]
    if (
        not proofs
        or any(proof.get("strategy") not in _PROOF_STRATEGIES for proof in proofs)
        or any(proof.get("qa", {}).get("passed") is not True for proof in proofs)
    ):
        raise RuntimeError("COMPONENT_PROOF_SET_INVALID")


def _catalog_component_proof(
    bpy,
    scene: dict,
    component: dict,
    asset_imports: list[dict],
) -> dict:
    role_id = str(component["role_id"])
    expected_role = _OBJECT_ROLES.get(role_id)
    if expected_role is None:
        raise RuntimeError(f"COMPONENT_PROOF_ROLE_UNSUPPORTED:{role_id}")
    roots = _component_roots(bpy, role_id)
    expected_quantity = (
        len(scene.get("sectors", []))
        if component["builder_profile"]["instance_strategy"] == "per_sector"
        else 1
    )
    if len(roots) != expected_quantity:
        raise RuntimeError(
            f"COMPONENT_PROOF_QUANTITY_MISMATCH:{role_id}:{len(roots)}:{expected_quantity}"
        )
    snapshot = component["manifest_snapshot"]
    builder = component["builder_profile"]
    instances = []
    for root in roots:
        objects = _semantic_objects(bpy, str(root.get("semantic_root") or root.name))
        record = next(
            (
                item
                for item in asset_imports
                if item.get("object_name") == str(root.get("semantic_root") or root.name)
            ),
            None,
        )
        if record is None:
            raise RuntimeError(f"COMPONENT_PROOF_ASSET_RECORD_MISSING:{role_id}:{root.name}")
        bbox = _bounding_box(objects)
        fingerprint = _geometry_fingerprint(objects)
        operation_ids = sorted(
            {operation_id for obj in objects for operation_id in _operation_ids(obj)}
        )
        resolved_parameters = {
            key: value
            for operation in plan_operations(scene)
            for instance in operation.get("instances", [])
            if instance.get("apply_to_role_id") == role_id
            and instance.get("instance_id") == str(root.get("assembly_instance_id") or "global")
            for key, value in (instance.get("resolved_parameters") or {}).items()
        }
        mesh_count = sum(1 for obj in objects if obj.type in {"MESH", "CURVE"})
        builder_matches = (
            root.get("builder_profile_id") == component["builder_profile_id"]
            and root.get("worker_handler") == builder["worker_handler"]
            and root.get("manifest_snapshot_sha256") == snapshot["snapshot_sha256"]
            and root.get("assembly_role_id") == role_id
        )
        passed = bool(mesh_count and bbox and fingerprint and builder_matches)
        instances.append(
            {
                "component_id": f"{role_id}:{root.get('assembly_instance_id') or root.name}",
                "instance_id": str(root.get("assembly_instance_id") or "global"),
                "object_role": expected_role,
                "semantic_root": str(root.get("semantic_root") or root.name),
                "geometry_source": record.get("effective_geometry_source"),
                "transform": {
                    "translation_m": [round(float(value), 9) for value in root.location],
                    "rotation_deg": [
                        round(float(value) * 180.0 / 3.141592653589793, 9)
                        for value in root.rotation_euler
                    ],
                    "scale": [round(float(value), 9) for value in root.scale],
                },
                "bounding_box_m": bbox,
                "geometry_fingerprint_sha256": fingerprint,
                "mesh_object_count": mesh_count,
                "assembly_operation_ids": operation_ids,
                "resolved_parameters": resolved_parameters,
                "qa": {
                    "semantic_geometry_present": mesh_count > 0,
                    "bounding_box_valid": bbox is not None,
                    "geometry_fingerprint_recorded": bool(fingerprint),
                    "builder_execution_matches": builder_matches,
                    "passed": passed,
                },
            }
        )
    return {
        "component_id": role_id,
        "role_id": role_id,
        "origin": "catalog_asset",
        "strategy": _catalog_strategy(component, instances),
        "generation_strategy": component["generation_strategy"],
        "asset_id": component["selected_asset_id"],
        "manifest": {
            "file_name": snapshot["manifest_file_name"],
            "source_sha256": snapshot["source_manifest_sha256"],
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "asset_file": snapshot["asset_file"],
            "verified_file_sha256": snapshot.get("verified_file_sha256"),
        },
        "builder": {
            "profile_id": builder["profile_id"],
            "profile_sha256": builder["profile_sha256"],
            "worker_handler": builder["worker_handler"],
        },
        "parameters": component.get("parameter_values", {}),
        "allowed_parameter_ids": component.get("allowed_parameter_ids", []),
        "quantity": len(instances),
        "expected_quantity": expected_quantity,
        "instances": instances,
        "requirement_links": component.get("requirement_links", []),
        "blueprint_links": component.get("blueprint_links", []),
        "qa": {
            "quantity_matches": len(instances) == expected_quantity,
            "all_instances_passed": all(item["qa"]["passed"] for item in instances),
            "passed": len(instances) == expected_quantity
            and all(item["qa"]["passed"] for item in instances),
        },
    }


def _catalog_strategy(component: dict, instances: list[dict]) -> str:
    if component["generation_strategy"] == "imported_glb_exact":
        return "reuse"
    if component.get("parameter_values") or any(
        instance.get("resolved_parameters") for instance in instances
    ):
        return "adapt"
    if component["generation_strategy"] == "internal_project_generated":
        return "compose"
    return "procedural_generate"


def plan_operations(scene: dict) -> list[dict]:
    operations = (scene.get("assembly_plan") or {}).get("operations", [])
    return [operation for operation in operations if isinstance(operation, dict)]


def _geometry_program_proof(bpy, program: dict) -> dict:
    program_id = str(program["program_id"])
    geometry_program_profile = (
        "typed_geometry_program_v2"
        if str(program.get("schema_version")) == "2.0.0"
        else "typed_geometry_program_v1"
    )
    root = next(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.get("geometry_program_group") is True
            and obj.get("geometry_program_id") == program_id
        ),
        None,
    )
    if root is None:
        raise RuntimeError(f"GEOMETRY_PROGRAM_PROOF_ROOT_MISSING:{program_id}")
    objects = [root, *list(root.children_recursive)]
    geometric_objects = [obj for obj in objects if obj.type in {"MESH", "CURVE"}]
    bbox = _bounding_box(geometric_objects)
    fingerprint = _geometry_fingerprint(geometric_objects)
    program_sha256 = _canonical_sha256(program)
    node_ids = sorted(
        str(obj.get("geometry_program_node_id"))
        for obj in objects
        if obj.get("geometry_program_node_id") is not None
    )
    expected_node_ids = sorted(str(node["node_id"]) for node in program.get("nodes", []))
    passed = bool(
        geometric_objects
        and bbox
        and fingerprint
        and node_ids == expected_node_ids
        and root.get("geometry_program_requested_quantity") == program["requested_quantity"]
    )
    exact_nodes = [node for node in program["nodes"] if node.get("kind") == "exact_asset"]
    envelope = program.get("maximum_dimensions_m")
    exact_dimensions_passed = (
        not exact_nodes
        or not envelope
        or bool(
            bbox
            and all(
                bbox["dimensions_m"][index] <= float(envelope[axis]) + 1e-6
                for index, axis in enumerate("xyz")
            )
        )
    )
    passed = passed and exact_dimensions_passed
    return {
        "exact_asset_sources": [
            {
                key: node[key]
                for key in (
                    "asset_id",
                    "asset_file",
                    "asset_sha256",
                    "manifest_file_name",
                    "manifest_sha256",
                )
            }
            for node in exact_nodes
        ],
        "component_id": f"geometry_program:{program_id}",
        "role_id": str(program["semantic_role"]),
        "origin": "catalog_asset" if exact_nodes else "geometry_program",
        "strategy": "reuse" if exact_nodes else "procedural_generate",
        "generation_strategy": "imported_glb_exact" if exact_nodes else geometry_program_profile,
        "asset_id": exact_nodes[0]["asset_id"] if exact_nodes else None,
        "manifest": None,
        "geometry_program": {
            "program_id": program_id,
            "schema_version": str(program.get("schema_version")),
            "program_sha256": program_sha256,
            "authorship": program["authorship"],
            "generator_provider": program["generator_provider"],
            "generator_model": program["generator_model"],
            "structured_output_mode": program["structured_output_mode"],
            "source_prompt_sha256": program["source_prompt_sha256"],
            "node_ids": node_ids,
        },
        "builder": {
            "profile_id": geometry_program_profile,
            "profile_sha256": program_sha256,
            "worker_handler": "geometry_program_compiler",
        },
        "parameters": {},
        "allowed_parameter_ids": [],
        "quantity": int(program["requested_quantity"]),
        "transform": {
            "translation_m": [round(float(value), 9) for value in root.location],
            "rotation_deg": [
                round(float(value) * 180.0 / 3.141592653589793, 9) for value in root.rotation_euler
            ],
            "scale": [round(float(value), 9) for value in root.scale],
        },
        "bounding_box_m": bbox,
        "geometry_fingerprint_sha256": fingerprint,
        "requirement_links": [f"geometry_requests:{program_id}"],
        "blueprint_links": [f"generated_component:{program_id}"],
        "qa": {
            "semantic_geometry_present": bool(geometric_objects),
            "bounding_box_valid": bbox is not None,
            "geometry_fingerprint_recorded": bool(fingerprint),
            "node_set_matches_program": node_ids == expected_node_ids,
            "exact_asset_requested_envelope_valid": exact_dimensions_passed,
            "passed": passed,
        },
    }


def _component_roots(bpy, role_id: str) -> list:
    roots = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("assembly_role_id") == role_id and obj.get("semantic_root") == obj.name
    ]
    return sorted(roots, key=lambda obj: (str(obj.get("assembly_instance_id") or ""), obj.name))


def _semantic_objects(bpy, semantic_root: str) -> list:
    return [obj for obj in bpy.context.scene.objects if obj.get("semantic_root") == semantic_root]


def _operation_ids(obj) -> list[str]:
    value = str(obj.get("assembly_operation_ids") or "")
    return [item for item in value.split(",") if item]


def _bounding_box(objects: Iterable) -> dict | None:
    vectors = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        vectors.extend(
            obj.matrix_world @ obj.location.__class__(corner) for corner in obj.bound_box
        )
    if not vectors:
        return None
    minimum = [min(float(vector[index]) for vector in vectors) for index in range(3)]
    maximum = [max(float(vector[index]) for vector in vectors) for index in range(3)]
    return {
        "minimum_m": [round(value, 9) for value in minimum],
        "maximum_m": [round(value, 9) for value in maximum],
        "dimensions_m": [round(maximum[index] - minimum[index], 9) for index in range(3)],
    }


def _geometry_fingerprint(objects: Iterable) -> str:
    digest = hashlib.sha256()
    geometric_count = 0
    for obj in sorted(objects, key=lambda item: item.name):
        if obj.type not in {"MESH", "CURVE"}:
            continue
        geometric_count += 1
        digest.update(obj.name.encode("utf-8"))
        digest.update(
            json.dumps(
                [[round(float(value), 9) for value in row] for row in obj.matrix_world],
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if obj.type == "MESH":
            for vertex in obj.data.vertices:
                digest.update(
                    json.dumps(
                        [round(float(value), 9) for value in vertex.co],
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
            for polygon in obj.data.polygons:
                digest.update(
                    json.dumps(list(polygon.vertices), separators=(",", ":")).encode("utf-8")
                )
        else:
            for spline in obj.data.splines:
                for point in spline.points:
                    digest.update(
                        json.dumps(
                            [round(float(value), 9) for value in point.co],
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
    return digest.hexdigest() if geometric_count else ""


def _canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
