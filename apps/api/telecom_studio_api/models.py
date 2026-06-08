from typing import Literal

from pydantic import BaseModel, Field


class DesignOptions(BaseModel):
    detail_level: Literal["low", "medium", "high"] = "high"
    use_llm: bool | None = None


class CreateDesignRequest(BaseModel):
    requirements_text: str = Field(min_length=1, max_length=5000)
    options: DesignOptions = Field(default_factory=DesignOptions)


class CreateDesignResponse(BaseModel):
    workflow_id: str
    status: str


class WorkflowStatus(BaseModel):
    workflow_id: str
    status: str
    version_id: str | None = None
    active_version_id: str | None = None
    artifacts: dict[str, str]
    warnings: list[dict]
    errors: list[dict]
    llm_provider: str | None = None
    llm_fallback_used: bool | None = None
    rag_context_count: int | None = None
    memory_hits: int | None = None
    memory_context_count: int | None = None
    generation_mode: str | None = None
    blender_available: bool | None = None
    qa_score: float | None = None
    tower_characteristics_summary: dict | None = None
    glb_inspection_summary: dict | None = None
    geometry_validation_summary: dict | None = None
    preview_inspection_summary: dict | None = None
    structural_qa_passed: bool | None = None
    expected_objects_present: bool | None = None
    total_duration_ms: int | None = None
    total_workflow_duration_ms: int | None = None
    metrics: dict[str, int | float | str | bool | None] | None = None
    quality_gates: list[dict] | None = None
    download_url: str | None = None
    trace_path: str | None = None
    tower_validation: dict | None = None
    rf_validation: dict | None = None


class ParseRequirementsRequest(BaseModel):
    requirements_text: str = Field(min_length=1, max_length=5000)
    detail_level: Literal["low", "medium", "high"] = "high"
    use_llm: bool | None = None


class ParseRequirementsResponse(BaseModel):
    requirements: dict | None
    warnings: list[dict]
    errors: list[dict]
    provider: str | None
    fallback_used: bool | None


class RagSearchResponse(BaseModel):
    query: str
    results: list[dict]


class EditDesignRequest(BaseModel):
    edit_prompt: str = Field(min_length=1, max_length=1000)


class EditDesignResponse(BaseModel):
    workflow_id: str
    edit_id: str
    status: str
    version_id: str | None = None
    diff_summary: dict | None = None
    patch: dict | None = None
    validation_report: dict | None = None
    artifacts: dict[str, str] | None = None
    generation_mode: str | None = None
    qa_score: float | None = None
    llm_provider: str | None = None
    llm_fallback_used: bool | None = None
    errors: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)


class ListDesignsResponse(BaseModel):
    workflow_id: str
    status: str
    created_at: str | None = None
    qa_score: float | None = None
    generation_mode: str | None = None


class VersionInfo(BaseModel):
    version_id: str
    parent_version_id: str | None = None
    created_at: str
    edit_description: str | None = None
    diff_summary: dict | None = None
    status: str | None = None
    active: bool = False
    artifact_dir: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    qa_score: float | None = None
    generation_mode: str | None = None
