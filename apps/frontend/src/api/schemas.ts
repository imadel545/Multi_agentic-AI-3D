import { z } from "zod";

const ForbiddenPublicFields = new Set([
  "artifact_dir",
  "absolute_path",
  "filesystem_path",
  "local_path",
  "resolved_path",
  "stacktrace",
  "traceback"
]);
const ForbiddenStringMarkers = ["/Users/", "/home/", "/private/var/", "/var/folders/", "file://"];

const UnknownRecord = z.object({}).catchall(z.unknown());

export class ContractValidationError extends Error {
  constructor(
    public readonly schemaName: string,
    public readonly issues: string[]
  ) {
    super(`${schemaName} response is not compatible with the frontend contract.`);
    this.name = "ContractValidationError";
  }
}

function forbidInternalPaths(value: unknown, ctx: z.RefinementCtx, path: string[] = []) {
  if (typeof value === "string") {
    for (const marker of ForbiddenStringMarkers) {
      if (value.includes(marker)) {
        ctx.addIssue({
          code: "custom",
          message: `internal filesystem marker ${marker} is not allowed`,
          path
        });
      }
    }
    if (/^[A-Za-z]:[\\/]/.test(value)) {
      ctx.addIssue({
        code: "custom",
        message: "absolute Windows filesystem paths are not allowed",
        path
      });
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => forbidInternalPaths(item, ctx, [...path, String(index)]));
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      if (ForbiddenPublicFields.has(key)) {
        ctx.addIssue({
          code: "custom",
          message: `internal field ${key} is not allowed in public frontend payloads`,
          path: [...path, key]
        });
      }
      forbidInternalPaths(nested, ctx, [...path, key]);
    }
  }
}

function publicSchema<T extends z.ZodType>(schema: T) {
  return schema.superRefine((value, ctx) => forbidInternalPaths(value, ctx));
}

const RuntimeCapabilitiesSchema = UnknownRecord.extend({
  streaming_transport: z.string().optional(),
  workflow_id_source: z.string().optional(),
  local_process_only: z.boolean().optional(),
  websocket_runtime: z.boolean().optional(),
  can_cancel: z.boolean().optional(),
  can_pause: z.boolean().optional(),
  can_resume: z.boolean().optional(),
  can_retry_same_workflow: z.boolean().optional(),
  can_human_in_loop: z.boolean().optional(),
  can_view_versions: z.boolean().optional(),
  can_edit_completed_design: z.boolean().optional(),
  can_rollback_versions: z.boolean().optional()
});

const RequirementWarningSchema = publicSchema(
  UnknownRecord.extend({
    code: z.string(),
    message: z.string()
  })
);

const RequirementErrorSchema = publicSchema(
  UnknownRecord.extend({
    code: z.string(),
    message: z.string()
  })
);

const TowerCharacteristicsSchema = UnknownRecord.extend({
  structure: z.string().nullish(),
  leg_count: z.number().nullish(),
  base_width_m: z.number().nullish(),
  top_width_m: z.number().nullish(),
  foundation_type: z.string().nullish(),
  material: z.string().nullish()
});

const RequirementCandidateEvidenceSchema = UnknownRecord.extend({
  value: z.unknown(),
  source: z.enum([
    "user_text",
    "llm",
    "deterministic",
    "default",
    "document",
    "user_confirmation",
    "repair"
  ]),
  source_text: z.string().nullish(),
  mechanism: z.string(),
  confidence: z.number().min(0).max(1),
  selected: z.boolean().default(false),
  rationale: z.string().nullish()
});

const RequirementFieldEvidenceSchema = UnknownRecord.extend({
  field: z.string(),
  selected_value: z.unknown(),
  selected_source: RequirementCandidateEvidenceSchema.shape.source,
  confidence: z.number().min(0).max(1),
  explicit: z.boolean(),
  defaulted: z.boolean(),
  candidates: z.array(RequirementCandidateEvidenceSchema).default([]),
  conflict: z.boolean().default(false),
  requires_confirmation: z.boolean().default(false),
  rationale: z.string()
});

