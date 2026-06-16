import json
from pathlib import Path

from core.contracts.geometry_validation import GeometryValidationReport
from core.contracts.glb_inspection import GlbInspectionReport
from core.contracts.scene import SceneSpec
from core.qa.mesh_qa import MeshQA

HEIGHT_TOLERANCE_M = 0.5
AZIMUTH_TOLERANCE_DEG = 5.0


class GLBGeometryValidator:
    def validate(
        self,
        scene: SceneSpec,
        glb_inspection: GlbInspectionReport,
        metadata_path: Path,
        glb_path: Path | None = None,
    ) -> GeometryValidationReport:
        metadata = _load_metadata(metadata_path)
        mesh_qa = MeshQA().validate(glb_path, scene) if glb_path and glb_path.exists() else None
        object_names = glb_inspection.object_names
        counts = _object_counts(object_names)
        expected_antennas = len(scene.sectors)
        expected_rru = sum(1 for sector in scene.sectors if sector.radio_asset_id)
        expected_cables = sum(1 for sector in scene.sectors if sector.include_cable)
        expected_beams = len(scene.sectors) if scene.visual_elements.include_sector_beams else 0
        expected_arrows = len(scene.sectors) if scene.visual_elements.include_azimuth_arrows else 0
        expected_cabinets = 1 if scene.visual_elements.include_power_cabinet else 0
        expected_gps = 1 if scene.visual_elements.include_gps_antenna else 0
        expected_foundation = _expected_foundation_count(scene)
        expected_labels = _expected_label_count(scene)
        missing_objects = _missing_sector_objects(scene, object_names)

        checks = {
            "tower_present": counts["tower"] >= 1,
            "antenna_count_valid": counts["antenna"] >= expected_antennas,
            "beam_count_valid": _count_matches_option(counts["beam"], expected_beams),
            "rru_count_valid": _count_matches_option(counts["rru"], expected_rru),
            "cable_count_valid": _count_matches_option(counts["cable"], expected_cables),
            "azimuth_arrow_count_valid": _count_matches_option(
                counts["azimuth_arrow"], expected_arrows
            ),
            "power_cabinet_count_valid": _count_matches_option(
                counts["power_cabinet"], expected_cabinets
            ),
            "gps_antenna_count_valid": _count_matches_option(counts["gps"], expected_gps),
            "foundation_count_valid": _count_matches_option(
                counts["foundation"], expected_foundation
            ),
            "label_count_valid": _count_matches_option(counts["label"], expected_labels),
            "sector_objects_present": not missing_objects,
            "object_names_match_scene_spec": _object_names_match_scene(
                scene,
                object_names,
                metadata,
                missing_objects,
            ),
            "approx_tower_height_valid": _approx_tower_height_valid(scene, metadata),
            "tower_characteristics_metadata_valid": _tower_characteristics_metadata_valid(
                scene,
                metadata,
            ),
            "approx_antenna_height_valid": _approx_antenna_heights_valid(scene, metadata),
            "azimuth_metadata_valid": _azimuths_valid(scene, metadata),
            "mechanical_tilt_metadata_valid": _mechanical_tilts_valid(scene, metadata),
            "bounding_box_reasonable": _bounding_box_reasonable(
                scene,
                metadata,
                glb_inspection,
            ),
        }
        warnings = []
        if "bounding_box_m" not in metadata:
            warnings.append("BOUNDING_BOX_GEOMETRY_NOT_PARSED")
        if mesh_qa is not None:
            warnings.extend(mesh_qa.warnings)
            if mesh_qa.bounding_box_m is not None:
                bbox = mesh_qa.bounding_box_m
                metadata["bounding_box_m"] = {
                    "min_x": bbox.min_x,
                    "min_y": bbox.min_y,
                    "min_z": bbox.min_z,
                    "max_x": bbox.max_x,
                    "max_y": bbox.max_y,
                    "max_z": bbox.max_z,
                    "width": bbox.width,
                    "depth": bbox.depth,
                    "height": bbox.height,
                }
                # Re-evaluate bounding box with real data.
                checks["bounding_box_reasonable"] = _bounding_box_reasonable(
                    scene, metadata, glb_inspection
                )
        critical_errors = [name for name, passed in checks.items() if not passed]
        return GeometryValidationReport(
            status="passed" if not critical_errors else "failed",
            geometry_source=mesh_qa.geometry_source if mesh_qa else "unknown",
            generation_strategy=mesh_qa.generation_strategy if mesh_qa else "unknown",
            checks=checks,
            object_counts=counts,
            missing_objects=missing_objects,
            warnings=warnings,
            critical_errors=critical_errors,
            height_tolerance_m=HEIGHT_TOLERANCE_M,
            azimuth_tolerance_deg=AZIMUTH_TOLERANCE_DEG,
            bounding_box_m=mesh_qa.bounding_box_m if mesh_qa else None,
            mesh_qa=mesh_qa,
            mesh_qa_level=mesh_qa.level if mesh_qa else "not_available",
        )


