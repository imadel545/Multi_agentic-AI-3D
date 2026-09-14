"""Deterministic accessory placement derived from declared scene dimensions."""

from __future__ import annotations

GPS_TOWER_CLEARANCE_M = 0.1
GPS_TOP_OFFSET_M = 0.5


def default_gps_position(
    *,
    tower_height_m: float,
    tower_base_width_m: float,
    tower_top_width_m: float,
    gps_depth_m: float,
) -> list[float]:
    """Place the GPS radome outside the tower envelope with a fixed clearance.

    The position is the accessory's base-centre datum.  The radial offset must
    therefore include half of the declared GPS depth; applying clearance to
    the centre alone lets the radome penetrate the tower.
    """

    if min(tower_height_m, tower_base_width_m, tower_top_width_m, gps_depth_m) <= 0:
        raise ValueError("GPS placement dimensions must be positive")
    gps_height = max(0.5, float(tower_height_m) - GPS_TOP_OFFSET_M)
    height_ratio = min(max(gps_height / float(tower_height_m), 0.0), 1.0)
    tower_width = (
        float(tower_base_width_m)
        + (float(tower_top_width_m) - float(tower_base_width_m)) * height_ratio
    )
    radial_offset = tower_width / 2 + float(gps_depth_m) / 2 + GPS_TOWER_CLEARANCE_M
    return [0.0, radial_offset, gps_height]