const RequirementConflictSchema = UnknownRecord.extend({
  field: z.string(),
  candidate_values: z.array(z.unknown()).min(2),
  source_texts: z.array(z.string()).default([]),
  reason: z.string(),
  resolved: z.boolean().default(false),
  resolution: z.string().nullish()
});

export const RequirementSpecSchema = publicSchema(
  UnknownRecord.extend({
    network_type: z.string(),
    site_type: z.string(),
    tower_type: z.string(),
    tower_height_m: z.number(),
    tower_characteristics: TowerCharacteristicsSchema,
    sector_count: z.number().int(),
    antenna_type: z.string(),
    antenna_install_height_m: z.number(),
    azimuths_deg: z.array(z.number()),
    mechanical_tilt_deg: z.number(),
    electrical_tilt_deg: z.number(),
    beamwidth_deg: z.number(),
    include_rru: z.boolean(),
    include_cables: z.boolean(),
    include_beams: z.boolean(),
    include_labels: z.boolean(),
    include_power_cabinet: z.boolean(),
    include_gps_antenna: z.boolean(),
    detail_level: z.string(),
    warnings: z.array(RequirementWarningSchema).default([]),
    repair_events: z.array(UnknownRecord).default([]),
    field_evidence: z.record(z.string(), RequirementFieldEvidenceSchema).default({}),
    conflicts: z.array(RequirementConflictSchema).default([]),
    assumptions: z.array(z.string()).default([]),
    requires_confirmation: z.boolean().default(false),
    confirmation_fields: z.array(z.string()).default([])
  })
);

export const ParseRequirementsResponseSchema = publicSchema(
  UnknownRecord.extend({
    requirements: RequirementSpecSchema.nullable(),
    requirements_hash: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
    warnings: z.array(RequirementWarningSchema).default([]),
    errors: z.array(RequirementErrorSchema).default([]),
    provider: z.string().nullish(),
    extraction_provider: z.string().nullish(),
    fallback_used: z.boolean().nullish(),
    llm_fallback_reason: z.string().nullish()
  })
);

export const UnsupportedActionSchema = UnknownRecord.extend({
  action: z.string(),
  reason: z.string().optional(),
  future_requirement: z.string().optional()
});

export const UserIssueSchema = publicSchema(
  UnknownRecord.extend({
    title: z.string(),
    severity: z.enum(["info", "warning", "error"]),
    impact: z.string(),
    recommended_action: z.string(),
    technical_code: z.string().nullish()
  })
);

export const HealthSchema = publicSchema(
  UnknownRecord.extend({
    status: z.string(),
    version: z.string().optional()
  })
);

export const StudioSummarySchema = publicSchema(
  UnknownRecord.extend({
    designs: z.array(UnknownRecord).default([]),
    total_designs: z.number().default(0),
    asset_inventory_status: z.string().nullish(),
    blender_available: z.boolean().nullish(),
    groq_available: z.boolean().nullish(),
    llm_available: z.boolean().nullish(),
    rag_embedding_provider: z.string().nullish(),
    rag_status: z.string().nullish(),
    rag_degraded: z.boolean().default(false),
    rag_reranker_provider: z.string().nullish(),
    rag_reranker_model: z.string().nullish(),
    rag_reranker_status: z.string().nullish(),
    rag_reranker_degraded_reason: z.string().nullish(),
    memory_status: z.string().nullish(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    warnings: z.array(UserIssueSchema).default([])
  })
);

export const CreateDesignResponseSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string().min(1),
    status: z.string().min(1)
  })
);

