import json
import struct
from pathlib import Path
from typing import Any

from core.contracts.glb_inspection import GlbInspectionReport
from core.contracts.scene import SceneSpec
from core.qa.mesh_qa import (
    _build_semantic_index,
    _semantic_object_counts,
    _semantic_sector_ids,
)

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
                primitive_count=0,
                position_accessor_count=0,
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
                primitive_count=0,
                position_accessor_count=0,
                material_count=0,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                warnings=[],
                critical_errors=["GLB_FILE_EMPTY"],
            )

        parsed = _parse_glb_or_gltf(glb_path)
        if parsed is not None:
            (
                payload,
                node_count,
                mesh_count,
                primitive_count,
                position_accessor_count,
                material_count,
            ) = parsed
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
                primitive_count=primitive_count,
                position_accessor_count=position_accessor_count,
                material_count=material_count,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                payload=payload,
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
                primitive_count=0,
                position_accessor_count=0,
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
            primitive_count=0,
            position_accessor_count=0,
            material_count=0,
            metadata_exists=metadata_path.exists() if metadata_path else False,
            warnings=[],
            critical_errors=["GLB_FORMAT_INVALID"],
        )


def _parse_glb_or_gltf(path: Path) -> tuple[dict[str, Any], int, int, int, int, int] | None:
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
    accessors = payload.get("accessors", [])
    primitive_count = 0
    position_accessor_count = 0
    if isinstance(meshes, list):
        for mesh in meshes:
            if not isinstance(mesh, dict):
                continue
            primitives = mesh.get("primitives", [])
            if not isinstance(primitives, list):
                continue
            primitive_count += len(primitives)
            for primitive in primitives:
                if not isinstance(primitive, dict):
                    continue
                accessor_index = primitive.get("attributes", {}).get("POSITION")
                if (
                    isinstance(accessor_index, int)
                    and isinstance(accessors, list)
                    and 0 <= accessor_index < len(accessors)
                    and isinstance(accessors[accessor_index], dict)
                    and int(accessors[accessor_index].get("count") or 0) > 0
                ):
                    position_accessor_count += 1
    return (
        payload,
        len(nodes) if isinstance(nodes, list) else 0,
        len(meshes) if isinstance(meshes, list) else 0,
        primitive_count,
        position_accessor_count,
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
    primitive_count: int,
    position_accessor_count: int,
    material_count: int,
    metadata_exists: bool,
    warnings: list[str],
    critical_errors: list[str],
    payload: dict[str, Any] | None = None,
) -> GlbInspectionReport:
    semantic_payload = payload or {"nodes": [{"name": name} for name in object_names]}
    semantic_index = _build_semantic_index(semantic_payload, scene)
    semantic_counts = _semantic_object_counts(semantic_index)
    semantic_sector_ids = _semantic_sector_ids(semantic_index)
    expected = _expected_semantic_categories(scene)
    found = {
        category: semantic_counts.get(role, 0) >= minimum for category, role, minimum in expected
    }
    expected_objects_present = all(found.values())
    minimum_node_count = _minimum_node_count(scene)
    minimum_node_count_valid = node_count >= minimum_node_count
    minimum_semantic_object_count_valid = len(semantic_index.entities) >= minimum_node_count
    report_warnings = list(warnings)
    if semantic_index.mode == "name_based":
        report_warnings.append("GLB_SEMANTIC_EXTRAS_MISSING_NAME_BASED_MODE")
    elif semantic_index.mode == "mixed_semantic_name_based":
        report_warnings.append("GLB_SEMANTIC_EXTRAS_PARTIAL_MIXED_MODE")
    checks = {
        "has_tower": found["tower"],
        "has_antennas": found["antennas"],
        "has_radios_or_rru": found["radios_or_rru"],
        "has_cables": found["cables"],
        "has_sector_beams": found["sector_beams"],
        "has_azimuth_arrows": found["azimuth_arrows"],
        "has_power_cabinet": found["power_cabinet"],
        "has_gps_antenna": found["gps_antenna"],
        "has_foundation": found["foundation"],
        "has_labels": found["labels"],
        "has_metadata": metadata_exists,
        "expected_objects_present": expected_objects_present,
        "minimum_node_count_valid": minimum_node_count_valid,
        "minimum_semantic_object_count_valid": minimum_semantic_object_count_valid,
        "semantic_roots_available": bool(semantic_index.entities),
        "semantic_root_coverage_complete": (
            semantic_index.mode == "semantic_extras" and expected_objects_present
        ),
        "mesh_primitives_present": primitive_count > 0,
        "position_accessors_nonempty": position_accessor_count > 0,
    }
    errors = list(critical_errors)
    if not expected_objects_present:
        errors.append("EXPECTED_GLB_OBJECTS_MISSING")
    if not minimum_node_count_valid:
        errors.append("MINIMUM_GLB_NODE_COUNT_NOT_MET")
    if not minimum_semantic_object_count_valid:
        errors.append("MINIMUM_SEMANTIC_OBJECT_COUNT_NOT_MET")
    if not format_valid:
        errors.append("GLB_FORMAT_INVALID")
    if inspection_mode == "glb_parse" and primitive_count == 0:
        errors.append("GLB_MESH_PRIMITIVES_MISSING")
    if inspection_mode == "glb_parse" and position_accessor_count == 0:
        errors.append("GLB_POSITION_ACCESSORS_EMPTY")
    structural_qa_passed = not errors
    return GlbInspectionReport(
        inspection_mode=inspection_mode,  # type: ignore[arg-type]
        file_exists=file_exists,
        file_size_bytes=file_size_bytes,
        format_valid=format_valid,
        node_count=node_count,
        mesh_count=mesh_count,
        primitive_count=primitive_count,
        position_accessor_count=position_accessor_count,
        material_count=material_count,
        object_names=object_names,
        semantic_inspection_mode=semantic_index.mode,
        semantic_root_count=len(semantic_index.entities),
        semantic_extras_root_count=semantic_index.extras_root_count,
        semantic_extras_coverage_ratio=semantic_index.extras_coverage_ratio,
        semantic_object_counts=semantic_counts,
        semantic_sector_ids=semantic_sector_ids,
        expected_object_prefixes_found=found,
        checks=checks,
        warnings=report_warnings,
        critical_errors=errors,
        structural_qa_passed=structural_qa_passed,
    )


