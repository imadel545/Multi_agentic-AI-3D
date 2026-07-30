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
    assert report.binary_chunk_count == 1
    assert report.buffer_count == 1
    assert report.valid_primitive_count == report.primitive_count
    assert report.checks["semantic_mesh_coverage_complete"] is True
    assert report.checks["has_tower"] is True
    assert report.checks["has_antennas"] is True
    assert report.checks["has_radios_or_rru"] is True
    assert report.semantic_inspection_mode == "name_based"
    assert report.semantic_root_count > 0
    assert "GLB_SEMANTIC_EXTRAS_MISSING_NAME_BASED_MODE" in report.warnings


def test_glb_inspector_rejects_json_only_accessor_claims(tmp_path: Path) -> None:
    scene = _scene()
    glb_path = tmp_path / "json_only.glb"
    _write_json_only_glb(glb_path, _expected_object_names(scene))

    report = GLBInspector().inspect(glb_path, scene)

    assert report.format_valid is True
    assert report.structural_qa_passed is False
    assert report.valid_primitive_count == 0
    assert "GLB_BINARY_CHUNK_MISSING" in report.critical_errors
    assert report.checks["all_mesh_primitives_have_binary_data"] is False


def test_glb_inspector_rejects_semantic_entity_without_mesh(tmp_path: Path) -> None:
    scene = _scene()
    names = _expected_object_names(scene)
    glb_path = tmp_path / "empty_semantic_root.glb"
    _write_test_glb(glb_path, names, empty_node_name=names[-1])

    report = GLBInspector().inspect(glb_path, scene)

    assert report.structural_qa_passed is False
    assert report.semantic_mesh_coverage_ratio < 1.0
    assert "GLB_SEMANTIC_ENTITY_WITHOUT_MESH" in report.critical_errors


def test_glb_inspector_rejects_out_of_range_indices(tmp_path: Path) -> None:
    scene = _scene()
    glb_path = tmp_path / "bad_indices.glb"
    _write_test_glb(glb_path, _expected_object_names(scene), indices=[0, 1, 99])

    report = GLBInspector().inspect(glb_path, scene)

    assert report.structural_qa_passed is False
    assert "GLTF_INDEX_DATA_INVALID" in report.critical_errors


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


def test_glb_inspector_rejects_box_only_profiled_radio_and_panel(tmp_path: Path) -> None:
    scene = _scene()
    names = ["tower_lattice", "foundation_concrete_pad"]
    for sector in scene.sectors:
        names.extend(
            [
                f"antenna_{sector.sector_id}",
                f"radio_{sector.sector_id}",
                f"cable_{sector.sector_id}",
                f"sector_beam_{sector.sector_id}",
                f"azimuth_arrow_{sector.sector_id}",
                f"label_sector_{sector.sector_id}_{int(sector.azimuth_deg)}deg",
            ]
        )
    glb_path = tmp_path / "box_only_equipment.glb"
    _write_test_glb(glb_path, names)

    report = GLBInspector().inspect(glb_path, scene, None)

    assert report.checks["has_antennas"] is True
    assert report.checks["has_radios_or_rru"] is True
    assert report.checks["technical_panel_detail_complete"] is False
    assert report.checks["technical_radio_detail_complete"] is False
    assert report.structural_qa_passed is False
    assert "TECHNICAL_PANEL_DETAIL_MISSING" in report.critical_errors
    assert "TECHNICAL_RADIO_DETAIL_MISSING" in report.critical_errors


def test_glb_inspector_requires_requested_accessories(tmp_path: Path) -> None:
    scene = _accessory_scene()
    glb_path = tmp_path / "design.glb"
    _write_test_glb(glb_path, _expected_object_names(scene))

    report = GLBInspector().inspect(glb_path, scene, None)

    assert report.structural_qa_passed is True
    assert report.checks["has_gps_antenna"] is True
    assert report.checks["has_power_cabinet"] is True


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
    assert report.visual_quality_valid is True
    assert report.checks["preview_visual_quality_valid"] is True
    assert report.preview_qa_passed is True


