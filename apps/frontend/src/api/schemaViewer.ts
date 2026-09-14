import { z } from "zod";
import {
  InputAnalysisStatusSchema,
  GeometryVector3Schema,
  LLMDecisionProvenanceSchema,
  MultimodalConsentSchema,
  MultimodalIntelligenceSchema,
  RequirementAnalysisReceiptSchema,
  RuntimeCapabilitiesSchema,
  UnsupportedActionSchema,
  UnknownRecord,
  UserIssueSchema,
  WorkflowLifecycleStatusSchema,
  validateInputAnalysisEnvelope,
  publicSchema
} from "./schemaCore";


export const ViewerArtifactSchema = publicSchema(
  UnknownRecord.extend({
    name: z.string(),
    url: z.string(),
    content_type: z.string(),
    available: z.boolean()
  })
);

export const GeometryFidelityCountsSchema = UnknownRecord.extend({
  schematic: z.number().int().nonnegative(),
  technical_generic: z.number().int().nonnegative(),
  vendor_qualified: z.number().int().nonnegative()
});

export const GeometryFidelityRolesSchema = UnknownRecord.extend({
  schematic: z.array(z.string()).default([]),
  technical_generic: z.array(z.string()).default([]),
  vendor_qualified: z.array(z.string()).default([])
});

export const GeometryProgramItemSchema = UnknownRecord.extend({
  program_id: z.string(),
  origin: z.enum(["geometry_program", "catalog_asset"]).optional(),
  semantic_role: z.string(),
  requested_quantity: z.number().int().positive(),
  node_count: z.number().int().positive(),
  authorship: z.enum(["llm_generated", "deterministic_generated"]),
  generator_provider: z.string(),
  generator_model: z.string(),
  structured_output_mode: z.enum([
    "strict_json_schema",
    "json_object_validated",
    "json_object_repaired"
  ]),
  source_prompt_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  source_description: z.string().nullish(),
  source_description_origin: z.enum([
    "user_requirement",
    "revision_preserved",
    "legacy_unavailable"
  ]).default("legacy_unavailable"),
  placement_context: z.string().nullish(),
  maximum_dimensions_m: GeometryVector3Schema.nullish(),
  limitations: z.array(z.string()).default([]),
  deterministic_adjustments: z.array(z.string()).default([])
});

export const GeometryProgramSummarySchema = UnknownRecord.extend({
  program_count: z.number().int().nonnegative(),
  generated_component_count: z.number().int().nonnegative(),
  reused_component_count: z.number().int().nonnegative().optional(),
  total_node_count: z.number().int().nonnegative(),
  repaired_program_count: z.number().int().nonnegative(),
  programs: z.array(GeometryProgramItemSchema).default([])
}).superRefine((value, ctx) => {
  const expected = {
    program_count: value.programs.length,
    generated_component_count: value.programs.reduce(
      (total, program) => total + (program.origin === "catalog_asset" ? 0 : program.requested_quantity),
      0
    ),
    reused_component_count: value.programs.reduce(
      (total, program) => total + (program.origin === "catalog_asset" ? program.requested_quantity : 0),
      0
    ),
    total_node_count: value.programs.reduce(
      (total, program) => total + program.node_count,
      0
    ),
    repaired_program_count: value.programs.filter(
      (program) => program.structured_output_mode === "json_object_repaired"
    ).length
  };
  for (const [field, expectedValue] of Object.entries(expected)) {
    const actual = value[field as keyof typeof expected] ?? (field === "reused_component_count" ? 0 : undefined);
    if (actual !== expectedValue) {
      ctx.addIssue({
        code: "custom",
        message: `${field} does not match programs`,
        path: [field]
      });
    }
  }
});

