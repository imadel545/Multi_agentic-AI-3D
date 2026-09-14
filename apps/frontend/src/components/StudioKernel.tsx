/**
 * Stable public surface for the studio UI.
 *
 * Implementations live in focused modules so the command flow, runtime status,
 * inspection drawers, and evidence formatting can evolve independently.
 */
export { BackendStatusBar } from "./StudioBackendStatus";
export { ChatCommandPanel } from "./StudioCommandPanel";
export {
  ActiveWorkflowContext,
  ConversationHistory,
  RequirementsUnderstanding,
  conversationHistoryEntries
} from "./StudioConversationContext";
export {
  DocumentPackIntake,
  MultimodalConsentControl,
  multimodalConsentIsAvailable
} from "./StudioDocumentIntake";
export {
  AgentStageRail,
  AgentTimeline,
  CurrentOperationStrip,
  LiveGenerationOverlay
} from "./StudioWorkflowActivity";
export { InspectorDock } from "./StudioInspectorDock";
export {
  ArtifactsPanel,
  InputAnalysisPanel,
  IssuesPanel,
  QaPanel,
  SummaryPanel,
  availablePreviewArtifacts,
  humanGeometryOutputMode
} from "./StudioDesignPanels";
export {
  LlmProvenancePanel,
  RagEvidencePanel,
  RuntimeCapabilitiesPanel,
  VersionSummary
} from "./StudioEvidencePanels";
export { meshQaLevelLabel, humanRagLimitation } from "./StudioProductDisplay";
export {
  displayIssueCount,
  humanRequirementWarning,
  summarizeAdaptationCapabilityGroups,
  summarizeTimelineRows,
  summarizeUserIssues
} from "./StudioWorkflowDisplay";
