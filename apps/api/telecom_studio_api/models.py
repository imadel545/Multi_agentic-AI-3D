from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.contracts.identifiers import CHAT_ID_PATTERN, DOCUMENT_PACK_ID_PATTERN
from core.contracts.requirement_analysis import InputAnalysisStatus, RequirementAnalysisReceipt
from core.contracts.requirements import RequirementSpec

MultimodalConsent = Literal[
    "disabled",
    "allow_input_analysis",
    "allow_input_and_visual_review",
]


class DesignOptions(BaseModel):
    detail_level: Literal["low", "medium", "high"] = "high"
    use_llm: bool | None = None
    multimodal_consent: MultimodalConsent = "disabled"


class CreateDesignRequest(BaseModel):
    chat_id: str | None = Field(default=None, pattern=CHAT_ID_PATTERN)
    document_pack_id: str | None = Field(default=None, pattern=DOCUMENT_PACK_ID_PATTERN)
    document_context_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    requirements_text: str = Field(min_length=1, max_length=5000)
    options: DesignOptions = Field(default_factory=DesignOptions)
    confirmed_requirements: RequirementSpec | None = None
    confirmed_requirements_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    confirmed_analysis_receipt: RequirementAnalysisReceipt | None = None

    @field_validator("requirements_text")
    @classmethod
    def validate_nonblank_requirements_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirements_text must contain a written request")
        return value

    @model_validator(mode="after")
    def validate_confirmed_requirements_pair(self) -> "CreateDesignRequest":
        if self.document_pack_id is not None and self.chat_id is None:
            raise ValueError("document_pack_id requires chat_id")
        if self.document_context_hash is not None and self.document_pack_id is None:
            raise ValueError("document_context_hash requires document_pack_id")
        if (self.confirmed_requirements is None) != (self.confirmed_requirements_hash is None):
            raise ValueError(
                "confirmed_requirements and confirmed_requirements_hash must be provided together"
            )
        confirmed = self.confirmed_requirements
        if (
            confirmed is not None
            and self.document_pack_id is not None
            and self.document_context_hash is None
        ):
            raise ValueError("confirmed document-aware requirements require document_context_hash")
        if self.confirmed_analysis_receipt is not None and confirmed is None:
            raise ValueError(
                "confirmed_analysis_receipt requires confirmed_requirements and its hash"
            )
        if confirmed is not None and self.options.detail_level != confirmed.detail_level:
            raise ValueError("options.detail_level must match confirmed_requirements.detail_level")
        if confirmed is not None and _has_unresolved_confirmation_state(confirmed):
            fields = ", ".join(confirmed.confirmation_fields)
            raise ValueError(
                "confirmed_requirements contains unresolved input conflicts"
                + (f": {fields}" if fields else "")
            )
        return self


def _has_unresolved_confirmation_state(requirements: RequirementSpec) -> bool:
    return any(
        (
            requirements.requires_confirmation,
            bool(requirements.confirmation_fields),
            any(not conflict.resolved for conflict in requirements.conflicts),
            any(
                evidence.conflict or evidence.requires_confirmation
                for evidence in requirements.field_evidence.values()
            ),
        )
    )


class CreateDesignResponse(BaseModel):
    workflow_id: str
    status: str


class UnsupportedAction(BaseModel):
    action: str
    reason: str
    future_requirement: str


class MultimodalIntelligenceCapability(BaseModel):
    status: Literal["disabled", "configured_unverified", "operational", "failed"]
    enabled: bool
    requires_project_consent: bool = True
    max_images_per_request: int = Field(default=3, ge=1, le=3)
    max_image_bytes: int = Field(default=20_000_000, ge=1, le=20_000_000)
    remote_processing: bool = True
    capabilities: list[str] = Field(default_factory=list)
    visual_design_critic: Literal["disabled_until_m5"] = "disabled_until_m5"
    last_error: str | None = None


class RuntimeCapabilities(BaseModel):
    streaming_transport: Literal["push_sse"] = "push_sse"
    event_source: Literal["push_sse"] = "push_sse"
    replay_source: Literal["workflow_events_jsonl"] = "workflow_events_jsonl"
    workflow_id_source: Literal["workflow_id"] = "workflow_id"
    local_process_only: bool = True
    broker: str = "jsonl_replay_plus_in_memory_queue"
    can_stream_events: bool = True
    can_poll_status: bool = True
    can_download_artifacts: bool = True
    can_view_versions: bool = True
    can_edit_completed_design: bool = True
    can_rollback_versions: bool = True
    can_cancel: bool = False
    can_pause: bool = False
    can_resume: bool = False
    can_retry_same_workflow: bool = False
    can_human_in_loop: bool = False
    websocket_runtime: bool = False
    multimodal_intelligence: MultimodalIntelligenceCapability
    limitations: list[str] = Field(default_factory=list)


