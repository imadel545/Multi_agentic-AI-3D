import pytest

from apps.blender_worker.generate_scene import (
    _governed_eevee_render_samples,
    _select_render_engine,
)


def test_render_engine_defaults_to_eevee_when_available() -> None:
    assert (
        _select_render_engine({"BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT"}, None)
        == "BLENDER_EEVEE_NEXT"
    )


def test_render_engine_allows_governed_headless_override() -> None:
    assert (
        _select_render_engine(
            {"BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT"},
            "BLENDER_WORKBENCH",
        )
        == "BLENDER_WORKBENCH"
    )


@pytest.mark.parametrize("requested", ["CYCLES", "", "BLENDER_EEVEE"])
def test_render_engine_rejects_invalid_or_unavailable_override(requested: str) -> None:
    available = {"BLENDER_WORKBENCH"}
    if not requested:
        assert _select_render_engine(available, requested) == "BLENDER_WORKBENCH"
        return
    with pytest.raises(RuntimeError):
        _select_render_engine(available, requested)


@pytest.mark.parametrize("raw_value, expected", [(None, None), ("", None), ("8", 8), ("64", 64)])
def test_governed_eevee_render_samples(raw_value: str | None, expected: int | None) -> None:
    assert _governed_eevee_render_samples(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["0", "65", "fast"])
def test_governed_eevee_render_samples_reject_invalid_values(raw_value: str) -> None:
    with pytest.raises(RuntimeError):
        _governed_eevee_render_samples(raw_value)
