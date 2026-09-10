"""Fail-closed extraction of native DXF faces for a quarantined CAD experiment.

This is not a solid tessellator or an asset qualification service. Only geometry
reachable from modelspace is considered; unused block definitions are not models.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any

_UNIT_CODES = {
    "in": 1,
    "inches": 1,
    "ft": 2,
    "feet": 2,
    "mm": 4,
    "millimeters": 4,
    "cm": 5,
    "centimeters": 5,
    "m": 6,
    "meters": 6,
}
_ANNOTATIONS = {
    "TEXT",
    "MTEXT",
    "ATTRIB",
    "ATTDEF",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "HATCH",
    "IMAGE",
    "WIPEOUT",
    "POINT",
    "LINE",
    "ARC",
    "CIRCLE",
    "ELLIPSE",
    "LWPOLYLINE",
    "SPLINE",
    "SOLID",
    "TRACE",
}
_SOLIDS = {
    "3DSOLID",
    "BODY",
    "REGION",
    "SURFACE",
    "PLANESURFACE",
    "EXTRUDEDSURFACE",
    "LOFTEDSURFACE",
    "REVOLVEDSURFACE",
    "SWEPTSURFACE",
}


class CadMeshExtractionError(ValueError):
    """Controlled refusal to claim a complete native-mesh extraction."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def extract_dxf_mesh(path: str | Path, *, units: str | None = None) -> dict[str, Any]:
    """Return world-space mesh vertices in metres, hierarchy and source evidence.

    Unit overrides resolve unitless files only; conflicting declared units fail.
    The input limit is 100 MB, hierarchy depth 32, 100,000 visited entities and
    two million vertices/faces. Subdivision, ACIS, clipped/multiple inserts and
    unsupported entities fail rather than silently producing a partial model.
    Wire and annotation entities are excluded and counted, not tessellated.
    """
    try:
        import ezdxf
        from ezdxf import units as dxf_units
        from ezdxf.math import Matrix44
    except ImportError as exc:
        raise CadMeshExtractionError(
            "dependency_missing", "DXF mesh reading requires ezdxf."
        ) from exc

    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() != ".dxf":
        raise CadMeshExtractionError("invalid_source", "A readable DXF file is required.")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise CadMeshExtractionError("resource_limit", "DXF exceeds the 100 MB extraction limit.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        doc = ezdxf.readfile(source)
    except (OSError, ezdxf.DXFError, ValueError) as exc:
        raise CadMeshExtractionError("invalid_dxf", "The DXF could not be read safely.") from exc

    try:
        declared = int(doc.header.get("$INSUNITS", 0))
    except (ValueError, TypeError) as exc:
        raise CadMeshExtractionError("unsupported_units", "DXF INSUNITS is invalid.") from exc
    if declared < 0 or declared > 24:
        raise CadMeshExtractionError("unsupported_units", "DXF INSUNITS is invalid.")
    override = _UNIT_CODES.get(units.lower()) if isinstance(units, str) else None
    if units is not None and override is None:
        raise CadMeshExtractionError(
            "unsupported_units", "Use mm, cm, m, in or ft for explicit units."
        )
    if override and declared and override != declared:
        raise CadMeshExtractionError("unit_conflict", "Explicit units conflict with DXF INSUNITS.")
    effective = declared or override
    if not effective:
        raise CadMeshExtractionError(
            "unitless_source", "Unitless DXF requires explicit source units."
        )
    try:
        scale = dxf_units.conversion_factor(effective, 6)
    except (ValueError, TypeError, IndexError) as exc:
        raise CadMeshExtractionError(
            "unsupported_units", "DXF source units are unsupported."
        ) from exc
    if not math.isfinite(scale) or scale <= 0:
        raise CadMeshExtractionError("unsupported_units", "DXF source units have no valid scale.")

    nodes: list[dict[str, Any]] = []
    encountered: Counter[str] = Counter()
    ignored: Counter[str] = Counter()
    total_vertices = total_faces = 0
    bounds_min = [math.inf] * 3
    bounds_max = [-math.inf] * 3

    def fail(code: str, message: str) -> None:
        raise CadMeshExtractionError(code, message)

    def walk(entities, matrix, parent_id, lineage, active_blocks) -> None:
        nonlocal total_vertices, total_faces
        if len(active_blocks) > 32:
            fail("resource_limit", "DXF block nesting exceeds 32 levels.")
        for entity in entities:
            kind = entity.dxftype()
            encountered[kind] += 1
            if sum(encountered.values()) > 100_000:
                fail("resource_limit", "DXF exceeds 100,000 reachable entities.")
            handle = entity.dxf.get("handle")
            if not handle:
                fail("missing_identity", "A reachable entity has no source handle.")
            node_id = f"{parent_id or 'modelspace'}/{handle}"
            base = {
                "node_id": node_id,
                "parent_id": parent_id,
                "entity_handle": handle,
                "entity_type": kind,
                "block_lineage": list(lineage),
                "layer": entity.dxf.get("layer", "0"),
            }
            if kind in _SOLIDS:
                fail(
                    "solid_requires_tessellation", f"Reachable {kind} requires a solid tessellator."
                )
            if kind == "INSERT":
                if entity.dxf.get("row_count", 1) != 1 or entity.dxf.get("column_count", 1) != 1:
                    fail(
                        "unsupported_minsert", "Multiple block inserts require separate validation."
                    )
                if entity.has_extension_dict:
                    # ACAD_FILTER/SPATIAL is the XCLIP attachment. Reject even
                    # disabled clipping because its intended state is unqualified.
                    extension = entity.get_extension_dict()
                    if "ACAD_FILTER" in extension:
                        fail("unsupported_clip", "Clipped block inserts are not supported.")
                block = entity.block()
                if block is None or block.block.dxf.flags & (4 | 8 | 16):
                    fail(
                        "unresolved_block", "A block reference is missing or externally referenced."
                    )
                name = entity.dxf.name
                if name.casefold() in active_blocks:
                    fail("cyclic_blocks", "Cyclic block references cannot be extracted.")
                combined = entity.matrix44() @ matrix
                if (
                    not all(math.isfinite(value) for value in combined)
                    or not math.isfinite(combined.determinant())
                    or combined.determinant() == 0
                ):
                    fail("invalid_transform", "A block transform is non-finite or singular.")
                nodes.append(
                    {**base, "kind": "insert", "block_name": name, "matrix_world": list(combined)}
                )
                for attribute in entity.attribs:
                    ignored[attribute.dxftype()] += 1
                walk(block, combined, node_id, [*lineage, name], (*active_blocks, name.casefold()))
                continue
            if kind in _ANNOTATIONS or (
                kind == "POLYLINE" and not entity.is_poly_face_mesh and not entity.is_polygon_mesh
            ):
                if entity.dxf.get("thickness", 0):
                    fail("unsupported_extrusion", "A wire or annotation has nonzero thickness.")
                ignored[kind] += 1
                continue
            vertices, faces = _native_faces(entity)
            total_vertices += len(vertices)
            total_faces += len(faces)
            if total_vertices > 2_000_000 or total_faces > 2_000_000:
                fail("resource_limit", "DXF mesh exceeds the vertex or face extraction limit.")
            transformed = [list(matrix.transform(vertex) * scale) for vertex in vertices]
            _validate_mesh(transformed, faces)
            for vertex in transformed:
                for axis in range(3):
                    bounds_min[axis] = min(bounds_min[axis], vertex[axis])
                    bounds_max[axis] = max(bounds_max[axis], vertex[axis])
            # Reflection changes geometric handedness. Reverse the exported
            # winding to preserve the source-facing normals under that transform.
            if matrix.determinant() < 0:
                faces = [list(reversed(face)) for face in faces]
            nodes.append({**base, "kind": "mesh", "vertices_m": transformed, "faces": faces})

    try:
        walk(doc.modelspace(), Matrix44(), None, [], ())
    except CadMeshExtractionError:
        raise
    except (ezdxf.DXFError, ValueError, IndexError, KeyError, TypeError, AttributeError) as exc:
        raise CadMeshExtractionError(
            "invalid_geometry", "DXF geometry could not be extracted completely."
        ) from exc
    if not total_faces:
        fail("empty_mesh", "The DXF contains no reachable supported mesh faces.")
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        fail("source_changed", "The DXF changed during extraction.")
    return {
        "schema_version": "1.0",
        "source": {"path": str(source), "sha256": digest, "format": "dxf"},
        "source_units": dxf_units.unit_name(effective).lower(),
        "meters_per_unit": scale,
        "units_evidence": {"insunits": declared, "explicit_units": units},
        "coordinate_system": "DXF modelspace WCS, metres; Z up",
        "matrix_world_units": "source units; evidence only, vertices_m already transformed",
        "extraction_scope": "reachable_native_meshes_excluding_recorded_wires_and_annotations",
        "counts": {
            "mesh_nodes": sum(node["kind"] == "mesh" for node in nodes),
            "vertices": total_vertices,
            "faces": total_faces,
            "entities_by_type": dict(sorted(encountered.items())),
            "ignored_entities_by_type": dict(sorted(ignored.items())),
        },
        "bounds_m": {"min": bounds_min, "max": bounds_max},
        "nodes": nodes,
        "generation_eligible": False,
        "professional_qualified": False,
        "limitations": [
            "Native mesh extraction only; no CAD solid tessellation.",
            "Wire and annotation entities are excluded and counted.",
            "CAD materials, textures, semantic roles and source rights are not qualified.",
            "No manifold, engineering or manufacturing qualification is claimed.",
        ],
    }


def _native_faces(entity) -> tuple[list, list[list[int]]]:
    kind = entity.dxftype()
    if kind == "3DFACE":
        vertices = entity.wcs_vertices()
        return vertices, [list(range(len(vertices)))]
    if kind == "MESH":
        if entity.dxf.get("subdivision_levels", 0):
            raise CadMeshExtractionError(
                "unsupported_subdivision", "Subdivision meshes require tessellation."
            )
        return list(entity.vertices), [list(face) for face in entity.faces]
    if kind == "POLYLINE" and entity.is_poly_face_mesh:
        # Preserve source vertex indexing; negative polyface indices encode
        # invisible edges, not a different vertex or a hole.
        vertices, indexed_faces = entity.indexed_faces()
        return [vertex.dxf.location for vertex in vertices], [
            list(face.indices) for face in indexed_faces
        ]
    if kind == "POLYLINE" and entity.is_polygon_mesh:
        if entity.dxf.get("smooth_type", 0):
            raise CadMeshExtractionError(
                "unsupported_subdivision", "Smoothed polygon meshes require tessellation."
            )
        m, n = entity.dxf.m_count, entity.dxf.n_count
        if m < 2 or n < 2 or len(entity.vertices) != m * n:
            raise CadMeshExtractionError("invalid_geometry", "Polygon mesh dimensions are invalid.")
        vertices = [vertex.dxf.location for vertex in entity.vertices]
        faces = []
        for row in range(m if entity.is_m_closed else m - 1):
            for col in range(n if entity.is_n_closed else n - 1):
                next_row, next_col = (row + 1) % m, (col + 1) % n
                faces.append(
                    [row * n + col, row * n + next_col, next_row * n + next_col, next_row * n + col]
                )
        return vertices, faces
    raise CadMeshExtractionError(
        "unsupported_entity", f"Reachable {kind} has no validated mesh converter."
    )


def _validate_mesh(vertices: list, faces: list[list[int]]) -> None:
    if not vertices or not faces:
        raise CadMeshExtractionError(
            "empty_entity", "A reachable mesh entity has no vertices or faces."
        )
    if any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in vertices):
        raise CadMeshExtractionError(
            "invalid_geometry", "Mesh vertices must be finite 3D coordinates."
        )
    from ezdxf.math import Vec3

    for face in faces:
        if (
            len(face) < 3
            or len(set(face)) != len(face)
            or any(not isinstance(i, int) or i < 0 or i >= len(vertices) for i in face)
        ):
            raise CadMeshExtractionError("invalid_geometry", "Mesh face indices are invalid.")
        origin = Vec3(vertices[face[0]])
        vectors = [Vec3(vertices[index]) - origin for index in face[1:]]
        extent = max(vector.magnitude for vector in vectors)
        if not extent or not any(
            vectors[i].cross(vectors[i + 1]).magnitude > extent * extent * 1e-12
            for i in range(len(vectors) - 1)
        ):
            raise CadMeshExtractionError("invalid_geometry", "Mesh contains a degenerate face.")