def _validate_input_analysis_envelope(
    *,
    status: InputAnalysisStatus,
    receipt: RequirementAnalysisReceipt | None,
) -> None:
    """Keep the public analysis claim inseparable from its server receipt.

    A persisted workflow can be older or locally damaged.  The read boundary
    normalizes those records before these models are constructed, while this
    invariant prevents a future projection from accidentally publishing a
    stronger claim than its evidence supports.
    """

    if status == "verified" and receipt is None:
        raise ValueError("verified input analysis status requires a receipt")
    if status != "verified" and receipt is not None:
        raise ValueError("input analysis receipt requires verified status")


class WorkflowStatus(BaseModel):
    workflow_id: str
    status: str
    origin: Literal["PRODUCT", "TEST", "EVALUATION", "IMPORT", "MIGRATION", "UNKNOWN"] = "UNKNOWN"
    created_at: str | None = None
    version_id: str | None = None
    active_version_id: str | None = None
    active_operation: dict | None = None
    multimodal_consent: MultimodalConsent = "disabled"
    artifacts: dict[str, str]
    active_version_artifacts: dict[str, str] | None = None
    warnings: list[dict]
    errors: list[dict]
    extraction_provider: str | None = None
    llm_provider: str | None = None
    llm_available: bool | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = None
    llm_decision_provenance: dict[str, Any] | None = None
    input_analysis: RequirementAnalysisReceipt | None = None
    input_analysis_status: InputAnalysisStatus = "unavailable"
    rag_context_count: int | None = None
    rag_planning_summary: dict | None = None
    rag_reranker_provider: str | None = None
    rag_reranker_model: str | None = None
    rag_reranker_status: str | None = None
    rag_reranker_degraded_reason: str | None = None
    rag_retrieval_status: str | None = None
    rag_retrieval_degraded_reason: str | None = None
    memory_hits: int | None = None
    memory_context_count: int | None = None
    generation_mode: str | None = None
    generation_strategy: str | None = None
    geometry_source: str | None = None
    mesh_qa_level: str | None = None
    mesh_qa_passed: bool | None = None
    blender_available: bool | None = None
    qa_score: float | None = None
    tower_characteristics_summary: dict | None = None
    glb_inspection_summary: dict | None = None
    geometry_validation_summary: dict | None = None
    preview_inspection_summary: dict | None = None
    asset_import_summary: dict | None = None
    asset_imports: list[dict] | None = None
    structural_qa_passed: bool | None = None
    glb_binary_integrity_passed: bool | None = None
    expected_objects_present: bool | None = None
    total_duration_ms: int | None = None
    total_workflow_duration_ms: int | None = None
    metrics: dict[str, int | float | str | bool | None] | None = None
    quality_gates: list[dict] | None = None
    requirement_coverage_passed: bool | None = None
    requirement_coverage_ratio: float | None = None
    completion_certificate_status: Literal["issued", "rejected"] | None = None
    certificate_contract_version: str | None = None
    certificate_coverage_gaps: list[str] = Field(default_factory=list)
    design_domain: str | None = None
    cognitive_plan_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    download_url: str | None = None
    trace_path: str | None = None
    trace_url: str | None = None
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    tower_validation: dict | None = None
    rf_validation: dict | None = None

    @model_validator(mode="after")
    def validate_input_analysis_envelope(self) -> "WorkflowStatus":
        _validate_input_analysis_envelope(
            status=self.input_analysis_status,
            receipt=self.input_analysis,
        )
        return self


class ParseRequirementsRequest(BaseModel):
    chat_id: str | None = Field(default=None, pattern=CHAT_ID_PATTERN)
    document_pack_id: str | None = Field(default=None, pattern=DOCUMENT_PACK_ID_PATTERN)
    requirements_text: str = Field(min_length=1, max_length=5000)
    detail_level: Literal["low", "medium", "high"] = "high"
    use_llm: bool | None = None

    @field_validator("requirements_text")
    @classmethod
    def validate_nonblank_requirements_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirements_text must contain a written request")
        return value

    @model_validator(mode="after")
    def validate_document_pack_binding(self) -> "ParseRequirementsRequest":
        if self.document_pack_id is not None and self.chat_id is None:
            raise ValueError("document_pack_id requires chat_id")
        return self


