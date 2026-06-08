from typing import Any

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.validation import ValidationIssue, ValidationReport


class PatchApplier:
    def apply(self, scene: SceneSpec, patch: ScenePatch) -> tuple[SceneSpec, ValidationReport]:
        data = scene.model_dump(mode="json")
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        for op in patch.operations:
            try:
                self._apply_op(data, op)
            except (ValueError, IndexError, KeyError, TypeError) as exc:
                errors.append(
                    ValidationIssue(
                        code="PATCH_APPLY_ERROR",
                        message=f"Failed to apply patch {op.path}: {exc}",
                        severity="error",
                    )
                )

        if errors:
            report = ValidationReport(
                design_id=scene.scene_id,
                status="failed",
                score=0.0,
                checks={"patch_applied": False},
                warnings=warnings,
                errors=errors,
            )
            # Return original on failure
            return scene, report

        try:
            patched = SceneSpec.model_validate(data)
        except Exception as exc:
            errors.append(
                ValidationIssue(
                    code="PATCH_VALIDATION_ERROR",
                    message=f"Patched scene failed validation: {exc}",
                    severity="error",
                )
            )
            report = ValidationReport(
                design_id=scene.scene_id,
                status="failed",
                score=0.0,
                checks={"patch_applied": False},
                warnings=warnings,
                errors=errors,
            )
            return scene, report

        report = ValidationReport(
            design_id=scene.scene_id,
            status="passed",
            score=1.0,
            checks={"patch_applied": True},
            warnings=warnings,
            errors=errors,
        )
        return patched, report

    def _apply_op(self, data: dict[str, Any], op: PatchOperation) -> None:
        parts = op.path.strip("/").split("/")
        if not parts:
            raise ValueError("Empty path")

        target = data
        for part in parts[:-1]:
            if part.isdigit():
                idx = int(part)
                if not isinstance(target, list) or idx >= len(target):
                    raise IndexError(f"Index {idx} out of range")
                target = target[idx]
            else:
                if part not in target:
                    target[part] = {}
                target = target[part]

        key = parts[-1]
        if op.op == "replace":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list) or idx >= len(target):
                    raise IndexError(f"Index {idx} out of range")
                target[idx] = op.value
            else:
                target[key] = op.value
        elif op.op == "add":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list):
                    raise TypeError("Target is not a list")
                target.insert(idx, op.value)
            else:
                target[key] = op.value
        elif op.op == "remove":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list) or idx >= len(target):
                    raise IndexError(f"Index {idx} out of range")
                target.pop(idx)
            else:
                if key not in target:
                    raise KeyError(f"Key {key} not found")
                del target[key]
