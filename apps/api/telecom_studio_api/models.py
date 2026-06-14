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
    asset_import_summary: dict | None = None
    asset_imports: list[dict] | None = None
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


# Product-oriented response models


class UserIssue(BaseModel):
    title: str
    severity: Literal["info", "warning", "error"]
    impact: str
    recommended_action: str
    technical_code: str | None = None


class UserSummary(BaseModel):
    workflow_id: str
    status: str
    current_operation: str
    next_recommended_action: str
    qa_summary: str
    human_readable_issues: list[UserIssue]
    active_version: str | None = None
    generation_mode: str | None = None
    asset_quality_summary: str | None = None
    limitations: list[str] = Field(default_factory=list)


class UserIssuesResponse(BaseModel):
    workflow_id: str
    status: str
    human_readable_issues: list[UserIssue]


class CurrentOperation(BaseModel):
    workflow_id: str
    status: str
    current_operation: str
    next_recommended_action: str
    progress_indicator: str | None = None
    current_phase: str | None = None
    current_node: str | None = None
    event_source: str = "status"


class ViewerArtifact(BaseModel):
    name: str
    url: str
    content_type: str
    available: bool


class ViewerBundle(BaseModel):
    workflow_id: str
    status: str
    active_version: str | None = None
    generation_mode: str | None = None
    qa_score: float | None = None
    asset_import_summary: dict | None = None
    human_warnings_count: int = 0
    human_errors_count: int = 0
    viewer_artifacts: list[ViewerArtifact]


class TimelineStep(BaseModel):
    step: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    timestamp: str | None = None
    human_readable: str


class TimelineSummary(BaseModel):
    workflow_id: str
    status: str
    timeline_steps: list[TimelineStep]


class DesignListSummary(BaseModel):
    workflow_id: str
    status: str
    created_at: str | None = None
    qa_score: float | None = None
    generation_mode: str | None = None
    current_operation: str | None = None


class StudioSummary(BaseModel):
    designs: list[DesignListSummary]
    total_designs: int
    active_designs: int
    completed_designs: int
    failed_designs: int
    pending_designs: int
    asset_inventory_status: str
    asset_count: int = 0
    real_glb_asset_count: int = 0
    missing_file_count: int = 0
    blender_available: bool | None = None
    groq_available: bool | None = None
    warnings: list[UserIssue] = Field(default_factory=list)
