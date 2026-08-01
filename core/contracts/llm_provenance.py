from typing import Any, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel


class LLMDecisionCandidate(StrictModel):
    capability_id: str = Field(min_length=1)
    asset_id: str | None = None
    profile_id: str = Field(min_length=1)
    path: str = Field(pattern=r"^/")
    execution_tool: str = Field(min_length=1)
    value_type: str = Field(min_length=1)
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[str | int | bool] = Field(default_factory=list)


class LLMDecisionLinks(StrictModel):
    blueprint_url: str = Field(pattern=r"^/designs/")
    scene_spec_url: str = Field(pattern=r"^/designs/")
    version_url: str = Field(pattern=r"^/designs/")


class LLMDecisionProvenance(StrictModel):
    """Durable evidence for one bounded model decision.

    The model may select only candidates declared here. Deterministic code still
    validates paths, values, tools and the resulting SceneSpec before Blender runs.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    workflow_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    parent_version_id: str | None = None
    provider: str = Field(min_length=1)
    model: str | None = None
    capability_called: str = Field(min_length=1)
    structured_decision: dict[str, Any] = Field(min_length=1)
    candidates_considered: list[LLMDecisionCandidate] = Field(min_length=1)
    strategy_selected: list[str] = Field(min_length=1)
    rationale: list[str] = Field(min_length=1)
    fallback_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=160)
    timestamp: str = Field(min_length=1)
    decision_contract_version: str = Field(min_length=1)
    source_prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_catalog_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    links: LLMDecisionLinks

    @model_validator(mode="after")
    def validate_fallback_truth(self) -> "LLMDecisionProvenance":
        if self.fallback_used and not self.fallback_reason:
            raise ValueError("fallback provenance requires fallback_reason")
        if not self.fallback_used and self.fallback_reason is not None:
            raise ValueError("primary decision provenance cannot contain fallback_reason")
        return self
