from core.agents.tower_engineer import TowerEngineerAgent, apply_tower_engineer_recommendations
from core.contracts.assets import AssetManifest, DimensionsM
from core.contracts.requirements import RequirementSpec
from core.contracts.tower import TowerCharacteristics


def _requirements(text_height: float = 42.0, **characteristics) -> RequirementSpec:
    return RequirementSpec(
        tower_type="lattice_tower",
        tower_height_m=text_height,
        sector_count=3,
        antenna_type="panel",
        antenna_install_height_m=38.0,
        azimuths_deg=[0, 120, 240],
        tower_characteristics=TowerCharacteristics(structure="lattice", **characteristics),
    )


def _tower_manifest() -> AssetManifest:
    return AssetManifest(
        asset_id="tower_lattice_30m",
        type="tower",
        file="tower.glb",
        dimensions_m=DimensionsM(width=4.0, depth=4.0, height=30.0),
        compatible_networks=["5G"],
        compatible_tower_types=["lattice_tower"],
    )


def test_tower_engineer_recommendation_changes_the_design() -> None:
    requirements = _requirements()
    report = TowerEngineerAgent().validate(requirements, _tower_manifest())
    applied, assumptions = apply_tower_engineer_recommendations(
        requirements, report, requirements_text="Créer un site 5G sur pylône treillis de 42 m"
    )
    characteristics = applied.tower_characteristics
    assert characteristics.has_platform and characteristics.platform_count == 1
    assert characteristics.platform_levels_m == [35.5]
    assert characteristics.has_ladder and characteristics.has_lightning_rod
    assert len(assumptions) == 3 and all(a in applied.assumptions for a in assumptions)


def test_explicitly_declined_accessories_are_respected() -> None:
    requirements = _requirements()
    report = TowerEngineerAgent().validate(requirements, _tower_manifest())
    applied, assumptions = apply_tower_engineer_recommendations(
        requirements,
        report,
        requirements_text="Pylône treillis de 42 m sans plateforme et sans échelle",
    )
    assert not applied.tower_characteristics.has_platform
    assert not applied.tower_characteristics.has_ladder
    assert applied.tower_characteristics.has_lightning_rod
    assert assumptions == ["Paratonnerre ajouté au sommet du pylône."]


def test_monopole_is_left_untouched() -> None:
    requirements = _requirements().model_copy(
        update={"tower_characteristics": TowerCharacteristics(structure="monopole", leg_count=1)}
    )
    report = TowerEngineerAgent().validate(requirements, _tower_manifest())
    applied, assumptions = apply_tower_engineer_recommendations(
        requirements, report, requirements_text="monopole 42 m"
    )
    assert applied == requirements and assumptions == []
