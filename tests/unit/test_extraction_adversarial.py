import pytest

from core.services.requirement_parser import parse_requirements_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
            "Azimuts : 0°, 120°, 240°.",
            {"network_type": "5G", "tower_type": "lattice_tower", "azimuths_deg": [0, 120, 240]},
        ),
        (
            "Create a 5G small-cell pole 10m with one sector at 8m. Azimuths: 90°.",
            {"network_type": "5G", "tower_type": "small_cell_pole", "azimuths_deg": [90]},
        ),
        (
            "Create 5G lattice tower 30m with three sectors.",
            {"network_type": "5G", "tower_type": "lattice_tower", "azimuths_deg": [0, 120, 240]},
        ),
        (
            "Créer un site MW microwave dish sur pylône treillis 30m avec 2 secteurs à 22m. "
            "Azimuths: 80/260.",
            {"network_type": "MW", "tower_type": "lattice_tower", "azimuths_deg": [80, 260]},
        ),
    ],
)
def test_deterministic_extraction_adversarial_inputs(text: str, expected: dict) -> None:
    spec = parse_requirements_text(text, detail_level="high")

    assert spec.network_type == expected["network_type"]
    assert spec.tower_type == expected["tower_type"]
    assert spec.azimuths_deg == expected["azimuths_deg"]


def test_incoherent_antenna_height_is_repaired() -> None:
    spec = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 20m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°.",
        detail_level="high",
    )

    assert spec.antenna_install_height_m == 17
    assert spec.repair_events[0].warning_code == "SCENE_SPEC_REPAIRED_ANTENNA_HEIGHT"