export const WorkflowStatusSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string().min(1),
    status: z.enum(["pending", "running", "completed", "failed"]).or(z.string()),
    created_at: z.string().nullish(),
    artifacts: z.record(z.string(), z.string()).default({}),
    warnings: z.array(UnknownRecord).default([]),
    errors: z.array(UnknownRecord).default([]),
    generation_mode: z.string().nullish(),
    generation_strategy: z.string().nullish(),
    geometry_source: z.string().nullish(),
    mesh_qa_level: z.string().nullish(),
    mesh_qa_passed: z.boolean().nullish(),
    blender_available: z.boolean().nullish(),
    qa_score: z.number().nullish(),
    glb_binary_integrity_passed: z.boolean().nullish(),
    requirement_coverage_passed: z.boolean().nullish(),
    requirement_coverage_ratio: z.number().min(0).max(1).nullish(),
    completion_certificate_status: z.enum(["issued", "rejected"]).nullish(),
    llm_provider: z.string().nullish(),
    llm_available: z.boolean().nullish(),
    llm_fallback_used: z.boolean().nullish(),
    llm_fallback_reason: z.string().nullish(),
    rag_context_count: z.number().nullish(),
    rag_planning_summary: UnknownRecord.nullish(),
    rag_reranker_provider: z.string().nullish(),
    rag_reranker_model: z.string().nullish(),
    rag_reranker_status: z.string().nullish(),
    rag_reranker_degraded_reason: z.string().nullish(),
    memory_context_count: z.number().nullish(),
    asset_import_summary: UnknownRecord.nullish(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  })
);

const EventPayloadSchema = UnknownRecord.extend({
  phase: z.string().nullish(),
  node: z.string().nullish(),
  human_label: z.string().nullish(),
  progress_message: z.string().nullish(),
  status: z.string().nullish(),
  duration_ms: z.number().nullish(),
  warnings: z.array(z.unknown()).default([]),
  errors: z.array(z.unknown()).default([]),
  artifact_refs: z.array(z.string()).default([])
});

export const WorkflowEventSchema = publicSchema(
  UnknownRecord.extend({
    event_id: z.string().min(1),
    sequence: z.number().int().positive().nullish(),
    event_type: z.string().min(1),
    workflow_id: z.string().min(1),
    timestamp: z.string().min(1),
    event_source: z.string().nullish(),
    payload: EventPayloadSchema.default({ artifact_refs: [], errors: [], warnings: [] })
  })
);

const ViewerArtifactSchema = publicSchema(
  UnknownRecord.extend({
    name: z.string(),
    url: z.string(),
    content_type: z.string(),
    available: z.boolean()
  })
);

export const ViewerBundleSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    status: z.string(),
    generation_mode: z.string().nullish(),
    generation_strategy: z.string().nullish(),
    geometry_source: z.string().nullish(),
    mesh_qa_level: z.string().nullish(),
    mesh_qa_passed: z.boolean().nullish(),
    qa_score: z.number().nullish(),
    asset_import_summary: UnknownRecord.nullish(),
    human_warnings_count: z.number().default(0),
    human_errors_count: z.number().default(0),
    primary_glb_url: z.string().nullish(),
    preview_url: z.string().nullish(),
    report_url: z.string().nullish(),
    metadata_url: z.string().nullish(),
    scene_spec_url: z.string().nullish(),
    qa_report_url: z.string().nullish(),
    generation_report_url: z.string().nullish(),
    geometry_validation_url: z.string().nullish(),
    requirement_coverage_url: z.string().nullish(),
    completion_certificate_url: z.string().nullish(),
    requirement_coverage_passed: z.boolean().nullish(),
    requirement_coverage_ratio: z.number().min(0).max(1).nullish(),
    completion_certificate_status: z.enum(["issued", "rejected"]).nullish(),
    rag_evidence_url: z.string().nullish(),
    requirements_spec_url: z.string().nullish(),
    extraction_report_url: z.string().nullish(),
    llm_provider: z.string().nullish(),
    llm_available: z.boolean().nullish(),
    llm_fallback_used: z.boolean().nullish(),
    llm_fallback_reason: z.string().nullish(),
    rag_context_count: z.number().nullish(),
    rag_planning_summary: UnknownRecord.nullish(),
    rag_reranker_provider: z.string().nullish(),
    rag_reranker_model: z.string().nullish(),
    rag_reranker_status: z.string().nullish(),
    rag_reranker_degraded_reason: z.string().nullish(),
    memory_context_count: z.number().nullish(),
    qa_summary: UnknownRecord.nullish(),
    viewer_artifacts: z.array(ViewerArtifactSchema).default([]),
    limitations: z.array(z.string()).default([]),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  })
);

