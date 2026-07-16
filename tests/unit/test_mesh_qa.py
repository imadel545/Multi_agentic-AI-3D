import json
import math
import struct
from pathlib import Path
from typing import Any

from core.agents.scene_planner import ScenePlanner
from core.qa.mesh_qa import (
    MeshQA,
    _build_semantic_index,
    _guess_geometry_source,
    _semantic_object_counts,
    _semantic_sector_ids,
    _tower_bounding_box,
    _transform_checks,
)
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text


def test_tower_height_uses_only_semantic_tower_geometry(tmp_path: Path) -> None:
    scene = _scene()
    payload = {
        "asset": {"version": "2.0"},
        "nodes": [
            {
                "name": "tower_root",
                "children": [1],
                "extras": {"semantic_root": True, "role": "tower"},
            },
            {"name": "tower_mesh", "mesh": 0},
            {
                "name": "gps_root",
                "translation": [0, 80, 0],
                "children": [3],
                "extras": {"semantic_root": True, "role": "gps"},
            },
            {"name": "gps_mesh", "mesh": 1},
        ],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}}]},
            {"primitives": [{"attributes": {"POSITION": 1}}]},
        ],
        "accessors": [
            {
                "count": 8,
                "type": "VEC3",
                "componentType": 5126,
                "min": [-1, 0, -1],
                "max": [1, 30, 1],
            },
            {
                "count": 8,
                "type": "VEC3",
                "componentType": 5126,
                "min": [-0.2, 0, -0.2],
                "max": [0.2, 1, 0.2],
            },
        ],
    }
    glb_path = tmp_path / "semantic.glb"
    _write_json_glb(glb_path, payload)

    index = _build_semantic_index(payload, scene)
    tower_bbox = _tower_bounding_box(glb_path, payload, index)
    report = MeshQA().validate(glb_path, scene)
    tower_check = next(check for check in report.checks if check.name == "tower_height_approx")

    assert tower_bbox is not None
    assert tower_bbox.height == 30.0
    assert report.bounding_box_m is not None
    assert report.bounding_box_m.max_y == 81.0
    assert tower_check.passed is True
    assert "tower_only=30.00m" in (tower_check.detail or "")


def test_semantic_index_counts_unique_roots_and_does_not_match_s1_to_s10() -> None:
    scene = _scene().model_copy(update={"sectors": [_scene().sectors[0]]})
    payload = {
        "nodes": [
            {
                "name": "tower_root",
                "children": [1, 2],
                "extras": {"semantic_root": "tower_root", "role": "tower"},
            },
            {
                "name": "tower_leg_1",
                "mesh": 0,
                "extras": {"semantic_root": "tower_root", "role": "tower"},
            },
            {
                "name": "tower_brace_1",
                "mesh": 0,
                "extras": {"semantic_root": "tower_root", "role": "tower"},
            },
            {"name": "antenna_S10", "mesh": 0},
            {"name": "antenna_S10_part_1", "mesh": 0},
        ]
    }

    index = _build_semantic_index(payload, scene)
    counts = _semantic_object_counts(index)
    sectors = _semantic_sector_ids(index)

    assert counts["tower"] == 1
    assert counts["antenna"] == 1
    assert sectors.get("antenna", []) == []


def test_name_based_legacy_glb_is_inspectable_but_not_mesh_qa_passed(tmp_path: Path) -> None:
    scene = _minimal_semantic_scene().model_copy(
        update={"sectors": [_minimal_semantic_scene().sectors[0]]}
    )
    payload = {
        "asset": {"version": "2.0"},
        "nodes": [
            {"name": "tower_leg_1", "mesh": 0},
            {"name": "tower_brace_1", "mesh": 0},
            {"name": "antenna_S1", "mesh": 1, "translation": [0, 24, 0]},
            {"name": "tower_lightning_rod", "mesh": 2, "translation": [0, 35, 0]},
        ],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}}]},
            {"primitives": [{"attributes": {"POSITION": 1}}]},
        ],
        "accessors": [
            {
                "count": 8,
                "type": "VEC3",
                "componentType": 5126,
                "min": [-1, 0, -1],
                "max": [1, 30, 1],
            },
            {
                "count": 8,
                "type": "VEC3",
                "componentType": 5126,
                "min": [-0.2, -0.8, -0.1],
                "max": [0.2, 0.8, 0.1],
            },
            {
                "count": 8,
                "type": "VEC3",
                "componentType": 5126,
                "min": [-0.05, 0, -0.05],
                "max": [0.05, 1, 0.05],
            },
        ],
    }
    glb_path = tmp_path / "legacy.glb"
    _write_json_glb(glb_path, payload)

    report = MeshQA().validate(glb_path, scene)

    assert report.glb_parse_ok is True
    assert report.level == "mesh_level_basic"
    assert report.mesh_qa_passed is False
    assert "MESH_QA_NAME_BASED_DEGRADED" in report.warnings
    tower_check = next(check for check in report.checks if check.name == "tower_height_approx")
    assert "tower_only=30.00m" in (tower_check.detail or "")


