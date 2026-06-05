from copy import deepcopy

from core.contracts.repair import RepairEvent, RepairReport

ANTENNA_HEIGHT_SAFETY_MARGIN_M = 3.0


def repair_requirement_candidate(candidate: dict, attempt: int = 1) -> tuple[dict, RepairReport]:
    repaired = deepcopy(candidate)
    events: list[RepairEvent] = []
    _repair_antenna_height(repaired, events, attempt)
    _repair_azimuths(repaired, events, attempt)
    _repair_sector_count(repaired, events, attempt)
    return repaired, RepairReport(status="repaired" if events else "not_needed", events=events)


def _repair_antenna_height(candidate: dict, events: list[RepairEvent], attempt: int) -> None:
    tower_height = float(candidate.get("tower_height_m") or 0)
    install_height = float(candidate.get("antenna_install_height_m") or 0)
    if tower_height <= 0 or install_height <= tower_height:
        return
    safe_height = max(1.0, tower_height - ANTENNA_HEIGHT_SAFETY_MARGIN_M)
    candidate["antenna_install_height_m"] = safe_height
    events.append(
        RepairEvent(
            attempt=attempt,
            handler="scene_repair_handler",
            reason="antenna_height_above_tower",
            before={"antenna_install_height_m": install_height},
            after={"antenna_install_height_m": safe_height},
            warning_code="SCENE_SPEC_REPAIRED_ANTENNA_HEIGHT",
            success=True,
        )
    )


def _repair_azimuths(candidate: dict, events: list[RepairEvent], attempt: int) -> None:
    azimuths = candidate.get("azimuths_deg")
    if not isinstance(azimuths, list):
        return
    normalized = []
    changed = False
    for azimuth in azimuths:
        value = float(azimuth)
        normal = value % 360
        normalized.append(normal)
        changed = changed or normal != value
    if not changed:
        return
    candidate["azimuths_deg"] = normalized
    events.append(
        RepairEvent(
            attempt=attempt,
            handler="scene_repair_handler",
            reason="azimuth_out_of_range",
            before={"azimuths_deg": azimuths},
            after={"azimuths_deg": normalized},
            warning_code="SCENE_SPEC_REPAIRED_AZIMUTH_NORMALIZED",
            success=True,
        )
    )


def _repair_sector_count(candidate: dict, events: list[RepairEvent], attempt: int) -> None:
    sector_count = int(candidate.get("sector_count") or 0)
    azimuths = candidate.get("azimuths_deg")
    if sector_count <= 0 or not isinstance(azimuths, list) or len(azimuths) == sector_count:
        return
    before = {"sector_count": sector_count, "azimuths_deg": list(azimuths)}
    if len(azimuths) < sector_count:
        step = 360 / sector_count
        repaired_azimuths = [round(step * index, 3) for index in range(sector_count)]
        candidate["azimuths_deg"] = repaired_azimuths
        after = {"sector_count": sector_count, "azimuths_deg": repaired_azimuths}
    else:
        candidate["azimuths_deg"] = azimuths[:sector_count]
        after = {"sector_count": sector_count, "azimuths_deg": azimuths[:sector_count]}
    events.append(
        RepairEvent(
            attempt=attempt,
            handler="scene_repair_handler",
            reason="sector_count_azimuth_mismatch",
            before=before,
            after=after,
            warning_code="SCENE_SPEC_REPAIRED_SECTOR_COUNT",
            success=True,
        )
    )
