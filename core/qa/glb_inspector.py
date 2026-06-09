import json
import struct
from pathlib import Path
from typing import Any

from core.contracts.glb_inspection import GlbInspectionReport
from core.contracts.scene import SceneSpec

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK_TYPE = 0x4E4F534A


class GLBInspector:
    def inspect(
        self,
        glb_path: Path,
        scene: SceneSpec,
        metadata_path: Path | None = None,
    ) -> GlbInspectionReport:
        file_exists = glb_path.exists()
        file_size_bytes = glb_path.stat().st_size if file_exists else 0
        if not file_exists:
            return _report(
                inspection_mode="not_available",
                file_exists=False,
                file_size_bytes=0,
                format_valid=False,
                scene=scene,
                object_names=[],
                node_count=0,
                mesh_count=0,
                material_count=0,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                warnings=[],
                critical_errors=["GLB_FILE_MISSING"],
            )
        if file_size_bytes == 0:
            return _report(
                inspection_mode="not_available",
                file_exists=True,
                file_size_bytes=0,
                format_valid=False,
                scene=scene,
                object_names=[],
                node_count=0,
                mesh_count=0,
                material_count=0,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                warnings=[],
                critical_errors=["GLB_FILE_EMPTY"],
            )

        parsed = _parse_glb_or_gltf(glb_path)
        if parsed is not None:
            payload, node_count, mesh_count, material_count = parsed
            object_names = [
                str(node.get("name", ""))
                for node in payload.get("nodes", [])
                if str(node.get("name", "")).strip()
            ]
            return _report(
                inspection_mode="glb_parse",
                file_exists=True,
                file_size_bytes=file_size_bytes,
                format_valid=True,
                scene=scene,
                object_names=object_names,
                node_count=node_count,
                mesh_count=mesh_count,
                material_count=material_count,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                warnings=[],
                critical_errors=[],
            )

        metadata = _load_metadata(metadata_path) if metadata_path else {}
        procedural_objects = [
            str(name) for name in metadata.get("procedural_objects_created", []) if str(name)
        ]
        if procedural_objects:
            return _report(
                inspection_mode="metadata_fallback",
                file_exists=True,
                file_size_bytes=file_size_bytes,
                format_valid=False,
                scene=scene,
                object_names=procedural_objects,
                node_count=len(procedural_objects),
                mesh_count=0,
                material_count=0,
                metadata_exists=True,
                warnings=["GLB_PARSE_FAILED_METADATA_FALLBACK_USED"],
                critical_errors=[],
            )

        return _report(
            inspection_mode="not_available",
            file_exists=True,
            file_size_bytes=file_size_bytes,
            format_valid=False,
            scene=scene,
            object_names=[],
            node_count=0,
            mesh_count=0,
            material_count=0,
            metadata_exists=metadata_path.exists() if metadata_path else False,
            warnings=[],
            critical_errors=["GLB_FORMAT_INVALID"],
        )


def _parse_glb_or_gltf(path: Path) -> tuple[dict[str, Any], int, int, int] | None:
    try:
        if path.suffix.lower() == ".gltf":
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = _parse_glb_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("asset", {}).get("version") is None:
        return None
    nodes = payload.get("nodes", [])
    meshes = payload.get("meshes", [])
    materials = payload.get("materials", [])
    return (
        payload,
        len(nodes) if isinstance(nodes, list) else 0,
        len(meshes) if isinstance(meshes, list) else 0,
        len(materials) if isinstance(materials, list) else 0,
    )


