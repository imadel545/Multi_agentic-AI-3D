import { z } from "zod";
import {
  ContractValidationError,
  CreateDesignResponseSchema,
  HealthSchema,
  InputAnalysisStatusSchema,
  LLMDecisionProvenanceSchema,
  MultimodalConsentSchema,
  MultimodalIntelligenceSchema,
  ParseRequirementsResponseSchema,
  RequirementAnalysisReceiptSchema,
  RequirementSpecSchema,
  StudioSummarySchema,
  UserIssueSchema,
  WorkflowEventSchema,
  WorkflowStatusSchema,
  publicSchema
} from "./schemaCore";
import {
  AssemblyPlanEvidenceSchema,
  AssetDecisionSummarySchema,
  ComponentProofInstanceSchema,
  ComponentProofSchema,
  ComponentProofsSchema,
  CurrentOperationSchema,
  GeometryFidelitySummarySchema,
  SectorPreviewSummarySchema,
  TimelineStepSchema,
  TimelineSummarySchema,
  TowerAccessSummarySchema,
  UserIssuesSchema,
  ViewerBundleSchema,
  VisualReviewSchema
} from "./schemaViewer";
import {
  AdaptationCapabilityCatalogSchema,
  AssetInventorySchema,
  AssetLibraryEntrySchema,
  AssetLibraryProbeSchema,
  AssetLibrarySearchSchema,
  AssetLibrarySummarySchema,
  AssetProvenanceSchema,
  QualifiedAssetInventoryEntrySchema,
  ResolvedAdaptationCapabilitySchema,
  SceneAdaptationCapabilitiesSchema
} from "./schemaAssets";
import {
  DocumentPackCapabilitiesSchema,
  DocumentPackSummarySchema
} from "./schemaDocuments";
import {
  EditDesignResponseSchema,
  PublicVersionInfoSchema,
  RollbackVersionResponseSchema
} from "./schemaRevisions";

export * from "./schemaCore";
export * from "./schemaViewer";
export * from "./schemaAssets";
export * from "./schemaDocuments";
export * from "./schemaRevisions";

export type Health = z.infer<typeof HealthSchema>;
export type StudioSummary = z.infer<typeof StudioSummarySchema>;
export type RequirementSpec = z.infer<typeof RequirementSpecSchema>;
export type ParseRequirementsResponse = z.infer<typeof ParseRequirementsResponseSchema>;
export type RequirementAnalysisReceipt = z.infer<typeof RequirementAnalysisReceiptSchema>;
export type InputAnalysisStatus = z.infer<typeof InputAnalysisStatusSchema>;
export type CreateDesignResponse = z.infer<typeof CreateDesignResponseSchema>;
export type WorkflowStatus = z.infer<typeof WorkflowStatusSchema>;
export type WorkflowEvent = z.infer<typeof WorkflowEventSchema>;
export type ViewerBundle = z.infer<typeof ViewerBundleSchema>;
export type MultimodalConsent = z.infer<typeof MultimodalConsentSchema>;
export type MultimodalIntelligence = z.infer<typeof MultimodalIntelligenceSchema>;
export type VisualReview = z.infer<typeof VisualReviewSchema>;
export type AssetDecisionSummary = z.infer<typeof AssetDecisionSummarySchema>;
export type SectorPreviewSummary = z.infer<typeof SectorPreviewSummarySchema>;
export type TowerAccessSummary = z.infer<typeof TowerAccessSummarySchema>;
export type ComponentProofs = z.infer<typeof ComponentProofsSchema>;
export type ComponentProof = z.infer<typeof ComponentProofSchema>;
export type ComponentProofInstance = z.infer<typeof ComponentProofInstanceSchema>;
export type AssemblyPlanEvidence = z.infer<typeof AssemblyPlanEvidenceSchema>;
export type LLMDecisionProvenance = z.infer<typeof LLMDecisionProvenanceSchema>;
export type GeometryFidelitySummary = z.infer<typeof GeometryFidelitySummarySchema>;
export type TimelineSummary = z.infer<typeof TimelineSummarySchema>;
export type TimelineStep = z.infer<typeof TimelineStepSchema>;
export type CurrentOperation = z.infer<typeof CurrentOperationSchema>;
export type UserIssues = z.infer<typeof UserIssuesSchema>;
export type UserIssue = z.infer<typeof UserIssueSchema>;
export type AssetInventory = z.infer<typeof AssetInventorySchema>;
export type QualifiedAssetInventoryEntry = z.infer<typeof QualifiedAssetInventoryEntrySchema>;
export type AssetLibrarySummary = z.infer<typeof AssetLibrarySummarySchema>;
export type AssetLibraryEntry = z.infer<typeof AssetLibraryEntrySchema>;
export type AssetLibrarySearch = z.infer<typeof AssetLibrarySearchSchema>;
export type AssetLibraryProbe = z.infer<typeof AssetLibraryProbeSchema>;
export type AssetProvenance = z.infer<typeof AssetProvenanceSchema>;
export type AdaptationCapabilityCatalog = z.infer<typeof AdaptationCapabilityCatalogSchema>;
export type SceneAdaptationCapabilities = z.infer<typeof SceneAdaptationCapabilitiesSchema>;
export type ResolvedAdaptationCapability = z.infer<typeof ResolvedAdaptationCapabilitySchema>;
export type DocumentPackCapabilities = z.infer<typeof DocumentPackCapabilitiesSchema>;
export type DocumentPackSummary = z.infer<typeof DocumentPackSummarySchema>;
export type PublicVersionInfo = z.infer<typeof PublicVersionInfoSchema>;
export type EditDesignResponse = z.infer<typeof EditDesignResponseSchema>;
export type RollbackVersionResponse = z.infer<typeof RollbackVersionResponseSchema>;
export type Conversation = z.infer<typeof ConversationSchema>;

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

export const ConversationSchema = publicSchema(z.object({
  workflow_id: z.string(),
  history_status: z.enum(["recorded", "legacy_partial", "damaged"]),
  messages: z.array(z.object({
    message_id: z.string(),
    role: z.enum(["user", "system"]),
    text: z.string(),
    timestamp: z.string(),
    operation_id: z.string().nullable(),
    target_semantic_root: z.string().nullable(),
    version_id: z.string().nullable()
  }))
}));
