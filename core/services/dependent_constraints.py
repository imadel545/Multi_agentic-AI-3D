"""Deterministic propagation of dependent scene constraints after a user edit.

A user who says "lower the tower to 20 m" expects the equipment mounted on that
tower to follow it. The bounded LLM plan is only allowed to emit operations that
are grounded in the prompt, so the dependent placements are derived here,
deterministically, and reported back as explicit assumptions. Nothing is
silently dropped: when a dependency cannot be resolved inside the declared
capabilities the edit fails with a reason the user can act on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch

TOWER_HEIGHT_PATH = "/tower/height_m"
MIN_INSTALL_HEIGHT_M = 1.0


@dataclass(frozen=True)
class DerivedAdaptation:
    operations: list[PatchOperation] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def _format_m(value: float) -> str:
    return f"{value:g} m"


def derive_dependent_operations(
    scene: SceneSpec,
    patch: ScenePatch,
    *,
    allowed_paths: set[str] | None = None,
) -> DerivedAdaptation:
    """Return the follow-up operations a patch implies on the current scene."""

    tower_ops = [op for op in patch.operations if op.path == TOWER_HEIGHT_PATH]
    if not tower_ops or scene.tower is None:
        return DerivedAdaptation()
    raw_height = tower_ops[-1].value
    if isinstance(raw_height, bool) or not isinstance(raw_height, int | float):
        return DerivedAdaptation()
    new_height = float(raw_height)
    old_height = float(scene.tower.height_m)
    if new_height >= old_height:
        return DerivedAdaptation()

    explicit_sector_paths = {op.path for op in patch.operations}
    operations: list[PatchOperation] = []
    moved: list[tuple[str, float, float]] = []
    for index, sector in enumerate(scene.sectors):
        path = f"/sectors/{index}/install_height_m"
        if path in explicit_sector_paths:
            continue
        if sector.install_height_m <= new_height:
            continue
        if allowed_paths is not None and path not in allowed_paths:
            raise ValueError(
                f"{sector.sector_id} install_height_m exceeds tower height "
                f"({sector.install_height_m:g} > {new_height:g}) and cannot be adapted"
            )
        top_offset = max(old_height - float(sector.install_height_m), 0.0)
        derived = round(max(new_height - top_offset, MIN_INSTALL_HEIGHT_M), 2)
        derived = min(derived, new_height)
        operations.append(PatchOperation(op="replace", path=path, value=derived))
        moved.append((sector.sector_id, float(sector.install_height_m), derived))
    assumptions: list[str] = []
    if moved:
        by_change: dict[tuple[float, float], list[str]] = {}
        for sector_id, before, after in moved:
            by_change.setdefault((before, after), []).append(sector_id)
        for (before, after), sector_ids in by_change.items():
            label = (
                f"du secteur {sector_ids[0]}"
                if len(sector_ids) == 1
                else f"des secteurs {', '.join(sector_ids[:-1])} et {sector_ids[-1]}"
            )
            assumptions.append(
                f"Antennes {label} ramenées de {_format_m(before)} à {_format_m(after)} "
                f"pour rester {_format_m(round(new_height - after, 2))} sous le sommet "
                f"du pylône ({_format_m(new_height)})."
            )
    return DerivedAdaptation(operations=operations, assumptions=assumptions)


def with_dependent_operations(
    scene: SceneSpec,
    patch: ScenePatch,
    *,
    allowed_paths: set[str] | None = None,
) -> ScenePatch:
    derived = derive_dependent_operations(scene, patch, allowed_paths=allowed_paths)
    if not derived.operations:
        return patch
    return patch.model_copy(
        update={
            "operations": [*patch.operations, *derived.operations],
            "assumptions": [*patch.assumptions, *derived.assumptions],
            "derived_assumptions": [*patch.derived_assumptions, *derived.assumptions],
        }
    )


_PYDANTIC_NOISE = re.compile(r"\s*\[type=.*", re.DOTALL)
_EXCEEDS = re.compile(
    r"(?P<sector>\S+) install_height_m exceeds tower height "
    r"\((?P<install>[\d.]+) > (?P<tower>[\d.]+)\)"
)


def edit_failure_user_text(message: str) -> str:
    """Translate an internal edit failure into a sentence a designer can act on."""

    cleaned = _PYDANTIC_NOISE.sub("", message or "").strip()
    cleaned = re.sub(r"^.*?Value error, ", "", cleaned, flags=re.DOTALL).strip()
    exceeds = _EXCEEDS.search(cleaned)
    if exceeds:
        install = float(exceeds.group("install"))
        tower = float(exceeds.group("tower"))
        return (
            f"les antennes du secteur {exceeds.group('sector')} sont installées à "
            f"{install:g} m, au-dessus de la hauteur de pylône demandée ({tower:g} m). "
            "Indiquez aussi la nouvelle hauteur des antennes."
        )
    lowered = cleaned.lower()
    if "not grounded in the edit prompt" in lowered or "not grounded in the prompt" in lowered:
        return (
            "je n’ai pas trouvé dans votre message la valeur à appliquer. Précisez "
            "l’élément visé et la nouvelle valeur (par exemple « antennes du secteur 2 à 24 m »)."
        )
    if "unrequested sector" in lowered:
        return "la modification visait un secteur non mentionné ; précisez le secteur."
    if "undeclared capability" in lowered or "unknown adaptation capability" in lowered:
        return (
            "cette modification n’est pas prise en charge sur ce design. Les éléments "
            "modifiables sont la structure du pylône, les hauteurs, azimuts et tilts des "
            "antennes, les radios et la position des accessoires."
        )
    if "dépasse les capacités du composant sélectionné" in lowered:
        return "la demande dépasse ce que le composant sélectionné permet de modifier."
    if not cleaned:
        return "la demande n’a pas pu être interprétée."
    return cleaned[0].lower() + cleaned[1:] if len(cleaned) > 1 else cleaned
