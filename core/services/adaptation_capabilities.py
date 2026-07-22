import hashlib
import json
import math
from pathlib import Path
from typing import Any

from core.contracts.adaptation import (
    AdaptationCapabilityCatalog,
    AdaptationOperation,
    AssetAdaptationPlan,
    ResolvedAdaptationCapability,
    SceneAdaptationCapabilities,
)
from core.contracts.scene import SceneSpec
from core.services.asset_registry import AssetRegistry


class AdaptationCapabilityService:
    """Resolve the edit surface from versioned asset capability declarations."""

    def __init__(self, project_root: Path, registry: AssetRegistry) -> None:
        self.project_root = project_root.resolve()
        self.registry = registry
        self.catalog_path = self.project_root / "assets/capabilities/adaptation_profiles.json"
        payload = self.catalog_path.read_bytes()
        self.catalog_hash = hashlib.sha256(payload).hexdigest()
        self.catalog = AdaptationCapabilityCatalog.model_validate(json.loads(payload))
        self._profiles = {profile.profile_id: profile for profile in self.catalog.profiles}

    def resolve(self, scene: SceneSpec) -> SceneAdaptationCapabilities:
        resolved: list[ResolvedAdaptationCapability] = []
        unsupported: list[str] = []
        missing_profiles: list[str] = []

        self._resolve_profile(
            profile_id="scene_controls_v1",
            asset_id=None,
            substitutions={},
            output=resolved,
            unsupported=unsupported,
            missing_profiles=missing_profiles,
        )

        tower_manifest = self.registry.get(scene.tower.asset_id)
        tower_profile = tower_manifest.adaptation_profile_id
        if scene.tower.generation_strategy in {"parametric_generated", "procedural_fallback"}:
            self._resolve_profile(
                profile_id=tower_profile,
                asset_id=tower_manifest.asset_id,
                substitutions={},
                output=resolved,
                unsupported=unsupported,
                missing_profiles=missing_profiles,
            )
        else:
            unsupported.append(
                "Le pylône actif est un GLB non paramétrique; sa géométrie interne ne peut "
                "pas être remodelée sans profil Geometry Nodes vérifié."
            )

        for index, sector in enumerate(scene.sectors):
            manifest = self.registry.get(sector.antenna_asset_id)
            self._resolve_profile(
                profile_id=manifest.adaptation_profile_id,
                asset_id=manifest.asset_id,
                substitutions={"index": index},
                output=resolved,
                unsupported=unsupported,
                missing_profiles=missing_profiles,
                capability_scope=f"sector_{index + 1}",
            )

        for index, accessory in enumerate(scene.accessory_assets):
            manifest = self.registry.get(accessory.asset_id)
            self._resolve_profile(
                profile_id=manifest.adaptation_profile_id,
                asset_id=manifest.asset_id,
                substitutions={"index": index},
                output=resolved,
                unsupported=unsupported,
                missing_profiles=missing_profiles,
                capability_scope=f"accessory_{index + 1}",
            )

        unique = {capability.capability_id: capability for capability in resolved}
        return SceneAdaptationCapabilities(
            scene_id=scene.scene_id,
            catalog_version=self.catalog.schema_version,
            catalog_hash=self.catalog_hash,
            capabilities=sorted(unique.values(), key=lambda item: item.capability_id),
            unsupported_operations=_unique_strings(unsupported),
            missing_profiles=_unique_strings(missing_profiles),
        )

    def validate_plan(
        self,
        capabilities: SceneAdaptationCapabilities,
        plan: AssetAdaptationPlan,
    ) -> None:
        by_id = {capability.capability_id: capability for capability in capabilities.capabilities}
        seen_paths: set[str] = set()
        for operation in plan.operations:
            capability = by_id.get(operation.capability_id)
            if capability is None:
                raise ValueError(f"Unknown adaptation capability: {operation.capability_id}")
            if operation.path != capability.path:
                raise ValueError(
                    f"Capability {operation.capability_id} cannot edit {operation.path}"
                )
            if operation.execution_tool != capability.execution_tool:
                raise ValueError(
                    f"Capability {operation.capability_id} requires "
                    f"{capability.execution_tool}, not {operation.execution_tool}"
                )
            if operation.path in seen_paths:
                raise ValueError(f"Duplicate adaptation operation for {operation.path}")
            self._validate_value(operation, capability)
            seen_paths.add(operation.path)

    def public_catalog(self) -> dict[str, Any]:
        return {
            "schema_version": self.catalog.schema_version,
            "catalog_hash": self.catalog_hash,
            "profiles": [profile.model_dump(mode="json") for profile in self.catalog.profiles],
        }

    def _resolve_profile(
        self,
        *,
        profile_id: str | None,
        asset_id: str | None,
        substitutions: dict[str, int],
        output: list[ResolvedAdaptationCapability],
        unsupported: list[str],
        missing_profiles: list[str],
        capability_scope: str = "scene",
    ) -> None:
        if not profile_id:
            missing_profiles.append(asset_id or capability_scope)
            return
        profile = self._profiles.get(profile_id)
        if profile is None:
            missing_profiles.append(profile_id)
            return
        unsupported.extend(profile.unsupported_operations)
        for parameter in profile.editable_parameters:
            path = parameter.path_template.format(**substitutions)
            capability_id = f"{capability_scope}:{parameter.parameter_id}"
            output.append(
                ResolvedAdaptationCapability(
                    capability_id=capability_id,
                    asset_id=asset_id,
                    profile_id=profile.profile_id,
                    label=parameter.label,
                    path=path,
                    value_type=parameter.value_type,
                    execution_tool=parameter.execution_tool,
                    effect=parameter.effect,
                    description=parameter.description,
                    unit=parameter.unit,
                    minimum=parameter.minimum,
                    maximum=parameter.maximum,
                    allowed_values=parameter.allowed_values,
                    requires_regeneration=parameter.requires_regeneration,
                )
            )

    @staticmethod
    def _validate_value(
        operation: AdaptationOperation,
        capability: ResolvedAdaptationCapability,
    ) -> None:
        value = operation.value
        value_type = capability.value_type
        if value_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{operation.path} requires a boolean")
            values = [value]
        elif value_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{operation.path} requires an integer")
            values = [value]
        elif value_type == "number":
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{operation.path} requires a number")
            values = [float(value)]
        elif value_type == "string":
            if not isinstance(value, str) or not value:
                raise ValueError(f"{operation.path} requires a non-empty string")
            values = [value]
        else:
            if (
                not isinstance(value, list)
                or len(value) != 3
                or any(
                    not isinstance(item, int | float) or isinstance(item, bool) for item in value
                )
            ):
                raise ValueError(f"{operation.path} requires a numeric XYZ vector")
            values = [float(item) for item in value]

        if any(isinstance(item, float) and not math.isfinite(item) for item in values):
            raise ValueError(f"{operation.path} contains a non-finite value")
        if capability.allowed_values and value not in capability.allowed_values:
            raise ValueError(f"{operation.path} value {value!r} is outside declared allowed values")
        numeric_values = [item for item in values if isinstance(item, int | float)]
        if capability.minimum is not None and any(
            float(item) < capability.minimum for item in numeric_values
        ):
            raise ValueError(f"{operation.path} is below {capability.minimum}")
        if capability.maximum is not None and any(
            float(item) > capability.maximum for item in numeric_values
        ):
            raise ValueError(f"{operation.path} exceeds {capability.maximum}")


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
