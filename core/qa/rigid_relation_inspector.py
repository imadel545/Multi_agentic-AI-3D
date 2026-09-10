"""Measure compiled catalog alignment in the exported GLB node hierarchy."""

import math

from core.contracts.parametric import MeshCheckResult
from core.qa.assembly_constraint_inspector import _world_matrices


def inspect_rigid_relations(scene, payload) -> list[MeshCheckResult]:
    if not scene.rigid_component_relations:
        return []
    try:
        matrices, parents = _world_matrices(payload)
        roots = {}
        root_indices = {}
        for index, node in enumerate(payload.get("nodes", [])):
            extras = node.get("extras") or {}
            if extras.get("geometry_program_node_id") == "catalog_asset":
                key = extras.get("geometry_program_id")
                if key in roots:
                    raise ValueError("Duplicate catalog placement identity")
                roots[key] = matrices[index]
                root_indices[key] = index
        required_programs = {
            key
            for relation in scene.rigid_component_relations
            for key in (relation.source_program_id, relation.target_program_id)
        }
        for key in required_programs:
            root_index = root_indices[key]
            meshes = [
                index
                for index, node in enumerate(payload["nodes"])
                if "mesh" in node and (node.get("extras") or {}).get("geometry_program_id") == key
            ]
            if not meshes:
                raise ValueError("Related component has no mesh evidence")
            for index in meshes:
                visited = set()
                while index != root_index:
                    if index in visited:
                        raise ValueError("Cyclic component hierarchy")
                    visited.add(index)
                    index = parents[index]
        measures = []
        for relation in scene.rigid_component_relations:
            source = roots[relation.source_program_id]
            target = roots[relation.target_program_id]
            offset = relation.offset_world_m
            # SceneSpec uses Blender Z-up; GLB exports right-handed Y-up.
            expected = (offset.x, offset.z, -offset.y)
            error = math.sqrt(
                sum((source[i][3] - target[i][3] - expected[i]) ** 2 for i in range(3))
            )
            orientation_error = max(
                abs(source[i][j] - target[i][j]) for i in range(3) for j in range(3)
            )
            passed = (
                math.isfinite(error)
                and error <= relation.tolerance_m
                and math.isfinite(orientation_error)
                and orientation_error <= 1e-6
            )
            measures.append(
                MeshCheckResult(
                    name=f"rigid_relation:{relation.relationship_id}",
                    passed=passed,
                    detail=(
                        f"position_error_m={error:.9g}; "
                        f"orientation_matrix_error={orientation_error:.9g}"
                    ),
                )
            )
        return measures
    except (KeyError, ValueError, IndexError, TypeError):
        return [
            MeshCheckResult(
                name="rigid_relation:exported_evidence",
                passed=False,
                detail="Exported catalog identities or transforms are missing or invalid.",
            )
        ]
