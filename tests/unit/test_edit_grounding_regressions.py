import pytest

from core.agents.scene_edit_agent import SceneEditAgent, _validate_patch_alignment
from core.contracts.assets import RadioGeometryProfile
from core.contracts.scene import SceneAccessoryPlacement, SceneAssetPlacement, SceneSpec, SectorSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.tower import TowerCharacteristics


def _scene(*, platforms: int = 0, accessory: bool = False) -> SceneSpec:
    levels = [10.0 + index * 5.0 for index in range(platforms)]
    return SceneSpec(
        scene_id="grounding_regression",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower",
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=30.0,
            characteristics=TowerCharacteristics(
                structure="lattice",
                leg_count=4,
                base_width_m=4.0,
                top_width_m=1.0,
                foundation_type="concrete_pad",
                has_platform=bool(platforms),
                platform_count=platforms,
                platform_levels_m=levels,
            ),
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="antenna",
                install_height_m=24.0,
                azimuth_deg=0.0,
                mechanical_tilt_deg=3.0,
                electrical_tilt_deg=0.0,
                beamwidth_deg=65.0,
            )
        ],
        accessory_assets=(
            [
                SceneAccessoryPlacement(
                    asset_id="cabinet",
                    asset_type="cabinet",
                    position=[0.0, 0.0, 0.0],
                    rotation_deg=[0.0, 0.0, 0.0],
                )
            ]
            if accessory
            else []
        ),
    )


def _patch(path: str, value) -> ScenePatch:
    return ScenePatch(
        edit_description="grounding regression",
        operations=[PatchOperation(op="replace", path=path, value=value)],
    )


def test_sector_number_does_not_ground_an_unrequested_sector_field() -> None:
    with pytest.raises(ValueError, match="not grounded"):
        _validate_patch_alignment(
            _scene(),
            "oriente le secteur 1 à 90 degrés",
            _patch("/sectors/0/electrical_tilt_deg", 1),
        )


def test_percentage_respects_decrease_direction_and_is_not_an_absolute_value() -> None:
    scene = _scene()
    _validate_patch_alignment(scene, "diminue la hauteur de 20 %", _patch("/tower/height_m", 24))
    for invalid in (20, 36):
        with pytest.raises(ValueError, match="numeric value is not grounded"):
            _validate_patch_alignment(
                scene,
                "diminue la hauteur de 20 %",
                _patch("/tower/height_m", invalid),
            )


def test_relative_length_cannot_be_reinterpreted_as_an_absolute_target() -> None:
    scene = _scene()
    _validate_patch_alignment(
        scene,
        "baisse la hauteur de 40 cm",
        _patch("/tower/height_m", 29.6),
    )
    with pytest.raises(ValueError, match="numeric value is not grounded"):
        _validate_patch_alignment(
            scene,
            "baisse la hauteur de 40 cm",
            _patch("/tower/height_m", 0.4),
        )


def test_lowering_rru_increases_its_downward_vertical_offset() -> None:
    scene = _scene()
    sector = scene.sectors[0].model_copy(
        update={
            "radio_asset_id": "radio",
            "radio_geometry_profile": RadioGeometryProfile(vertical_offset_m=1.2),
        }
    )
    scene = scene.model_copy(update={"sectors": [sector]})
    path = "/sectors/0/radio_geometry_profile/vertical_offset_m"
    _validate_patch_alignment(
        scene,
        "baisse le RRU du secteur 1 de 40 cm",
        _patch(path, 1.6),
    )
    with pytest.raises(ValueError, match="numeric value is not grounded"):
        _validate_patch_alignment(
            scene,
            "baisse le RRU du secteur 1 de 40 cm",
            _patch(path, 0.8),
        )


def test_removing_one_platform_cannot_delete_every_platform() -> None:
    scene = _scene(platforms=3)
    _validate_patch_alignment(
        scene,
        "retire une plateforme",
        _patch("/tower/characteristics/platform_count", 2),
    )
    with pytest.raises(ValueError, match="numeric value is not grounded"):
        _validate_patch_alignment(
            scene,
            "retire une plateforme",
            _patch("/tower/characteristics/platform_count", 0),
        )


def test_absolute_plural_platform_count_is_grounded() -> None:
    _validate_patch_alignment(
        _scene(platforms=1),
        "mets deux plateformes",
        _patch("/tower/characteristics/platform_count", 2),
    )


