import json
from pathlib import Path
from typing import Any

from core.contracts.glb_inspection import GlbInspectionReport
from core.contracts.scene import SceneSpec
from core.qa.gltf_integrity import inspect_gltf_integrity
from core.qa.mesh_qa import (
    _build_semantic_index,
    _semantic_object_counts,
    _semantic_sector_ids,
)


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
                valid_primitive_count=0,
                position_accessor_count=0,
                buffer_count=0,
                buffer_view_count=0,
                binary_chunk_count=0,
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
                valid_primitive_count=0,
                position_accessor_count=0,
                buffer_count=0,
                buffer_view_count=0,
                binary_chunk_count=0,
                material_count=0,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                warnings=[],
                critical_errors=["GLB_FILE_EMPTY"],
            )

        integrity = inspect_gltf_integrity(glb_path)
        if integrity.payload is not None:
            payload = integrity.payload
            nodes = payload.get("nodes", [])
            meshes = payload.get("meshes", [])
            materials = payload.get("materials", [])
            object_names = [
                str(node.get("name", ""))
                for node in payload.get("nodes", [])
                if str(node.get("name", "")).strip()
            ]
            return _report(
                inspection_mode="glb_parse",
                file_exists=True,
                file_size_bytes=file_size_bytes,
                format_valid=integrity.container_valid,
                scene=scene,
                object_names=object_names,
                node_count=len(nodes) if isinstance(nodes, list) else 0,
                mesh_count=len(meshes) if isinstance(meshes, list) else 0,
                primitive_count=integrity.primitive_count,
                valid_primitive_count=integrity.valid_primitive_count,
                position_accessor_count=integrity.valid_position_accessor_count,
                buffer_count=integrity.buffer_count,
                buffer_view_count=integrity.buffer_view_count,
                binary_chunk_count=integrity.binary_chunk_count,
                material_count=len(materials) if isinstance(materials, list) else 0,
                metadata_exists=metadata_path.exists() if metadata_path else False,
                payload=payload,
                valid_mesh_indices=integrity.valid_mesh_indices,
                warnings=[],
                critical_errors=list(integrity.errors),
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
                valid_primitive_count=0,
                position_accessor_count=0,
                buffer_count=0,
                buffer_view_count=0,
                binary_chunk_count=0,
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
            valid_primitive_count=0,
            position_accessor_count=0,
            buffer_count=0,
            buffer_view_count=0,
            binary_chunk_count=0,
            material_count=0,
            metadata_exists=metadata_path.exists() if metadata_path else False,
            warnings=[],
            critical_errors=["GLB_FORMAT_INVALID"],
        )


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
    valid_primitive_count: int,
    position_accessor_count: int,
    buffer_count: int,
    buffer_view_count: int,
    binary_chunk_count: int,
    material_count: int,
    metadata_exists: bool,
    warnings: list[str],
    critical_errors: list[str],
    payload: dict[str, Any] | None = None,
    valid_mesh_indices: frozenset[int] = frozenset(),
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
    nodes = semantic_payload.get("nodes", [])
    semantic_entities_with_mesh = [
        entity
        for entity in semantic_index.entities
        if any(
            isinstance(nodes[node_index], dict)
            and nodes[node_index].get("mesh") in valid_mesh_indices
            for node_index in entity.node_indices
            if isinstance(nodes, list) and 0 <= node_index < len(nodes)
        )
    ]
    semantic_mesh_coverage_ratio = (
        len(semantic_entities_with_mesh) / len(semantic_index.entities)
        if semantic_index.entities
        else 0.0
    )
    semantic_mesh_coverage_complete = bool(semantic_index.entities) and (
        len(semantic_entities_with_mesh) == len(semantic_index.entities)
    )
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
        "all_mesh_primitives_have_binary_data": valid_primitive_count == primitive_count > 0,
        "position_accessors_nonempty": position_accessor_count > 0,
        "buffers_present": buffer_count > 0,
        "buffer_views_present": buffer_view_count > 0,
        "binary_payload_present": binary_chunk_count > 0,
        "semantic_mesh_coverage_complete": semantic_mesh_coverage_complete,
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
    if inspection_mode == "glb_parse" and not semantic_mesh_coverage_complete:
        errors.append("GLB_SEMANTIC_ENTITY_WITHOUT_MESH")
    errors = list(dict.fromkeys(errors))
    structural_qa_passed = not errors
    return GlbInspectionReport(
        inspection_mode=inspection_mode,  # type: ignore[arg-type]
        file_exists=file_exists,
        file_size_bytes=file_size_bytes,
        format_valid=format_valid,
        node_count=node_count,
        mesh_count=mesh_count,
        primitive_count=primitive_count,
        valid_primitive_count=valid_primitive_count,
        position_accessor_count=position_accessor_count,
        buffer_count=buffer_count,
        buffer_view_count=buffer_view_count,
        binary_chunk_count=binary_chunk_count,
        material_count=material_count,
        object_names=object_names,
        semantic_inspection_mode=semantic_index.mode,
        semantic_root_count=len(semantic_index.entities),
        semantic_extras_root_count=semantic_index.extras_root_count,
        semantic_extras_coverage_ratio=semantic_index.extras_coverage_ratio,
        semantic_mesh_coverage_ratio=semantic_mesh_coverage_ratio,
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
    count = sum(1 for sector in scene.sectors if sector.include_label)
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
