"""Golden scene tests validating parametric tower generation and mesh QA.

These tests exercise real Blender generation for representative telecom
scenarios and assert that the backend exposes honest generation strategy and
mesh-level QA information.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service


@pytest.mark.parametrize(
    ("name", "requirements_text"),
    [
        (
            "lattice_30m",
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°.",
        ),
        (
            "monopole_36m",
            "Site 5G monopole 36m, 3 secteurs à 28m, azimuts 0 120 240, inclure RRU",
        ),
        (
            "rooftop_12m",
            "Site 5G rooftop mast 12m, 2 secteurs à 8m, azimuts 90 270, inclure RRU",
        ),
        (
            "small_cell_10m",
            "Small cell 5G pole 10m, 1 secteur à 7m azimuth 180, inclure RRU",
        ),
    ],
)
def test_parametric_golden_scene(name: str, requirements_text: str, tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=requirements_text,
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        assert response["status"] == "completed"

        status = client.get(f"/designs/{workflow_id}").json()
        assert status["status"] == "completed"
        assert status["generation_mode"] == "real_blender"
        assert status["generation_strategy"] == "mixed"
        assert status["mesh_qa_level"] in {"mesh_level_basic", "mesh_level_transform_basic"}
        assert status["mesh_qa_passed"] is True
        assert status["glb_inspection_summary"]["inspection_mode"] == "glb_parse"
        assert status["glb_inspection_summary"]["mesh_count"] > 0
        assert status["glb_inspection_summary"]["checks"]["has_labels"] is True
        assert status["geometry_validation_summary"]["status"] == "passed"
        assert status["geometry_validation_summary"]["checks"]["label_count_valid"] is True
        scene_spec = client.get(f"/designs/{workflow_id}/artifacts/scene_spec").json()
        assert status["geometry_validation_summary"]["object_counts"]["label"] >= len(
            scene_spec["sectors"]
        )
        if name == "lattice_30m":
            assert status["glb_inspection_summary"]["checks"]["has_foundation"] is True
            assert status["geometry_validation_summary"]["checks"]["foundation_count_valid"] is True
            assert status["geometry_validation_summary"]["object_counts"]["foundation"] >= 1

        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert bundle["generation_strategy"] == "mixed"
        assert bundle["mesh_qa_level"] in {"mesh_level_basic", "mesh_level_transform_basic"}
        assert bundle["mesh_qa_passed"] is True
        assert any(a["name"] == "design.glb" and a["available"] for a in bundle["viewer_artifacts"])
    finally:
        workflow_service.outputs_dir = original_outputs


def test_invalid_design_fails_cleanly(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text="Tour 5000m avec 100 secteurs",
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        assert response["status"] == "failed"
        status = client.get(f"/designs/{response['workflow_id']}").json()
        assert status["status"] == "failed"
        error_codes = {error["code"] for error in status.get("errors", [])}
        assert "INVALID_REQUIREMENTS" in error_codes
        assert "tower_height_m" in str(status["errors"])
        assert "sector_count" in str(status["errors"])
    finally:
        workflow_service.outputs_dir = original_outputs
