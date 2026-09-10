"""Verify LibreDWG polyface conversion before consuming its DXF output.

This deliberately narrow bridge compares source handles, vertices and face
indices before repairing LibreDWG's unsigned representation of signed int16
hidden-edge indices. It is not a general DWG fidelity certificate.
"""

from __future__ import annotations

import math


def verify_polyface_conversion(source: dict, document) -> dict:
    records = source.get("OBJECTS", [])
    if source.get("HEADER", {}).get("INSUNITS", 0) != document.header.get("$INSUNITS", 0):
        raise ValueError("DWG_CONVERSION_UNITS_CHANGED")
    relevant = {"POLYLINE_PFACE", "VERTEX_PFACE", "VERTEX_PFACE_FACE"}
    allowed = relevant | {
        "INSERT",
        "ATTRIB",
        "ATTDEF",
        "SEQEND",
        "BLOCK",
        "ENDBLK",
        "LINE",
        "ARC",
        "CIRCLE",
        "TEXT",
        "MTEXT",
        "LWPOLYLINE",
        "POINT",
        "DIMENSION_ANG2LN",
        "DIMENSION_ALIGNED",
        "DIMENSION_LINEAR",
    }
    unsupported = sorted(
        {r["entity"] for r in records if r.get("entity") not in allowed and "entity" in r}
    )
    if unsupported:
        raise ValueError(f"DWG_POLYFACE_BRIDGE_UNSUPPORTED_ENTITIES:{unsupported}")
    entities = [r for r in records if r.get("entity") in relevant]
    if not entities:
        raise ValueError("DWG_POLYFACE_BRIDGE_NO_FACES")
    corrected = 0
    vertices = 0
    faces = 0
    mesh_handles = set()
    for record in entities:
        handle = format(record["handle"][2], "X")
        entity = document.entitydb.get(handle)
        if entity is None:
            raise ValueError(f"DWG_CONVERSION_HANDLE_MISSING:{handle}")
        kind = record["entity"]
        if kind == "POLYLINE_PFACE":
            if entity.dxftype() != "POLYLINE" or not entity.is_poly_face_mesh:
                raise ValueError("DWG_CONVERSION_POLYFACE_CHANGED")
            if record.get("entmode") != 2 or entity.get_layout() != document.modelspace():
                raise ValueError("DWG_BRIDGE_REQUIRES_MODELSPACE_POLYFACES")
            ordered_handles = [format(value[-1], "X") for value in record["vertex"]]
            if ordered_handles != [v.dxf.handle for v in entity.vertices]:
                raise ValueError("DWG_CONVERSION_VERTEX_ORDER_CHANGED")
            mesh_handles.add(handle)
        elif kind == "VERTEX_PFACE":
            if entity.dxftype() != "VERTEX" or entity.is_face_record:
                raise ValueError("DWG_CONVERSION_VERTEX_TYPE_CHANGED")
            if not all(
                math.isfinite(float(a))
                and math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-12)
                for a, b in zip(record["point"], entity.dxf.location, strict=True)
            ):
                raise ValueError("DWG_CONVERSION_VERTEX_CHANGED")
            vertices += 1
        else:
            if entity.dxftype() != "VERTEX" or not entity.is_face_record:
                raise ValueError("DWG_CONVERSION_FACE_TYPE_CHANGED")
            source_indices = record["vertind"]
            keys = ("vtx0", "vtx1", "vtx2", "vtx3")
            values = [entity.dxf.get(key, 0) for key in keys]
            if source_indices != values:
                raise ValueError("DWG_CONVERSION_FACE_INDICES_CHANGED")
            for key, value in zip(keys, values, strict=True):
                if 32768 <= value <= 65535:
                    setattr(entity.dxf, key, value - 65536)
                    corrected += 1
            faces += 1
    actual_mesh_handles = {
        e.dxf.handle
        for e in document.entitydb.values()
        if e.dxftype() == "POLYLINE" and e.is_poly_face_mesh
    }
    if actual_mesh_handles != mesh_handles:
        raise ValueError("DWG_CONVERSION_MESH_SET_CHANGED")
    # Force traversal now: invalid indices must not be repaired by geometry tools.
    for handle in mesh_handles:
        polyface = document.entitydb[handle]
        for face in polyface.faces():
            if len(face) < 4:  # First record is the face definition itself.
                raise ValueError("DWG_CONVERSION_DEGENERATE_FACE")
    return {
        "source_vertices_compared": vertices,
        "source_faces_compared": faces,
        "source_meshes_compared": len(mesh_handles),
        "unsigned_hidden_edge_indices_normalized": corrected,
        "method": "Source-handle vertex and face-index equality before signed-int16 decoding",
        "scope": "modelspace polyface topology and WCS positions; not block-based DWG assemblies",
    }
