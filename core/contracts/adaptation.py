from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from core.contracts.common import StrictModel
from core.contracts.scene import SceneSpec
from core.contracts.scene_edit import ScenePatch
from core.contracts.validation import ValidationReport

AdaptationValueType = Literal["number", "integer", "boolean", "string", "vector3"]
AdaptationTool = Literal[
    "parametric_rebuild",
    "sector_layout",
    "asset_transform",
    "scene_visibility",
]
AdaptationEffect = Literal["geometry", "placement", "material", "visibility", "rf"]


class EditableParameterDefinition(StrictModel):
    parameter_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    path_template: str = Field(pattern=r"^/")
    value_type: AdaptationValueType
    execution_tool: AdaptationTool
    effect: AdaptationEffect
    description: str = Field(min_length=1)
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[str | int | bool] = Field(default_factory=list)
    requires_regeneration: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "EditableParameterDefinition":
        if self.minimum is not None and self.maximum is not None:
            if self.maximum < self.minimum:
                raise ValueError("maximum must be greater than or equal to minimum")
        if self.allowed_values and self.value_type not in {"string", "integer", "boolean"}:
            raise ValueError("allowed_values is only valid for string, integer or boolean values")
        return self


class AssetCapabilityProfileDefinition(StrictModel):
    profile_id: str = Field(min_length=1)
    representation: Literal[
        "parametric_scene",
        "semantic_glb",
        "opaque_glb",
        "scene_controls",
        "reference_only",
    ]
    editable_parameters: list[EditableParameterDefinition] = Field(default_factory=list)
    unsupported_operations: list[str] = Field(default_factory=list)


class AdaptationCapabilityCatalog(StrictModel):
    schema_version: str = "1.0.0"
    profiles: list[AssetCapabilityProfileDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "AdaptationCapabilityCatalog":
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("adaptation capability profile ids must be unique")
        return self


class ResolvedAdaptationCapability(StrictModel):
    capability_id: str = Field(min_length=1)
    asset_id: str | None = None
    profile_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    path: str = Field(pattern=r"^/")
    value_type: AdaptationValueType
    execution_tool: AdaptationTool
    effect: AdaptationEffect
    description: str = Field(min_length=1)
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[str | int | bool] = Field(default_factory=list)
    requires_regeneration: bool = True


class SceneAdaptationCapabilities(StrictModel):
    scene_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(min_length=1)
    capabilities: list[ResolvedAdaptationCapability] = Field(min_length=1)
    unsupported_operations: list[str] = Field(default_factory=list)
    missing_profiles: list[str] = Field(default_factory=list)

    @property
    def allowed_paths(self) -> set[str]:
        return {capability.path for capability in self.capabilities}


class AdaptationOperation(StrictModel):
    op: Literal["replace"] = "replace"
    capability_id: str = Field(min_length=1)
    path: str = Field(pattern=r"^/")
    value: Any
    execution_tool: AdaptationTool
    rationale: str = Field(min_length=1, max_length=240)


class AssetAdaptationPlan(StrictModel):
    edit_description: str = Field(min_length=1, max_length=400)
    operations: list[AdaptationOperation] = Field(min_length=1, max_length=32)
    unsupported_requests: list[str] = Field(default_factory=list, max_length=16)
    assumptions: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("unsupported_requests", "assumptions")
    @classmethod
    def reject_blank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("blank list entries are not allowed")
        return values


class AdaptationDecision(StrictModel):
    workflow_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    capabilities: SceneAdaptationCapabilities
    plan: AssetAdaptationPlan
    patch: ScenePatch
    patched_scene: SceneSpec
    validation_report: ValidationReport
    planner_provider: str = Field(min_length=1)
    planner_fallback_used: bool = False
    planner_fallback_reason: str | None = Field(default=None, max_length=160)
    graph_trace: list[dict[str, Any]] = Field(default_factory=list)
