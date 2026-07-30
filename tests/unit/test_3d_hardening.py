import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.api.telecom_studio_api.workflow import WorkflowService
from apps.blender_worker.generate_scene import _try_import_glb_asset
from core.contracts.parametric import BoundingBoxM
from core.contracts.scene import (
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)
from core.contracts.tower import TowerCharacteristics
from core.qa.glb_inspector import GLBInspector
from core.qa.mesh_qa import (
    MeshQA,
    _is_allowed_primary_equipment_contact,
    _SemanticEntity,
)
from core.services.scene_versioning import (
    SceneVersioningService,
    _verify_critical_report_proof,
    _write_critical_report_proof,
)


def _minimal_scene() -> SceneSpec:
    return SceneSpec(
        scene_id="wf_hardening",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
            characteristics=TowerCharacteristics(
                structure="lattice",
                leg_count=4,
                base_width_m=4,
                top_width_m=1,
                foundation_type="unknown",
                material="galvanized_steel",
            ),
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="antenna",
                install_height_m=24,
                azimuth_deg=0,
                beamwidth_deg=65,
                include_cable=False,
                include_label=False,
            )
        ],
        visual_elements=VisualElements(
            include_sector_beams=False,
            include_azimuth_arrows=False,
            include_height_markers=False,
            include_labels=False,
        ),
    )


def _write_malformed_transform_glb(path: Path) -> None:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 30, 0)
    payload = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [
            {
                "name": "tower",
                "mesh": 0,
                "extras": {
                    "semantic_root": "tower",
                    "semantic_id": "tower",
                    "role": "tower",
                    "geometry_source": "parametric_generated",
                    "generation_strategy": "parametric_generated",
                },
            },
            {
                "name": "antenna_S1",
                "mesh": 0,
                "rotation": [0.0],
                "extras": {
                    "semantic_root": "antenna_S1",
                    "semantic_id": "antenna_S1",
                    "role": "antenna",
                    "sector_id": "S1",
                    "requested_hba_m": 24,
                    "requested_azimuth_deg": 0,
                    "semantic_forward_axis": "-Z",
                    "geometry_source": "parametric_generated",
                    "generation_strategy": "parametric_generated",
                },
            },
        ],
        "scenes": [{"nodes": [0, 1]}],
        "scene": 0,
    }
    json_chunk = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary_chunk = positions + (b"\0" * ((-len(positions)) % 4))
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(binary_chunk), 0x004E4942)
        + binary_chunk
    )


def test_malformed_glb_node_transform_is_a_controlled_qa_failure(tmp_path: Path) -> None:
    scene = _minimal_scene()
    glb_path = tmp_path / "malformed-transform.glb"
    _write_malformed_transform_glb(glb_path)

    inspection = GLBInspector().inspect(glb_path, scene)
    mesh_qa = MeshQA().validate(glb_path, scene)

    assert inspection.structural_qa_passed is False
    assert "GLTF_NODE_TRANSFORM_INVALID" in inspection.critical_errors
    assert mesh_qa.mesh_qa_passed is False
    assert "GLTF_NODE_TRANSFORM_INVALID" in mesh_qa.critical_errors


def test_failed_blender_import_removes_every_partially_created_object(tmp_path: Path) -> None:
    class ObjectCollection(list):
        def remove(self, value, *, do_unlink=False):
            assert do_unlink is True
            super().remove(value)

    existing = SimpleNamespace(name="existing")
    objects = ObjectCollection([existing])

    class ImportScene:
        @staticmethod
        def gltf(*, filepath):
            assert filepath
            objects.append(SimpleNamespace(name="partial_mesh"))
            raise RuntimeError("synthetic importer failure")

    asset = tmp_path / "asset.glb"
    asset.write_bytes(b"synthetic")
    bpy = SimpleNamespace(
        data=SimpleNamespace(objects=objects),
        ops=SimpleNamespace(import_scene=ImportScene()),
    )
    asset_imports: list[dict] = []
    warnings: list[str] = []

    mode = _try_import_glb_asset(
        bpy=bpy,
        asset_id="TEST",
        asset_file=str(asset),
        asset_source="internal_cleaned",
        asset_metadata={},
        fallback_allowed=True,
        object_role="antenna",
        object_name="antenna_S1_TEST",
        location=(0, 0, 24),
        rotation=(0, 0, 0),
        asset_imports=asset_imports,
        warnings=warnings,
    )

    assert mode == "procedural_fallback"
    assert objects == [existing]
    assert asset_imports[0]["imported_object_count"] == 0


def test_same_sector_contact_rejects_thin_full_containment() -> None:
    antenna = _SemanticEntity("antenna", "antenna", "S1", 0, (0,), {}, "extras")
    radio = _SemanticEntity("radio", "rru", "S1", 1, (1,), {}, "extras")
    antenna_bounds = BoundingBoxM(
        min_x=-0.2,
        min_y=-0.7,
        min_z=-0.08,
        max_x=0.2,
        max_y=0.7,
        max_z=0.08,
    )
    contained_radio_bounds = BoundingBoxM(
        min_x=-0.1,
        min_y=-0.25,
        min_z=-0.05,
        max_x=0.1,
        max_y=0.25,
        max_z=0.05,
    )
    shallow_contact_bounds = contained_radio_bounds.model_copy(
        update={"min_z": 0.05, "max_z": 0.15}
    )

    assert not _is_allowed_primary_equipment_contact(
        antenna,
        radio,
        antenna_bounds,
        contained_radio_bounds,
        (0.2, 0.5, 0.1),
    )
    assert _is_allowed_primary_equipment_contact(
        antenna,
        radio,
        antenna_bounds,
        shallow_contact_bounds,
        (0.2, 0.5, 0.03),
    )


def test_critical_report_proof_detects_single_report_tamper(tmp_path: Path) -> None:
    for file_name in (
        "qa_report.json",
        "geometry_validation.json",
        "glb_inspection.json",
        "requirement_coverage.json",
        "design_blueprint.json",
        "blueprint_requirement_coverage.json",
        "blueprint_scene_coverage.json",
        "quality_gates.json",
    ):
        (tmp_path / file_name).write_text(
            json.dumps({"file": file_name, "status": "passed"}),
            encoding="utf-8",
        )

    proof = _write_critical_report_proof(tmp_path)
    assert len(proof["artifacts"]) == 8
    _verify_critical_report_proof(tmp_path)

    (tmp_path / "qa_report.json").write_text(
        json.dumps({"status": "failed", "score": 0}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CRITICAL_REPORT_HASH_MISMATCH"):
        _verify_critical_report_proof(tmp_path)


def test_version_artifact_containment_precedes_archive_side_effect(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outside = tmp_path / "outside"
    outside.mkdir()
    service = SceneVersioningService(outputs)
    version = service.save_version(
        "wf_hardening",
        _minimal_scene(),
        status="completed",
        artifact_dir=str(outside),
        activate=False,
    )
    archive_calls: list[Path] = []
    workflow = SimpleNamespace(
        outputs_dir=outputs,
        versioning=service,
        _sync_output_services=lambda: None,
        _make_archive=lambda path: archive_calls.append(path),
    )

    with pytest.raises(KeyError):
        WorkflowService.artifact_path(
            workflow,
            "wf_hardening",
            "download",
            version_id=version.version_id,
        )
    assert archive_calls == []