def _object_counts(object_names: list[str]) -> dict[str, int]:
    normalized = [_normalize(name) for name in object_names]
    return {
        "tower": _count(normalized, ("tower",)),
        "antenna": _count(normalized, ("antenna", "dish")),
        "rru": _count(normalized, ("radio", "rru")),
        "cable": _count(normalized, ("cable",)),
        "beam": _count(normalized, ("sector_beam", "beam")),
        "azimuth_arrow": _count(normalized, ("azimuth_arrow",)),
        "power_cabinet": _count(normalized, ("power_cabinet", "cabinet")),
        "gps": _count(normalized, ("gps_antenna", "gps")),
        "foundation": _count(normalized, ("foundation", "foundation_concrete_pad")),
        "label": _count(normalized, ("label",)),
    }


def _count(normalized_names: list[str], prefixes: tuple[str, ...]) -> int:
    return sum(
        1
        for name in normalized_names
        if not _is_auxiliary_object(name)
        and any(name == prefix or name.startswith(f"{prefix}_") for prefix in prefixes)
    )


def _count_matches_option(actual: int, expected: int) -> bool:
    if expected == 0:
        return actual == 0
    return actual >= expected


def _missing_sector_objects(scene: SceneSpec, object_names: list[str]) -> list[str]:
    normalized = [_normalize(name) for name in object_names]
    missing = []
    for sector in scene.sectors:
        sector_token = _normalize(sector.sector_id)
        if not _has_sector_object(normalized, ("antenna", "dish"), sector_token):
            missing.append(f"antenna:{sector.sector_id}")
        if sector.radio_asset_id and not _has_sector_object(
            normalized,
            ("radio", "rru"),
            sector_token,
        ):
            missing.append(f"radio:{sector.sector_id}")
        if sector.include_cable and not _has_sector_object(normalized, ("cable",), sector_token):
            missing.append(f"cable:{sector.sector_id}")
        if scene.visual_elements.include_sector_beams and not _has_sector_object(
            normalized,
            ("sector_beam", "beam"),
            sector_token,
        ):
            missing.append(f"beam:{sector.sector_id}")
        if scene.visual_elements.include_labels and not _has_sector_object(
            normalized,
            ("label",),
            sector_token,
        ):
            missing.append(f"label:{sector.sector_id}")
    if scene.visual_elements.include_power_cabinet and not _has_object(
        normalized, ("power_cabinet", "cabinet")
    ):
        missing.append("power_cabinet")
    if scene.visual_elements.include_gps_antenna and not _has_object(
        normalized, ("gps_antenna", "gps")
    ):
        missing.append("gps_antenna")
    if _expected_foundation_count(scene) and not _has_object(
        normalized, ("foundation", "foundation_concrete_pad")
    ):
        missing.append("foundation_concrete_pad")
    if scene.visual_elements.include_labels:
        if scene.visual_elements.include_power_cabinet and not _has_object(
            normalized, ("label_power_cabinet",)
        ):
            missing.append("label:power_cabinet")
        if scene.visual_elements.include_gps_antenna and not _has_object(
            normalized, ("label_gps_antenna",)
        ):
            missing.append("label:gps_antenna")
    return missing


def _has_sector_object(
    normalized_names: list[str],
    prefixes: tuple[str, ...],
    sector_token: str,
) -> bool:
    return any(
        sector_token in name
        and not _is_auxiliary_object(name)
        and any(name == prefix or name.startswith(f"{prefix}_") for prefix in prefixes)
        for name in normalized_names
    )


