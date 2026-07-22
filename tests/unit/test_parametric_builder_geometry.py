import math
from types import SimpleNamespace

import pytest

from apps.blender_worker.generate_scene import _compute_scene_bounding_box
from apps.blender_worker.parametric_builder import (
    sector_forward_vector,
    segment_geometry,
    tower_envelope_radius_at_height,
    tower_material_profile,
)


class _Vector:
    def __init__(self, coordinates) -> None:
        self.x, self.y, self.z = coordinates


class _IdentityMatrix:
    def __matmul__(self, vector: _Vector) -> _Vector:
        return vector


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


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ((-2.0, 3.0, 1.0), (4.0, -5.0, 8.0)),
    ],
)
def test_segment_geometry_reconstructs_requested_endpoints(start, end) -> None:
    geometry = segment_geometry(start, end)

    assert geometry is not None
    half = geometry.length / 2
    reconstructed_start = tuple(
        geometry.midpoint[index] - geometry.direction[index] * half for index in range(3)
    )
    reconstructed_end = tuple(
        geometry.midpoint[index] + geometry.direction[index] * half for index in range(3)
    )
    assert reconstructed_start == pytest.approx(start)
    assert reconstructed_end == pytest.approx(end)


def test_segment_geometry_rejects_zero_length() -> None:
    assert segment_geometry((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) is None


def test_scene_bounding_box_metadata_exposes_extents_and_dimensions() -> None:
    mesh = SimpleNamespace(
        type="MESH",
        data=SimpleNamespace(vertices=[object()]),
        bound_box=[(-2.0, -1.5, 0.0), (3.0, 2.5, 30.0)],
        matrix_world=_IdentityMatrix(),
        location=_Vector((0.0, 0.0, 0.0)),
    )
    bpy = SimpleNamespace(
        context=SimpleNamespace(scene=SimpleNamespace(objects=[mesh])),
    )

    bounding_box = _compute_scene_bounding_box(bpy)

    assert bounding_box["width"] == pytest.approx(5.0)
    assert bounding_box["depth"] == pytest.approx(4.0)
    assert bounding_box["height"] == pytest.approx(30.0)
