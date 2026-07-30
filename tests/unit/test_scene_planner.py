from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.assets import AssetManifest, AssetQualification, DimensionsM
from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec
from core.services.asset_registry import AssetRegistry


def test_scene_planner_rejects_rag_overrides_for_source_requirements() -> None:
    rag_context = [
        {
            "collection": "scene_templates",
            "doc_id": "template:5g",
            "score": 0.98,
            "payload": {
                "planning_hints": {
                    "beamwidth_deg": 80,
                    "antenna_install_height_m": 25,
                    "mechanical_tilt_deg": 7,
                    "electrical_tilt_deg": 4,
                    "include_cables": False,
                    "include_sector_beams": False,
                }
            },
        },
        {
            "payload": "high_detail GPS cabinet 999m beamwidth 5",
        },
    ]
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_planner_hints",
        requirements=_requirements(),
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        rag_context=rag_context,
    )

    assert [sector.beamwidth_deg for sector in scene.sectors] == [65.0, 65.0, 65.0]
    assert [sector.install_height_m for sector in scene.sectors] == [24.0, 24.0, 24.0]
    assert [sector.mechanical_tilt_deg for sector in scene.sectors] == [3.0, 3.0, 3.0]
    assert [sector.electrical_tilt_deg for sector in scene.sectors] == [0.0, 0.0, 0.0]
    assert all(sector.include_cable is True for sector in scene.sectors)
    assert scene.visual_elements.include_sector_beams is True
    assert scene.visual_elements.include_gps_antenna is False
    assert scene.visual_elements.include_power_cabinet is False
    assert scene.accessory_assets == []
    payload = rag_context[0]["payload"]
    assert payload["planning_hints"] == {}
    assert payload["planning_hint_candidates"]["antenna_install_height_m"] == 25
    assert {item["status"] for item in payload["planning_decisions"]} == {"rejected"}
    assert {item["reason"] for item in payload["planning_decisions"]} == {
        "source_requirement_protected"
    }


def test_scene_planner_applies_only_highest_ranked_hint_to_inferred_field() -> None:
    requirements = _requirements().model_copy(
        update={
            "warnings": [
                WarningItem(
                    code="DEFAULT_INSTALL_HEIGHT_USED",
                    message="Antenna install height inferred as 24m.",
                )
            ]
        }
    )
    rag_context = [
        {
            "collection": "scene_templates",
            "doc_id": "best",
            "score": 0.95,
            "payload": {
                "network_type": "5G",
                "tower_type": "lattice_tower",
                "source_path": "/Users/example/private/scene_templates.md",
                "planning_hints": {"antenna_install_height_m": 25},
            },
        },
        {
            "collection": "scene_templates",
            "doc_id": "second",
            "score": 0.80,
            "payload": {
                "network_type": "5G",
                "tower_type": "lattice_tower",
                "planning_hints": {"antenna_install_height_m": 23},
            },
        },
    ]

    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_inferred_hba",
        requirements=requirements,
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        rag_context=rag_context,
    )

    assert {sector.install_height_m for sector in scene.sectors} == {25.0}
    assert rag_context[0]["payload"]["planning_hints"] == {"antenna_install_height_m": 25.0}
    assert rag_context[0]["payload"]["rag_planning_applied"] is True
    selected = rag_context[0]["payload"]["planning_decisions"][0]
    assert selected["status"] == "applied"
    assert selected["provenance"]["doc_id"] == "best"
    assert selected["provenance"]["source_path"] == "scene_templates.md"
    lower_ranked = rag_context[1]["payload"]["planning_decisions"][0]
    assert lower_ranked["status"] == "rejected"
    assert lower_ranked["reason"] == "lower_ranked_conflict"


