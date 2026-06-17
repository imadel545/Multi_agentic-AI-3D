import json
from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.glb_inspection import GlbInspectionReport
from core.qa.glb_geometry_validator import GLBGeometryValidator
from core.qa.mesh_qa import _object_prefix_counts
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text


def test_geometry_validation_valid_5g_scene(tmp_path: Path) -> None:
    scene = _scene()
    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(_object_names(scene)),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "passed"
    assert report.checks["antenna_count_valid"] is True
    assert report.checks["rru_count_valid"] is True
    assert report.checks["cable_count_valid"] is True
    assert report.checks["tower_characteristics_metadata_valid"] is True
    assert report.checks["azimuth_metadata_valid"] is True
    assert report.checks["mechanical_tilt_metadata_valid"] is True


def test_geometry_validation_missing_antenna_fails(tmp_path: Path) -> None:
    scene = _scene()
    names = [name for name in _object_names(scene) if not name.startswith("antenna_S3")]

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(names),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "failed"
    assert report.checks["antenna_count_valid"] is False
    assert "antenna:S3" in report.missing_objects


def test_geometry_validation_missing_beam_fails(tmp_path: Path) -> None:
    scene = _scene()
    names = [name for name in _object_names(scene) if not name.startswith("sector_beam_S2")]

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(names),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "failed"
    assert report.checks["beam_count_valid"] is False
    assert "beam:S2" in report.missing_objects


def test_geometry_validation_ignores_auxiliary_heads_for_required_counts(tmp_path: Path) -> None:
    scene = _scene()
    names = _object_names(scene) + [
        "sector_beam_head_S1",
        "sector_beam_head_S2",
        "azimuth_arrow_head_S1",
    ]

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(names),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "passed"
    assert report.object_counts["beam"] == 3
    assert report.object_counts["azimuth_arrow"] == 3


def test_geometry_validation_auxiliary_head_does_not_replace_missing_beam(
    tmp_path: Path,
) -> None:
    scene = _scene()
    names = [name for name in _object_names(scene) if not name.startswith("sector_beam_S2")] + [
        "sector_beam_head_S2"
    ]

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(names),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "failed"
    assert report.checks["beam_count_valid"] is False
    assert "beam:S2" in report.missing_objects


def test_geometry_validation_respects_no_cables_option(tmp_path: Path) -> None:
    scene = _scene("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Sans câbles.")
    names = _object_names(scene)

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(names),
        _metadata_path(tmp_path, scene),
    )

    assert report.status == "passed"
    assert report.object_counts["cable"] == 0
    assert report.checks["cable_count_valid"] is True


def test_geometry_validation_requires_requested_accessories(tmp_path: Path) -> None:
    scene = _accessory_scene()

    passed = GLBGeometryValidator().validate(
        scene,
        _glb_report(_object_names(scene)),
        _metadata_path(tmp_path, scene),
    )
    missing = GLBGeometryValidator().validate(
        scene,
        _glb_report(
            [
                name
                for name in _object_names(scene)
                if not name.startswith(("gps_antenna", "power_cabinet"))
            ]
        ),
        _metadata_path(tmp_path, scene),
    )

    assert passed.status == "passed"
    assert passed.checks["gps_antenna_count_valid"] is True
    assert passed.checks["power_cabinet_count_valid"] is True
    assert missing.status == "failed"
    assert "gps_antenna" in missing.missing_objects
    assert "power_cabinet" in missing.missing_objects


