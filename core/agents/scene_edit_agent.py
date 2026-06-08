import json
import re

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.llm.groq import GroqStructuredClient


class SceneEditAgent:
    def __init__(self, groq_client: GroqStructuredClient | None = None) -> None:
        self.groq = groq_client

    def create_patch(
        self,
        workflow_id: str,
        scene: SceneSpec,
        edit_prompt: str,
    ) -> ScenePatch:
        if self.groq is not None:
            try:
                return self._llm_patch(scene, edit_prompt)
            except Exception:
                pass
        return self._fallback_patch(scene, edit_prompt)

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
        return ScenePatch(
            edit_description=raw.get("edit_description", edit_prompt),
            operations=operations,
            edit_llm_provider="groq",
            edit_llm_fallback_used=False,
        )

    def _fallback_patch(self, scene: SceneSpec, edit_prompt: str) -> ScenePatch:
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
        azimuth_match = re.search(r"(\d+(?:\.\d+)?)\s*°?\s*(?:deg)?", text)
        if azimuth_match and any(
            k in text for k in ("azimut", "azimuth", "orientation", "diriger")
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
        tilt_match = re.search(r"(\d+(?:\.\d+)?)\s*°?\s*(?:deg)?", text)
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
        if any(k in text for k in ("beam", "faisceau", "secteur")):
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
