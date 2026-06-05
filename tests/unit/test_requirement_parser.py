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
