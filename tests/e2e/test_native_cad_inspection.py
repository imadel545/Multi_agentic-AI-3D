"""Real local CAD corpus smoke; synthetic geometry is not substituted if absent."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scripts.inspect_native_cad import inspect


@pytest.mark.blender_runtime
def test_real_native_dwg_preserves_source_faces_through_blender(tmp_path):
    source = Path("assets/library/raw/maj_des_blocs/3D/Batiment/Mobilier/Chaise/ac3_billo2.dwg")
    if not source.exists() or not shutil.which("dwgread") or not shutil.which("dwg2dxf"):
        pytest.skip("Requires the real local CAD corpus and LibreDWG.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == "b5d422142d550efb3e7dd0aa0eab09efd500e1333f8a93bc9d1efa1956902903"
    result = inspect(source, tmp_path)
    assert result["status"] == "geometry_inspected_not_qualified"
    assert result["generation_eligible"] is False
    assert result["professional_qualified"] is False
    assert result["source_unchanged"] is True
    assert result["conversion"]["source_vertices_compared"] == 7952
    assert result["conversion"]["source_faces_compared"] == 12720
    assert result["conversion"]["source_meshes_compared"] == 4
    assert result["blender"]["geometry_roundtrip"]["triangles"] == 12720
    assert result["blender"]["geometry_roundtrip"]["maximum_vertex_error_m"] <= 1e-8
    extraction = json.loads((tmp_path / "extraction.json").read_text())
    assert extraction["meters_per_unit"] == pytest.approx(0.001)
    assert extraction["bounds_m"]["max"][2] == pytest.approx(0.000675, abs=1e-9)
    for record in result["artifacts"].values():
        assert hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() == record["sha256"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