def test_scene_planner_applies_bounded_tilt_hints_only_when_defaults_are_explicit() -> None:
    requirements = _requirements().model_copy(
        update={
            "warnings": [
                WarningItem(
                    code="DEFAULT_MECHANICAL_TILT_USED",
                    message="Mechanical tilt used the controlled default.",
                ),
                WarningItem(
                    code="DEFAULT_ELECTRICAL_TILT_USED",
                    message="Electrical tilt used the controlled default.",
                ),
            ]
        }
    )
    rag_context = [
        {
            "collection": "telecom_rules",
            "doc_id": "rule:tilt",
            "score": 0.94,
            "payload": {
                "network_type": "5G",
                "tower_type": "lattice_tower",
                "planning_hints": {
                    "mechanical_tilt_deg": 6,
                    "electrical_tilt_deg": 3,
                },
            },
        }
    ]

    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_inferred_tilts",
        requirements=requirements,
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        rag_context=rag_context,
    )

    assert {sector.mechanical_tilt_deg for sector in scene.sectors} == {6.0}
    assert {sector.electrical_tilt_deg for sector in scene.sectors} == {3.0}
    assert rag_context[0]["payload"]["planning_hints"] == {
        "mechanical_tilt_deg": 6.0,
        "electrical_tilt_deg": 3.0,
    }


def test_scene_planner_records_equal_hint_as_no_op_not_rag_use() -> None:
    rag_context = [
        {
            "payload": {
                "planning_hints": {"antenna_install_height_m": 24},
            }
        }
    ]

    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_no_op_hint",
        requirements=_requirements(),
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        rag_context=rag_context,
    )

    assert {sector.install_height_m for sector in scene.sectors} == {24.0}
    assert rag_context[0]["payload"]["planning_hints"] == {}
    assert rag_context[0]["payload"]["rag_planning_applied"] is False
    assert rag_context[0]["payload"]["planning_decisions"][0]["status"] == "no_op"


def test_scene_planner_does_not_override_explicit_requirements_from_memory() -> None:
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_planner_memory",
        requirements=_requirements().model_copy(update={"include_beams": False}),
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        memory_recall={
            "error_patterns": [
                {
                    "issue_code": "RF_AZIMUTH_SPACING_LOW",
                    "count": 2,
                }
            ],
            "error_memory": [
                {
                    "issue_code": "TOWER_AVIATION_LIGHT_RECOMMENDED",
                    "count": 9,
                }
            ],
        },
    )

    assert scene.visual_elements.include_sector_beams is False
    assert scene.visual_elements.include_gps_antenna is False


def test_scene_planner_carries_explicit_requirement_accessories() -> None:
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_planner_accessories",
        requirements=_requirements().model_copy(
            update={"include_gps_antenna": True, "include_power_cabinet": True}
        ),
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        accessory_assets=[_gps(), _cabinet()],
    )

    assert scene.visual_elements.include_gps_antenna is True
    assert scene.visual_elements.include_power_cabinet is True
    assert {accessory.asset_id for accessory in scene.accessory_assets} == {
        "GPS_ANTENNA_001",
        "POWER_CABINET_001",
    }
    assert all(accessory.asset_file for accessory in scene.accessory_assets)
    placements = {accessory.asset_type: accessory for accessory in scene.accessory_assets}
    assert placements["cabinet"].position[2] == 0.0
    assert placements["gps"].position[2] == 29.5
    assert placements["gps"].position[1] < 1.0


def test_scene_planner_uses_only_manifest_authorized_generation_modes() -> None:
    import_qualification = AssetQualification(
        status="qualified_for_generation",
        allowed_generation_modes=["imported_glb_exact"],
        verified_file_sha256="a" * 64,
        mesh_integrity_verified=True,
        dimensions_verified=True,
        pivot_verified=True,
        orientation_verified=True,
        qualification_method="test qualification",
    )
    parametric_qualification = AssetQualification(
        status="qualified_for_generation",
        allowed_generation_modes=["parametric_generated"],
        dimensions_verified=True,
        qualification_method="test parametric profile",
    )
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_asset_policy",
        requirements=_requirements().model_copy(update={"include_gps_antenna": True}),
        tower=_tower().model_copy(update={"qualification": parametric_qualification}),
        antenna=_antenna().model_copy(update={"qualification": import_qualification}),
        radio=_radio().model_copy(update={"qualification": parametric_qualification}),
        accessory_assets=[_gps().model_copy(update={"qualification": import_qualification})],
    )

    assert scene.tower.generation_strategy == "parametric_generated"
    assert scene.sectors[0].antenna_generation_strategy == "imported_glb_exact"
    assert scene.sectors[0].antenna_geometry_source == "imported_glb_exact"
    assert scene.sectors[0].radio_generation_strategy == "internal_project_generated"
    assert scene.accessory_assets[0].generation_strategy == "imported_glb_exact"
    assert scene.sectors[0].antenna_asset_metadata.verified_file_sha256 == "a" * 64


