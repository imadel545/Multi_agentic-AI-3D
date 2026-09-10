"""Bounded neutral STEP assembly tessellation for quarantined asset evidence.

This adapter reads a neutral STEP file through Open CASCADE's XDE reader.  It
preserves the occurrence tree and source part names, then tessellates each leaf
solid into world-space metres.  It is deliberately an evidence boundary: the
returned document describes geometry that was read and measured, but it does
not grant catalogue rights or mark an asset generation-eligible.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from pathlib import Path
from typing import Any


class StepMeshExtractionError(ValueError):
    """Controlled refusal to claim a complete STEP extraction."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_PREFIXES = {
    "NONE": 1.0,
    "KILO": 1_000.0,
    "HECTO": 100.0,
    "DECA": 10.0,
    "DECI": 0.1,
    "CENTI": 0.01,
    "MILLI": 0.001,
    "MICRO": 0.000001,
    "NANO": 0.000000001,
}
_SI_LENGTH = re.compile(
    r"SI_UNIT\s*\(\s*\.([A-Z]+)\.\s*,\s*\.METRE\.\s*\)", re.IGNORECASE
)
_CONVERSION_LENGTH = re.compile(
    r"CONVERSION_BASED_UNIT\s*\(\s*'([^']+)'", re.IGNORECASE
)
_MAX_BYTES = 250 * 1024 * 1024
_MAX_OCCURRENCES = 4096
_MAX_VERTICES = 4_000_000
_MAX_TRIANGLES = 4_000_000


