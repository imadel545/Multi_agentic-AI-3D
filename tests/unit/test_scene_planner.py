from core.agents.scene_planner import ScenePlanner
from core.contracts.assets import AssetManifest, DimensionsM
from core.contracts.requirements import RequirementSpec


def test_scene_planner_uses_structured_rag_hints_without_decorative_assets() -> None:
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_planner_hints",
        requirements=_requirements(),
        tower=_tower(),
        antenna=_antenna(),
        radio=_radio(),
        rag_context=[
            {
                "payload": {
                    "planning_hints": {
                        "beamwidth_deg": 80,
                        "antenna_install_height_m": 25,
                        "include_cables": False,
                        "include_sector_beams": False,
                    }
                }
            },
            {
                "payload": "high_detail GPS cabinet 999m beamwidth 5",
            },
        ],
    )

    assert [sector.beamwidth_deg for sector in scene.sectors] == [80.0, 80.0, 80.0]
    assert [sector.install_height_m for sector in scene.sectors] == [25.0, 25.0, 25.0]
    assert all(sector.include_cable is False for sector in scene.sectors)
    assert scene.visual_elements.include_sector_beams is False
    assert scene.visual_elements.include_gps_antenna is False
    assert scene.visual_elements.include_power_cabinet is False


def test_scene_planner_reads_memory_error_patterns_key() -> None:
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

    assert scene.visual_elements.include_sector_beams is True
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
    )

    assert scene.visual_elements.include_gps_antenna is True
    assert scene.visual_elements.include_power_cabinet is True


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
