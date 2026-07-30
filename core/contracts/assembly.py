from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel


class AssetCandidateScore(StrictModel):
    asset_id: str = Field(min_length=1, max_length=120)
    total_score: float = Field(ge=0, le=100)
    compatibility_score: float = Field(ge=0, le=100)
    generation_score: float = Field(ge=0, le=100)
    dimensional_score: float = Field(ge=0, le=100)
    reasons: list[str] = Field(min_length=1, max_length=12)


class AssemblyComponentSelection(StrictModel):
    role_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9._-]*$")
    asset_type: str = Field(min_length=1, max_length=48)
    required: bool = True
    candidate_scores: list[AssetCandidateScore] = Field(default_factory=list, max_length=24)
    selected_asset_id: str | None = Field(default=None, min_length=1, max_length=120)
    builder_profile_id: str = Field(min_length=1, max_length=120)
    generation_strategy: Literal[
        "imported_glb_exact", "internal_project_generated", "procedural_fallback"
    ]
    allowed_parameter_ids: list[str] = Field(default_factory=list, max_length=32)
    selection_reason: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def validate_selection(self) -> AssemblyComponentSelection:
        candidate_ids = [candidate.asset_id for candidate in self.candidate_scores]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate scores must have unique asset IDs")
        if self.selected_asset_id is not None and self.selected_asset_id not in candidate_ids:
            raise ValueError("selected asset must be one of the scored candidates")
        if (
            self.required
            and self.selected_asset_id is None
            and self.generation_strategy != "procedural_fallback"
        ):
            raise ValueError("required component needs an asset or a procedural fallback")
        return self


class AssemblyConnection(StrictModel):
    connection_id: str = Field(min_length=1, max_length=120)
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    source_role_id: str = Field(min_length=1, max_length=96)
    source_connector_id: str = Field(min_length=1, max_length=96)
    target_role_id: str = Field(min_length=1, max_length=96)
    target_connector_id: str = Field(min_length=1, max_length=96)
    required: bool = True


class AssemblyPlan(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    workflow_id: str = Field(min_length=1, max_length=120)
    units: Literal["meters"] = "meters"
    components: list[AssemblyComponentSelection] = Field(min_length=3, max_length=32)
    connections: list[AssemblyConnection] = Field(min_length=1, max_length=64)
    selection_authority: Literal["llm_bounded", "deterministic_fallback"]
    llm_fallback_used: bool
    llm_fallback_reason: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_plan(self) -> AssemblyPlan:
        roles = [component.role_id for component in self.components]
        if len(roles) != len(set(roles)):
            raise ValueError("assembly roles must be unique")
        known = set(roles)
        for connection in self.connections:
            if connection.source_role_id not in known or connection.target_role_id not in known:
                raise ValueError("assembly connection references an unknown role")
        if self.llm_fallback_used != (self.selection_authority == "deterministic_fallback"):
            raise ValueError("selection authority must match fallback truth")
        if self.llm_fallback_used and not self.llm_fallback_reason:
            raise ValueError("fallback plan requires a reason")
        return self
