import { z } from "zod";

const ForbiddenPublicFields = new Set([
  "artifact_dir",
  "filesystem_path",
  "local_path",
  "resolved_path"
]);
const ForbiddenStringMarkers = ["/Users/"];

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
  can_human_in_loop: z.boolean().optional()
});

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

export const DocumentPackCapabilitiesSchema = publicSchema(
  UnknownRecord.extend({
    document_pack_status: z.string(),
    supported_upload_format: z.string(),
    supported_extensions: z.array(z.string()).default([]),
    limitations: z.array(z.string()).default([]),
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
    conflict_count: z.number().default(0),
    can_generate_design: z.boolean().default(false),
    qa_score: z.number().nullish(),
    processing_warning_count: z.number().default(0),
    tool_status: z.record(z.string(), z.string()).default({})
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
    created_at: z.string(),
    active: z.boolean().default(false),
    artifacts: z.record(z.string(), z.string()).default({}),
    qa_score: z.number().nullish(),
    generation_mode: z.string().nullish()
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
export type DocumentPackCapabilities = z.infer<typeof DocumentPackCapabilitiesSchema>;
export type DocumentPackSummary = z.infer<typeof DocumentPackSummarySchema>;
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