def test_geometry_validation_scales_bounding_box_sanity_for_tall_parametric_tower(
    tmp_path: Path,
) -> None:
    scene = _scene(
        "Créer un site 5G sur pylône treillis 90m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, boîte alimentation, "
        "dalle béton, GPS et labels."
    )
    metadata_path = _metadata_path(tmp_path, scene)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["bounding_box_m"] = {
        "width": 54.0,
        "depth": 54.0,
        "height": 90.9,
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = GLBGeometryValidator().validate(
        scene,
        _glb_report(_object_names(scene)),
        metadata_path,
    )

    assert scene.tower.height_m == 90.0
    assert report.checks["bounding_box_reasonable"] is True


def test_mesh_qa_prefix_counts_do_not_treat_gps_as_sector_antenna() -> None:
    counts = _object_prefix_counts(
        [
            "tower_TOWER_LATTICE_30M",
            "gps_antenna_GPS_ANTENNA_001",
            "power_cabinet_POWER_CABINET_001",
        ]
    )

    assert counts.get("antenna", 0) == 0
    assert counts["gps"] == 1
    assert counts["power_cabinet"] == 1


def _scene(prompt: str | None = None):
    requirements = parse_requirements_text(
        prompt
        or (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles et faisceaux."
        )
    )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower(
        requirements.tower_type,
        requirements.network_type,
        requirements.tower_height_m,
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = (
        registry.select_asset("radio", requirements.network_type, requirements.tower_type)
        if requirements.include_rru
        else None
    )
    return ScenePlanner().build_scene_spec("wf_geometry", requirements, tower, antenna, radio)


def _accessory_scene():
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, GPS et armoire énergie."
    ).model_copy(
        update={
            "mechanical_tilt_deg": 5,
            "include_gps_antenna": True,
            "include_power_cabinet": True,
        }
    )
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
        "wf_geometry_accessories",
        requirements,
        tower,
        antenna,
        radio,
        accessory_assets=[gps, cabinet],
    )


def _object_names(scene) -> list[str]:
    names = ["tower_leg", f"tower_{scene.tower.asset_id}"]
    if scene.tower.characteristics.foundation_type == "concrete_pad":
        names.append("foundation_concrete_pad")
    for sector in scene.sectors:
        names.append(f"antenna_{sector.sector_id}_{sector.antenna_asset_id}")
        if sector.radio_asset_id:
            names.append(f"radio_{sector.sector_id}_{sector.radio_asset_id}")
        if sector.include_cable:
            names.append(f"cable_{sector.sector_id}")
        if scene.visual_elements.include_sector_beams:
            names.append(f"sector_beam_{sector.sector_id}")
        if scene.visual_elements.include_azimuth_arrows:
            names.append(f"azimuth_arrow_{sector.sector_id}")
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


def _metadata_path(tmp_path: Path, scene) -> Path:
    path = tmp_path / "scene_metadata.json"
    assets = [scene.tower.asset_id]
    for sector in scene.sectors:
        assets.append(sector.antenna_asset_id)
        if sector.radio_asset_id:
            assets.append(sector.radio_asset_id)
    for accessory in scene.accessory_assets:
        assets.append(accessory.asset_id)
    path.write_text(
        json.dumps(
            {
                "scene_id": scene.scene_id,
                "assets_used": sorted(set(assets)),
                "tower_height_m": scene.tower.height_m,
                "tower_characteristics": scene.tower.characteristics.model_dump(),
                "azimuths_deg": [sector.azimuth_deg for sector in scene.sectors],
                "antenna_heights_m": [sector.install_height_m for sector in scene.sectors],
                "mechanical_tilts_deg": [sector.mechanical_tilt_deg for sector in scene.sectors],
            }
        ),
        encoding="utf-8",
    )
    return path


def _glb_report(object_names: list[str]) -> GlbInspectionReport:
    return GlbInspectionReport(
        inspection_mode="glb_parse",
        file_exists=True,
        file_size_bytes=4096,
        format_valid=True,
        node_count=len(object_names),
        mesh_count=max(1, len(object_names)),
        material_count=3,
        object_names=object_names,
        expected_object_prefixes_found={},
        checks={"expected_objects_present": True, "minimum_node_count_valid": True},
        warnings=[],
        critical_errors=[],
        structural_qa_passed=True,
    )
