from typing import Any

from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import PatchOperation, ScenePatch
from core.contracts.validation import ValidationIssue, ValidationReport


class PatchApplier:
    def apply(
        self,
        scene: SceneSpec,
        patch: ScenePatch,
        *,
        allowed_paths: set[str] | None = None,
    ) -> tuple[SceneSpec, ValidationReport]:
        data = scene.model_dump(mode="json")
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        for op in patch.operations:
            try:
                if allowed_paths is not None and op.path not in allowed_paths:
                    raise ValueError("path is not declared by the active capability profile")
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
        self._apply_parts(data, parts, op)

    def _apply_parts(self, target: Any, parts: list[str], op: PatchOperation) -> None:
        if not parts:
            raise ValueError("Empty path")
        part = parts[0]
        if part == "*":
            if not isinstance(target, list):
                raise TypeError("Wildcard target is not a list")
            for item in target:
                self._apply_parts(item, parts[1:], op)
            return
        if len(parts) == 1:
            self._apply_leaf(target, part, op)
            return
        next_target = self._resolve_next_target(target, part)
        self._apply_parts(next_target, parts[1:], op)

    @staticmethod
    def _resolve_next_target(target: Any, part: str) -> Any:
        if part.isdigit():
            idx = int(part)
            if not isinstance(target, list) or idx >= len(target):
                raise IndexError(f"Index {idx} out of range")
            return target[idx]
        if not isinstance(target, dict):
            raise TypeError(f"Cannot access key {part} on non-object target")
        if part not in target:
            target[part] = {}
        return target[part]

    @staticmethod
    def _apply_leaf(target: Any, key: str, op: PatchOperation) -> None:
        if key == "*":
            raise ValueError("Leaf wildcard is not supported")
        if op.op == "replace":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list) or idx >= len(target):
                    raise IndexError(f"Index {idx} out of range")
                target[idx] = op.value
            else:
                if not isinstance(target, dict):
                    raise TypeError(f"Cannot replace key {key} on non-object target")
                target[key] = op.value
        elif op.op == "add":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list):
                    raise TypeError("Target is not a list")
                target.insert(idx, op.value)
            else:
                if not isinstance(target, dict):
                    raise TypeError(f"Cannot add key {key} on non-object target")
                target[key] = op.value
        elif op.op == "remove":
            if key.isdigit():
                idx = int(key)
                if not isinstance(target, list) or idx >= len(target):
                    raise IndexError(f"Index {idx} out of range")
                target.pop(idx)
            else:
                if not isinstance(target, dict):
                    raise TypeError(f"Cannot remove key {key} on non-object target")
                if key not in target:
                    raise KeyError(f"Key {key} not found")
                del target[key]