def _parse_glb_json(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("GLB file is too small")
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError("Invalid GLB header")
    # Allow trailing padding or extra chunks beyond declared length
    if declared_length > len(data):
        raise ValueError("Invalid GLB header: declared length exceeds file size")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != GLB_JSON_CHUNK_TYPE:
        raise ValueError("First GLB chunk is not JSON")
    start = 20
    end = start + chunk_length
    if end > len(data):
        raise ValueError("Invalid GLB JSON chunk length")
    return json.loads(data[start:end].decode("utf-8").rstrip(" \t\r\n\0"))


def _report(
    *,
    inspection_mode: str,
    file_exists: bool,
    file_size_bytes: int,
    format_valid: bool,
    scene: SceneSpec,
    object_names: list[str],
    node_count: int,
    mesh_count: int,
    material_count: int,
    metadata_exists: bool,
    warnings: list[str],
    critical_errors: list[str],
) -> GlbInspectionReport:
    expected = _expected_prefixes(scene)
    found = {
        category: _count_matching(object_names, prefixes) >= minimum
        for category, prefixes, minimum in expected
    }
    expected_objects_present = all(found.values())
    minimum_node_count = _minimum_node_count(scene)
    minimum_node_count_valid = node_count >= minimum_node_count
    checks = {
        "has_tower": found["tower"],
        "has_antennas": found["antennas"],
        "has_radios_or_rru": found["radios_or_rru"],
        "has_cables": found["cables"],
        "has_sector_beams": found["sector_beams"],
        "has_azimuth_arrows": found["azimuth_arrows"],
        "has_power_cabinet": found["power_cabinet"],
        "has_gps_antenna": found["gps_antenna"],
        "has_metadata": metadata_exists,
        "expected_objects_present": expected_objects_present,
        "minimum_node_count_valid": minimum_node_count_valid,
    }
    errors = list(critical_errors)
    if not expected_objects_present:
        errors.append("EXPECTED_GLB_OBJECTS_MISSING")
    if not minimum_node_count_valid:
        errors.append("MINIMUM_GLB_NODE_COUNT_NOT_MET")
    if inspection_mode == "glb_parse" and not format_valid:
        errors.append("GLB_FORMAT_INVALID")
    structural_qa_passed = not errors
    return GlbInspectionReport(
        inspection_mode=inspection_mode,  # type: ignore[arg-type]
        file_exists=file_exists,
        file_size_bytes=file_size_bytes,
        format_valid=format_valid,
        node_count=node_count,
        mesh_count=mesh_count,
        material_count=material_count,
        object_names=object_names,
        expected_object_prefixes_found=found,
        checks=checks,
        warnings=warnings,
        critical_errors=errors,
        structural_qa_passed=structural_qa_passed,
    )


def _expected_prefixes(scene: SceneSpec) -> list[tuple[str, tuple[str, ...], int]]:
    sector_count = len(scene.sectors)
    radio_count = sum(1 for sector in scene.sectors if sector.radio_asset_id)
    cable_count = sum(1 for sector in scene.sectors if sector.include_cable)
    beam_count = sector_count if scene.visual_elements.include_sector_beams else 0
    arrow_count = sector_count if scene.visual_elements.include_azimuth_arrows else 0
    cabinet_count = 1 if scene.visual_elements.include_power_cabinet else 0
    gps_count = 1 if scene.visual_elements.include_gps_antenna else 0
    return [
        ("tower", ("tower", "tower_"), 1),
        (
            "antennas",
            ("antenna", "antenna_", "antenna_panel", "antenna_dish", "dish_"),
            sector_count,
        ),
        ("radios_or_rru", ("radio", "radio_", "rru", "rru_"), radio_count),
        ("cables", ("cable", "cable_"), cable_count),
        ("sector_beams", ("beam", "beam_", "sector_beam", "sector_beam_"), beam_count),
        ("azimuth_arrows", ("azimuth_arrow", "azimuth_arrow_"), arrow_count),
        ("power_cabinet", ("power_cabinet", "cabinet"), cabinet_count),
        ("gps_antenna", ("gps_antenna", "gps"), gps_count),
    ]


def _minimum_node_count(scene: SceneSpec) -> int:
    minimum = 1 + len(scene.sectors)
    minimum += sum(1 for sector in scene.sectors if sector.radio_asset_id)
    minimum += sum(1 for sector in scene.sectors if sector.include_cable)
    if scene.visual_elements.include_sector_beams:
        minimum += len(scene.sectors)
    if scene.visual_elements.include_azimuth_arrows:
        minimum += len(scene.sectors)
    if scene.visual_elements.include_power_cabinet:
        minimum += 1
    if scene.visual_elements.include_gps_antenna:
        minimum += 1
    return minimum


def _count_matching(object_names: list[str], prefixes: tuple[str, ...]) -> int:
    if not prefixes:
        return 0
    normalized = [name.lower().replace(":", "_") for name in object_names]
    return sum(
        1
        for name in normalized
        if any(name == prefix or name.startswith(prefix) for prefix in prefixes)
    )


def _load_metadata(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
