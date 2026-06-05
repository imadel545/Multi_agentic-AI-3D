import json
import struct
import zlib
from binascii import crc32
from pathlib import Path
from typing import Any

from core.agents.scene_planner import ScenePlanner
from core.qa.glb_inspector import GLBInspector
from core.qa.preview_inspector import PreviewInspector
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text


def test_glb_inspector_valid_file(tmp_path: Path) -> None:
    scene = _scene()
    glb_path = tmp_path / "design.glb"
    metadata_path = tmp_path / "scene_metadata.json"
    _write_test_glb(glb_path, _expected_object_names(scene))
    metadata_path.write_text("{}", encoding="utf-8")

    report = GLBInspector().inspect(glb_path, scene, metadata_path)

    assert report.inspection_mode == "glb_parse"
    assert report.file_exists is True
    assert report.format_valid is True
    assert report.node_count >= 16
    assert report.mesh_count >= 1
    assert report.material_count >= 1
    assert report.structural_qa_passed is True
    assert report.checks["has_tower"] is True
    assert report.checks["has_antennas"] is True
    assert report.checks["has_radios_or_rru"] is True


def test_glb_inspector_missing_file(tmp_path: Path) -> None:
    report = GLBInspector().inspect(tmp_path / "missing.glb", _scene(), None)

    assert report.inspection_mode == "not_available"
    assert report.file_exists is False
    assert report.structural_qa_passed is False
    assert "GLB_FILE_MISSING" in report.critical_errors


def test_glb_inspector_empty_file_fails(tmp_path: Path) -> None:
    glb_path = tmp_path / "empty.glb"
    glb_path.write_bytes(b"")

    report = GLBInspector().inspect(glb_path, _scene(), None)

    assert report.file_exists is True
    assert report.file_size_bytes == 0
    assert report.structural_qa_passed is False
    assert "GLB_FILE_EMPTY" in report.critical_errors


def test_glb_inspection_blocks_empty_glb(tmp_path: Path) -> None:
    glb_path = tmp_path / "empty.glb"
    glb_path.write_bytes(b"")

    report = GLBInspector().inspect(glb_path, _scene(), None)

    assert report.checks["expected_objects_present"] is False
    assert report.checks["minimum_node_count_valid"] is False
    assert report.critical_errors


def test_glb_inspection_detects_missing_expected_objects(tmp_path: Path) -> None:
    scene = _scene()
    glb_path = tmp_path / "design.glb"
    _write_test_glb(glb_path, ["tower_only"])

    report = GLBInspector().inspect(glb_path, scene, None)

    assert report.format_valid is True
    assert report.structural_qa_passed is False
    assert report.checks["has_tower"] is True
    assert report.checks["has_antennas"] is False
    assert "EXPECTED_GLB_OBJECTS_MISSING" in report.critical_errors


def test_preview_inspector_valid_png(tmp_path: Path) -> None:
    scene = _scene()
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_png_bytes(1920, 1080))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.inspection_mode == "png_parse"
    assert report.file_exists is True
    assert report.width == 1920
    assert report.height == 1080
    assert report.format == "png"
    assert report.minimum_resolution_valid is True
    assert report.preview_qa_passed is True


def test_preview_inspector_missing_png(tmp_path: Path) -> None:
    report = PreviewInspector().inspect(tmp_path / "missing.png", _scene())

    assert report.inspection_mode == "not_available"
    assert report.file_exists is False
    assert report.preview_qa_passed is False
    assert "PREVIEW_FILE_MISSING" in report.critical_errors


def _scene():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°."
    )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    return ScenePlanner().build_scene_spec("wf_glb_inspection", requirements, tower, antenna, radio)


def _expected_object_names(scene) -> list[str]:
    names = ["tower_lattice"]
    for sector in scene.sectors:
        names.extend(
            [
                f"antenna_{sector.sector_id}",
                f"radio_{sector.sector_id}",
                f"cable_{sector.sector_id}",
                f"sector_beam_{sector.sector_id}",
                f"azimuth_arrow_{sector.sector_id}",
            ]
        )
    return names


def _write_test_glb(path: Path, object_names: list[str]) -> None:
    payload: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": name, "mesh": 0} for name in object_names],
        "meshes": [{"name": "mesh_0", "primitives": []}],
        "materials": [{"name": "material_0"}],
    }
    json_chunk = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    length = 12 + 8 + len(json_chunk)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
    )


def _png_bytes(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    row = b"\x00" + (b"\xff\xff\xff" * width)
    image = zlib.compress(row * height, level=9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(
        b"IEND", b""
    )
