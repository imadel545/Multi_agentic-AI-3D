"""Synthetic storage fixtures exercise the narrowly scoped LibreDWG bridge."""

import pytest

from core.services.cad_conversion import verify_polyface_conversion

ezdxf = pytest.importorskip("ezdxf")


def _fixture():
    doc = ezdxf.new()
    doc.units = 4
    mesh = doc.modelspace().add_polyface()
    mesh.append_faces([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]])
    face = mesh.vertices[-1]
    face.dxf.vtx2 = 65533
    source = {
        "HEADER": {"INSUNITS": 4},
        "OBJECTS": [
            {
                "entity": "POLYLINE_PFACE",
                "handle": [0, 2, int(mesh.dxf.handle, 16)],
                "entmode": 2,
                "vertex": [[5, 2, int(v.dxf.handle, 16)] for v in mesh.vertices],
            }
        ],
    }
    for vertex in mesh.vertices:
        data = {"handle": [0, 2, int(vertex.dxf.handle, 16)]}
        if vertex.is_face_record:
            data.update(
                entity="VERTEX_PFACE_FACE",
                vertind=[vertex.dxf.get(k, 0) for k in ("vtx0", "vtx1", "vtx2", "vtx3")],
            )
        else:
            data.update(entity="VERTEX_PFACE", point=list(vertex.dxf.location))
        source["OBJECTS"].append(data)
    return source, doc, mesh


def test_verified_unsigned_hidden_edge_is_decoded_without_moving_vertices():
    source, doc, mesh = _fixture()
    report = verify_polyface_conversion(source, doc)
    assert report["source_vertices_compared"] == 3
    assert report["source_faces_compared"] == 1
    assert report["unsigned_hidden_edge_indices_normalized"] == 1
    assert mesh.vertices[-1].dxf.vtx2 == -3
    assert len(list(mesh.faces())) == 1


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("coordinate", "VERTEX_CHANGED"),
        ("indices", "FACE_INDICES_CHANGED"),
        ("order", "VERTEX_ORDER_CHANGED"),
        ("units", "UNITS_CHANGED"),
        ("solid", "UNSUPPORTED_ENTITIES"),
        ("block", "REQUIRES_MODELSPACE"),
    ],
)
def test_conversion_discrepancies_are_rejected(mutation, error):
    source, doc, mesh = _fixture()
    if mutation == "coordinate":
        mesh.vertices[0].dxf.location = (10, 0, 0)
    elif mutation == "indices":
        mesh.vertices[-1].dxf.vtx0 = 2
    elif mutation == "order":
        source["OBJECTS"][0]["vertex"].reverse()
    elif mutation == "units":
        doc.units = 6
    elif mutation == "solid":
        source["OBJECTS"].append({"entity": "3DSOLID"})
    elif mutation == "block":
        source["OBJECTS"][0]["entmode"] = 0
    with pytest.raises(ValueError, match=error):
        verify_polyface_conversion(source, doc)
