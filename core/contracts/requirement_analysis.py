from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import DetailLevel, StrictModel

InputAnalysisStatus = Literal["verified", "legacy_unattested", "unavailable"]


class RequirementAnalysisReceipt(StrictModel):
    """Server-issued evidence for the analysis that preceded confirmation.

    This receipt describes the bounded extraction that a person reviewed before
    submitting a confirmed ``RequirementSpec``.  It is deliberately distinct
    from ``LLMDecisionProvenance``: the latter records an executable design or
    edit decision, while this object records the origin of the input analysis.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: str = Field(pattern=r"^ira_[a-f0-9]{32}$")
    issued_at: str = Field(min_length=20, max_length=40)
    confirmed_prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_requirements_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detail_level: DetailLevel
    provider: str = Field(min_length=1, max_length=160)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    extraction_provider: str = Field(min_length=1, max_length=40)
    fallback_used: bool
    fallback_reason: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_fallback_truth(self) -> "RequirementAnalysisReceipt":
        if self.fallback_used and not self.fallback_reason:
            raise ValueError("fallback input analysis receipt requires fallback_reason")
        if not self.fallback_used and self.fallback_reason is not None:
            raise ValueError("primary input analysis receipt cannot contain fallback_reason")
        return self