export const GeometryFidelitySummarySchema = publicSchema(
  UnknownRecord.extend({
    component_count: z.number().int().nonnegative(),
    counts: GeometryFidelityCountsSchema,
    roles: GeometryFidelityRolesSchema
  }).superRefine((value, ctx) => {
    const countedComponents =
      value.counts.schematic +
      value.counts.technical_generic +
      value.counts.vendor_qualified;
    if (countedComponents !== value.component_count) {
      ctx.addIssue({
        code: "custom",
        message: "geometry fidelity counts must equal component_count",
        path: ["counts"]
      });
    }
  })
);

export const ViewerQaSummarySchema = UnknownRecord.extend({
  qa_status: z.enum(["not_started", "incomplete", "failed", "passed"]).optional(),
  qa_executed: z.boolean().optional(),
  blocked_before_qa: z.boolean().optional(),
  mesh_qa_level: z.string().nullish(),
  mesh_qa_passed: z.boolean().nullish(),
  qa_score: z.number().nullish(),
  checks_passed: z.array(z.string()).default([]),
  checks_failed: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  errors: z.array(z.string()).default([]),
  upstream_errors: z.array(z.string()).default([]),
  limitations: z.array(z.string()).default([]),
  geometry_source: z.string().nullish(),
  generation_strategy: z.string().nullish(),
  object_counts: UnknownRecord.nullish(),
  missing_objects: z.array(z.string()).nullish(),
  glb_parse_structural: z.boolean().nullish(),
  preview_pixel_framing_qa: z.boolean().optional(),
  preview_subject_framing_valid: z.boolean().nullish(),
  preview_subject_bbox_width_ratio: z.number().nullish(),
  preview_subject_bbox_height_ratio: z.number().nullish(),
  preview_subject_center_x_ratio: z.number().nullish(),
  preview_subject_min_edge_margin_ratio: z.number().nullish(),
  preview_subject_touches_frame: z.boolean().nullish()
});

export const VisualReviewSchema = publicSchema(
  UnknownRecord.extend({
    status: z
      .enum(["not_requested", "passed_advisory", "review_required", "failed"])
      .default("not_requested"),
    advisory_only: z.literal(true),
    summary: z.string().nullish(),
    findings: z.array(z.string()).default([]),
    limitations: z.array(z.string()).default([])
  })
);

export const AssetDecisionComponentSummarySchema = publicSchema(
  UnknownRecord.extend({
    component_id: z.string().nullish(),
    role_id: z.string().nullish(),
    strategy: z.enum([
      "reuse_full_design",
      "adapt_full_design",
      "reuse_component",
      "adapt_component",
      "compose_assets",
      "compose_and_generate",
      "procedural_generate",
      "clarify",
      "unsupported"
    ]).nullish(),
    asset_id: z.string().nullish(),
    considered_count: z.number().int().nonnegative().optional(),
    rejected_count: z.number().int().nonnegative().optional(),
    rationale: z.string().nullish(),
    risks: z.array(z.string()).default([]),
    strategy_evidence: z.literal("planned_not_execution_verified").nullish()
  })
);

export const AssetDecisionSummarySchema = publicSchema(
  UnknownRecord.extend({
    components: z.array(AssetDecisionComponentSummarySchema).default([]),
    considered_asset_count: z.number().int().nonnegative().optional(),
    selected_asset_count: z.number().int().nonnegative().optional(),
    decision_authority: z.string().nullish(),
    fallback_used: z.boolean().default(false),
    fallback_reason: z.string().nullish()
  })
);

export const AssemblyConstraintSummarySchema = publicSchema(
  UnknownRecord.extend({
    status: z.enum(["passed", "failed", "not_available"]),
    measurement_scope: z.string().min(1),
    required_connection_count: z.number().int().nonnegative(),
    measured_instance_count: z.number().int().nonnegative(),
    resolved_support_count: z.number().int().nonnegative().default(0),
    max_position_error_m: z.number().nonnegative(),
    max_angular_error_deg: z.number().nonnegative(),
    limitations: z.array(z.string()).default([])
  })
);

