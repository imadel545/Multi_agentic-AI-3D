"""Bounded conversational edits for compiler-authored exact assets.

An exact asset is an immutable catalog representation.  The only edits this
module can produce are the translation and rotation fields that the resolved
manifest explicitly exposes.  It never edits source meshes, materials or
scale and it refuses an ambiguous component or an axis that was not granted
by the manifest.
"""

from __future__ import annotations

import re
import unicodedata

from core.contracts.adaptation import SceneAdaptationCapabilities
from core.contracts.scene_edit import PatchOperation, ScenePatch

_NUMBER = r"-?\d+(?:[.,]\d+)?"
_AXES = "xyz"
_TRANSFORM_WORDS = (
    "position",
    "positionne",
    "positionner",
    "placement",
    "translation",
    "translate",
    "deplace",
    "déplace",
    "move",
    "place",
)
_ROTATION_WORDS = (
    "rotation",
    "rotate",
    "tourne",
    "orientation",
)


def fallback_rigid_patch(
    edit_prompt: str,
    capabilities: SceneAdaptationCapabilities,
    fallback_reason: str,
) -> ScenePatch | None:
    """Parse one explicit exact-asset pose request into a typed patch.

    The parser is deliberately conservative.  Axis/value pairs are required
    for multi-axis assets, so a phrase such as ``move it 1 m`` cannot silently
    invent a direction.  A single exact asset may be addressed by role alone;
    multiple exact assets require an asset id or a distinctive label token.
    """

    exact = [
        capability
        for capability in capabilities.capabilities
        if capability.execution_tool == "asset_transform"
        and re.fullmatch(
            r"/geometry_programs/\d+/nodes/0/transform/(translation_m|rotation_deg)/[xyz]",
            capability.path,
        )
    ]
    if not exact:
        return None
    prompt = edit_prompt.lower()
    if not any(word in prompt for word in (*_TRANSFORM_WORDS, *_ROTATION_WORDS)):
        return None

    target = _select_target(exact, prompt)
    if target is None:
        return None
    target_asset_id, target_capabilities = target
    operations: list[PatchOperation] = []
    for field, words, unit in (
        ("translation_m", _TRANSFORM_WORDS, "m"),
        ("rotation_deg", _ROTATION_WORDS, "deg"),
    ):
        if not any(word in prompt for word in words):
            continue
        values = _axis_values(
            prompt,
            unit=unit,
            require_explicit_unit=any(word in prompt for word in _TRANSFORM_WORDS)
            and any(word in prompt for word in _ROTATION_WORDS),
        )
        if not values:
            continue
        by_axis = {
            capability.path.rsplit("/", 1)[-1]: capability
            for capability in target_capabilities
            if f"/{field}/" in capability.path
        }
        for axis, value in values.items():
            capability = by_axis.get(axis)
            if capability is None:
                raise ValueError(f"L’axe {axis.upper()} n’est pas autorisé pour cet asset.")
            if capability.minimum is not None and value < capability.minimum:
                raise ValueError(f"La valeur {value:g} est sous la limite de l’axe {axis.upper()}.")
            if capability.maximum is not None and value > capability.maximum:
                raise ValueError(f"La valeur {value:g} dépasse la limite de l’axe {axis.upper()}.")
            operations.append(
                PatchOperation(op="replace", path=capability.path, value=value)
            )

    if not operations:
        return None
    return ScenePatch(
        edit_description=edit_prompt,
        operations=operations,
        adaptation_tools=["asset_transform"],
        edit_llm_provider="deterministic_fallback",
        edit_llm_fallback_used=True,
        edit_llm_fallback_reason=fallback_reason,
        assumptions=[
            f"Pose absolue limitée aux axes déclarés de l’asset {target_asset_id}."
        ],
    )


def _select_target(exact, prompt: str):
    asset_ids = {capability.asset_id for capability in exact if capability.asset_id}
    if len(asset_ids) <= 1:
        return next(iter(asset_ids), None), exact
    normalized_prompt = _normalize(prompt)
    matches = []
    for asset_id in sorted(asset_ids):
        tokens = {
            token
            for token in _normalize(asset_id).split()
            if len(token) >= 4
        }
        labels = {
            token
            for capability in exact
            if capability.asset_id == asset_id
            for token in _normalize(capability.label).split()
            if len(token) >= 4
        }
        if tokens & set(normalized_prompt.split()) or labels & set(normalized_prompt.split()):
            matches.append(asset_id)
    if len(matches) != 1:
        return None
    return matches[0], [capability for capability in exact if capability.asset_id == matches[0]]


def _axis_values(
    prompt: str,
    *,
    unit: str,
    require_explicit_unit: bool = False,
) -> dict[str, float]:
    values: dict[str, float] = {}
    unit_token = r"(?:m|°|deg(?:rees)?|degr[eé]s)"

    def accepts(marker: str | None) -> bool:
        if require_explicit_unit and marker is None:
            return False
        if marker is None:
            return True
        is_distance = marker.lower() == "m"
        return (unit == "m") == is_distance

    # Both ``x = 1.2`` and ``1.2 m sur x`` are common user formulations.
    for match in re.finditer(
        rf"\b([{_AXES}])\s*(?:=|:|à|a|to|at|sur|en|on)?\s*({_NUMBER})"
        rf"\s*(?P<unit>{unit_token})?",
        prompt,
        flags=re.IGNORECASE,
    ):
        if not accepts(match.group("unit")):
            continue
        values[match.group(1).lower()] = float(match.group(2).replace(",", "."))
    for match in re.finditer(
        rf"({_NUMBER})\s*(?P<unit>{unit_token})?\s*"
        rf"(?:sur|along|axis|axe|en|on)\s*([{_AXES}])\b",
        prompt,
        flags=re.IGNORECASE,
    ):
        if not accepts(match.group("unit")):
            continue
        values[match.group(3).lower()] = float(match.group(1).replace(",", "."))
    # A bracketed vector is accepted only when it supplies all three axes.
    for vector in re.finditer(
        rf"\[\s*({_NUMBER})\s*[,;]\s*({_NUMBER})\s*[,;]\s*({_NUMBER})\s*\]"
        rf"\s*(?P<unit>{unit_token})?",
        prompt,
        flags=re.IGNORECASE,
    ):
        if not accepts(vector.group("unit")):
            continue
        values.update(
            {
                axis: float(vector.group(index).replace(",", "."))
                for index, axis in enumerate(_AXES, start=1)
            }
        )
    return values


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