export const TimelineStepSchema = publicSchema(
  UnknownRecord.extend({
    step: z.string(),
    node: z.string().nullish(),
    label: z.string().nullish(),
    human_label: z.string().nullish(),
    progress_message: z.string().nullish(),
    phase: z.string().nullish(),
    status: z.string(),
    timestamp: z.string().nullish(),
    duration_ms: z.number().nullish(),
    warnings_count: z.number().default(0),
    errors_count: z.number().default(0),
    artifact_refs: z.array(z.string()).default([]),
    human_readable: z.string()
  })
);

export const TimelineSummarySchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    status: z.string(),
    event_source: z.string().nullish(),
    timeline_steps: z.array(TimelineStepSchema).default([])
  })
);

export const CurrentOperationSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    status: z.string(),
    current_operation: z.string(),
    phase: z.string().nullish(),
    current_phase: z.string().nullish(),
    current_node: z.string().nullish(),
    human_label: z.string().nullish(),
    progress_message: z.string().nullish(),
    progress_label: z.string().nullish(),
    event_source: z.string().nullish(),
    state_source: z.string().nullish(),
    progress_indicator: z.string().nullish(),
    is_running: z.boolean().default(false),
    is_terminal: z.boolean().default(false),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  })
);

export const UserIssuesSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    status: z.string(),
    human_readable_issues: z.array(UserIssueSchema).default([])
  })
);

export const AssetInventorySchema = publicSchema(
  UnknownRecord.extend({
    status: z.string(),
    asset_count: z.number(),
    missing_file_count: z.number(),
    real_glb_asset_count: z.number(),
    entries: z.array(UnknownRecord).default([]),
    missing_files: z.array(UnknownRecord).default([])
  })
);

export const AssetLibrarySummarySchema = publicSchema(
  UnknownRecord.extend({
    status: z.string(),
    schema_version: z.string(),
    catalog_available: z.boolean().default(false),
    file_count: z.number().int().nonnegative().optional(),
    unique_content_count: z.number().int().nonnegative().optional(),
    duplicate_file_count: z.number().int().nonnegative().optional(),
    generation_eligible_count: z.number().int().nonnegative().default(0),
    cad_with_reference_preview_count: z.number().int().nonnegative().default(0),
    reference_preview_link_count: z.number().int().nonnegative().default(0),
    claimed_dimension_counts: z.record(z.string(), z.number().int().nonnegative()).optional(),
    extension_counts: z.record(z.string(), z.number().int().nonnegative()).optional(),
    license_status: z.string().optional(),
    dwg_probe_available: z.boolean().optional(),
    limitations: z.array(z.string()).default([])
  })
);

export const AssetLibraryEntrySchema = publicSchema(
  UnknownRecord.extend({
    file_id: z.string(),
    relative_path: z.string(),
    extension: z.string(),
    size_bytes: z.number().int().nonnegative(),
    claimed_dimension: z.string(),
    category: z.string(),
    duplicate_of: z.string().nullish(),
    license_status: z.string(),
    qualification_status: z.string(),
    conversion_status: z.string(),
    generation_eligible: z.boolean().default(false),
    reference_preview_file_ids: z.array(z.string()).default([]),
    related_cad_file_ids: z.array(z.string()).default([]),
    retrieval_score: z.number().optional()
  })
);

export const AssetLibrarySearchSchema = publicSchema(
  UnknownRecord.extend({
    query: z.string(),
    filters: z.record(z.string(), z.unknown()).default({}),
    result_count: z.number().int().nonnegative(),
    results: z.array(AssetLibraryEntrySchema).default([]),
    selection_policy: z.string(),
    generation_eligible: z.boolean().default(false),
    next_action: z.string()
  })
);

