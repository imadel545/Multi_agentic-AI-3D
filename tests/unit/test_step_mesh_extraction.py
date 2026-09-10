from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.services.step_mesh_extraction import StepMeshExtractionError, extract_step_mesh

ocp = pytest.importorskip("OCP")


def _write_box_step(path: Path) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    writer = STEPControl_Writer()
    assert writer.Transfer(BRepPrimAPI_MakeBox(100, 50, 20).Shape(), STEPControl_AsIs).name == (
        "IFSelect_RetDone"
    )
    assert writer.Write(str(path)).name == "IFSelect_RetDone"


def test_step_box_preserves_explicit_units_and_measured_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "box.step"
    _write_box_step(source)

    result = extract_step_mesh(source, linear_deflection_m=0.0001)

    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["source_units"] == {
        "name": "millimetre",
        "unit_scale_to_m": 0.001,
        "evidence": "STEP HEADER SI_UNIT length declaration",
    }
    assert result["counts"] == {
        "top_level_shapes": 1,
        "occurrences": 1,
        "assembly_nodes": 0,
        "mesh_nodes": 1,
        "source_faces": 6,
        "triangles": 12,
        "vertices": 24,
        "valid_brep_nodes": 1,
    }
    assert result["dimensions_m"] == pytest.approx({"x": 0.1, "y": 0.05, "z": 0.02})
    node = result["nodes"][0]
    assert node["kind"] == "mesh"
    assert node["parent_id"] is None
    assert node["source_face_count"] == 6
    assert node["triangle_count"] == 12
    assert node["surface_area_m2"] == pytest.approx(0.016, abs=1e-5)
    assert result["qualification"]["status"] == "geometry_inspected_not_qualified"
    assert result["qualification"]["professional_asset_admission"] is False


def test_step_adapter_refuses_missing_unit_declaration(tmp_path: Path) -> None:
    source = tmp_path / "unitless.step"
    source.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        "#1=PRODUCT('box');\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="ascii",
    )

    with pytest.raises(StepMeshExtractionError) as error:
        extract_step_mesh(source)

    assert error.value.code == "unsupported_units"


@pytest.mark.slow
def test_official_sierra_panel_retains_professional_part_identity_when_available() -> None:
    source = Path("/tmp/studio-professional-panel-20260910/panel.step")
    if not source.is_file():
        pytest.skip("The separately provisioned, license-restricted benchmark source is absent.")

    result = extract_step_mesh(source, linear_deflection_m=0.00015)
    names = {node["name"] for node in result["nodes"] if node["kind"] == "mesh"}

    assert result["source_units"]["name"] == "millimetre"
    assert result["counts"]["mesh_nodes"] == 18
    assert {
        "SP8-0668-VAR",
        "CABLES^LPAM-BC3G-26-3SP_TWO CABLES",
        "SC1-SMA-PC174_CRIMPED",
        "SR1-174-XLPE",
    }.issubset(names)
    assert result["dimensions_m"]["x"] == pytest.approx(0.46812, abs=0.0002)
    assert result["dimensions_m"]["y"] == pytest.approx(0.09302, abs=0.0002)
    assert result["dimensions_m"]["z"] == pytest.approx(0.04454, abs=0.0002)
    assert result["qualification"]["hierarchy_preserved"] is True
    assert result["qualification"]["professional_asset_admission"] is False