def _has_object(normalized_names: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(
        not _is_auxiliary_object(name)
        and any(name == prefix or name.startswith(f"{prefix}_") for prefix in prefixes)
        for name in normalized_names
    )


def _is_auxiliary_object(normalized_name: str) -> bool:
    return "_head_" in normalized_name or normalized_name.endswith("_head")


def _expected_foundation_count(scene: SceneSpec) -> int:
    return 1 if scene.tower.characteristics.foundation_type == "concrete_pad" else 0


def _expected_label_count(scene: SceneSpec) -> int:
    if not scene.visual_elements.include_labels:
        return 0
    count = len(scene.sectors)
    if scene.visual_elements.include_power_cabinet:
        count += 1
    if scene.visual_elements.include_gps_antenna:
        count += 1
    return count


def _object_names_match_scene(
    scene: SceneSpec,
    object_names: list[str],
    metadata: dict,
    missing_objects: list[str],
) -> bool:
    if missing_objects:
        return False
    normalized = [_normalize(name) for name in object_names]
    expected_asset_ids = {scene.tower.asset_id}
    for sector in scene.sectors:
        expected_asset_ids.add(sector.antenna_asset_id)
        if sector.radio_asset_id:
            expected_asset_ids.add(sector.radio_asset_id)
    for accessory in scene.accessory_assets:
        expected_asset_ids.add(accessory.asset_id)
    metadata_assets = {_normalize(asset_id) for asset_id in metadata.get("assets_used", [])}
    return all(
        _normalize(asset_id) in metadata_assets
        or any(_normalize(asset_id) in name for name in normalized)
        for asset_id in expected_asset_ids
    )


def _approx_tower_height_valid(scene: SceneSpec, metadata: dict) -> bool:
    value = _number(metadata.get("tower_height_m"))
    return value is not None and abs(value - scene.tower.height_m) <= HEIGHT_TOLERANCE_M


def _tower_characteristics_metadata_valid(scene: SceneSpec, metadata: dict) -> bool:
    value = metadata.get("tower_characteristics")
    if not isinstance(value, dict):
        return False
    expected = scene.tower.characteristics.model_dump()
    return all(value.get(key) == expected_value for key, expected_value in expected.items())


def _approx_antenna_heights_valid(scene: SceneSpec, metadata: dict) -> bool:
    values = metadata.get("antenna_heights_m")
    if not isinstance(values, list) or len(values) != len(scene.sectors):
        return False
    expected = [sector.install_height_m for sector in scene.sectors]
    parsed = [_number(value) for value in values]
    if any(value is None for value in parsed):
        return False
    return all(
        abs(float(actual) - target) <= HEIGHT_TOLERANCE_M
        for actual, target in zip(parsed, expected, strict=True)
    )


def _azimuths_valid(scene: SceneSpec, metadata: dict) -> bool:
    values = metadata.get("azimuths_deg")
    if not isinstance(values, list) or len(values) != len(scene.sectors):
        return False
    expected = [sector.azimuth_deg for sector in scene.sectors]
    parsed = [_number(value) for value in values]
    if any(value is None for value in parsed):
        return False
    return all(
        _angular_delta(float(actual), target) <= AZIMUTH_TOLERANCE_DEG
        for actual, target in zip(parsed, expected, strict=True)
    )


def _mechanical_tilts_valid(scene: SceneSpec, metadata: dict) -> bool:
    values = metadata.get("mechanical_tilts_deg")
    if not isinstance(values, list) or len(values) != len(scene.sectors):
        return False
    expected = [sector.mechanical_tilt_deg for sector in scene.sectors]
    parsed = [_number(value) for value in values]
    if any(value is None for value in parsed):
        return False
    return all(
        abs(float(actual) - target) <= 0.05 for actual, target in zip(parsed, expected, strict=True)
    )


def _bounding_box_reasonable(
    scene: SceneSpec,
    metadata: dict,
    glb_inspection: GlbInspectionReport,
) -> bool:
    bbox = metadata.get("bounding_box_m")
    if isinstance(bbox, dict):
        height = _number(bbox.get("height"))
        width = _number(bbox.get("width"))
        depth = _number(bbox.get("depth"))
        if height is None or width is None or depth is None:
            return False
        return (
            scene.tower.height_m - HEIGHT_TOLERANCE_M <= height <= scene.tower.height_m + 10
            and 0 < width <= 50
            and 0 < depth <= 50
        )
    return (
        glb_inspection.file_exists
        and glb_inspection.file_size_bytes > 32
        and glb_inspection.node_count >= len(scene.sectors) + 1
        and _approx_tower_height_valid(scene, metadata)
    )


def _load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize(value: str) -> str:
    return str(value).lower().replace(":", "_").replace("-", "_")


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _angular_delta(actual: float, expected: float) -> float:
    delta = abs((actual - expected) % 360)
    return min(delta, 360 - delta)
