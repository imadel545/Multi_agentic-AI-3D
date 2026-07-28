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
        "Créer un site 5G sur pylône treillis 20m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°.",
        detail_level="high",
    )

    assert spec.antenna_install_height_m == 17
    assert spec.repair_events[0].warning_code == "SCENE_SPEC_REPAIRED_ANTENNA_HEIGHT"
    assert spec.requires_confirmation is True
    assert "antenna_install_height_m" in spec.confirmation_fields


@pytest.mark.parametrize(
    "text",
    [
        (
            "Créer un pylône treillis de 37 m avec quatre secteurs à 31 m. "
            "Azimuts 0°, 90°, 180° et 270°."
        ),
        (
            "Créer un pylône treillis de 37 m avec quatre secteurs à 31 m. "
            "Azimuts 0°, 90°, 180°, 270°."
        ),
        ("Create a 37 m lattice tower with four sectors at 31 m. Azimuths 0, 90, 180 and 270."),
    ],
)
def test_multilingual_lists_preserve_four_sector_intent(text: str) -> None:
    spec = parse_requirements_text(text, detail_level="high")

    assert spec.tower_height_m == 37
    assert spec.sector_count == 4
    assert spec.antenna_install_height_m == 31
    assert spec.azimuths_deg == [0, 90, 180, 270]
    assert spec.requires_confirmation is False
    assert spec.field_evidence["sector_count"].selected_source == "user_text"


def test_unresolved_contradiction_is_visible_and_blocks_confirmation() -> None:
    spec = parse_requirements_text(
        "Créer un pylône de 30 m puis un pylône de 42 m avec 3 secteurs. Azimuts 0, 120, 240."
    )

    assert spec.tower_height_m == 30
    assert spec.requires_confirmation is True
    assert spec.confirmation_fields == ["tower_height_m"]
    assert spec.conflicts[0].resolved is False
    assert len(spec.field_evidence["tower_height_m"].candidates) == 2


def test_explicit_late_correction_wins_but_keeps_audit_trail() -> None:
    spec = parse_requirements_text(
        "Créer un pylône de 30 m avec 3 secteurs. Azimuts 0, 120, 240. "
        "Correction finale: hauteur pylône 42 m, quatre secteurs. "
        "Azimuts 0, 90, 180, 270."
    )

    assert spec.tower_height_m == 42
    assert spec.sector_count == 4
    assert spec.azimuths_deg == [0, 90, 180, 270]
    assert spec.requires_confirmation is False
    assert spec.conflicts
    assert all(conflict.resolved for conflict in spec.conflicts)


def test_antenna_height_correction_does_not_mutate_tower_height() -> None:
    spec = parse_requirements_text(
        "Créer un pylône de 30 m avec trois secteurs, antennes à 25 m. "
        "Correction finale: HBA 27 m. Azimuts 0, 120 et 240."
    )

    assert spec.tower_height_m == 30
    assert spec.antenna_install_height_m == 27
    assert spec.requires_confirmation is False
    assert spec.field_evidence["antenna_install_height_m"].selected_value == 27


def test_absent_values_are_typed_assumptions_not_hidden_facts() -> None:
    spec = parse_requirements_text("Créer un site télécom standard.")

    assert spec.requires_confirmation is False
    assert spec.field_evidence["tower_height_m"].defaulted is True
    assert spec.field_evidence["tower_height_m"].selected_source == "default"
    assert spec.assumptions
