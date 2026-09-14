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

        # V2 scenes may consist entirely of geometry programs, with no V1 tower.
        if original.tower is None or patched.tower is None:
            if original.tower != patched.tower:
                summary["tower_changed"] = True
                summary["tower_changes"]["presence"] = {
                    "old": original.tower is not None,
                    "new": patched.tower is not None,
                }
        else:
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

        original_programs = {
            p.program_id: p.model_dump(mode="json") for p in original.geometry_programs
        }
        patched_programs = {
            p.program_id: p.model_dump(mode="json") for p in patched.geometry_programs
        }
        program_changes = []
        for program_id in sorted(original_programs.keys() | patched_programs.keys()):
            old, new = original_programs.get(program_id), patched_programs.get(program_id)
            if old != new:
                program_changes.append({"program_id": program_id, "old": old, "new": new})
        summary["geometry_programs_changed"] = bool(program_changes)
        summary["geometry_program_changes"] = program_changes

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
        for sid in sorted(set(orig_sectors) | set(patch_sectors)):
            if sid not in orig_sectors:
                summary["sectors_changed"] = True
                summary["sector_changes"].append({"sector_id": sid, "change": "added"})
            elif sid not in patch_sectors:
                summary["sectors_changed"] = True
                summary["sector_changes"].append({"sector_id": sid, "change": "removed"})
            else:
                original_payload = orig_sectors[sid].model_dump(mode="json")
                patched_payload = patch_sectors[sid].model_dump(mode="json")
                sdiff = {}
                for field in sorted(set(original_payload) | set(patched_payload)):
                    if field == "sector_id":
                        continue
                    old_val = original_payload.get(field)
                    new_val = patched_payload.get(field)
                    if old_val != new_val:
                        sdiff[field] = {"old": old_val, "new": new_val}
                if sdiff:
                    summary["sectors_changed"] = True
                    summary["sector_changes"].append({"sector_id": sid, "fields": sdiff})

        return summary