def test_semantic_transform_checks_validate_hba_and_azimuth_per_sector() -> None:
    scene = _minimal_semantic_scene()
    payload = _semantic_transform_payload(scene)

    result = _transform_checks(payload, scene)
    checks = {check.name: check for check in result["checks"]}

    assert result["semantic_transform_checks_complete"] is True
    assert checks["semantic_extras_complete"].passed is True
    assert checks["antenna_hba_transform_approx"].passed is True
    assert checks["antenna_azimuth_transform_approx"].passed is True
    assert "S2:requested=120.00,actual=120.00" in (
        checks["antenna_azimuth_transform_approx"].detail or ""
    )


def test_semantic_transform_checks_reject_wrong_sector_orientation() -> None:
    scene = _minimal_semantic_scene()
    payload = _semantic_transform_payload(scene)
    s2 = next(node for node in payload["nodes"] if node.get("extras", {}).get("sector_id") == "S2")
    s2["rotation"] = [0.0, 0.0, 0.0, 1.0]

    result = _transform_checks(payload, scene)
    checks = {check.name: check for check in result["checks"]}

    assert result["semantic_transform_checks_complete"] is False
    assert checks["antenna_azimuth_transform_approx"].passed is False
    assert "S2:requested=120.00,actual=0.00" in (
        checks["antenna_azimuth_transform_approx"].detail or ""
    )


def test_mixed_geometry_sources_are_reported_explicitly() -> None:
    scene = _minimal_semantic_scene()
    payload = _semantic_transform_payload(scene)
    antenna = next(
        node for node in payload["nodes"] if node.get("extras", {}).get("role") == "antenna"
    )
    antenna["extras"]["geometry_source"] = "internal_project_generated"

    source, mixed = _guess_geometry_source(_build_semantic_index(payload, scene))

    assert source == "mixed"
    assert mixed is False


def _scene():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
    )
    registry = AssetRegistry(Path("assets/manifests"))
    return ScenePlanner().build_scene_spec(
        "wf_mesh_qa",
        requirements,
        registry.select_tower(
            requirements.tower_type,
            requirements.network_type,
            requirements.tower_height_m,
        ),
        registry.select_asset("antenna", requirements.network_type, requirements.tower_type),
        registry.select_asset("radio", requirements.network_type, requirements.tower_type),
    )


def _minimal_semantic_scene():
    scene = _scene()
    sectors = [
        sector.model_copy(update={"radio_asset_id": None, "include_cable": False})
        for sector in scene.sectors
    ]
    tower = scene.tower.model_copy(
        update={
            "characteristics": scene.tower.characteristics.model_copy(
                update={"foundation_type": "unknown"}
            )
        }
    )
    visual_elements = scene.visual_elements.model_copy(
        update={
            "include_sector_beams": False,
            "include_azimuth_arrows": False,
            "include_labels": False,
            "include_power_cabinet": False,
            "include_gps_antenna": False,
        }
    )
    return scene.model_copy(
        update={"tower": tower, "sectors": sectors, "visual_elements": visual_elements}
    )


def _semantic_transform_payload(scene) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "name": "tower_root",
            "extras": {
                "semantic_root": True,
                "role": "tower",
                "geometry_source": "parametric_generated",
                "generation_strategy": "parametric_generated",
            },
        }
    ]
    for sector in scene.sectors:
        azimuth_radians = math.radians(sector.azimuth_deg)
        nodes.append(
            {
                "name": f"antenna_{sector.sector_id}",
                "translation": [0.0, sector.install_height_m, 0.0],
                "rotation": [
                    0.0,
                    -math.sin(azimuth_radians / 2.0),
                    0.0,
                    math.cos(azimuth_radians / 2.0),
                ],
                "extras": {
                    "semantic_root": True,
                    "role": "antenna",
                    "sector_id": sector.sector_id,
                    "requested_hba_m": sector.install_height_m,
                    "requested_azimuth_deg": sector.azimuth_deg,
                    "front_axis": "+Y",
                    "geometry_source": "parametric_generated",
                    "generation_strategy": "parametric_generated",
                },
            }
        )
    return {"asset": {"version": "2.0"}, "nodes": nodes}


def _write_json_glb(path: Path, payload: dict[str, Any]) -> None:
    json_chunk = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    length = 12 + 8 + len(json_chunk)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
    )
