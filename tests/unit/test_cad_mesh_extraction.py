"""Synthetic unit fixtures only: none qualifies a raw or professional CAD asset."""

import hashlib
import json
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from core.services.cad_mesh_extraction import (  # noqa: E402
    CadMeshExtractionError,
    extract_dxf_mesh,
)


def _document(units=4):
    doc = ezdxf.new("R2013")
    doc.header["$INSUNITS"] = units
    return doc


def _write(doc, path: Path) -> Path:
    doc.saveas(path)
    return path


def test_nested_blocks_preserve_source_geometry_world_pose_and_identity(tmp_path):
    doc = _document()
    leaf = doc.blocks.new("test_leaf", base_point=(10, 0, 0))
    face = leaf.add_3dface([(10, 0, 0), (1010, 0, 0), (10, 1000, 0)])
    assembly = doc.blocks.new("test_assembly")
    inner = assembly.add_blockref("test_leaf", (1000, 0, 0), dxfattribs={"rotation": 90})
    outer = doc.modelspace().add_blockref("test_assembly", (0, 2000, 3000))
    doc.modelspace().add_text("test annotation")
    # Unsupported geometry in an unused block is not part of modelspace.
    doc.blocks.new("unused_test_solid").add_3dsolid()
    path = _write(doc, tmp_path / "nested.dxf")
    result = extract_dxf_mesh(path)

    mesh = next(node for node in result["nodes"] if node["kind"] == "mesh")
    assert mesh["node_id"] == f"modelspace/{outer.dxf.handle}/{inner.dxf.handle}/{face.dxf.handle}"
    assert mesh["block_lineage"] == ["test_assembly", "test_leaf"]
    assert mesh["vertices_m"][0] == pytest.approx([1, 2, 3])
    assert mesh["vertices_m"][1] == pytest.approx([1, 3, 3])
    assert mesh["vertices_m"][2] == pytest.approx([0, 2, 3])
    assert result["bounds_m"]["min"] == pytest.approx([0, 2, 3])
    assert result["bounds_m"]["max"] == pytest.approx([1, 3, 3])
    assert result["counts"]["ignored_entities_by_type"] == {"TEXT": 1}
    assert result["counts"]["entities_by_type"] == {"3DFACE": 1, "INSERT": 2, "TEXT": 1}
    assert result["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["generation_eligible"] is result["professional_qualified"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("solid_kind", ["3dsolid", "region", "body"])
def test_reachable_mixed_solid_cannot_return_partial_mesh(tmp_path, solid_kind):
    doc = _document()
    doc.dxfversion = "AC1024"
    doc.modelspace().add_3dface([(0, 0, 0), (100, 0, 0), (0, 100, 0)])
    block = doc.blocks.new("test_mixed")
    solid = getattr(block, f"add_{solid_kind}")()
    # Opaque, deliberately synthetic SAT: this test verifies refusal by entity
    # type and must not depend on a licensed ACIS kernel or real solid payload.
    solid.sat = ("test-only opaque SAT payload",)
    doc.modelspace().add_blockref("test_mixed", (0, 0, 0))
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(_write(doc, tmp_path / "mixed.dxf"))
    assert error.value.code == "solid_requires_tessellation"


def test_unitless_requires_explicit_units_and_declared_conflicts_fail(tmp_path):
    doc = _document(0)
    doc.modelspace().add_3dface([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    path = _write(doc, tmp_path / "unitless.dxf")
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(path)
    assert error.value.code == "unitless_source"
    result = extract_dxf_mesh(path, units="m")
    assert result["meters_per_unit"] == 1
    assert result["units_evidence"] == {"insunits": 0, "explicit_units": "m"}
    doc.header["$INSUNITS"] = 4
    _write(doc, path)
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(path, units="m")
    assert error.value.code == "unit_conflict"


def test_polyface_negative_hidden_edge_and_closed_polymesh(tmp_path):
    doc = _document(6)
    polyface = doc.modelspace().add_polyface()
    polyface.append_face([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    record = polyface.vertices[-1]
    record.dxf.vtx2 = -record.dxf.vtx2
    polymesh = doc.modelspace().add_polymesh((3, 2))
    for m, xy in enumerate([(0, 0), (1, 0), (0, 1)]):
        for n in range(2):
            polymesh.set_mesh_vertex((m, n), (*xy, n))
    polymesh.close(m_close=True)
    result = extract_dxf_mesh(_write(doc, tmp_path / "poly.dxf"))
    assert result["counts"]["faces"] == 4
    assert result["nodes"][0]["faces"] == [[0, 1, 2]]
    assert result["nodes"][1]["faces"][-1] == [4, 5, 1, 0]


def test_unsigned_corrupt_polyface_index_fails_without_silent_repair(tmp_path):
    doc = _document()
    polyface = doc.modelspace().add_polyface()
    polyface.append_face([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    polyface.vertices[-1].dxf.vtx2 = 65533
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(_write(doc, tmp_path / "corrupt_poly.dxf"))
    assert error.value.code == "invalid_geometry"


def test_mesh_and_reflection_preserve_normals_by_reversing_winding(tmp_path):
    doc = _document(6)
    block = doc.blocks.new("test_mesh")
    mesh = block.add_mesh()
    with mesh.edit_data() as data:
        data.vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        data.faces = [(0, 1, 2)]
    doc.modelspace().add_blockref("test_mesh", (0, 0, 0), dxfattribs={"xscale": -1})
    result = extract_dxf_mesh(_write(doc, tmp_path / "mirror.dxf"))
    assert result["nodes"][1]["faces"] == [[2, 1, 0]]
    assert result["nodes"][1]["vertices_m"][1] == [-1, 0, 0]


@pytest.mark.parametrize(
    "case,expected",
    [
        ("missing", "unresolved_block"),
        ("cyclic", "cyclic_blocks"),
        ("minsert", "unsupported_minsert"),
        ("clipped", "unsupported_clip"),
    ],
)
def test_unsafe_block_expansion_is_rejected(tmp_path, case, expected):
    doc = _document()
    block = doc.blocks.new("test_block")
    block.add_3dface([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    reference = doc.modelspace().add_blockref("test_block", (0, 0, 0))
    if case == "missing":
        reference.dxf.name = "missing_block"
    elif case == "cyclic":
        block.add_blockref("test_block", (0, 0, 0))
    elif case == "minsert":
        reference.dxf.row_count = 2
    elif case == "clipped":
        from ezdxf.xclip import XClip

        XClip(reference).set_block_clipping_path([(0, 0), (1, 1)])
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(_write(doc, tmp_path / "unsafe.dxf"))
    assert error.value.code == expected


@pytest.mark.parametrize(
    "case,expected",
    [
        ("wire", "empty_mesh"),
        ("collinear", "invalid_geometry"),
        ("nonfinite", "invalid_geometry"),
        ("subdivision", "unsupported_subdivision"),
        ("helix", "unsupported_entity"),
    ],
)
def test_invalid_or_nonmesh_geometry_has_controlled_refusal(tmp_path, case, expected):
    doc = _document()
    model = doc.modelspace()
    if case == "wire":
        model.add_polyline3d([(0, 0, 0), (1, 0, 1), (1, 1, 0)])
    elif case == "collinear":
        model.add_3dface([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    elif case == "nonfinite":
        model.add_3dface([(0, 0, 0), (float("nan"), 0, 0), (0, 1, 0)])
    elif case == "subdivision":
        mesh = model.add_mesh(dxfattribs={"subdivision_levels": 1})
        with mesh.edit_data() as data:
            data.vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
            data.faces = [(0, 1, 2)]
    else:
        model.new_entity("HELIX", dxfattribs={})
    with pytest.raises(CadMeshExtractionError) as error:
        extract_dxf_mesh(_write(doc, tmp_path / "invalid.dxf"))
    assert error.value.code == expected