export const SectorPreviewSummarySchema = publicSchema(
  UnknownRecord.extend({
    sector_id: z.string().min(1),
    preview_url: z.string().min(1),
    semantic_roots: z.array(z.string().min(1)).min(1),
    expected_roles: z.array(z.string().min(1)).min(1),
    exported_roles: z.array(z.string().min(1)).min(1),
    framed_roles: z.array(z.string().min(1)).min(1),
    post_blender_identity_verified: z.boolean(),
    visual_framing_verified: z.boolean(),
    subject_bbox_height_ratio: z.number().min(0).max(1).nullish(),
    subject_contrast_mean: z.number().nonnegative().nullish(),
    limitations: z.array(z.string()).default([])
  })
);

export const TowerAccessSummarySchema = publicSchema(
  UnknownRecord.extend({
    semantic_root: z.string().min(1),
    semantic_role: z.literal("tower_access"),
    interaction_mode: z.literal("inspection_only"),
    post_blender_geometry_verified: z.literal(true),
    requested_ladder: z.boolean(),
    rung_count: z.number().int().nonnegative(),
    platform_levels_m: z.array(z.number().positive()).default([]),
    measurement_scope: z.literal("exported_glb_tower_access_geometry"),
    limitations: z.array(z.string()).default([])
  })
);

export const ViewerBundleSchema = publicSchema(
  UnknownRecord.extend({
    workflow_id: z.string(),
    version_id: z.string().nullish(),
    status: WorkflowLifecycleStatusSchema,
    generation_mode: z.string().nullish(),
    generation_strategy: z.string().nullish(),
    geometry_source: z.string().nullish(),
    mesh_qa_level: z.string().nullish(),
    mesh_qa_passed: z.boolean().nullish(),
    qa_score: z.number().nullish(),
    asset_import_summary: UnknownRecord.nullish(),
    geometry_fidelity_summary: GeometryFidelitySummarySchema.nullish(),
    geometry_program_summary: GeometryProgramSummarySchema.nullish(),
    assembly_constraint_summary: AssemblyConstraintSummarySchema.nullish(),
    sector_previews: z.array(SectorPreviewSummarySchema).optional(),
    tower_access_summary: TowerAccessSummarySchema.nullish(),
    human_warnings_count: z.number().default(0),
    human_errors_count: z.number().default(0),
    primary_glb_url: z.string().nullish(),
    preview_url: z.string().nullish(),
    report_url: z.string().nullish(),
    metadata_url: z.string().nullish(),
    scene_spec_url: z.string().nullish(),
    assembly_plan_url: z.string().nullish(),
    constraint_evidence_url: z.string().nullish(),
    tower_access_evidence_url: z.string().nullish(),
    qa_report_url: z.string().nullish(),
    generation_report_url: z.string().nullish(),
    geometry_validation_url: z.string().nullish(),
    component_proofs_url: z.string().nullish(),
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
    llm_decision_provenance: LLMDecisionProvenanceSchema.nullish(),
    llm_decision_provenance_url: z.string().nullish(),
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
    multimodal_consent: MultimodalConsentSchema.optional(),
    multimodal_intelligence: MultimodalIntelligenceSchema.nullish(),
    asset_decision_summary: AssetDecisionSummarySchema.nullish(),
    visual_review: VisualReviewSchema.nullish(),
    qa_summary: ViewerQaSummarySchema.nullish(),
    viewer_artifacts: z.array(ViewerArtifactSchema).default([]),
    limitations: z.array(z.string()).default([]),
    runtime_capabilities: RuntimeCapabilitiesSchema.nullish(),
    unsupported_actions: z.array(UnsupportedActionSchema).default([]),
    available_actions: z.array(z.string()).default([])
  }).superRefine((bundle, ctx) => validateInputAnalysisEnvelope(bundle, ctx))
);

export const ComponentProofInstanceSchema = publicSchema(
  UnknownRecord.extend({
    instance_id: z.string(),
    object_role: z.string(),
    semantic_root: z.string(),
    geometry_source: z.string(),
    bounding_box_m: UnknownRecord.extend({
      minimum_m: z.tuple([z.number(), z.number(), z.number()]),
      maximum_m: z.tuple([z.number(), z.number(), z.number()]),
      dimensions_m: z.tuple([
        z.number().nonnegative(),
        z.number().nonnegative(),
        z.number().nonnegative()
      ])
    }).nullish(),
    qa: UnknownRecord.nullish()
  })
);