def test_preview_inspector_rejects_dark_flat_png(tmp_path: Path) -> None:
    scene = _scene()
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_png_bytes(1920, 1080, color=(24, 24, 24)))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.minimum_resolution_valid is True
    assert report.visual_quality_valid is False
    assert report.preview_qa_passed is False
    assert "PREVIEW_VISUAL_QUALITY_INVALID" in report.critical_errors


def test_preview_inspector_rejects_gradient_without_a_detectable_subject(
    tmp_path: Path,
) -> None:
    scene = _scene(
        "Créer un site 5G sur pylône treillis 90m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_subtle_light_png_bytes(1920, 1080))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.visual_quality_valid is False
    assert report.checks["preview_subject_framing_valid"] is False
    assert report.preview_qa_passed is False


def test_preview_inspector_rejects_subject_touching_frame(tmp_path: Path) -> None:
    scene = _scene()
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_subject_png_bytes(1920, 1080, top=0, bottom=1080))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.subject_touches_frame is True
    assert report.checks["preview_subject_not_clipped"] is False
    assert report.preview_qa_passed is False


def test_preview_inspector_allows_bounded_ground_contact(tmp_path: Path) -> None:
    scene = _scene()
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_subject_png_bytes(1920, 1080, top=100, bottom=900, ground_top=900))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.subject_min_edge_margin_ratio < 0.01
    assert report.subject_touches_frame is False
    assert report.checks["preview_subject_not_clipped"] is True
    assert report.preview_qa_passed is True


def test_preview_inspector_rejects_upper_silhouette_touching_side(tmp_path: Path) -> None:
    scene = _scene()
    preview_path = tmp_path / "preview.png"
    preview_path.write_bytes(_subject_png_bytes(1920, 1080, top=100, bottom=900, left=0, right=400))

    report = PreviewInspector().inspect(preview_path, scene)

    assert report.subject_touches_frame is True
    assert report.preview_qa_passed is False


def test_preview_inspector_missing_png(tmp_path: Path) -> None:
    report = PreviewInspector().inspect(tmp_path / "missing.png", _scene())

    assert report.inspection_mode == "not_available"
    assert report.file_exists is False
    assert report.preview_qa_passed is False
    assert "PREVIEW_FILE_MISSING" in report.critical_errors


def _scene(prompt: str | None = None):
    requirements = parse_requirements_text(
        prompt
        or (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°."
        )
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


def _accessory_scene():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter GPS et armoire énergie."
    ).model_copy(update={"include_gps_antenna": True, "include_power_cabinet": True})
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)
    gps = registry.select_asset("gps", requirements.network_type, requirements.tower_type)
    cabinet = registry.select_asset("cabinet", requirements.network_type, requirements.tower_type)
    return ScenePlanner().build_scene_spec(
        "wf_glb_inspection_accessories",
        requirements,
        tower,
        antenna,
        radio,
        accessory_assets=[gps, cabinet],
    )


def _expected_object_names(scene) -> list[str]:
    names = ["tower_lattice"]
    if scene.tower.characteristics.foundation_type == "concrete_pad":
        names.append("foundation_concrete_pad")
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
        if sector.antenna_geometry_profile is not None:
            names.extend(
                [
                    f"antenna_{sector.sector_id}_radome",
                    f"antenna_{sector.sector_id}_rear_chassis",
                ]
            )
            names.extend(
                f"antenna_{sector.sector_id}_mount_rail_{index + 1:02d}"
                for index in range(sector.antenna_geometry_profile.rear_mount_rail_count)
            )
            names.extend(
                f"antenna_{sector.sector_id}_bottom_port_{index + 1:02d}"
                for index in range(sector.antenna_geometry_profile.bottom_port_count)
            )
        if sector.radio_geometry_profile is not None:
            names.append(f"radio_{sector.sector_id}_enclosure")
            names.extend(
                f"radio_{sector.sector_id}_heat_sink_{index + 1:02d}"
                for index in range(sector.radio_geometry_profile.heat_sink_fin_count)
            )
            names.extend(
                f"radio_{sector.sector_id}_mount_rail_{index + 1:02d}"
                for index in range(sector.radio_geometry_profile.mounting_rail_count)
            )
            names.extend(
                f"radio_{sector.sector_id}_bottom_connector_{index + 1:02d}"
                for index in range(sector.radio_geometry_profile.bottom_connector_count)
            )
        if scene.visual_elements.include_labels:
            names.append(f"label_sector_{sector.sector_id}_{int(sector.azimuth_deg)}deg")
    for accessory in scene.accessory_assets:
        if accessory.asset_type == "gps":
            names.append(f"gps_antenna_{accessory.asset_id}")
            if scene.visual_elements.include_labels:
                names.append("label_gps_antenna")
        if accessory.asset_type == "cabinet":
            names.append(f"power_cabinet_{accessory.asset_id}")
            if scene.visual_elements.include_labels:
                names.append("label_power_cabinet")
    return names


