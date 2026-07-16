import math

import pytest

from apps.blender_worker.parametric_builder import (
    sector_forward_vector,
    tower_envelope_radius_at_height,
    tower_material_profile,
)


@pytest.mark.parametrize(
    ("azimuth_deg", "expected_xy"),
    [(0.0, (0.0, 1.0)), (120.0, (math.sqrt(3) / 2, -0.5)), (240.0, (-math.sqrt(3) / 2, -0.5))],
)
def test_sector_forward_vector_uses_telecom_azimuth_and_local_downtilt(
    azimuth_deg: float,
    expected_xy: tuple[float, float],
) -> None:
    direction = sector_forward_vector(azimuth_deg, 3.0)

    assert direction[0] == pytest.approx(expected_xy[0] * math.cos(math.radians(3.0)))
    assert direction[1] == pytest.approx(expected_xy[1] * math.cos(math.radians(3.0)))
    assert direction[2] == pytest.approx(-math.sin(math.radians(3.0)))


def test_tower_envelope_uses_taper_and_square_lattice_direction() -> None:
    cardinal = tower_envelope_radius_at_height(
        height_m=24.0,
        tower_height_m=30.0,
        base_width_m=4.0,
        top_width_m=1.0,
        structure="lattice",
        leg_count=4,
        azimuth_rad=0.0,
    )
    diagonal = tower_envelope_radius_at_height(
        height_m=24.0,
        tower_height_m=30.0,
        base_width_m=4.0,
        top_width_m=1.0,
        structure="lattice",
        leg_count=4,
        azimuth_rad=math.radians(45.0),
    )

    assert cardinal == pytest.approx(0.8)
    assert diagonal == pytest.approx(0.8 * math.sqrt(2))


def test_tower_material_profiles_are_physically_distinct() -> None:
    galvanized = tower_material_profile("galvanized_steel")
    painted = tower_material_profile("painted_steel")
    concrete = tower_material_profile("concrete")

    assert galvanized != painted
    assert concrete[2] == 0.0
    assert concrete[1] > galvanized[1]