def test_scene_planner_propagates_geometry_fidelity_to_runtime_metadata() -> None:
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_geometry_fidelity",
        requirements=_requirements(),
        tower=_tower(),
        antenna=_antenna().model_copy(update={"geometry_fidelity": "technical_generic"}),
        radio=_radio().model_copy(update={"geometry_fidelity": "vendor_qualified"}),
    )

    assert scene.tower.asset_metadata.geometry_fidelity == "schematic"
    assert scene.sectors[0].antenna_asset_metadata.geometry_fidelity == "technical_generic"
    assert scene.sectors[0].radio_asset_metadata.geometry_fidelity == "vendor_qualified"


def test_scene_planner_resolves_bounded_geometry_profiles_from_detail_level() -> None:
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower("lattice_tower", "5G", 30)
    antenna = registry.get("ANT_PANEL_5G_001")
    radio = registry.get("RRU_SMALL_001")
    planner = ScenePlanner()

    high = planner.build_scene_spec(
        workflow_id="wf_detail_high",
        requirements=_requirements().model_copy(update={"detail_level": "high"}),
        tower=tower,
        antenna=antenna,
        radio=radio,
    )
    medium = planner.build_scene_spec(
        workflow_id="wf_detail_medium",
        requirements=_requirements().model_copy(update={"detail_level": "medium"}),
        tower=tower,
        antenna=antenna,
        radio=radio,
    )
    low = planner.build_scene_spec(
        workflow_id="wf_detail_low",
        requirements=_requirements().model_copy(update={"detail_level": "low"}),
        tower=tower,
        antenna=antenna,
        radio=radio,
    )

    high_sector = high.sectors[0]
    medium_sector = medium.sectors[0]
    low_sector = low.sectors[0]
    assert (high.detail_level, medium.detail_level, low.detail_level) == (
        "high",
        "medium",
        "low",
    )
    assert high_sector.radio_geometry_profile is not None
    assert medium_sector.radio_geometry_profile is not None
    assert low_sector.radio_geometry_profile is not None
    assert high_sector.antenna_geometry_profile is not None
    assert medium_sector.antenna_geometry_profile is not None
    assert low_sector.antenna_geometry_profile is not None

    assert high_sector.radio_geometry_profile.heat_sink_fin_count == 8
    assert high_sector.radio_geometry_profile.bottom_connector_count == 4
    assert medium_sector.radio_geometry_profile.heat_sink_fin_count == 6
    assert medium_sector.radio_geometry_profile.bottom_connector_count == 3
    assert low_sector.radio_geometry_profile.heat_sink_fin_count == 4
    assert low_sector.radio_geometry_profile.bottom_connector_count == 2
    assert high_sector.antenna_geometry_profile.bottom_port_count == 4
    assert medium_sector.antenna_geometry_profile.bottom_port_count == 3
    assert low_sector.antenna_geometry_profile.bottom_port_count == 2

    assert high_sector.radio_dimensions_m == low_sector.radio_dimensions_m
    assert high_sector.antenna_dimensions_m == low_sector.antenna_dimensions_m
    assert high_sector.install_height_m == low_sector.install_height_m
    assert high_sector.azimuth_deg == low_sector.azimuth_deg
    assert (
        high_sector.radio_geometry_profile.vertical_offset_m
        == low_sector.radio_geometry_profile.vertical_offset_m
    )
    assert (
        high_sector.radio_geometry_profile.radial_inset_m
        == low_sector.radio_geometry_profile.radial_inset_m
    )


