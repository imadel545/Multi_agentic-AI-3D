"""One explicit Blender runtime contract for certifiable local generation."""

from collections.abc import Mapping

QUALIFIED_BLENDER_VERSION = "4.5.12 LTS"
QUALIFIED_BLENDER_VERSION_TUPLE = (4, 5, 12)


def has_qualified_blender_runtime(runtime: object) -> bool:
    """Accept only the Blender release used by the governed product runtime."""

    if not isinstance(runtime, Mapping):
        return False
    version_tuple = runtime.get("version_tuple")
    return (
        runtime.get("version") == QUALIFIED_BLENDER_VERSION
        and isinstance(version_tuple, list)
        and tuple(version_tuple) == QUALIFIED_BLENDER_VERSION_TUPLE
        and runtime.get("background") is True
        and runtime.get("factory_startup") is True
    )


def output_reports_qualified_blender(output: str) -> bool:
    """Check a headless startup transcript without accepting a newer executable.

    A controlled Python marker can precede Blender's own banner on native
    macOS, so the banner is a qualified transcript line rather than always
    the first non-empty line.
    """

    expected = f"Blender {QUALIFIED_BLENDER_VERSION}"
    return any(
        line.strip() == expected or line.strip().startswith(f"{expected} (")
        for line in output.splitlines()
    )