export const ResolvedAdaptationCapabilitySchema = publicSchema(
  UnknownRecord.extend({
    capability_id: z.string(),
    asset_id: z.string().nullish(),
    profile_id: z.string(),
    label: z.string(),
    path: z.string(),
    value_type: z.string(),
    execution_tool: z.string(),
    effect: z.string(),
    description: z.string(),
    unit: z.string().nullish(),
    minimum: z.number().nullish(),
    maximum: z.number().nullish(),
    allowed_values: z.array(z.union([z.string(), z.number(), z.boolean()])).default([]),
    requires_regeneration: z.boolean().default(true)
  })
);

export const SceneAdaptationCapabilitiesSchema = publicSchema(
  UnknownRecord.extend({
    scene_id: z.string(),
    catalog_version: z.string(),
    catalog_hash: z.string(),
    capabilities: z.array(ResolvedAdaptationCapabilitySchema).default([]),
    unsupported_operations: z.array(z.string()).default([]),
    missing_profiles: z.array(z.string()).default([])
  })
);

export const AdaptationCapabilityCatalogSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.string(),
    catalog_hash: z.string(),
    profiles: z.array(UnknownRecord).default([])
  })
);

export const DocumentPackCapabilitiesSchema = publicSchema(
  UnknownRecord.extend({
    document_pack_status: z.string(),
    supported_upload_format: z.string(),
    supported_extensions: z.array(z.string()).default([]),
    limitations: z.array(z.string()).default([]),
    limits: UnknownRecord.extend({
      max_zip_size_mb: z.number().positive().optional(),
      max_member_size_mb: z.number().positive().optional(),
      max_member_count: z.number().int().positive().optional(),
      max_uncompressed_size_mb: z.number().positive().optional(),
      processing_mode: z.string().optional(),
      execution: z.string().optional()
    }).optional(),
    truth: UnknownRecord.default({}),
    capabilities: z.record(z.string(), UnknownRecord).default({})
  })
);

export const DocumentPackSummarySchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    status: z.string(),
    document_count: z.number().default(0),
    high_priority_count: z.number().default(0),
    missing_blocking_count: z.number().default(0),
    blocking_fields: z.array(z.string()).default([]),
    conflict_count: z.number().default(0),
    can_generate_design: z.boolean().default(false),
    qa_score: z.number().nullish(),
    processing_warning_count: z.number().default(0),
    tool_status: z.record(z.string(), z.string()).default({})
  })
);

export const DocumentPackFieldSchema = publicSchema(
  UnknownRecord.extend({
    field: z.string(),
    value: z.unknown().nullish(),
    status: z.string(),
    confidence: z.number(),
    sources: z.array(UnknownRecord).default([]),
    values: z.array(z.unknown()).default([]),
    severity: z.string().nullish(),
    resolution: z.string().nullish(),
    reason: z.string().nullish()
  })
);

export const DocumentSourceEvidenceSchema = publicSchema(
  UnknownRecord.extend({
    document_id: z.string(),
    file: z.string(),
    source_type: z.string(),
    page: z.number().int().positive().nullish(),
    sheet: z.string().nullish(),
    layer: z.string().nullish(),
    confidence: z.number().nullish(),
    evidence: z.string()
  })
);

export const DocumentReferenceSchema = publicSchema(
  UnknownRecord.extend({
    document_id: z.string(),
    path: z.string(),
    filename: z.string(),
    extension: z.string(),
    size_bytes: z.number().nonnegative(),
    category: z.string(),
    relevance_score: z.number(),
    confidence: z.number(),
    reason: z.string(),
    priority: z.string(),
    purpose: z.string(),
    used_for_design: z.boolean(),
    why_used_or_ignored: z.string(),
    extraction_status: z.string(),
    processing_tools: z.array(z.string()).default([]),
    processing_warnings: z.array(z.string()).default([]),
    duplicate_of: z.string().nullish()
  })
);

export const DocumentExtractionSchema = publicSchema(
  UnknownRecord.extend({
    field: z.string(),
    value: z.unknown(),
    confidence: z.number(),
    source: DocumentSourceEvidenceSchema
  })
);

