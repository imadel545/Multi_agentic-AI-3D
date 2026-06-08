from typing import Any

from core.contracts.scene import SceneSpec


class DiffEngine:
    @staticmethod
    def diff_scenes(original: SceneSpec, patched: SceneSpec) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "tower_changed": False,
            "sectors_changed": False,
            "visual_elements_changed": False,
            "sector_changes": [],
            "tower_changes": {},
            "visual_changes": {},
        }

        # Tower diff
        if original.tower.height_m != patched.tower.height_m:
            summary["tower_changed"] = True
            summary["tower_changes"]["height_m"] = {
                "old": original.tower.height_m,
                "new": patched.tower.height_m,
            }
        orig_char = original.tower.characteristics.model_dump()
        patch_char = patched.tower.characteristics.model_dump()
        char_diff = {
            k: {"old": orig_char[k], "new": patch_char[k]}
            for k in orig_char
            if orig_char[k] != patch_char[k]
        }
        if char_diff:
            summary["tower_changed"] = True
            summary["tower_changes"].update(char_diff)

        # Visual elements diff
        orig_vis = original.visual_elements.model_dump()
        patch_vis = patched.visual_elements.model_dump()
        vis_diff = {
            k: {"old": orig_vis[k], "new": patch_vis[k]}
            for k in orig_vis
            if orig_vis[k] != patch_vis[k]
        }
        if vis_diff:
            summary["visual_elements_changed"] = True
            summary["visual_changes"] = vis_diff

        # Sector diff
        orig_sectors = {s.sector_id: s for s in original.sectors}
        patch_sectors = {s.sector_id: s for s in patched.sectors}
        for sid in set(orig_sectors) | set(patch_sectors):
            if sid not in orig_sectors:
                summary["sectors_changed"] = True
                summary["sector_changes"].append({"sector_id": sid, "change": "added"})
            elif sid not in patch_sectors:
                summary["sectors_changed"] = True
                summary["sector_changes"].append({"sector_id": sid, "change": "removed"})
            else:
                sorig = orig_sectors[sid]
                spatch = patch_sectors[sid]
                sdiff = {}
                for field in (
                    "azimuth_deg",
                    "install_height_m",
                    "mechanical_tilt_deg",
                    "electrical_tilt_deg",
                    "beamwidth_deg",
                    "include_cable",
                    "include_label",
                ):
                    old_val = getattr(sorig, field)
                    new_val = getattr(spatch, field)
                    if old_val != new_val:
                        sdiff[field] = {"old": old_val, "new": new_val}
                if sdiff:
                    summary["sectors_changed"] = True
                    summary["sector_changes"].append({"sector_id": sid, "fields": sdiff})

        return summary