def _write_test_glb(
    path: Path,
    object_names: list[str],
    *,
    empty_node_name: str | None = None,
    indices: list[int] | None = None,
) -> None:
    vertices = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    index_values = indices or [0, 1, 2]
    index_bytes = struct.pack("<3H", *index_values)
    index_bytes += b"\0" * ((4 - len(index_bytes) % 4) % 4)
    binary_chunk = vertices + index_bytes
    payload: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "nodes": [
            {"name": name} if name == empty_node_name else {"name": name, "mesh": 0}
            for name in object_names
        ],
        "meshes": [
            {
                "name": "mesh_0",
                "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}],
            }
        ],
        "buffers": [{"byteLength": len(binary_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vertices)},
            {"buffer": 0, "byteOffset": len(vertices), "byteLength": len(index_bytes)},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "count": 3,
                "type": "VEC3",
                "componentType": 5126,
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            },
            {"bufferView": 1, "count": 3, "type": "SCALAR", "componentType": 5123},
        ],
        "materials": [{"name": "material_0"}],
    }
    _write_glb_payload(path, payload, binary_chunk)


def _write_json_only_glb(path: Path, object_names: list[str]) -> None:
    payload: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": name, "mesh": 0} for name in object_names],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [
            {
                "count": 3,
                "type": "VEC3",
                "componentType": 5126,
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
    }
    _write_glb_payload(path, payload, None)


def _write_glb_payload(path: Path, payload: dict[str, Any], binary_chunk: bytes | None) -> None:
    json_chunk = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    binary_record = (
        struct.pack("<II", len(binary_chunk), 0x004E4942) + binary_chunk
        if binary_chunk is not None
        else b""
    )
    length = 12 + 8 + len(json_chunk) + len(binary_record)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + binary_record
    )


def _png_bytes(
    width: int,
    height: int,
    color: tuple[int, int, int] | None = None,
) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            if color is None:
                if width * 0.4 <= x <= width * 0.6 and height * 0.1 <= y <= height * 0.9:
                    value = 155 + ((x + y) % 55)
                    row.extend((value, min(255, value + 20), min(255, value + 28)))
                else:
                    row.extend((28, 40, 50))
            else:
                row.extend(color)
        rows.append(bytes(row))
    image = zlib.compress(b"".join(rows), level=9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(b"IEND", b"")
    )


def _subject_png_bytes(
    width: int,
    height: int,
    *,
    top: int,
    bottom: int,
    left: int | None = None,
    right: int | None = None,
    ground_top: int | None = None,
) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    subject_left = left if left is not None else round(width * 0.4)
    subject_right = right if right is not None else round(width * 0.6)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            is_subject = subject_left <= x <= subject_right and top <= y < bottom
            if ground_top is not None and y >= ground_top:
                is_subject = True
            row.extend((180, 205, 220) if is_subject else (28, 40, 50))
        rows.append(bytes(row))
    image = zlib.compress(b"".join(rows), level=9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(b"IEND", b"")
    )


def _subtle_light_png_bytes(width: int, height: int) -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = crc32(chunk_type + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + chunk_type + payload + checksum.to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            # Mimics a tall, thin tower preview on a light studio background:
            # low contrast, but not a flat placeholder.
            value = 210 + int(18 * y / max(height - 1, 1)) + int(4 * x / max(width - 1, 1))
            row.extend((value, value, min(255, value + 5)))
        rows.append(bytes(row))
    image = zlib.compress(b"".join(rows), level=9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", image) + chunk(b"IEND", b"")
    )
