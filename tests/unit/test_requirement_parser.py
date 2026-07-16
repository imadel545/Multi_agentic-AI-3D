from core.services.requirement_parser import parse_requirements_text


def test_parse_sample_5g_lattice_site() -> None:
    spec = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m. Installer 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter une RRU sous chaque antenne."
    )

    assert spec.network_type == "5G"
    assert spec.tower_type == "lattice_tower"
    assert spec.tower_height_m == 30
    assert spec.antenna_install_height_m == 24
    assert spec.sector_count == 3
    assert spec.azimuths_deg == [0, 120, 240]
    assert spec.include_rru is True
    assert spec.tower_characteristics.structure == "lattice"
    assert spec.tower_characteristics.base_width_m == 4.0


def test_tower_height_is_not_confused_with_hba_when_hba_appears_first() -> None:
    spec = parse_requirements_text(
        "Installer 3 secteurs à 24m sur un pylône treillis de 30m. Azimuts : 0°, 120°, 240°."
    )

    assert spec.tower_height_m == 30
    assert spec.antenna_install_height_m == 24
    assert "DEFAULT_TOWER_HEIGHT_USED" not in {warning.code for warning in spec.warnings}


def test_hba_only_does_not_become_an_explicit_tower_height() -> None:
    spec = parse_requirements_text("Installer 3 secteurs à 24m avec azimuts 0, 120 et 240.")

    assert spec.tower_height_m == 30
    assert spec.antenna_install_height_m == 24
    assert "DEFAULT_TOWER_HEIGHT_USED" in {warning.code for warning in spec.warnings}


def test_parse_professional_tower_characteristics() -> None:
    spec = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m, 4 jambes, base 4m, sommet 1m, "
        "fondation béton, 2 plateformes, échelle, paratonnerre et balisage aviation. "
        "Installer 3 secteurs à 24m. Azimuts : 0°, 120°, 240°."
    )

    characteristics = spec.tower_characteristics
    assert characteristics.structure == "lattice"
    assert characteristics.leg_count == 4
    assert characteristics.base_width_m == 4
    assert characteristics.top_width_m == 1
    assert characteristics.foundation_type == "concrete_pad"
    assert characteristics.has_platform is True
    assert characteristics.platform_count == 2
    assert characteristics.has_ladder is True
    assert characteristics.has_lightning_rod is True
    assert characteristics.has_aviation_light is True
    assert characteristics.material == "galvanized_steel"


def test_parser_adds_warnings_for_defaults() -> None:
    spec = parse_requirements_text("Créer un site télécom standard.")

    assert spec.tower_type == "lattice_tower"
    assert spec.sector_count == 3
    assert spec.warnings


def test_parse_power_cabinet_and_concrete_pad_from_prompt() -> None:
    spec = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, boîte alimentation, "
        "dalle béton et labels."
    )

    assert spec.include_power_cabinet is True
    assert spec.include_gps_antenna is False
    assert spec.include_labels is True
    assert spec.tower_characteristics.foundation_type == "concrete_pad"


def test_parser_extracts_rf_controls_and_marks_only_real_defaults() -> None:
    spec = parse_requirements_text(
        "Créer un site 4G sur monopole 42m avec 2 secteurs à 36m. "
        "Azimuts : 45°, 225°. Tilt mécanique 2 degrés, tilt électrique 4 degrés, "
        "beamwidth 90 degrés, sans câbles et sans labels."
    )

    assert spec.network_type == "4G"
    assert spec.mechanical_tilt_deg == 2
    assert spec.electrical_tilt_deg == 4
    assert spec.beamwidth_deg == 90
    assert spec.include_cables is False
    assert spec.include_labels is False
    warning_codes = {warning.code for warning in spec.warnings}
    assert "DEFAULT_INSTALL_HEIGHT_USED" not in warning_codes
    assert "DEFAULT_MECHANICAL_TILT_USED" not in warning_codes
    assert "DEFAULT_ELECTRICAL_TILT_USED" not in warning_codes
    assert "DEFAULT_BEAMWIDTH_USED" not in warning_codes
    assert "DEFAULT_CABLES_USED" not in warning_codes


def test_parser_marks_planning_fields_that_are_inferred() -> None:
    spec = parse_requirements_text("Créer un site 5G sur pylône treillis 30m avec 3 secteurs.")

    warning_codes = {warning.code for warning in spec.warnings}
    assert "DEFAULT_INSTALL_HEIGHT_USED" in warning_codes
    assert "DEFAULT_BEAMWIDTH_USED" in warning_codes
    assert "DEFAULT_CABLES_USED" in warning_codes
    assert "DEFAULT_BEAMS_USED" in warning_codes
