"""Coherent platform state for bounded tower access edits.

Platform levels are design intent, but the public adaptation capability only
exposes the platform presence and count.  When one of those declared fields is
edited, this module preserves explicit levels where possible and uses the
tower's declared access profile for any new placement that must be derived.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.tower import TowerAccessGeometryProfile

PLATFORM_PRESENCE_PATH = "/tower/characteristics/has_platform"
PLATFORM_COUNT_PATH = "/tower/characteristics/platform_count"
_PLATFORM_EDIT_PATHS = {PLATFORM_PRESENCE_PATH, PLATFORM_COUNT_PATH}


@dataclass(frozen=True)
class PlatformEditResolution:
    has_platform: bool
    platform_count: int
    platform_levels_m: tuple[float, ...]
    assumptions: tuple[str, ...] = ()


def resolve_platform_edit(
    scene: SceneSpec,
    patch: ScenePatch,
) -> PlatformEditResolution | None:
    """Resolve an explicit platform toggle/count edit into a valid target state.

    ``None`` means the patch did not explicitly edit either supported platform
    field.  In particular, merely editing tower height or carrying an access
    profile never rewrites explicit platform levels.
    """

    if scene.tower is None:
        return None
    relevant = [
        operation for operation in patch.operations if operation.path in _PLATFORM_EDIT_PATHS
    ]
    if not relevant:
        return None
    for operation in relevant:
        if operation.op not in {"replace", "add"}:
            raise ValueError("platform presence and count edits must provide replacement values")

    presence_op = _last_operation(relevant, PLATFORM_PRESENCE_PATH)
    count_op = _last_operation(relevant, PLATFORM_COUNT_PATH)
    requested_presence = _presence_value(presence_op) if presence_op is not None else None
    requested_count = _count_value(count_op) if count_op is not None else None
    if (
        requested_presence is not None
        and requested_count is not None
        and requested_presence != (requested_count > 0)
    ):
        raise ValueError("platform presence contradicts the requested platform count")

    current = scene.tower.characteristics
    if requested_count is not None:
        target_count = requested_count
        target_presence = target_count > 0
    elif requested_presence is False:
        target_count = 0
        target_presence = False
    elif requested_presence is True:
        target_count = max(current.platform_count, 1)
        target_presence = True
    else:  # pragma: no cover - one relevant operation always supplies a value
        return None

    existing_levels = tuple(float(level) for level in current.platform_levels_m)
    if not target_presence:
        assumptions = ()
        if current.has_platform or current.platform_count or existing_levels:
            assumptions = (
                "Plateformes désactivées : les niveaux explicites et le compteur "
                "ont été retirés ensemble.",
            )
        return PlatformEditResolution(False, 0, (), assumptions)

    if target_count == current.platform_count:
        return PlatformEditResolution(True, target_count, existing_levels)

    if target_count < len(existing_levels):
        # Keep the highest levels: these are normally the service platforms
        # nearest the mounted equipment and make an add/remove round trip stable.
        retained = tuple(sorted(existing_levels)[-target_count:])
        return PlatformEditResolution(
            True,
            target_count,
            retained,
            (
                f"Plateformes ramenées de {current.platform_count} à {target_count} : "
                f"{_retained_levels_text(retained, upper=True)}",
            ),
        )

    profile = scene.tower.tower_access_geometry_profile
    if profile is None:
        if existing_levels:
            raise ValueError(
                "additional platform levels require a declared tower access geometry profile"
            )
        # A legacy count-only scene has no explicit levels to reconcile.  Keep
        # that representation rather than inventing an undeclared policy.
        return PlatformEditResolution(
            True,
            target_count,
            (),
            (
                f"Compteur de plateformes porté de {current.platform_count} à {target_count} ; "
                "aucun niveau explicite n’était déclaré dans ce design.",
            ),
        )

    levels = list(existing_levels)
    derived: list[float] = []
    for candidate in _profile_levels(scene.tower.height_m, target_count, profile):
        if any(abs(candidate - level) <= 1e-6 for level in levels):
            continue
        levels.append(candidate)
        derived.append(candidate)
        if len(levels) == target_count:
            break
    if len(levels) != target_count:
        raise ValueError(
            "declared tower access geometry profile cannot place unique platform levels"
        )

    details: list[str] = []
    if existing_levels:
        details.append(_retained_levels_text(existing_levels))
    if derived:
        noun = "niveau ajouté" if len(derived) == 1 else "niveaux ajoutés"
        details.append(f"{noun} à {_format_levels(derived)} selon les règles d’accès du pylône")
    assumptions = (
        f"Plateformes portées de {current.platform_count} à {target_count} : {'; '.join(details)}.",
    )
    return PlatformEditResolution(True, target_count, tuple(sorted(levels)), assumptions)


def apply_platform_edit_resolution(
    data: dict[str, object],
    resolution: PlatformEditResolution | None,
) -> None:
    """Apply a previously validated resolution to SceneSpec JSON data."""

    if resolution is None:
        return
    tower = data.get("tower")
    if not isinstance(tower, dict):
        raise ValueError("platform edit requires a tower")
    characteristics = tower.get("characteristics")
    if not isinstance(characteristics, dict):
        raise ValueError("platform edit requires tower characteristics")
    characteristics["has_platform"] = resolution.has_platform
    characteristics["platform_count"] = resolution.platform_count
    characteristics["platform_levels_m"] = list(resolution.platform_levels_m)


def _last_operation(
    operations: list[PatchOperation],
    path: str,
) -> PatchOperation | None:
    return next((operation for operation in reversed(operations) if operation.path == path), None)


def _presence_value(operation: PatchOperation) -> bool:
    if not isinstance(operation.value, bool):
        raise ValueError("platform presence must be a boolean")
    return operation.value


def _count_value(operation: PatchOperation) -> int:
    if isinstance(operation.value, bool) or not isinstance(operation.value, int):
        raise ValueError("platform count must be an integer")
    if not 0 <= operation.value <= 12:
        raise ValueError("platform count must remain between 0 and 12")
    return operation.value


def _profile_levels(
    height_m: float,
    count: int,
    profile: TowerAccessGeometryProfile,
) -> tuple[float, ...]:
    start = float(profile.legacy_platform_start_height_ratio)
    span = float(profile.legacy_platform_span_height_ratio)
    return tuple(
        round(height_m * (start + span * index / max(count, 1)), 6) for index in range(count)
    )


def _format_levels(levels: tuple[float, ...] | list[float]) -> str:
    labels = [f"{level:g} m" for level in sorted(levels)]
    if len(labels) < 2:
        return labels[0]
    return f"{', '.join(labels[:-1])} et {labels[-1]}"


def _retained_levels_text(levels: tuple[float, ...], *, upper: bool = False) -> str:
    if len(levels) == 1:
        qualifier = " supérieur" if upper else ""
        return f"niveau{qualifier} existant conservé à {_format_levels(levels)}"
    qualifier = " supérieurs" if upper else ""
    return f"niveaux{qualifier} existants conservés à {_format_levels(levels)}"
