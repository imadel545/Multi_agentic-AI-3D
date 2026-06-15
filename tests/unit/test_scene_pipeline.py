from pathlib import Path

from core.agents import ScenePlanner
from core.rules import RuleEngine
from core.services.asset_registry import AssetRegistry
from core.services.requirement_parser import parse_requirements_text
from core.validation import validate_scene_spec


def test_requirement_to_valid_scene_spec() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type, requirements.network_type, requirements.tower_height_m
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)

    requirement_report = RuleEngine().validate_requirements(requirements, [tower, antenna, radio])
    scene = ScenePlanner().build_scene_spec("wf_test", requirements, tower, antenna, radio)
    scene_report = validate_scene_spec(scene, registry.list_assets())

    assert requirement_report.status == "passed"
    assert scene_report.status == "passed"
    assert scene.tower.asset_id == "TOWER_LATTICE_30M"
    assert scene.tower.characteristics.structure == "lattice"
    assert scene.tower.characteristics.base_width_m == 4.0
    assert [sector.azimuth_deg for sector in scene.sectors] == [0, 120, 240]


def test_parametric_monopole_mount_zone_scales_to_requested_height() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    requirements = parse_requirements_text(
        "Créer un site 5G monopole 36m avec 3 secteurs à 30m. Azimuts : 0°, 120°, 240°."
    )
    tower = registry.select_tower(
        requirements.tower_type, requirements.network_type, requirements.tower_height_m
    )
    antenna = registry.select_asset("antenna", requirements.network_type, requirements.tower_type)
    radio = registry.select_asset("radio", requirements.network_type, requirements.tower_type)

    scene = ScenePlanner().build_scene_spec("wf_monopole_36", requirements, tower, antenna, radio)
    scene_report = validate_scene_spec(scene, registry.list_assets())

    assert scene.tower.asset_id == "TOWER_MONOPOLE_30M"
    assert scene.tower.height_m == 36.0
    assert [sector.install_height_m for sector in scene.sectors] == [30.0, 30.0, 30.0]
    assert scene_report.checks["mount_zones_valid"] is True
    assert scene_report.status == "passed"
