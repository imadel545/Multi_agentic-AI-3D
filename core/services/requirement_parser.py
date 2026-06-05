import re

from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec
from core.contracts.tower import TowerCharacteristics
from core.repair import repair_requirement_candidate

TOWER_SYNONYMS = {
    "treillis": "lattice_tower",
    "lattice": "lattice_tower",
    "monopole": "monopole",
    "rooftop": "rooftop_mast",
    "toit": "rooftop_mast",
    "small-cell": "small_cell_pole",
    "small cell": "small_cell_pole",
}


def parse_requirements_text(
    requirements_text: str, detail_level: str | None = None
) -> RequirementSpec:
    """Deterministic baseline parser; LLM extraction will replace this behind the same contract."""
    text = requirements_text.lower()
    warnings: list[WarningItem] = []

    network_type = _extract_network_type(text)
    if network_type == "5G" and "5g" not in text and "4g" not in text and "mw" not in text:
        warnings.append(
            WarningItem(code="DEFAULT_NETWORK_USED", message="Network type inferred as 5G.")
        )

    tower_type = next(
        (normalized for token, normalized in TOWER_SYNONYMS.items() if token in text),
        "lattice_tower",
    )
    if not any(token in text for token in TOWER_SYNONYMS):
        warnings.append(
            WarningItem(code="DEFAULT_TOWER_USED", message="Tower type inferred as lattice_tower.")
        )

    tower_height_m = _first_number_before_or_after_meter(text, default=30.0)
    if tower_height_m == 30.0 and not re.search(r"\b30\s*m\b|\b30m\b", text):
        warnings.append(
            WarningItem(code="DEFAULT_TOWER_HEIGHT_USED", message="Tower height inferred as 30m.")
        )
    tower_characteristics = _extract_tower_characteristics(
        text,
        tower_type,
        tower_height_m,
        warnings,
    )

    sector_count = _extract_sector_count(text)
    if sector_count is None:
        sector_count = 3
        warnings.append(
            WarningItem(code="DEFAULT_SECTOR_COUNT_USED", message="Sector count inferred as 3.")
        )

    install_height = _extract_install_height(text, default=min(24.0, tower_height_m))
    if (
        install_height == min(24.0, tower_height_m)
        and "secteur" not in text
        and "antenne" not in text
    ):
        warnings.append(
            WarningItem(
                code="DEFAULT_INSTALL_HEIGHT_USED",
                message=f"Antenna install height inferred as {install_height}m.",
            )
        )

    azimuths = _extract_azimuths(text)
    if not azimuths:
        step = 360 / sector_count
        azimuths = [round(step * index, 3) for index in range(sector_count)]
        warnings.append(
            WarningItem(
                code="DEFAULT_AZIMUTHS_USED",
                message=f"Azimuths inferred as {azimuths}.",
            )
        )

    antenna_type = _extract_antenna_type(text, network_type)
    candidate = {
        "network_type": network_type,
        "tower_type": tower_type,
        "tower_height_m": tower_height_m,
        "tower_characteristics": tower_characteristics.model_dump(),
        "sector_count": sector_count,
        "antenna_type": antenna_type,
        "antenna_install_height_m": install_height,
        "azimuths_deg": azimuths,
        "include_rru": network_type != "MW" and not _contains_negation_for(text, ["rru", "radio"]),
        "include_cables": not _contains_negation_for(text, ["cable", "câble"]),
        "include_beams": not _contains_negation_for(text, ["faisceau", "beam"]),
        "include_labels": not _contains_negation_for(text, ["label", "étiquette", "etiquette"]),
        "detail_level": detail_level
        or ("high" if "élevé" in text or "eleve" in text else "medium"),
        "warnings": warnings,
    }
    repaired, repair_report = repair_requirement_candidate(candidate)
    repaired["warnings"] = [
        *warnings,
        *[
            WarningItem(
                code=event.warning_code,
                message=f"{event.reason}: {event.before} -> {event.after}",
            )
            for event in repair_report.events
            if event.success
        ],
    ]
    repaired["repair_events"] = repair_report.events
    return RequirementSpec(**repaired)


def _first_number_before_or_after_meter(text: str, default: float) -> float:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*m\b", text)
    if not match:
        return default
    return float(match.group(1).replace(",", "."))


def _extract_network_type(text: str) -> str:
    if "microwave" in text or "dish" in text or "mw" in text:
        return "MW"
    if "5g" in text:
        return "5G"
    if "4g" in text:
        return "4G"
    return "5G"


def _extract_antenna_type(text: str, network_type: str) -> str:
    if "microwave" in text or "dish" in text or network_type == "MW":
        return "microwave_dish"
    if "mimo" in text:
        return "massive_mimo"
    if network_type == "4G":
        return "panel_4g"
    return "panel_5g"


