from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel

VisionCapability = Literal[
    "multimodal_interpretation",
    "asset_visual_review",
    "visual_design_critic",
]
VisionCapabilityStatus = Literal[
    "disabled",
    "configured_unverified",
    "operational",
    "failed",
]
VisionResponseMode = Literal["json_object_validated", "json_object_repaired"]


class NormalizedImageRegion(StrictModel):
    """Normalized image coordinates; no local filesystem location is exposed."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> NormalizedImageRegion:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("normalized image region must remain inside the image")
        return self


class VisualEvidenceSource(StrictModel):
    source_id: str = Field(pattern=r"^image_[1-3]$")
    file_name: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    width_px: int = Field(gt=0, le=16_384)
    height_px: int = Field(gt=0, le=16_384)
    page: int | None = Field(default=None, ge=1)
    region: NormalizedImageRegion | None = None


class VisualObservedObject(StrictModel):
    object_id: str = Field(pattern=r"^object_[a-z0-9_-]+$", max_length=96)
    source_id: str = Field(pattern=r"^image_[1-3]$")
    label: str = Field(min_length=1, max_length=160)
    semantic_role: str | None = Field(default=None, max_length=96)
    confidence: float = Field(ge=0, le=1)
    region: NormalizedImageRegion | None = None
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)


class VisualTextObservation(StrictModel):
    source_id: str = Field(pattern=r"^image_[1-3]$")
    text: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    language: str | None = Field(default=None, max_length=32)
    region: NormalizedImageRegion | None = None


class VisualSpatialRelation(StrictModel):
    source_id: str = Field(pattern=r"^image_[1-3]$")
    subject_object_id: str = Field(pattern=r"^object_[a-z0-9_-]+$", max_length=96)
    relation: Literal[
        "left_of",
        "right_of",
        "above",
        "below",
        "inside",
        "contains",
        "attached_to",
        "overlaps",
        "near",
        "aligned_with",
        "unknown",
    ]
    object_object_id: str = Field(pattern=r"^object_[a-z0-9_-]+$", max_length=96)
    confidence: float = Field(ge=0, le=1)


class VisualDefectObservation(StrictModel):
    source_id: str = Field(pattern=r"^image_[1-3]$")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=96)
    description: str = Field(min_length=1, max_length=800)
    severity: Literal["info", "warning", "review_required"]
    confidence: float = Field(ge=0, le=1)
    region: NormalizedImageRegion | None = None


class ModelInvocationEvidence(StrictModel):
    provider: Literal["groq"] = "groq"
    model: str = Field(min_length=1, max_length=160)
    capability: VisionCapability
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_mode: VisionResponseMode
    latency_ms: int = Field(ge=0)
    attempts: int = Field(ge=1, le=12)
    timestamp: datetime


class VisionCapabilityHealth(StrictModel):
    capability: VisionCapability
    status: VisionCapabilityStatus
    advisory_only: bool = True
    consecutive_failures: int = Field(default=0, ge=0)
    circuit_open_until: datetime | None = None
    last_error: str | None = Field(default=None, max_length=160)
    last_success_at: datetime | None = None


class VisualEvidencePacket(StrictModel):
    """Persistable visual evidence with bounded advisory authority.

    Exact dimensions, engineering compliance, licensing and certification are
    deliberately absent. Those remain deterministic or human-confirmed facts.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    capability: VisionCapability
    advisory_only: Literal[True] = True
    sources: list[VisualEvidenceSource] = Field(min_length=1, max_length=3)
    observed_objects: list[VisualObservedObject] = Field(default_factory=list, max_length=128)
    text_observations: list[VisualTextObservation] = Field(default_factory=list, max_length=128)
    spatial_relations: list[VisualSpatialRelation] = Field(default_factory=list, max_length=128)
    suspected_defects: list[VisualDefectObservation] = Field(default_factory=list, max_length=64)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(min_length=1, max_length=16)
    invocation: ModelInvocationEvidence

    @model_validator(mode="after")
    def validate_references(self) -> VisualEvidencePacket:
        source_ids = {source.source_id for source in self.sources}
        object_ids = {item.object_id for item in self.observed_objects}
        if len(source_ids) != len(self.sources):
            raise ValueError("visual evidence sources must have unique source_id values")
        if len(object_ids) != len(self.observed_objects):
            raise ValueError("visual observations must have unique object_id values")
        referenced_sources = {
            item.source_id
            for collection in (
                self.observed_objects,
                self.text_observations,
                self.spatial_relations,
                self.suspected_defects,
            )
            for item in collection
        }
        if referenced_sources - source_ids:
            raise ValueError("visual evidence references an unknown source_id")
        for relation in self.spatial_relations:
            if relation.subject_object_id not in object_ids:
                raise ValueError("visual relation references an unknown subject object")
            if relation.object_object_id not in object_ids:
                raise ValueError("visual relation references an unknown target object")
        if self.invocation.capability != self.capability:
            raise ValueError("invocation capability must match visual evidence capability")
        return self