class ParseRequirementsResponse(BaseModel):
    requirements: RequirementSpec | None
    requirements_hash: str | None = None
    warnings: list[dict]
    errors: list[dict]
    provider: str | None
    extraction_provider: str | None = None
    fallback_used: bool | None
    llm_fallback_reason: str | None = None
    analysis_receipt: RequirementAnalysisReceipt | None = None
    document_context_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class RagSearchResponse(BaseModel):
    query: str
    results: list[dict]


class MemoryVectorReindexResponse(BaseModel):
    status: str
    collections: dict[str, int]
    total_documents: int = Field(ge=0)
    embedding_provider: str
    embedding_dimensions: int = Field(gt=0)
    source_counts: dict[str, int]
    skipped_source_counts: dict[str, int]
    candidate_counts: dict[str, int]
    compacted_points: int = Field(ge=0)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    sqlite_preserved: bool
    legacy_collections_preserved: bool


class EditDesignRequest(BaseModel):
    edit_prompt: str = Field(min_length=1, max_length=1000)
    target_semantic_root: str | None = Field(default=None, min_length=1, max_length=240)
    expected_version_id: str | None = Field(default=None, pattern=r"^v[a-f0-9]{8}$")

    @model_validator(mode="after")
    def validate_target_version_pair(self) -> "EditDesignRequest":
        if (self.target_semantic_root is None) != (self.expected_version_id is None):
            raise ValueError(
                "target_semantic_root and expected_version_id must be provided together"
            )
        return self


class EditDesignResponse(BaseModel):
    workflow_id: str
    edit_id: str
    status: str
    edit_status: str | None = None
    message: str | None = None
    version_id: str | None = None
    diff_summary: dict | None = None
    patch: dict | None = None
    validation_report: dict | None = None
    artifacts: dict[str, str] | None = None
    generation_mode: str | None = None
    llm_decision_provenance: dict[str, Any] | None = None
    qa_score: float | None = None
    extraction_provider: str | None = None
    llm_provider: str | None = None
    llm_available: bool | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = None
    viewer_bundle_url: str | None = None
    timeline_url: str | None = None
    user_issues_url: str | None = None
    current_operation_url: str | None = None
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
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
    llm_decision_provenance: dict[str, Any] | None = None


class PublicVersionInfo(BaseModel):
    version_id: str
    parent_version_id: str | None = None
    created_at: str
    edit_description: str | None = None
    diff_summary: dict | None = None
    status: str | None = None
    active: bool = False
    artifacts: dict[str, str] = Field(default_factory=dict)
    qa_score: float | None = None
    generation_mode: str | None = None
    llm_decision_provenance: dict[str, Any] | None = None


class RollbackVersionResponse(BaseModel):
    workflow_id: str
    version_id: str
    active_version_id: str
    rolled_back: bool
    status: str
    message: str
    viewer_bundle_url: str
    timeline_url: str
    user_issues_url: str
    current_operation_url: str
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)


class WorkflowEventView(BaseModel):
    event_id: str
    sequence: int | None = None
    event_type: str
    workflow_id: str
    timestamp: str
    event_source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DocumentToolCapabilityView(BaseModel):
    name: str
    status: str
    purpose: str
    module: str | None = None
    command: str | None = None
    fallback: str
    warnings: list[str] = Field(default_factory=list)


class DocumentPackCapabilitiesView(BaseModel):
    pdf_text_extraction: DocumentToolCapabilityView
    pdf_table_extraction: DocumentToolCapabilityView
    pdf_layout_extraction: DocumentToolCapabilityView
    ocr: DocumentToolCapabilityView
    dxf_parsing: DocumentToolCapabilityView
    dwg_conversion: DocumentToolCapabilityView
    coordinate_conversion: DocumentToolCapabilityView
    groq_bounded_extraction: DocumentToolCapabilityView
    multimodal_intelligence: MultimodalIntelligenceCapability
    document_pack_status: str
    supported_upload_format: str
    supported_inputs: dict[str, Any]
    supported_extensions: list[str]
    limits: dict[str, Any]
    max_size: dict[str, Any]
    available_tools: list[str]
    disabled_tools: list[str]
    limitations: list[str]
    truth: dict[str, Any]
    next_action: str
    capabilities: dict[str, DocumentToolCapabilityView]


