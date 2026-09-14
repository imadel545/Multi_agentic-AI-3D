import { z } from "zod";

export const HttpUrlSchema = z.string().url().refine((value) => {
  const protocol = new URL(value).protocol;
  return protocol === "http:" || protocol === "https:";
}, "URL must use HTTP or HTTPS");
import { publicPathIssue } from "./publicUrl";

export const ForbiddenPublicFields = new Set([
  "artifact_dir",
  "absolute_path",
  "filesystem_path",
  "local_path",
  "resolved_path",
  "stacktrace",
  "traceback"
]);

export const UnknownRecord = z.object({}).catchall(z.unknown());
export const WorkflowLifecycleStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "legacy_unverified",
  "integrity_failed"
]);

export class ContractValidationError extends Error {
  constructor(
    public readonly schemaName: string,
    public readonly issues: string[]
  ) {
    super(`${schemaName} response is not compatible with the frontend contract.`);
    this.name = "ContractValidationError";
  }
}

export function forbidInternalPaths(value: unknown, ctx: z.RefinementCtx, path: string[] = []) {
  if (typeof value === "string") {
    const issue = publicPathIssue(value, path.at(-1));
    if (issue) {
      ctx.addIssue({
        code: "custom",
        message: issue,
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

export function publicSchema<T extends z.ZodType>(schema: T) {
  return schema.superRefine((value, ctx) => forbidInternalPaths(value, ctx));
}

export const MultimodalConsentSchema = z.enum([
  "disabled",
  "allow_input_analysis",
  "allow_input_and_visual_review"
]);

export const MultimodalIntelligenceSchema = publicSchema(
  UnknownRecord.extend({
    status: z.enum(["disabled", "configured_unverified", "operational", "failed"]),
    enabled: z.boolean(),
    requires_project_consent: z.literal(true),
    max_images_per_request: z.number().int().positive().max(3),
    max_image_bytes: z.number().int().positive().max(20_000_000),
    remote_processing: z.literal(true),
    capabilities: z.array(z.string()).default([]),
    visual_design_critic: z.literal("disabled_until_m5")
  })
);

export const RuntimeCapabilitiesSchema = UnknownRecord.extend({
  streaming_transport: z.string().optional(),
  workflow_id_source: z.string().optional(),
  local_process_only: z.boolean().optional(),
  websocket_runtime: z.boolean().optional(),
  can_cancel: z.boolean().optional(),
  can_pause: z.boolean().optional(),
  can_resume: z.boolean().optional(),
  can_retry_same_workflow: z.boolean().optional(),
  can_human_in_loop: z.boolean().optional(),
  can_download_artifacts: z.boolean().optional(),
  can_view_versions: z.boolean().optional(),
  can_edit_completed_design: z.boolean().optional(),
  can_rollback_versions: z.boolean().optional(),
  multimodal_intelligence: MultimodalIntelligenceSchema.nullish()
});

export const RequirementWarningSchema = publicSchema(
  UnknownRecord.extend({
    code: z.string(),
    message: z.string()
  })
);

export const RequirementErrorSchema = publicSchema(
  UnknownRecord.extend({
    code: z.string(),
    message: z.string()
  })
);

export const TowerCharacteristicsSchema = UnknownRecord.extend({
  structure: z.string().nullish(),
  leg_count: z.number().nullish(),
  base_width_m: z.number().nullish(),
  top_width_m: z.number().nullish(),
  foundation_type: z.string().nullish(),
  material: z.string().nullish()
});

export const RequirementCandidateEvidenceSchema = UnknownRecord.extend({
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

export const RequirementFieldEvidenceSchema = UnknownRecord.extend({
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

export const RequirementConflictSchema = UnknownRecord.extend({
  field: z.string(),
  candidate_values: z.array(z.unknown()).min(2),
  source_texts: z.array(z.string()).default([]),
  reason: z.string(),
  resolved: z.boolean().default(false),
  resolution: z.string().nullish()
});

export const GeometryVector3Schema = UnknownRecord.extend({
  x: z.number().positive(),
  y: z.number().positive(),
  z: z.number().positive()
});

export const GeometryRequestSchema = UnknownRecord.extend({
  request_id: z.string(),
  semantic_role: z.string(),
  description: z.string(),
  quantity: z.number().int().positive(),
  placement_context: z.string().nullish(),
  maximum_dimensions_m: GeometryVector3Schema.nullish()
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
    geometry_requests: z.array(GeometryRequestSchema).default([]),
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

export const InputAnalysisStatusSchema = z.enum([
  "verified",
  "legacy_unattested",
  "unavailable"
]);

export const RequirementAnalysisReceiptSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.literal("1.0.0"),
    receipt_id: z.string().regex(/^ira_[a-f0-9]{32}$/),
    issued_at: z.string().min(20).max(40),
    confirmed_prompt_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    confirmed_requirements_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    detail_level: z.enum(["low", "medium", "high"]),
    provider: z.string().min(1).max(160),
    model: z.string().min(1).max(160).nullable(),
    extraction_provider: z.string().min(1).max(40),
    fallback_used: z.boolean(),
    fallback_reason: z.string().min(1).max(240).nullable()
  }).superRefine((receipt, ctx) => {
    if (receipt.fallback_used && !receipt.fallback_reason) {
      ctx.addIssue({
        code: "custom",
        message: "fallback analysis receipt requires a fallback reason",
        path: ["fallback_reason"]
      });
    }
    if (!receipt.fallback_used && receipt.fallback_reason !== null) {
      ctx.addIssue({
        code: "custom",
        message: "primary analysis receipt cannot contain a fallback reason",
        path: ["fallback_reason"]
      });
    }
  })
);

export function validateInputAnalysisEnvelope(
  value: {
    input_analysis?: z.infer<typeof RequirementAnalysisReceiptSchema> | null;
    input_analysis_status?: z.infer<typeof InputAnalysisStatusSchema>;
  },
  ctx: z.RefinementCtx
) {
  if (value.input_analysis_status === "verified" && !value.input_analysis) {
    ctx.addIssue({
      code: "custom",
      message: "verified input analysis requires a receipt",
      path: ["input_analysis"]
    });
  }
  if (value.input_analysis && value.input_analysis_status !== "verified") {
    ctx.addIssue({
      code: "custom",
      message: "an input analysis receipt requires verified status",
      path: ["input_analysis_status"]
    });
  }
}

export const ParseRequirementsResponseSchema = publicSchema(
  UnknownRecord.extend({
    requirements: RequirementSpecSchema.nullable(),
    requirements_hash: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
    document_context_hash: z.string().regex(/^[a-f0-9]{64}$/).nullish(),
    warnings: z.array(RequirementWarningSchema).default([]),
    errors: z.array(RequirementErrorSchema).default([]),
    provider: z.string().nullish(),
    extraction_provider: z.string().nullish(),
    fallback_used: z.boolean().nullish(),
    llm_fallback_reason: z.string().nullish(),
    analysis_receipt: RequirementAnalysisReceiptSchema.nullish()
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
    status: z.literal("ok"),
    service: z.literal("agentic_telecom_3d_studio_api"),
    version: z.string(),
    api_contract_version: z.literal("2026-07-29")
  })
);

export const StudioSummarySchema = publicSchema(
  UnknownRecord.extend({
    designs: z.array(UnknownRecord).default([]),
    total_designs: z.number().default(0),
    asset_inventory_status: z.string().nullish(),
    asset_count: z.number().int().nonnegative().default(0),
    real_glb_asset_count: z.number().int().nonnegative().default(0),
    import_qualified_glb_count: z.number().int().nonnegative().default(0),
    generation_eligible_asset_count: z.number().int().nonnegative().default(0),
    reference_only_asset_count: z.number().int().nonnegative().default(0),
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
    rag_retrieval_status: z.string().nullish(),
    rag_retrieval_degraded_reason: z.string().nullish(),
    memory_status: z.string().nullish(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    warnings: z.array(UserIssueSchema).default([])
  })
);

export const LLMDecisionProvenanceSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.string(),
    workflow_id: z.string(),
    version_id: z.string(),
    parent_version_id: z.string().nullish(),
    provider: z.string(),
    model: z.string().nullish(),
    capability_called: z.string(),
    structured_decision: UnknownRecord,
    candidates_considered: z.array(UnknownRecord).default([]),
    strategy_selected: z.array(z.string()).default([]),
    rationale: z.array(z.string()).default([]),
    fallback_used: z.boolean(),
    fallback_reason: z.string().nullish(),
    timestamp: z.string(),
    decision_contract_version: z.string(),
    source_prompt_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    capability_catalog_hash: z.string().regex(/^[a-f0-9]{64}$/),
    links: UnknownRecord
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
    status: WorkflowLifecycleStatusSchema,
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
    llm_decision_provenance: LLMDecisionProvenanceSchema.nullish(),
    input_analysis: RequirementAnalysisReceiptSchema.nullish(),
    input_analysis_status: InputAnalysisStatusSchema.optional(),
    rag_context_count: z.number().nullish(),
    rag_planning_summary: UnknownRecord.nullish(),
    rag_reranker_provider: z.string().nullish(),
    rag_reranker_model: z.string().nullish(),
    rag_reranker_status: z.string().nullish(),
    rag_reranker_degraded_reason: z.string().nullish(),
    rag_retrieval_status: z.string().nullish(),
    rag_retrieval_degraded_reason: z.string().nullish(),
    memory_context_count: z.number().nullish(),
    asset_import_summary: UnknownRecord.nullish(),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  }).superRefine((status, ctx) => validateInputAnalysisEnvelope(status, ctx))
);

export const EventPayloadSchema = UnknownRecord.extend({
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

