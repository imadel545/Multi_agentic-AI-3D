import re

from core.contracts.common import WarningItem
from core.contracts.requirements import RequirementSpec
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
