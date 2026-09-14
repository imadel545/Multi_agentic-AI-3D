import math

import pytest

from apps.blender_worker.generate_scene import _platform_support_segments
from core.qa.tower_access_inspector import _gltf_to_scene_point, _support_geometry_measurement
from core.services.accessory_placement import GPS_TOWER_CLEARANCE_M, default_gps_position


def _tower_scene() -> dict:
    return {
        "tower": {
            "height_m": 24.0,
            "characteristics": {
                "structure": "lattice",
                "leg_count": 4,
                "base_width_m": 4.0,
                "top_width_m": 1.0,
            },
        }
    }


def test_default_gps_position_clears_tower_by_radome_half_depth() -> None:
    position = default_gps_position(
        tower_height_m=24.0,
        tower_base_width_m=4.0,
        tower_top_width_m=1.0,
        gps_depth_m=0.32,
    )
    tower_width = 4.0 + (1.0 - 4.0) * (position[2] / 24.0)
    observed_clearance = position[1] - 0.32 / 2 - tower_width / 2

    assert position == pytest.approx([0.0, 0.79125, 23.5])
    assert observed_clearance == pytest.approx(GPS_TOWER_CLEARANCE_M)


def test_tower_access_glb_points_restore_blender_axis_sign() -> None:
    assert _gltf_to_scene_point((1.0, 3.0, -2.0)) == (1.0, 2.0, 3.0)


def test_platform_supports_run_from_tower_legs_to_deck_underside() -> None:
    face = math.pi
    segments = _platform_support_segments(
        _tower_scene(),
        face=face,
        level=13.2,
        width=2.2,
        thickness=0.08,
        support_radius=0.025,
        support_offset=0.66,
        support_drop=0.75,
        deck_center_radius=2.475,
    )

    assert len(segments) == 2
    for start, end in segments:
        start_radial = start[0] * math.sin(face) + start[1] * math.cos(face)
        end_radial = end[0] * math.sin(face) + end[1] * math.cos(face)
        assert end_radial - start_radial > 2.2 * 0.3
        assert end[2] - start[2] > 2.2 * 0.15
        assert end[2] == pytest.approx(13.2 - 0.08 - 0.025)


def test_platform_supports_reject_a_declared_drop_below_ground() -> None:
    with pytest.raises(RuntimeError, match="TOWER_ACCESS_PLATFORM_SUPPORT_BELOW_GROUND"):
        _platform_support_segments(
            _tower_scene(),
            face=math.pi,
            level=0.5,
            width=2.2,
            thickness=0.08,
            support_radius=0.025,
            support_offset=0.66,
            support_drop=0.75,
            deck_center_radius=2.475,
        )


def test_support_measurement_rejects_short_rods_hidden_inside_deck() -> None:
    face = math.pi

    def point(radial: float, tangential: float, z: float) -> tuple[float, float, float]:
        return (
            math.sin(face) * radial + math.cos(face) * tangential,
            math.cos(face) * radial - math.sin(face) * tangential,
            z,
        )

    profile = {
        "access_face_azimuth_deg": 180.0,
        "platform_tower_clearance_m": 0.2,
        "platform_depth_m": 2.2,
        "platform_thickness_m": 0.08,
    }
    deck = {
        "points": [
            point(radial, tangential, z)
            for radial in (1.375, 3.575)
            for tangential in (-1.1, 1.1)
            for z in (13.12, 13.2)
        ]
    }
    hidden = [
        {"points": [point(1.195, tangent, 13.16), point(1.375, tangent, 13.16)]}
        for tangent in (-0.66, 0.66)
    ]
    tower_count, deck_count, radial_span, vertical_drop = _support_geometry_measurement(
        hidden,
        deck,
        profile,
        13.2,
    )

    assert tower_count == 2
    assert deck_count == 0
    assert radial_span == pytest.approx(0.18)
    assert vertical_drop == pytest.approx(0.0)

    visible = [
        {"points": list(segment)}
        for segment in _platform_support_segments(
            _tower_scene(),
            face=face,
            level=13.2,
            width=2.2,
            thickness=0.08,
            support_radius=0.025,
            support_offset=0.66,
            support_drop=0.75,
            deck_center_radius=2.475,
        )
    ]
    tower_count, deck_count, radial_span, vertical_drop = _support_geometry_measurement(
        visible,
        deck,
        profile,
        13.2,
    )
    assert tower_count == 2
    assert deck_count == 2
    assert radial_span is not None and radial_span >= 2.2 * 0.3
    assert vertical_drop is not None and vertical_drop >= 2.2 * 0.15
