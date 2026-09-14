import { z } from "zod";
import {
  LLMDecisionProvenanceSchema,
  RuntimeCapabilitiesSchema,
  UnsupportedActionSchema,
  UnknownRecord,
  publicSchema
} from "./schemaCore";

export const PublicVersionInfoSchema = publicSchema(
  UnknownRecord.extend({
    version_id: z.string(),
    parent_version_id: z.string().nullish(),
    created_at: z.string(),
    active: z.boolean().default(false),
    artifacts: z.record(z.string(), z.string()).default({}),
    qa_score: z.number().nullish(),
    generation_mode: z.string().nullish(),
    llm_decision_provenance: LLMDecisionProvenanceSchema.nullish(),
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
    llm_decision_provenance: LLMDecisionProvenanceSchema.nullish(),
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