def _extract_tower_characteristics(
    text: str,
    tower_type: str,
    tower_height_m: float,
    warnings: list[WarningItem],
) -> TowerCharacteristics:
    structure = _tower_structure_for_type(tower_type)
    explicit_values = any(
        token in text
        for token in [
            "jambe",
            "jambes",
            "pied",
            "pieds",
            "legs",
            "base",
            "sommet",
            "tête",
            "tete",
            "top",
            "plateforme",
            "platform",
            "échelle",
            "echelle",
            "ladder",
            "paratonnerre",
            "lightning",
            "balisage",
            "aviation",
            "fondation",
            "massif",
            "béton",
            "beton",
            "galvan",
        ]
    )
    if not explicit_values:
        warnings.append(
            WarningItem(
                code="DEFAULT_TOWER_CHARACTERISTICS_USED",
                message="Tower structural characteristics inferred from tower type and height.",
            )
        )
    has_platform = _contains_any(text, ["plateforme", "platform"])
    platform_count = _extract_count_before_terms(text, ["plateforme", "platform"])
    if has_platform and platform_count is None:
        platform_count = 1
    return TowerCharacteristics(
        structure=structure,
        leg_count=_extract_leg_count(text, structure),
        base_width_m=_extract_named_width(text, ["base"], _default_base_width(tower_type)),
        top_width_m=_extract_named_width(
            text,
            ["sommet", "tête", "tete", "top"],
            _default_top_width(tower_type),
        ),
        foundation_type=_extract_foundation_type(text, tower_type),
        has_platform=has_platform,
        platform_count=platform_count or 0,
        has_ladder=_contains_any(text, ["échelle", "echelle", "ladder"]),
        has_lightning_rod=_contains_any(text, ["paratonnerre", "lightning rod"]),
        has_aviation_light=_contains_any(text, ["balisage", "feu aviation", "aviation light"]),
        material=_extract_tower_material(text),
    )


def _tower_structure_for_type(tower_type: str) -> str:
    return {
        "lattice_tower": "lattice",
        "monopole": "monopole",
        "rooftop_mast": "rooftop_mast",
        "small_cell_pole": "small_cell_pole",
    }.get(tower_type, "lattice")


def _extract_leg_count(text: str, structure: str) -> int:
    match = re.search(r"([1-4])\s*(?:jambes?|pieds?|legs?)\b", text)
    if match:
        return int(match.group(1))
    if structure == "lattice":
        return 4
    return 1


def _extract_named_width(text: str, terms: list[str], default: float) -> float:
    for term in terms:
        match = re.search(
            rf"(?<![a-z])(?:largeur\s+)?{term}\b\s*(?:de|=|:)?\s*(\d+(?:[.,]\d+)?)\s*m\b",
            text,
        )
        if match:
            return float(match.group(1).replace(",", "."))
    return default


def _default_base_width(tower_type: str) -> float:
    return {
        "lattice_tower": 4.0,
        "monopole": 1.2,
        "rooftop_mast": 2.0,
        "small_cell_pole": 0.6,
    }.get(tower_type, 4.0)


def _default_top_width(tower_type: str) -> float:
    return {
        "lattice_tower": 1.0,
        "monopole": 0.5,
        "rooftop_mast": 1.0,
        "small_cell_pole": 0.35,
    }.get(tower_type, 1.0)


def _extract_foundation_type(text: str, tower_type: str) -> str:
    if _contains_any(text, ["rooftop", "toit"]):
        return "rooftop_anchored"
    if _contains_any(text, ["fondation", "massif", "béton", "beton", "concrete pad"]):
        return "concrete_pad"
    if tower_type == "small_cell_pole":
        return "pole_base"
    if tower_type == "rooftop_mast":
        return "rooftop_anchored"
    return "concrete_pad"


def _extract_tower_material(text: str) -> str:
    if _contains_any(text, ["acier peint", "painted steel"]):
        return "painted_steel"
    if _contains_any(
        text,
        [
            "pylône béton",
            "pylone beton",
            "tour béton",
            "tour beton",
            "concrete tower",
            "concrete pole",
        ],
    ):
        return "concrete"
    if _contains_any(text, ["galvanisé", "galvanise", "galvanized", "galvanise"]):
        return "galvanized_steel"
    return "galvanized_steel"


def _extract_count_before_terms(text: str, terms: list[str]) -> int | None:
    for term in terms:
        match = re.search(rf"(\d+)\s*{term}s?\b", text)
        if match:
            return int(match.group(1))
    return None


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _extract_sector_count(text: str) -> int | None:
    match = re.search(r"(\d+)\s+secteurs?", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s+sectors?", text)
    if match:
        return int(match.group(1))
    word_counts = {"one": 1, "two": 2, "three": 3, "four": 4}
    for word, count in word_counts.items():
        if re.search(rf"\b{word}\s+sectors?\b", text):
            return count
    return None


def _extract_install_height(text: str, default: float) -> float:
    matches = [
        float(value.replace(",", ".")) for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*m\b", text)
    ]
    if len(matches) >= 2:
        return matches[1]
    return default


def _extract_azimuths(text: str) -> list[float]:
    azimuth_block = re.search(r"(?:azimuts?|azimuths?)\s*:?\s*([0-9°,\s;/]+)", text)
    if not azimuth_block:
        return []
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", azimuth_block.group(1))]


def _contains_negation_for(text: str, terms: list[str]) -> bool:
    return any(f"sans {term}" in text or f"no {term}" in text for term in terms)
