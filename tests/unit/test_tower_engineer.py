import pytest

from core.agents.tower_engineer import TowerEngineerAgent
from core.contracts.assets import AssetManifest, DimensionsM
from core.contracts.requirements import RequirementSpec
from core.contracts.tower import TowerCharacteristics


@pytest.fixture
def agent() -> TowerEngineerAgent:
    return TowerEngineerAgent()


@pytest.fixture
def valid_requirements() -> RequirementSpec:
    return RequirementSpec(
        tower_type="lattice_tower",
        tower_height_m=30,
        tower_characteristics=TowerCharacteristics(
            structure="lattice",
            leg_count=4,
            base_width_m=4.0,
            top_width_m=1.0,
            foundation_type="concrete_pad",
            has_platform=True,
            platform_count=1,
            has_ladder=True,
            has_lightning_rod=True,
            has_aviation_light=False,
            material="galvanized_steel",
        ),
        sector_count=3,
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
    )


@pytest.fixture
def tower_asset() -> AssetManifest:
    return AssetManifest(
        asset_id="tower_lattice_30m",
        type="tower",
        file="tower.glb",
        dimensions_m=DimensionsM(width=4.0, depth=4.0, height=30.0),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
    )


def test_tower_engineer_passes_valid(agent, valid_requirements, tower_asset):
    report = agent.validate(valid_requirements, tower_asset)
    assert report.status == "passed"
    assert report.structural_score == 1.0
    assert report.checks["leg_count_appropriate"] is True


def test_tower_engineer_fails_lattice_with_2_legs(agent, valid_requirements, tower_asset):
    req = valid_requirements.model_copy(
        update={
            "tower_characteristics": valid_requirements.tower_characteristics.model_copy(
                update={"leg_count": 2, "has_platform": False, "platform_count": 0}
            )
        }
    )
    report = agent.validate(req, tower_asset)
    assert report.status == "failed"
    assert any(e.code == "TOWER_LATTICE_MIN_3_LEGS" for e in report.errors)


def test_tower_engineer_warns_on_invalid_taper(agent, valid_requirements, tower_asset):
    req = valid_requirements.model_copy(
        update={
            "tower_characteristics": valid_requirements.tower_characteristics.model_copy(
                update={"top_width_m": 5.0, "has_platform": False, "platform_count": 0}
            )
        }
    )
    report = agent.validate(req, tower_asset)
    assert report.status == "failed"
    assert any(e.code == "TOWER_TAPER_INVALID" for e in report.errors)


def test_tower_engineer_warns_on_rooftop_concrete_pad(agent, valid_requirements, tower_asset):
    req = valid_requirements.model_copy(
        update={
            "tower_characteristics": valid_requirements.tower_characteristics.model_copy(
                update={
                    "structure": "rooftop_mast",
                    "foundation_type": "concrete_pad",
                    "has_platform": False,
                    "platform_count": 0,
                }
            )
        }
    )
    report = agent.validate(req, tower_asset)
    assert any(w.code == "TOWER_FOUNDATION_RECOMMENDATION" for w in report.warnings)


def test_tower_engineer_recommends_aviation_light(agent, valid_requirements, tower_asset):
    req = valid_requirements.model_copy(update={"tower_height_m": 50})
    report = agent.validate(req, tower_asset)
    assert any(w.code == "TOWER_AVIATION_LIGHT_RECOMMENDED" for w in report.warnings)