def test_article_does_not_ground_an_unrequested_count_field() -> None:
    with pytest.raises(ValueError, match="not grounded"):
        _validate_patch_alignment(
            _scene(),
            "ajoute une couleur rouge au pylône",
            _patch("/tower/characteristics/platform_count", 1),
        )


def test_named_paint_colour_must_match_the_prompt() -> None:
    scene = _scene()
    _validate_patch_alignment(
        scene,
        "peins le pylône en rouge",
        _patch("/tower/characteristics/paint_color_hex", "#c62828"),
    )
    with pytest.raises(ValueError, match="colour value is not grounded"):
        _validate_patch_alignment(
            scene,
            "peins le pylône en rouge",
            _patch("/tower/characteristics/paint_color_hex", "#1e5aa8"),
        )


def test_units_cannot_cross_from_length_to_angle() -> None:
    with pytest.raises(ValueError, match="numeric value is not grounded"):
        _validate_patch_alignment(
            _scene(),
            "oriente le secteur 1 à 40 cm",
            _patch("/sectors/0/azimuth_deg", 40),
        )


def test_single_letter_axis_terms_match_whole_words() -> None:
    with pytest.raises(ValueError, match="not grounded"):
        _validate_patch_alignment(
            _scene(accessory=True),
            "agrandis le pylône de 2 mètres",
            _patch("/accessory_assets/0/position", [0.0, 2.0, 0.0]),
        )


def test_vector_edit_cannot_mutate_an_unrequested_axis() -> None:
    with pytest.raises(ValueError, match="vector value is not grounded"):
        _validate_patch_alignment(
            _scene(accessory=True),
            "mets la position x de l'armoire à 1 m",
            _patch("/accessory_assets/0/position", [1.0, 1.0, 0.0]),
        )


def test_tower_absolute_height_phrase_remains_supported() -> None:
    _validate_patch_alignment(
        _scene(),
        "mets la tour à 40 m",
        _patch("/tower/height_m", 40),
    )


@pytest.mark.parametrize(
    "alias",
    ("boîte alimentation", "boitier alimentation", "coffret alimentation"),
)
def test_fallback_adds_compound_power_cabinet_aliases(alias: str) -> None:
    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        _scene(),
        f"ajoute la {alias}",
    )

    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/visual_elements/include_power_cabinet", True)
    ]


@pytest.mark.parametrize(
    "alias",
    ("boite alimentation", "boîtier alimentation", "coffret alimentation"),
)
def test_fallback_removes_compound_power_cabinet_aliases(alias: str) -> None:
    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        _scene(),
        f"retire le {alias}",
    )

    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/visual_elements/include_power_cabinet", False)
    ]


def test_fallback_matches_exact_power_box_removal_command() -> None:
    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        _scene(),
        "supprime boite alimentation",
    )

    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/visual_elements/include_power_cabinet", False)
    ]


def test_plain_box_does_not_authorize_power_cabinet_mutation() -> None:
    with pytest.raises(ValueError, match="could not interpret prompt"):
        SceneEditAgent(groq_client=None).create_patch(
            "grounding_regression",
            _scene(),
            "supprime la boîte",
        )


def test_fallback_supports_plural_arrow_and_label_removal() -> None:
    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        _scene(),
        "supprime les flèches et les étiquettes",
    )

    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/visual_elements/include_azimuth_arrows", False),
        ("/visual_elements/include_labels", False),
    ]


def test_fallback_supports_incline_antenna_phrase() -> None:
    scene = _scene()
    sector_2 = scene.sectors[0].model_copy(update={"sector_id": "S2", "azimuth_deg": 120.0})
    scene = scene.model_copy(update={"sectors": [scene.sectors[0], sector_2]})

    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        scene,
        "incline l’antenne du secteur 2 de 6 degrés",
    )

    assert [(operation.path, operation.value) for operation in patch.operations] == [
        ("/sectors/1/mechanical_tilt_deg", 6.0)
    ]


def test_fallback_supports_shorten_tower_phrase() -> None:
    patch = SceneEditAgent(groq_client=None).create_patch(
        "grounding_regression",
        _scene(),
        "raccourcis pylône à 24 m",
    )

    assert ("/tower/height_m", 24.0) in [
        (operation.path, operation.value) for operation in patch.operations
    ]