# Product-oriented response models


class AssetInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str
    type: str
    file: str
    file_exists: bool
    asset_file_exists: bool
    asset_import_mode: str
    asset_import_success: bool | None = None
    effective_generation_mode: str
    import_fallback_allowed: bool
    source: str | None = None
    source_provenance: str | None = None
    family: str | None = None
    subtype: str | None = None
    manufacturer: str | None = None
    reference: str | None = None
    original_url: str | None = None
    source_format: str | None = None
    geometry_status: str | None = None
    fidelity_status: str | None = None
    qualification_version: str | None = None
    license: str | None = None
    attribution_required: bool = False
    status: str | None = None
    dimensions_m: dict[str, Any] | None = None
    asset_dimensions_checked: bool = False
    adaptation_profile_id: str | None = None
    qualification_status: str
    generation_eligible: bool
    allowed_generation_modes: list[str] = Field(default_factory=list)
    qualification_method: str | None = None
    qualification_limitations: list[str] = Field(default_factory=list)
    milestone_evidence_eligible: bool = False
    milestone_evidence_failures: list[str] = Field(default_factory=list)
    preview_set: list[dict[str, Any]] = Field(default_factory=list)
    local_evidence_status: Literal["available", "partial", "unavailable", "not_published"] = (
        "not_published"
    )
    reference_evidence_available: bool = False
    provenance_url: str | None = None
    verified_file_sha256: str | None = None
    qualified_file_hash_matches: bool | None = None
    mesh_integrity_verified: bool = False
    pivot_verified: bool = False
    orientation_verified: bool = False
    warnings: list[str] = Field(default_factory=list)


class AssetInventoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    asset_count: int
    asset_count_by_type: dict[str, int] = Field(default_factory=dict)
    missing_file_count: int
    real_glb_asset_count: int
    import_ready_asset_count: int
    import_qualified_glb_count: int
    generation_eligible_asset_count: int
    professional_evidence_asset_count: int
    reference_only_asset_count: int
    qualified_integrity_failure_count: int
    professional_evidence_rejected_count: int = 0
    reference_evidence_missing_count: int = 0
    procedural_fallback_count: int
    parametric_generation_count: int
    procedural_generation_required: bool
    entries: list[AssetInventoryEntry]
    missing_files: list[AssetInventoryEntry] = Field(default_factory=list)


class AssetQualificationReviewCheck(BaseModel):
    check_id: str
    status: Literal["passed", "incomplete"]
    title: str
    detail: str


class AssetQualificationReviewBlocker(BaseModel):
    code: str
    message: str


class AssetQualificationReviewAction(BaseModel):
    action_id: str
    kind: Literal["internal_preview", "external_source"]
    label: str
    url: str


class AssetQualificationReview(BaseModel):
    status: Literal["technical_asset", "reference_only", "blocked", "evidence_invalid", "admitted"]
    summary: str
    checks: list[AssetQualificationReviewCheck] = Field(default_factory=list)
    blockers: list[AssetQualificationReviewBlocker] = Field(default_factory=list)
    available_actions: list[AssetQualificationReviewAction] = Field(default_factory=list)


class AssetProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str
    family: str
    source_format: str
    geometry_status: str
    generation_eligible: bool
    qualification: dict[str, Any]
    qa: dict[str, Any]
    milestone_evidence_eligible: bool
    milestone_evidence_failures: list[str] = Field(default_factory=list)
    usage_rights: dict[str, Any]
    local_evidence_status: Literal["available", "partial", "unavailable", "not_published"]
    representations: list[dict[str, Any]] = Field(default_factory=list)
    previews: list[dict[str, Any]] = Field(default_factory=list)
    review: AssetQualificationReview


class AssetLibrarySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    schema_version: str
    catalog_available: bool = False
    generation_eligible_count: int = 0
    limitations: list[str] = Field(default_factory=list)


class AssetLibrarySearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    result_count: int
    results: list["AssetLibrarySearchEntry"] = Field(default_factory=list)
    selection_policy: str
    generation_eligible: bool
    next_action: str


