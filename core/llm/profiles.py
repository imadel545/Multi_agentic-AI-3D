from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.vision import VisionCapability

GroqCapabilityId = Literal[
    "text_reasoning",
    "multimodal_interpretation",
    "asset_visual_review",
    "visual_design_critic",
]
GroqResponsePolicy = Literal["strict_json_schema", "json_object_local_validation"]


class GroqCapabilityProfile(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    capability: GroqCapabilityId
    model: str = Field(min_length=1, max_length=160)
    response_policy: GroqResponsePolicy
    timeout_s: float = Field(gt=0, le=180)
    max_completion_tokens: int = Field(ge=128, le=65_536)
    enabled: bool = True
    advisory_only: bool = False


class GroqCapabilityProfiles(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    text_reasoning: GroqCapabilityProfile
    multimodal_interpretation: GroqCapabilityProfile
    asset_visual_review: GroqCapabilityProfile
    visual_design_critic: GroqCapabilityProfile

    def vision(self, capability: VisionCapability) -> GroqCapabilityProfile:
        return getattr(self, capability)


def build_groq_capability_profiles(
    *,
    text_model: str = "openai/gpt-oss-120b",
    vision_model: str = "qwen/qwen3.6-27b",
    text_timeout_s: float = 30.0,
    text_max_completion_tokens: int = 4096,
    vision_timeout_s: float = 45.0,
    vision_max_completion_tokens: int = 2048,
    vision_enabled: bool = False,
    visual_design_critic_enabled: bool = False,
) -> GroqCapabilityProfiles:
    return GroqCapabilityProfiles(
        text_reasoning=GroqCapabilityProfile(
            capability="text_reasoning",
            model=text_model,
            response_policy="strict_json_schema",
            timeout_s=text_timeout_s,
            max_completion_tokens=text_max_completion_tokens,
        ),
        multimodal_interpretation=GroqCapabilityProfile(
            capability="multimodal_interpretation",
            model=vision_model,
            response_policy="json_object_local_validation",
            timeout_s=vision_timeout_s,
            max_completion_tokens=vision_max_completion_tokens,
            enabled=vision_enabled,
            advisory_only=True,
        ),
        asset_visual_review=GroqCapabilityProfile(
            capability="asset_visual_review",
            model=vision_model,
            response_policy="json_object_local_validation",
            timeout_s=vision_timeout_s,
            max_completion_tokens=vision_max_completion_tokens,
            enabled=vision_enabled,
            advisory_only=True,
        ),
        visual_design_critic=GroqCapabilityProfile(
            capability="visual_design_critic",
            model=vision_model,
            response_policy="json_object_local_validation",
            timeout_s=vision_timeout_s,
            max_completion_tokens=vision_max_completion_tokens,
            enabled=vision_enabled and visual_design_critic_enabled,
            advisory_only=True,
        ),
    )