def extract_step_mesh(
    path: str | Path,
    *,
    linear_deflection_m: float = 0.00005,
    angular_deflection_rad: float = 0.5,
) -> dict[str, Any]:
    """Read and tessellate a STEP assembly while retaining source evidence.

    ``linear_deflection_m`` is converted to the source unit before asking OCCT
    to mesh.  The adapter refuses files without one unambiguous SI metre unit,
    malformed XDE trees, invalid B-Reps, missing leaf faces and resource-limit
    violations.  A face's triangulation location and every XDE occurrence
    location are applied before coordinates are converted to metres.
    """

    source = Path(path).resolve()
    if source.suffix.lower() not in {".step", ".stp"}:
        raise StepMeshExtractionError("invalid_source", "A STEP or STP file is required.")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise StepMeshExtractionError(
            "source_unreadable", "The STEP file could not be read."
        ) from exc
    if len(raw) > _MAX_BYTES:
        raise StepMeshExtractionError("resource_limit", "STEP exceeds the 250 MB safety limit.")
    source_hash = hashlib.sha256(raw).hexdigest()
    unit_name, unit_scale = _step_length_unit(raw)
    if not math.isfinite(linear_deflection_m) or not 0 < linear_deflection_m <= 0.01:
        raise StepMeshExtractionError(
            "invalid_tolerance", "Linear tessellation tolerance must be between 0 and 10 mm."
        )
    if not math.isfinite(angular_deflection_rad) or not 0 < angular_deflection_rad <= math.pi:
        raise StepMeshExtractionError(
            "invalid_tolerance", "Angular tessellation tolerance is outside the safe range."
        )

    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.collections import Sequence_TDF_Label
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDF import TDF_Label
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
    except ImportError as exc:
        raise StepMeshExtractionError(
            "dependency_missing", "STEP inspection requires the optional cad OCP dependency."
        ) from exc

    reader = STEPCAFControl_Reader()
    try:
        status = reader.ReadFile(str(source))
    except Exception as exc:  # OCCT raises wrapped Standard_Failure exceptions.
        raise StepMeshExtractionError(
            "step_read_failed", "The STEP reader rejected the file."
        ) from exc
    if getattr(status, "name", str(status)) not in {
        "IFSelect_RetDone",
        "IFSelect_ReturnStatus.IFSelect_RetDone",
    }:
        raise StepMeshExtractionError(
            "step_read_failed", "The STEP reader did not complete successfully."
        )

    document = TDocStd_Document(TCollection_ExtendedString("agentic-step-inspection"))
    try:
        transferred = reader.Transfer(document)
    except Exception as exc:
        raise StepMeshExtractionError(
            "step_transfer_failed", "The STEP assembly could not be transferred."
        ) from exc
    if not transferred:
        raise StepMeshExtractionError("step_transfer_failed", "The STEP assembly transfer failed.")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free = Sequence_TDF_Label()
    shape_tool.GetFreeShapes(free)
    if free.Length() < 1:
        raise StepMeshExtractionError(
            "empty_assembly", "The STEP file contains no top-level shape."
        )

    nodes: list[dict[str, Any]] = []
    counts = {
        "top_level_shapes": free.Length(),
        "occurrences": 0,
        "assembly_nodes": 0,
        "mesh_nodes": 0,
        "source_faces": 0,
        "triangles": 0,
        "vertices": 0,
        "valid_brep_nodes": 0,
    }
    all_points: list[tuple[float, float, float]] = []

    def fail(code: str, message: str) -> None:
        raise StepMeshExtractionError(code, message)

    def entry(label) -> str:
        stream = io.BytesIO()
        label.EntryDump(stream)
        return stream.getvalue().decode("ascii", errors="strict")

    def name(label) -> str:
        try:
            from OCP.TDataStd import TDataStd_Name

            attribute = TDataStd_Name()
            if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
                value = attribute.Get().ToExtString().strip()
                if value:
                    return value
        except Exception:
            # A missing display name is acceptable; the XDE entry is the stable identity.
            pass
        return "Unnamed STEP component"

    def matrix(label_shape):
        return label_shape.Location().Transformation()

    def identity_shape(shape):
        # XDE definitions can carry a location.  Strip it before applying the
        # occurrence transform so it is represented exactly once.
        if shape.Location().IsIdentity():
            return shape
        return shape.Located(TopLoc_Location())

    def transform_point(point, transform):
        transformed = point.Transformed(transform)
        values = tuple(float(transformed.Coord(index)) * unit_scale for index in (1, 2, 3))
        if not all(math.isfinite(value) for value in values):
            fail("non_finite_geometry", "STEP tessellation produced a non-finite coordinate.")
        return values

    def mesh_leaf(
        shape,
        *,
        node_id: str,
        parent_id: str | None,
        label,
        definition,
        transform,
    ):
        display_name = name(definition)
        if shape.IsNull():
            fail("empty_component", f"STEP component {display_name} has no shape.")
        analyzer = BRepCheck_Analyzer(shape, True, False, False)
        if not analyzer.IsValid():
            fail("invalid_brep", f"STEP component {display_name} has invalid B-Rep topology.")
        counts["valid_brep_nodes"] += 1
        # The OCCT deflection is expressed in the source length unit.
        mesh = BRepMesh_IncrementalMesh(
            shape,
            linear_deflection_m / unit_scale,
            False,
            angular_deflection_rad,
            False,
        )
        if not mesh.IsDone():
            fail("tessellation_failed", f"STEP component {name(label)} could not be tessellated.")
        vertices: list[tuple[float, float, float]] = []
        faces: list[list[int]] = []
        surface_area_m2 = 0.0
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        face_count = 0
        while explorer.More():
            face_count += 1
            face = TopoDS.Face(explorer.Current())
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)
            if triangulation is None:
                fail(
                    "face_tessellation_missing",
                    f"STEP face in {display_name} has no triangulation.",
                )
            face_transform = transform.Multiplied(location.Transformation())
            offset = len(vertices)
            for index in range(1, triangulation.NbNodes() + 1):
                vertices.append(transform_point(triangulation.Node(index), face_transform))
            for triangle_index in range(1, triangulation.NbTriangles() + 1):
                triangle = triangulation.Triangle(triangle_index)
                first, second, third = (triangle.Value(index) - 1 + offset for index in (1, 2, 3))
                if face.Orientation() == TopAbs_REVERSED:
                    second, third = third, second
                faces.append([first, second, third])
                a, b, c = (vertices[index] for index in (first, second, third))
                ab = tuple(b[index] - a[index] for index in range(3))
                ac = tuple(c[index] - a[index] for index in range(3))
                cross = (
                    ab[1] * ac[2] - ab[2] * ac[1],
                    ab[2] * ac[0] - ab[0] * ac[2],
                    ab[0] * ac[1] - ab[1] * ac[0],
                )
                surface_area_m2 += 0.5 * math.sqrt(sum(value * value for value in cross))
            explorer.Next()
        if face_count == 0 or not faces:
            fail(
                "component_has_no_faces",
                f"STEP component {display_name} contains no tessellatable faces.",
            )
        if len(vertices) > _MAX_VERTICES or len(faces) > _MAX_TRIANGLES:
            fail("resource_limit", "A STEP component exceeds the tessellation resource limit.")
        counts["mesh_nodes"] += 1
        counts["source_faces"] += face_count
        counts["vertices"] += len(vertices)
        counts["triangles"] += len(faces)
        if counts["vertices"] > _MAX_VERTICES or counts["triangles"] > _MAX_TRIANGLES:
            fail("resource_limit", "STEP assembly exceeds the tessellation resource limit.")
        all_points.extend(vertices)
        lower = [min(point[index] for point in vertices) for index in range(3)]
        upper = [max(point[index] for point in vertices) for index in range(3)]
        nodes.append(
            {
                "node_id": node_id,
                "parent_id": parent_id,
                "kind": "mesh",
                "name": display_name,
                "occurrence_name": name(label),
                "entity_handle": entry(label),
                "definition_entry": entry(definition),
                "layer": "STEP",
                "vertices_m": vertices,
                "faces": faces,
                "source_face_count": face_count,
                "triangle_count": len(faces),
                "surface_area_m2": surface_area_m2,
                "bounding_box_m": {"minimum": lower, "maximum": upper},
            }
        )

    def visit(
        label,
        parent_id: str | None,
        parent_transform,
        active_definitions: tuple[str, ...],
        *,
        root=False,
    ):
        if counts["occurrences"] >= _MAX_OCCURRENCES:
            fail("resource_limit", "STEP assembly exceeds 4,096 occurrences.")
        counts["occurrences"] += 1
        has_reference = TDF_Label()
        is_reference = shape_tool.GetReferredShape_s(label, has_reference)
        definition = has_reference if is_reference else label
        definition_entry = entry(definition)
        if definition_entry in active_definitions:
            fail("cyclic_assembly", "STEP assembly contains a cyclic component reference.")
        located = shape_tool.GetShape_s(label)
        definition_shape = shape_tool.GetShape_s(definition)
        occurrence_transform = matrix(located)
        definition_transform = matrix(definition_shape)
        world_transform = (
            parent_transform.Multiplied(occurrence_transform).Multiplied(definition_transform)
        )
        shape = identity_shape(definition_shape)
        components = Sequence_TDF_Label()
        is_assembly = shape_tool.GetComponents_s(definition, components)
        node_id = f"step:{entry(label)}" if root else f"{parent_id}/step:{entry(label)}"
        display_name = name(definition)
        if is_assembly and components.Length() > 0:
            counts["assembly_nodes"] += 1
            nodes.append(
                {
                    "node_id": node_id,
                    "parent_id": parent_id,
                    "kind": "assembly",
                    "name": display_name,
                    "occurrence_name": name(label),
                    "entity_handle": entry(label),
                    "definition_entry": definition_entry,
                    "layer": "STEP",
                    "component_count": components.Length(),
                }
            )
            for index in range(1, components.Length() + 1):
                visit(
                    components.Value(index),
                    node_id,
                    world_transform,
                    (*active_definitions, definition_entry),
                )
            return
        mesh_leaf(
            shape,
            node_id=node_id,
            parent_id=parent_id,
            label=label,
            definition=definition,
            transform=world_transform,
        )

    identity = TopLoc_Location().Transformation()
    for index in range(1, free.Length() + 1):
        visit(free.Value(index), None, identity, (), root=True)

    if not all_points:
        fail("empty_tessellation", "STEP produced no mesh vertices.")
    lower = [min(point[index] for point in all_points) for index in range(3)]
    upper = [max(point[index] for point in all_points) for index in range(3)]
    return {
        "schema_version": "1.0.0",
        "adapter": "ocp_step_xde",
        "adapter_version": "1.0.0",
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "format": "step",
            "size_bytes": len(raw),
        },
        "source_units": {
            "name": unit_name,
            "unit_scale_to_m": unit_scale,
            "evidence": "STEP HEADER SI_UNIT length declaration",
        },
        "coordinate_frame": {
            "source": "STEP XDE occurrence and face triangulation frames",
            "output": "right_handed_z_up_metres",
            "transform_applied": True,
        },
        "tessellation": {
            "linear_deflection_m": linear_deflection_m,
            "angular_deflection_rad": angular_deflection_rad,
            "mesh_method": "BRepMesh_IncrementalMesh",
        },
        "nodes": nodes,
        "counts": counts,
        "bounding_box_m": {"minimum": lower, "maximum": upper},
        "dimensions_m": {
            axis: upper[index] - lower[index]
            for index, axis in enumerate(("x", "y", "z"))
        },
        "qualification": {
            "status": "geometry_inspected_not_qualified",
            "units_confident": True,
            "hierarchy_preserved": True,
            "geometry_fidelity": "tessellated_neutral_source",
            "source_hash_verified": True,
            "professional_asset_admission": False,
            "limitations": [
                "Tessellated geometry is a viewer derivative; it is not a signed "
                "engineering approval.",
                "Source terms and redistribution rights are not granted by this adapter.",
                "Semantic role, connector fit and adaptation boundaries require a "
                "separate qualification record.",
            ],
        },
    }


def _step_length_unit(raw: bytes) -> tuple[str, float]:
    """Extract one explicit SI metre unit; never infer scale from extents."""

    text = raw.decode("latin1", errors="replace")
    matches = [
        (prefix.upper(), _PREFIXES.get(prefix.upper()))
        for prefix in _SI_LENGTH.findall(text)
    ]
    if not matches or any(scale is None for _, scale in matches):
        conversion_names = _CONVERSION_LENGTH.findall(text)
        raise StepMeshExtractionError(
            "unsupported_units",
            "STEP must declare one supported SI metre length unit; "
            f"found {conversion_names[0] if conversion_names else 'none'}.",
        )
    scales = {float(scale) for _, scale in matches if scale is not None}
    if len(scales) != 1:
        raise StepMeshExtractionError("unit_conflict", "STEP declares conflicting length units.")
    prefix, scale = matches[0]
    unit_name = "metre" if prefix == "NONE" else f"{prefix.lower()}metre"
    return unit_name, float(scale)