def _expected_semantic_categories(scene: SceneSpec) -> list[tuple[str, str, int]]:
    sector_count = len(scene.sectors)
    radio_count = sum(1 for sector in scene.sectors if sector.radio_asset_id)
    cable_count = sum(1 for sector in scene.sectors if sector.include_cable)
    beam_count = sector_count if scene.visual_elements.include_sector_beams else 0
    arrow_count = sector_count if scene.visual_elements.include_azimuth_arrows else 0
    cabinet_count = 1 if scene.visual_elements.include_power_cabinet else 0
    gps_count = 1 if scene.visual_elements.include_gps_antenna else 0
    foundation_count = _expected_foundation_count(scene)
    label_count = _expected_label_count(scene)
    return [
        ("tower", "tower", 1),
        ("antennas", "antenna", sector_count),
        ("radios_or_rru", "rru", radio_count),
        ("cables", "cable", cable_count),
        ("sector_beams", "beam", beam_count),
        ("azimuth_arrows", "azimuth_arrow", arrow_count),
        ("power_cabinet", "power_cabinet", cabinet_count),
        ("gps_antenna", "gps", gps_count),
        ("foundation", "foundation", foundation_count),
        ("labels", "label", label_count),
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
    minimum += _expected_foundation_count(scene)
    minimum += _expected_label_count(scene)
    return minimum


def _expected_foundation_count(scene: SceneSpec) -> int:
    return int(scene.tower.characteristics.foundation_type != "unknown")


def _expected_label_count(scene: SceneSpec) -> int:
    if not scene.visual_elements.include_labels:
        return 0
    count = len(scene.sectors)
    if scene.visual_elements.include_power_cabinet:
        count += 1
    if scene.visual_elements.include_gps_antenna:
        count += 1
    return count


def _load_metadata(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
