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


def test_parser_adds_warnings_for_defaults() -> None:
    spec = parse_requirements_text("Créer un site télécom standard.")

    assert spec.tower_type == "lattice_tower"
    assert spec.sector_count == 3
    assert spec.warnings