const DocumentProcessingReferenceSchema = publicSchema(
  UnknownRecord.extend({
    document_id: z.string(),
    path: z.string(),
    extension: z.string(),
    category: z.string(),
    extractability: z.string(),
    extraction_status: z.string(),
    cad_status: z.string(),
    processing_tools: z.array(z.string()).default([]),
    processing_warnings: z.array(z.string()).default([])
  })
);

export const DocumentPackProcessingSchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    documents: z.array(DocumentProcessingReferenceSchema).default([]),
    warnings: z.array(z.string()).default([]),
    tool_status: z.record(z.string(), z.string()).default({}),
    groq_rejected_fields: z.array(UnknownRecord).default([])
  })
);

export const DocumentPackProvenanceSchema = publicSchema(
  z.record(z.string(), z.array(DocumentSourceEvidenceSchema))
);

export const DocumentPackConsolidatedSpecSchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    source_mode: z.string(),
    llm_provider: z.string().nullish(),
    llm_fallback_used: z.boolean().nullish(),
    confidence_summary: z.record(z.string(), z.number()),
    processing_warnings: z.array(z.string()).default([]),
    document_references: z.array(DocumentReferenceSchema).default([]),
    provenance_map: z.record(z.string(), z.array(DocumentSourceEvidenceSchema)).default({})
  })
);

const DocumentPackQACheckSchema = publicSchema(
  UnknownRecord.extend({
    name: z.string(),
    passed: z.boolean(),
    reason: z.string()
  })
);

export const DocumentPackQASchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    status: z.string(),
    score: z.number(),
    checks: z.array(DocumentPackQACheckSchema).default([]),
    warnings: z.array(z.string()).default([]),
    blocking_issues: z.array(z.string()).default([]),
    ready_to_generate: z.boolean(),
    ready_confidence: z.number(),
    recommended_user_actions: z.array(z.string()).default([]),
    tool_failures: z.array(z.string()).default([]),
    memory_writeback: UnknownRecord.default({})
  })
);

export const DocumentPackGenerateDesignResponseSchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    status: z.string(),
    workflow_id: z.string().nullish(),
    mapping: UnknownRecord.nullish(),
    extraction_report: UnknownRecord.nullish()
  })
);

export const PublicVersionInfoSchema = publicSchema(
  UnknownRecord.extend({
    version_id: z.string(),
    parent_version_id: z.string().nullish(),
    created_at: z.string(),
    active: z.boolean().default(false),
    artifacts: z.record(z.string(), z.string()).default({}),
    qa_score: z.number().nullish(),
    generation_mode: z.string().nullish(),
    edit_description: z.string().nullish(),
    diff_summary: UnknownRecord.nullish(),
    status: z.string().nullish()
  })
);

export const EditDesignResponseSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    edit_id: z.string(),
    status: z.string(),
    edit_status: z.string().nullish(),
    message: z.string().nullish(),
    version_id: z.string().nullish(),
    diff_summary: UnknownRecord.nullish(),
    patch: UnknownRecord.nullish(),
    validation_report: UnknownRecord.nullish(),
    artifacts: z.record(z.string(), z.string()).nullish(),
    generation_mode: z.string().nullish(),
    qa_score: z.number().nullish(),
    extraction_provider: z.string().nullish(),
    llm_provider: z.string().nullish(),
    llm_available: z.boolean().nullish(),
    llm_fallback_used: z.boolean().nullish(),
    llm_fallback_reason: z.string().nullish(),
    viewer_bundle_url: z.string().nullish(),
    timeline_url: z.string().nullish(),
    user_issues_url: z.string().nullish(),
    current_operation_url: z.string().nullish(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([]),
    errors: z.array(UnknownRecord).default([]),
    warnings: z.array(UnknownRecord).default([])
  })
);

