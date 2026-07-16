from core.agents.scene_planner import ScenePlanner
from core.contracts.assets import AssetManifest, DimensionsM
from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec


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
