import json
import logging
import re

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.llm.groq import GroqStructuredClient

logger = logging.getLogger(__name__)


class SceneEditAgent:
    def __init__(self, groq_client: GroqStructuredClient | None = None) -> None:
        self.groq = groq_client

    def create_patch(
        self,
        workflow_id: str,
        scene: SceneSpec,
        edit_prompt: str,
    ) -> ScenePatch:
        fallback_reason = "groq_edit_client_unavailable"
        if self.groq is not None:
            try:
                return self._llm_patch(scene, edit_prompt)
            except Exception as exc:
                fallback_reason = f"groq_edit_failed:{type(exc).__name__}"
                logger.warning(
                    "LLM scene edit failed for workflow %s; falling back to deterministic parser.",
                    workflow_id,
                    exc_info=True,
                )
        return self._fallback_patch(scene, edit_prompt, fallback_reason=fallback_reason)

    def _llm_patch(self, scene: SceneSpec, edit_prompt: str) -> ScenePatch:
        scene_json = json.dumps(scene.model_dump(mode="json"), indent=2, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a telecom scene editing assistant. "
                    "Given a SceneSpec JSON and a user edit prompt (in French or English), "
                    "produce a JSON object containing an array of patch operations. "
                    "Allowed paths: /tower/height_m, /tower/characteristics/*, "
                    "/sectors/*/azimuth_deg, /sectors/*/install_height_m, "
                    "/sectors/*/mechanical_tilt_deg, /sectors/*/electrical_tilt_deg, "
                    "/sectors/*/beamwidth_deg, /sectors/*/include_cable, "
                    "/sectors/*/include_label, /visual_elements/*. "
                    "Operations: replace, add, remove. "
                    "Return ONLY the JSON object with keys: edit_description, operations."
                ),
            },
            {
                "role": "user",
                "content": f"SceneSpec:\n{scene_json}\n\nEdit prompt:\n{edit_prompt}",
            },
        ]
        payload = {
            "model": self.groq.model if self.groq else "openai/gpt-oss-120b",
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        raw = self.groq._post_raw(payload)
        operations = [PatchOperation.model_validate(op) for op in raw.get("operations", [])]
        patch = ScenePatch(
            edit_description=raw.get("edit_description", edit_prompt),
            operations=operations,
            edit_llm_provider="groq",
            edit_llm_fallback_used=False,
        )
        _validate_patch_alignment(scene, edit_prompt, patch)
        return patch

    def _fallback_patch(
        self,
        scene: SceneSpec,
        edit_prompt: str,
        *,
        fallback_reason: str,
    ) -> ScenePatch:
        text = edit_prompt.lower()
        operations: list[PatchOperation] = []

        # Height changes
        height_match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
        if height_match and any(
            k in text for k in ("hauteur", "height", "antenne", "tour", "tower")
        ):
            val = float(height_match.group(1))
            if "tour" in text or "tower" in text:
                operations.append(PatchOperation(op="replace", path="/tower/height_m", value=val))
            elif "antenne" in text or "antenna" in text:
                for idx in range(len(scene.sectors)):
                    operations.append(
                        PatchOperation(
                            op="replace", path=f"/sectors/{idx}/install_height_m", value=val
                        )
                    )

        # Azimuth changes
        azimuth_match = _target_value_match(
            text,
            ("azimut", "azimuth", "orientation", "diriger", "oriente"),
        )
        if azimuth_match and any(
            k in text for k in ("azimut", "azimuth", "orientation", "diriger", "oriente")
        ):
            val = float(azimuth_match.group(1))
            sector_idx = self._extract_sector_index(text)
            if sector_idx is not None and sector_idx < len(scene.sectors):
                operations.append(
                    PatchOperation(
                        op="replace", path=f"/sectors/{sector_idx}/azimuth_deg", value=val
                    )
                )

        # Tilt changes
        tilt_match = _target_value_match(
            text,
            ("tilt", "inclinaison", "mécanique", "mecanique", "électrique", "electrique"),
        )
        if tilt_match and any(
            k in text for k in ("tilt", "inclinaison", "mécanique", "mécanique", "electrique")
        ):
            val = float(tilt_match.group(1))
            sector_idx = self._extract_sector_index(text)
            path = "/sectors/{idx}/mechanical_tilt_deg"
            if "électrique" in text or "electrical" in text:
                path = "/sectors/{idx}/electrical_tilt_deg"
            if sector_idx is not None and sector_idx < len(scene.sectors):
                operations.append(
                    PatchOperation(op="replace", path=path.format(idx=sector_idx), value=val)
                )

        # Visual elements toggles
        if any(k in text for k in ("gps", "gnss")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(op="replace", path="/visual_elements/include_gps_antenna", value=val)
            )
        if any(k in text for k in ("power cabinet", "armoire", "cabinet")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(
                    op="replace", path="/visual_elements/include_power_cabinet", value=val
                )
            )
        if any(k in text for k in ("câble", "cable")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            for idx in range(len(scene.sectors)):
                operations.append(
                    PatchOperation(op="replace", path=f"/sectors/{idx}/include_cable", value=val)
                )
        if any(k in text for k in ("beam", "faisceau")):
            val = not ("supprime" in text or "remove" in text or "enlève" in text)
            operations.append(
                PatchOperation(
                    op="replace", path="/visual_elements/include_sector_beams", value=val
                )
            )

        if not operations:
            raise ValueError(f"Fallback patch could not interpret prompt: {edit_prompt}")

        return ScenePatch(
            edit_description=edit_prompt,
            operations=operations,
            edit_llm_provider="deterministic_fallback",
            edit_llm_fallback_used=True,
            edit_llm_fallback_reason=fallback_reason,
        )

    @staticmethod
    def _extract_sector_index(text: str) -> int | None:
        match = re.search(r"secteur\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        match = re.search(r"sector\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        match = re.search(r"s\s*(\d+)", text)
        if match:
            return int(match.group(1)) - 1
        return None


_PATH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/tower/height_m", ("hauteur", "height", "tour", "tower", "pylône", "pylone")),
    ("/tower/characteristics/structure", ("structure", "treillis", "lattice", "monopole")),
    ("/tower/characteristics/leg_count", ("jambe", "pied", "leg")),
    ("/tower/characteristics/base_width_m", ("largeur", "base", "width")),
    ("/tower/characteristics/top_width_m", ("largeur", "sommet", "top", "width")),
    ("/tower/characteristics/foundation_type", ("fondation", "dalle", "foundation", "base")),
    ("/tower/characteristics/has_platform", ("plateforme", "platform")),
    ("/tower/characteristics/platform_count", ("plateforme", "platform")),
    ("/tower/characteristics/has_ladder", ("échelle", "echelle", "ladder")),
    ("/tower/characteristics/has_lightning_rod", ("paratonnerre", "lightning")),
    ("/tower/characteristics/has_aviation_light", ("balisage", "aviation")),
    (
        "/tower/characteristics/material",
        ("matériau", "materiau", "material", "acier", "béton", "beton"),
    ),
    ("/visual_elements/include_gps_antenna", ("gps", "gnss")),
    ("/visual_elements/include_power_cabinet", ("armoire", "cabinet", "alimentation", "power")),
    ("/visual_elements/include_sector_beams", ("faisceau", "beam", "secteur")),
    ("/visual_elements/include_azimuth_arrows", ("azimut", "azimuth", "flèche", "fleche", "arrow")),
    (
        "/visual_elements/include_height_markers",
        ("hauteur", "height", "marker", "repère", "repere"),
    ),
    ("/visual_elements/include_labels", ("label", "étiquette", "etiquette")),
)

_SECTOR_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "azimuth_deg": ("azimut", "azimuth", "orientation", "diriger", "oriente"),
    "install_height_m": ("hauteur", "height", "hba", "antenne", "antenna"),
    "mechanical_tilt_deg": ("tilt", "inclinaison", "mécanique", "mecanique"),
    "electrical_tilt_deg": ("tilt", "inclinaison", "électrique", "electrique"),
    "beamwidth_deg": ("beamwidth", "ouverture", "faisceau", "beam"),
    "include_cable": ("câble", "cable"),
    "include_label": ("label", "étiquette", "etiquette"),
}


def _validate_patch_alignment(scene: SceneSpec, edit_prompt: str, patch: ScenePatch) -> None:
    normalized = edit_prompt.lower()
    source_numbers = [
        float(value.replace(",", ".")) for value in re.findall(r"-?\d+(?:[.,]\d+)?", normalized)
    ]
    mentioned_sectors = {
        int(value) - 1
        for value in re.findall(r"(?:secteur|sector|s)\s*(\d+)", normalized)
        if int(value) > 0
    }
    for operation in patch.operations:
        terms = _terms_for_path(operation.path)
        if not terms or not any(term in normalized for term in terms):
            raise ValueError(
                f"Patch operation is not grounded in the edit prompt: {operation.path}"
            )
        parts = operation.path.split("/")
        if operation.path.startswith("/sectors/") and parts[2].isdigit() and mentioned_sectors:
            if int(parts[2]) not in mentioned_sectors:
                raise ValueError(f"Patch targets an unrequested sector: {operation.path}")
        if isinstance(operation.value, int | float) and not isinstance(operation.value, bool):
            if not _numeric_value_is_grounded(
                scene,
                operation,
                source_numbers,
                normalized,
            ):
                raise ValueError(
                    f"Patch numeric value is not grounded in the prompt: {operation.path}"
                )
        if isinstance(operation.value, bool):
            expected = not any(
                marker in normalized
                for marker in ("supprime", "retire", "enlève", "enleve", "remove", "sans ")
            )
            if operation.value is not expected:
                raise ValueError(f"Patch boolean value contradicts the prompt: {operation.path}")


def _terms_for_path(path: str) -> tuple[str, ...]:
    if path.startswith("/sectors/"):
        field = path.rsplit("/", 1)[-1]
        return _SECTOR_FIELD_TERMS.get(field, ())
    return next(
        (known_terms for prefix, known_terms in _PATH_TERMS if path.startswith(prefix)),
        (),
    )


def _target_value_match(text: str, keywords: tuple[str, ...]) -> re.Match[str] | None:
    explicit = re.search(
        r"(?:à|to|=)\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*(?:deg)?",
        text,
    )
    if explicit:
        return explicit
    if not any(keyword in text for keyword in keywords):
        return None
    sector_number = SceneEditAgent._extract_sector_index(text)
    for match in re.finditer(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*(?:deg)?", text):
        value = float(match.group(1).replace(",", "."))
        if sector_number is not None and value == sector_number + 1:
            continue
        return match
    return None


def _numeric_value_is_grounded(
    scene: SceneSpec,
    operation: PatchOperation,
    source_numbers: list[float],
    normalized_prompt: str,
) -> bool:
    value = float(operation.value)
    if any(abs(value - source) <= 0.01 for source in source_numbers):
        return True
    current = _current_numeric_value(scene, operation.path)
    if current is None:
        return False
    if any(term in normalized_prompt for term in ("augmente", "increase", "ajoute", "raise")):
        return any(abs(value - (current + delta)) <= 0.01 for delta in source_numbers)
    if any(
        term in normalized_prompt for term in ("diminue", "decrease", "réduit", "reduit", "lower")
    ):
        return any(abs(value - (current - delta)) <= 0.01 for delta in source_numbers)
    return False


def _current_numeric_value(scene: SceneSpec, path: str) -> float | None:
    if path == "/tower/height_m":
        return float(scene.tower.height_m)
    parts = path.split("/")
    if path.startswith("/sectors/") and parts[2].isdigit():
        index = int(parts[2])
        if index >= len(scene.sectors):
            return None
        value = getattr(scene.sectors[index], parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    if path.startswith("/tower/characteristics/"):
        value = getattr(scene.tower.characteristics, parts[3], None)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None