export const RollbackVersionResponseSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    version_id: z.string(),
    active_version_id: z.string(),
    active_operation: z
      .object({
        kind: z.string(),
        operation_id: z.string(),
        status: z.string(),
        human_label: z.string(),
        started_at: z.string()
      })
      .optional(),
    rolled_back: z.boolean(),
    status: z.string(),
    message: z.string(),
    viewer_bundle_url: z.string(),
    timeline_url: z.string(),
    user_issues_url: z.string(),
    current_operation_url: z.string(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  })
);

export const VersionsSchema = z.array(PublicVersionInfoSchema);

export type Health = z.infer<typeof HealthSchema>;
export type StudioSummary = z.infer<typeof StudioSummarySchema>;
export type RequirementSpec = z.infer<typeof RequirementSpecSchema>;
export type ParseRequirementsResponse = z.infer<typeof ParseRequirementsResponseSchema>;
export type CreateDesignResponse = z.infer<typeof CreateDesignResponseSchema>;
export type WorkflowStatus = z.infer<typeof WorkflowStatusSchema>;
export type WorkflowEvent = z.infer<typeof WorkflowEventSchema>;
export type ViewerBundle = z.infer<typeof ViewerBundleSchema>;
export type TimelineSummary = z.infer<typeof TimelineSummarySchema>;
export type TimelineStep = z.infer<typeof TimelineStepSchema>;
export type CurrentOperation = z.infer<typeof CurrentOperationSchema>;
export type UserIssues = z.infer<typeof UserIssuesSchema>;
export type UserIssue = z.infer<typeof UserIssueSchema>;
export type AssetInventory = z.infer<typeof AssetInventorySchema>;
export type AssetLibrarySummary = z.infer<typeof AssetLibrarySummarySchema>;
export type AssetLibraryEntry = z.infer<typeof AssetLibraryEntrySchema>;
export type AssetLibrarySearch = z.infer<typeof AssetLibrarySearchSchema>;
export type AdaptationCapabilityCatalog = z.infer<typeof AdaptationCapabilityCatalogSchema>;
export type SceneAdaptationCapabilities = z.infer<typeof SceneAdaptationCapabilitiesSchema>;
export type ResolvedAdaptationCapability = z.infer<typeof ResolvedAdaptationCapabilitySchema>;
export type DocumentPackCapabilities = z.infer<typeof DocumentPackCapabilitiesSchema>;
export type DocumentPackSummary = z.infer<typeof DocumentPackSummarySchema>;
export type DocumentPackField = z.infer<typeof DocumentPackFieldSchema>;
export type DocumentPackQA = z.infer<typeof DocumentPackQASchema>;
export type DocumentReference = z.infer<typeof DocumentReferenceSchema>;
export type DocumentExtraction = z.infer<typeof DocumentExtractionSchema>;
export type DocumentSourceEvidence = z.infer<typeof DocumentSourceEvidenceSchema>;
export type DocumentPackProcessing = z.infer<typeof DocumentPackProcessingSchema>;
export type DocumentPackProvenance = z.infer<typeof DocumentPackProvenanceSchema>;
export type DocumentPackConsolidatedSpec = z.infer<typeof DocumentPackConsolidatedSpecSchema>;
export type DocumentPackReview = {
  summary: DocumentPackSummary;
  conflicts: DocumentPackField[];
  missingFields: DocumentPackField[];
  qa: DocumentPackQA;
  documents: DocumentReference[];
  extractions: DocumentExtraction[];
  provenance: DocumentPackProvenance;
  processing: DocumentPackProcessing;
  consolidatedSpec: DocumentPackConsolidatedSpec;
};
export type DocumentPackGenerateDesignResponse = z.infer<typeof DocumentPackGenerateDesignResponseSchema>;
export type PublicVersionInfo = z.infer<typeof PublicVersionInfoSchema>;
export type EditDesignResponse = z.infer<typeof EditDesignResponseSchema>;
export type RollbackVersionResponse = z.infer<typeof RollbackVersionResponseSchema>;

export function parseContract<T>(schemaName: string, schema: z.ZodType<T>, payload: unknown): T {
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new ContractValidationError(
      schemaName,
      result.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`)
    );
  }
  return result.data;
}