def test_scene_planner_resolves_optional_tower_widths_into_scene_spec() -> None:
    requirements = _requirements().model_copy(
        update={
            "tower_characteristics": _requirements().tower_characteristics.model_copy(
                update={"base_width_m": None, "top_width_m": None}
            )
        }
    )
    tower = _tower().model_copy(
        update={"dimensions_m": DimensionsM(width=3.2, depth=3.2, height=30.0)}
    )

    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_resolved_tower_dimensions",
        requirements=requirements,
        tower=tower,
        antenna=_antenna(),
        radio=_radio(),
    )

    assert scene.tower.characteristics.base_width_m == 3.2
    assert scene.tower.characteristics.top_width_m == 0.8


def test_scene_planner_carries_asset_license_metadata() -> None:
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_asset_metadata",
        requirements=_requirements(),
        tower=_tower().model_copy(
            update={
                "source": "cc_by",
                "license": "CC Attribution",
                "attribution_required": True,
                "attribution": "Cell Tower Replica by poly by google via GetGLB",
                "original_url": "https://www.getglb.com/architecture/cell-tower-replica/",
            }
        ),
        antenna=_antenna().model_copy(
            update={
                "source": "internal_cleaned",
                "license": "internal_project_generated",
                "attribution": "Project-authored minimal antenna",
            }
        ),
        radio=_radio(),
    )

    assert scene.tower.asset_source == "cc_by"
    assert scene.tower.asset_metadata.license == "CC Attribution"
    assert scene.tower.asset_metadata.attribution_required is True
    assert scene.tower.asset_metadata.original_url == (
        "https://www.getglb.com/architecture/cell-tower-replica/"
    )
    assert scene.sectors[0].antenna_asset_source == "internal_cleaned"
    assert scene.sectors[0].antenna_asset_metadata.license == "internal_project_generated"


def _requirements() -> RequirementSpec:
    return RequirementSpec(
        network_type="5G",
        site_type="telecom_site",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_type="panel_5g",
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        mechanical_tilt_deg=3,
        electrical_tilt_deg=0,
        beamwidth_deg=65,
        include_rru=True,
        include_cables=True,
        include_beams=True,
        include_labels=True,
        detail_level="high",
    )


def _tower() -> AssetManifest:
    return AssetManifest(
        asset_id="TOWER_LATTICE_30M",
        type="tower",
        file="assets/towers/tower_lattice_30m.glb",
        height_m=30,
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
        status="validated",
    )


def _antenna() -> AssetManifest:
    return AssetManifest(
        asset_id="ANT_PANEL_5G_001",
        type="antenna",
        file="assets/antennas/ant_panel_5g_001.glb",
        dimensions_m=DimensionsM(width=0.4, depth=0.18, height=1.2),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
        status="validated",
    )


def _radio() -> AssetManifest:
    return AssetManifest(
        asset_id="RRU_SMALL_001",
        type="radio",
        file="assets/radios/rru_small_001.glb",
        dimensions_m=DimensionsM(width=0.35, depth=0.18, height=0.45),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
        status="validated",
    )


def _gps() -> AssetManifest:
    return AssetManifest(
        asset_id="GPS_ANTENNA_001",
        type="gps",
        file="assets/antennas/gps_antenna_001.glb",
        dimensions_m=DimensionsM(width=0.32, depth=0.32, height=0.22),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
        status="validated",
    )


def _cabinet() -> AssetManifest:
    return AssetManifest(
        asset_id="POWER_CABINET_001",
        type="cabinet",
        file="assets/cabinets/power_cabinet_001.glb",
        dimensions_m=DimensionsM(width=1.0, depth=0.45, height=1.6),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
        status="validated",
    )