export const ComponentProofSchema = publicSchema(
  UnknownRecord.extend({
    component_id: z.string(),
    role_id: z.string(),
    origin: z.string(),
    strategy: z.enum(["reuse", "adapt", "compose", "procedural_generate"]),
    generation_strategy: z.string(),
    asset_id: z.string().nullish(),
    quantity: z.number().int().nonnegative(),
    instances: z.array(ComponentProofInstanceSchema).default([]),
    qa: UnknownRecord.nullish()
  })
);

export const GeometryProgramProofSchema = publicSchema(
  UnknownRecord.extend({
    component_id: z.string(),
    role_id: z.string(),
    origin: z.enum(["geometry_program", "catalog_asset"]),
    strategy: z.enum(["procedural_generate", "reuse"]),
    generation_strategy: z.string(),
    exact_asset_sources: z.array(UnknownRecord.extend({
      asset_id: z.string().min(1),
      asset_file: z.string().min(1),
      asset_sha256: z.string().regex(/^[a-f0-9]{64}$/),
      manifest_file_name: z.string().min(1),
      manifest_sha256: z.string().regex(/^[a-f0-9]{64}$/)
    })).optional(),
    quantity: z.number().int().positive(),
    geometry_program: UnknownRecord.nullish(),
    bounding_box_m: UnknownRecord.extend({
      minimum_m: z.tuple([z.number(), z.number(), z.number()]),
      maximum_m: z.tuple([z.number(), z.number(), z.number()]),
      dimensions_m: z.tuple([
        z.number().nonnegative(),
        z.number().nonnegative(),
        z.number().nonnegative()
      ])
    }).nullish(),
    qa: UnknownRecord.nullish()
  }).superRefine((proof, ctx) => {
    const exact = proof.origin === "catalog_asset";
    if (exact
      ? proof.strategy !== "reuse" || proof.generation_strategy !== "imported_glb_exact" ||
        proof.quantity !== 1 || proof.exact_asset_sources?.length !== 1
      : proof.strategy !== "procedural_generate" || proof.generation_strategy === "imported_glb_exact" ||
        Boolean(proof.exact_asset_sources?.length)) {
      ctx.addIssue({ code: "custom", message: "geometry proof origin and execution strategy are inconsistent" });
    }
  })
);

export const ComponentProofsSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.string(),
    workflow_id: z.string(),
    components: z.array(ComponentProofSchema).default([]),
    geometry_programs: z.array(GeometryProgramProofSchema).default([])
  })
);

export const AssemblyCandidateScoreSchema = publicSchema(
  UnknownRecord.extend({
    asset_id: z.string(),
    total_score: z.number(),
    fidelity_score: z.number().default(0),
    reasons: z.array(z.string()).default([])
  })
);

export const AssemblyPlanComponentSchema = publicSchema(
  UnknownRecord.extend({
    role_id: z.string(),
    asset_type: z.string(),
    required: z.boolean(),
    candidate_scores: z.array(AssemblyCandidateScoreSchema).default([]),
    selected_asset_id: z.string().nullish(),
    generation_strategy: z.string(),
    selection_risks: z.array(z.string()).default([]),
    selection_reason: z.string().nullish()
  })
);

export const AssemblyPlanEvidenceSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.string(),
    workflow_id: z.string(),
    selection_authority: z.string(),
    selection_provider: z.string(),
    selection_model: z.string().nullish(),
    components: z.array(AssemblyPlanComponentSchema).default([]),
    connections: z.array(UnknownRecord).default([]),
    operations: z.array(UnknownRecord).default([])
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
    task_started_at: z.string().nullish(),
    task_finished_at: z.string().nullish(),
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