class AssetLibraryRetrievalEvidence(BaseModel):
    """Explain the bounded catalogue lookup without implying mesh inspection."""

    method: Literal["corpus_idf_metadata"]
    matched_terms: dict[str, list[str]] = Field(default_factory=dict)
    query_coverage: float = Field(ge=0.0, le=1.0)
    geometry_verified: Literal[False] = False


class AssetLibrarySearchEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_id: str
    relative_path: str
    extension: str
    size_bytes: int = Field(ge=0)
    claimed_dimension: str
    category: str
    duplicate_of: str | None = None
    license_status: str
    qualification_status: str
    conversion_status: str
    generation_eligible: bool = False
    reference_preview_file_ids: list[str] = Field(default_factory=list)
    related_cad_file_ids: list[str] = Field(default_factory=list)
    retrieval_score: float | None = None
    retrieval_evidence: AssetLibraryRetrievalEvidence | None = None


class AssetLibraryProbeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: dict[str, Any]
    probe_status: str
    tool: str
    entity_counts: dict[str, int] = Field(default_factory=dict)
    contains_acis_3d_solids: bool
    contains_mesh_convertible_geometry: bool
    conversion_route: str
    blender_ready: bool
    generation_eligible: bool
    limitations: list[str] = Field(default_factory=list)


class AdaptationCapabilityCatalogResponse(BaseModel):
    schema_version: str
    catalog_hash: str
    profiles: list[dict[str, Any]] = Field(default_factory=list)


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
    multimodal_consent: MultimodalConsent = "disabled"
    generation_mode: str | None = None
    generation_strategy: str | None = None
    geometry_source: str | None = None
    mesh_qa_level: str | None = None
    mesh_qa_passed: bool | None = None
    extraction_provider: str | None = None
    llm_provider: str | None = None
    llm_available: bool | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = None
    input_analysis_status: InputAnalysisStatus = "unavailable"
    asset_quality_summary: str | None = None
    limitations: list[str] = Field(default_factory=list)
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)


class UserIssuesResponse(BaseModel):
    workflow_id: str
    status: str
    human_readable_issues: list[UserIssue]


class CurrentOperation(BaseModel):
    workflow_id: str
    status: str
    phase: str | None = None
    current_operation: str
    human_label: str | None = None
    progress_message: str | None = None
    progress_label: str | None = None
    next_recommended_action: str
    progress_indicator: str | None = None
    current_phase: str | None = None
    current_node: str | None = None
    event_source: str = "status"
    state_source: str | None = None
    is_running: bool = False
    is_terminal: bool = False
    last_event_at: str | None = None
    task_started_at: str | None = None
    task_finished_at: str | None = None
    generation_mode: str | None = None
    generation_strategy: str | None = None
    geometry_source: str | None = None
    mesh_qa_level: str | None = None
    mesh_qa_passed: bool | None = None
    extraction_provider: str | None = None
    llm_provider: str | None = None
    llm_available: bool | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = None
    qa_score: float | None = None
    human_warnings_count: int = 0
    human_errors_count: int = 0
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)


class ViewerArtifact(BaseModel):
    name: str
    url: str
    content_type: str
    available: bool


class GeometryFidelityCounts(BaseModel):
    schematic: int = Field(default=0, ge=0)
    technical_generic: int = Field(default=0, ge=0)
    vendor_qualified: int = Field(default=0, ge=0)


class GeometryFidelityRoles(BaseModel):
    schematic: list[str] = Field(default_factory=list)
    technical_generic: list[str] = Field(default_factory=list)
    vendor_qualified: list[str] = Field(default_factory=list)


class GeometryFidelitySummary(BaseModel):
    component_count: int = Field(ge=0)
    counts: GeometryFidelityCounts
    roles: GeometryFidelityRoles


class GeometryProgramItem(BaseModel):
    program_id: str
    semantic_role: str
    requested_quantity: int = Field(ge=1)
    node_count: int = Field(ge=1)
    authorship: Literal["llm_generated", "deterministic_generated"]
    generator_provider: str
    generator_model: str
    structured_output_mode: Literal[
        "strict_json_schema",
        "json_object_validated",
        "json_object_repaired",
    ]
    source_prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_description: str | None = None
    source_description_origin: Literal[
        "user_requirement",
        "revision_preserved",
        "legacy_unavailable",
    ] = "legacy_unavailable"
    placement_context: str | None = None
    maximum_dimensions_m: dict[str, float] | None = None
    limitations: list[str] = Field(default_factory=list)
    deterministic_adjustments: list[str] = Field(default_factory=list)


