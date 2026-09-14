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
from core.services.platform_edit_resolution import resolve_platform_edit
from core.validation.scene_validator import parametric_tower_mount_envelope

TOWER_HEIGHT_PATH = "/tower/height_m"


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
    # Mirror the practical mounting envelope enforced by the scene validator for
    # parametric towers: antennas must stay below 98 % of the tower height.
    min_install, max_install = parametric_tower_mount_envelope(new_height)
    max_install = min(max_install, new_height)
    for index, sector in enumerate(scene.sectors):
        path = f"/sectors/{index}/install_height_m"
        if path in explicit_sector_paths:
            continue
        if sector.install_height_m <= max_install:
            continue
        if allowed_paths is not None and path not in allowed_paths:
            raise ValueError(
                f"{sector.sector_id} install_height_m exceeds tower height "
                f"({sector.install_height_m:g} > {new_height:g}) and cannot be adapted"
            )
        top_offset = max(old_height - float(sector.install_height_m), 0.0)
        derived = round(max(new_height - top_offset, min_install), 2)
        derived = min(derived, max_install)
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
    platform_resolution = resolve_platform_edit(scene, patch)
    platform_assumptions = (
        list(platform_resolution.assumptions) if platform_resolution is not None else []
    )
    new_assumptions = list(dict.fromkeys([*derived.assumptions, *platform_assumptions]))
    if not derived.operations and not new_assumptions:
        return patch
    return patch.model_copy(
        update={
            "operations": [*patch.operations, *derived.operations],
            "assumptions": list(dict.fromkeys([*patch.assumptions, *new_assumptions])),
            "derived_assumptions": list(
                dict.fromkeys([*patch.derived_assumptions, *new_assumptions])
            ),
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
    if "fallback patch could not interpret prompt" in lowered:
        return (
            "je n’ai pas compris quelle modification appliquer. Nommez l’élément et la "
            "valeur souhaitée (par exemple « supprime l’armoire », « hauteur du pylône à 36 m » "
            "ou « azimut du secteur 1 à 90 degrés »)."
        )
    if "does not compile blueprint intent" in lowered or "blueprint_not_compiled" in lowered:
        return "la modification n’a pas pu être vérifiée avec les composants du design."
    if "does not preserve requirement" in lowered or "requirement_not_covered" in lowered:
        return (
            "la modification contredit une exigence confirmée du design. Précisez la "
            "nouvelle exigence pour que le design soit mis à jour de façon cohérente."
        )
    if "contradicts the prompt" in lowered:
        return (
            "je n’ai pas su déterminer s’il fallait ajouter ou retirer cet élément ; précisez-le."
        )
    if "platform_count must match len(platform_levels_m)" in lowered:
        return (
            "le nombre de plateformes ne correspond pas aux niveaux indiqués. "
            "Indiquez un niveau pour chaque plateforme."
        )
    if (
        "mount_zones_valid" in lowered
        or "mount zone" in lowered
        or "mounting zone" in lowered
        or "connector_tolerance_exceeded" in lowered
        or "mount-to-support" in lowered
    ):
        return (
            "la position demandée ne respecte pas la zone de montage du composant. "
            "Indiquez une hauteur compatible avec le support."
        )
    if "antenna_install_height_m cannot exceed tower_height_m" in lowered:
        return (
            "la hauteur d’installation des antennes dépasse celle du pylône. "
            "Indiquez une hauteur d’antenne inférieure."
        )
    if not cleaned:
        return "la demande n’a pas pu être interprétée."
    return (
        "une erreur technique a empêché la vérification de cette modification. "
        "Réessayez ou reformulez la demande."
    )
