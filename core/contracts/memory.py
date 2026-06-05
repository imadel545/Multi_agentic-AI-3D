from pydantic import Field

from core.contracts.common import NetworkType, StrictModel


class MemorySummary(StrictModel):
    workflow_id: str = Field(min_length=1)
    network_type: NetworkType
    tower_type: str = Field(min_length=1)
    sector_count: int = Field(ge=1)
    generation_mode: str = Field(min_length=1)
    qa_score: float = Field(ge=0, le=1)
    warnings: list[dict] = Field(default_factory=list)
    scene_spec_path: str = Field(min_length=1)
    validation_report_path: str = Field(min_length=1)
    reusable_pattern: bool = False
    created_at: int = Field(ge=0)


class MemoryRecallResult(StrictModel):
    similar_workflows: list[dict] = Field(default_factory=list)
    reusable_patterns: list[dict] = Field(default_factory=list)
    error_patterns: list[dict] = Field(default_factory=list)
    memory_hits: int = Field(default=0, ge=0)
    memory_context_count: int = Field(default=0, ge=0)


class MemoryIndexResult(StrictModel):
    status: str = Field(min_length=1)
    indexed_collections: dict[str, int] = Field(default_factory=dict)
    indexed_points: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