class GeometryProgramSummary(BaseModel):
    program_count: int = Field(ge=0)
    generated_component_count: int = Field(ge=0)
    total_node_count: int = Field(ge=0)
    repaired_program_count: int = Field(ge=0)
    programs: list[GeometryProgramItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aggregates(self) -> "GeometryProgramSummary":
        if self.program_count != len(self.programs):
            raise ValueError("program_count must equal the number of programs")
        if self.generated_component_count != sum(
            program.requested_quantity for program in self.programs
        ):
            raise ValueError("generated_component_count does not match programs")
        if self.total_node_count != sum(program.node_count for program in self.programs):
            raise ValueError("total_node_count does not match programs")
        if self.repaired_program_count != sum(
            program.structured_output_mode == "json_object_repaired" for program in self.programs
        ):
            raise ValueError("repaired_program_count does not match programs")
        return self


class ViewerQaSummary(BaseModel):
    qa_status: Literal["not_started", "incomplete", "failed", "passed"]
    qa_executed: bool
    blocked_before_qa: bool
    mesh_qa_level: str | None = None
    mesh_qa_passed: bool | None = None
    qa_score: float | None = None
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    upstream_errors: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    geometry_source: str | None = None
    generation_strategy: str | None = None
    object_counts: dict[str, Any] | None = None
    missing_objects: list[str] | None = None
    glb_parse_structural: bool | None = None
    preview_pixel_framing_qa: bool
    preview_subject_framing_valid: bool | None = None
    preview_subject_bbox_width_ratio: float | None = None
    preview_subject_bbox_height_ratio: float | None = None
    preview_subject_center_x_ratio: float | None = None
    preview_subject_min_edge_margin_ratio: float | None = None
    preview_subject_touches_frame: bool | None = None


class AssemblyConstraintSummary(BaseModel):
    status: Literal["passed", "failed", "not_available"]
    measurement_scope: str = Field(min_length=1)
    required_connection_count: int = Field(ge=0)
    measured_instance_count: int = Field(ge=0)
    resolved_support_count: int = Field(default=0, ge=0)
    max_position_error_m: float = Field(ge=0)
    max_angular_error_deg: float = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


class SectorPreviewSummary(BaseModel):
    """Public, selection-safe description of one post-Blender sector preview."""

    sector_id: str = Field(min_length=1)
    preview_url: str = Field(min_length=1)
    semantic_roots: list[str] = Field(min_length=1)
    expected_roles: list[str] = Field(min_length=1)
    exported_roles: list[str] = Field(min_length=1)
    framed_roles: list[str] = Field(min_length=1)
    post_blender_identity_verified: bool
    visual_framing_verified: bool
    subject_bbox_height_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_contrast_mean: float | None = Field(default=None, ge=0.0)
    limitations: list[str] = Field(default_factory=list)


class TowerAccessSummary(BaseModel):
    """Public result of the exported-GLB access geometry inspection."""

    semantic_root: str = Field(min_length=1)
    semantic_role: Literal["tower_access"] = "tower_access"
    interaction_mode: Literal["inspection_only"] = "inspection_only"
    post_blender_geometry_verified: Literal[True] = True
    requested_ladder: bool
    rung_count: int = Field(ge=0)
    platform_levels_m: list[float] = Field(default_factory=list)
    measurement_scope: Literal["exported_glb_tower_access_geometry"]
    limitations: list[str] = Field(default_factory=list)


class ViewerBundle(BaseModel):
    version_id: str | None = None
    workflow_id: str
    status: str
    active_version: str | None = None
    multimodal_consent: MultimodalConsent = "disabled"
    multimodal_intelligence: MultimodalIntelligenceCapability | None = None
    asset_decision_summary: dict[str, Any] | None = None
    visual_review: dict[str, Any] | None = None
    generation_mode: str | None = None
    generation_strategy: str | None = None
    geometry_source: str | None = None
    mesh_qa_level: str | None = None
    mesh_qa_passed: bool | None = None
    qa_score: float | None = None
    asset_import_summary: dict | None = None
    geometry_fidelity_summary: GeometryFidelitySummary | None = None
    geometry_program_summary: GeometryProgramSummary | None = None
    assembly_constraint_summary: AssemblyConstraintSummary | None = None
    sector_previews: list[SectorPreviewSummary] = Field(default_factory=list)
    tower_access_summary: TowerAccessSummary | None = None
    human_warnings_count: int = 0
    human_errors_count: int = 0
    primary_glb_url: str | None = None
    preview_url: str | None = None
    report_url: str | None = None
    metadata_url: str | None = None
    component_proofs_url: str | None = None
    requirements_spec_url: str | None = None
    extraction_report_url: str | None = None
    input_analysis_receipt_url: str | None = None
    scene_spec_url: str | None = None
    assembly_plan_url: str | None = None
    constraint_evidence_url: str | None = None
    tower_access_evidence_url: str | None = None
    qa_report_url: str | None = None
    generation_report_url: str | None = None
    geometry_validation_url: str | None = None
    requirement_coverage_url: str | None = None
    completion_certificate_url: str | None = None
    requirement_coverage_passed: bool | None = None
    requirement_coverage_ratio: float | None = None
    completion_certificate_status: Literal["issued", "rejected"] | None = None
    design_domain: str | None = None
    cognitive_plan_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    cognitive_plan_url: str | None = None
    capability_observations_url: str | None = None
    rag_evidence_url: str | None = None
    extraction_provider: str | None = None
    llm_provider: str | None = None
    llm_available: bool | None = None
    llm_fallback_used: bool | None = None
    llm_fallback_reason: str | None = None
    llm_decision_provenance: dict[str, Any] | None = None
    llm_decision_provenance_url: str | None = None
    input_analysis: RequirementAnalysisReceipt | None = None
    input_analysis_status: InputAnalysisStatus = "unavailable"
    rag_context_count: int | None = None
    rag_planning_summary: dict | None = None
    rag_reranker_provider: str | None = None
    rag_reranker_model: str | None = None
    rag_reranker_status: str | None = None
    rag_reranker_degraded_reason: str | None = None
    rag_retrieval_status: str | None = None
    rag_retrieval_degraded_reason: str | None = None
    memory_context_count: int | None = None
    qa_summary: ViewerQaSummary | None = None
    viewer_artifacts: list[ViewerArtifact]
    limitations: list[str] = Field(default_factory=list)
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input_analysis_envelope(self) -> "ViewerBundle":
        _validate_input_analysis_envelope(
            status=self.input_analysis_status,
            receipt=self.input_analysis,
        )
        return self


class TimelineStep(BaseModel):
    step: str
    node: str | None = None
    label: str | None = None
    human_label: str | None = None
    progress_message: str | None = None
    phase: str | None = None
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    timestamp: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    warnings_count: int = 0
    errors_count: int = 0
    artifact_refs: list[str] = Field(default_factory=list)
    human_readable: str


class TimelineSummary(BaseModel):
    workflow_id: str
    status: str
    event_source: str | None = None
    timeline_steps: list[TimelineStep]


class DesignListSummary(BaseModel):
    workflow_id: str
    status: str
    created_at: str | None = None
    qa_score: float | None = None
    generation_mode: str | None = None
    completion_certificate_status: Literal["issued", "rejected"] | None = None
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
    import_qualified_glb_count: int = 0
    generation_eligible_asset_count: int = 0
    reference_only_asset_count: int = 0
    missing_file_count: int = 0
    blender_available: bool | None = None
    groq_available: bool | None = None
    llm_available: bool | None = None
    rag_embedding_provider: str | None = None
    rag_status: str | None = None
    rag_degraded: bool = False
    rag_reranker: str | None = None
    rag_reranker_status: str | None = None
    rag_reranker_provider: str | None = None
    rag_reranker_model: str | None = None
    rag_reranker_degraded_reason: str | None = None
    rag_operational_status: str | None = None
    rag_last_operation: str | None = None
    rag_reindex_url: str | None = None
    memory_status: str | None = None
    memory_backend: str | None = None
    workflow_memory_count: int = 0
    design_memory_count: int = 0
    document_pack_memory_count: int = 0
    document_pack_issue_memory_count: int = 0
    memory_vector_status: str | None = None
    memory_vector_errors: list[str] = Field(default_factory=list)
    memory_vector_reindex_url: str | None = None
    runtime_capabilities: RuntimeCapabilities | None = None
    unsupported_actions: list[UnsupportedAction] = Field(default_factory=list)
    warnings: list[UserIssue] = Field(default_factory=list)
