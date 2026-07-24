import type {
  CurrentOperation,
  StudioSummary,
  TimelineSummary,
  UserIssues,
  ViewerBundle,
  WorkflowStatus
} from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";

export type WorkflowPhase =
  | "idle"
  | "drafting"
  | "submitting"
  | "streaming"
  | "running"
  | "completed"
  | "failed"
  | "degraded";

export type RuntimeMode = "sse" | "polling" | "idle";
export type DesignQuality = "unknown" | "valid" | "degraded" | "failed";
export type ProviderHealth = "unknown" | "primary" | "degraded";
export type ArtifactReadiness = "unknown" | "waiting" | "ready" | "missing";

export type ResourceErrorMap = Record<string, string>;

export type WorkflowMachineState = {
  phase: WorkflowPhase;
  runtimeMode: RuntimeMode;
  pendingSubmission: boolean;
  designQuality: DesignQuality;
  providerHealth: ProviderHealth;
  artifactReadiness: ArtifactReadiness;
  prompt: string;
  workflowId: string | null;
  summary: StudioSummary | null;
  status: WorkflowStatus | null;
  currentOperation: CurrentOperation | null;
  viewerBundle: ViewerBundle | null;
  timeline: TimelineSummary | null;
  userIssues: UserIssues | null;
  events: NormalizedWorkflowEvent[];
  error: string | null;
  transportError: string | null;
  resourceErrors: ResourceErrorMap;
};

export type WorkflowMachineAction =
  | { type: "BOOTSTRAP_LOADED"; summary: StudioSummary }
  | { type: "PROMPT_CHANGED"; prompt: string }
  | { type: "SUBMIT_STARTED" }
  | { type: "DESIGN_CREATED"; workflowId: string }
  | { type: "WORKFLOW_RESTORED"; status: WorkflowStatus }
  | { type: "REVISION_STARTED"; runtimeMode: Exclude<RuntimeMode, "idle"> }
  | { type: "EVENT_RECEIVED"; event: NormalizedWorkflowEvent }
  | { type: "SSE_FAILED"; message: string }
  | { type: "SSE_RECOVERED" }
  | { type: "STATUS_LOADED"; status: WorkflowStatus }
  | { type: "CURRENT_OPERATION_LOADED"; currentOperation: CurrentOperation }
  | { type: "VIEWER_BUNDLE_LOADED"; viewerBundle: ViewerBundle }
  | { type: "TIMELINE_LOADED"; timeline: TimelineSummary }
  | { type: "USER_ISSUES_LOADED"; userIssues: UserIssues }
  | { type: "RESOURCE_FAILED"; resource: string; message: string }
  | { type: "RESOURCE_RECOVERED"; resource: string }
  | { type: "REQUEST_FAILED"; message: string }
  | { type: "RESET" };

export const initialWorkflowState: WorkflowMachineState = {
  phase: "idle",
  runtimeMode: "idle",
  pendingSubmission: false,
  designQuality: "unknown",
  providerHealth: "unknown",
  artifactReadiness: "unknown",
  prompt: "",
  workflowId: null,
  summary: null,
  status: null,
  currentOperation: null,
  viewerBundle: null,
  timeline: null,
  userIssues: null,
  events: [],
  error: null,
  transportError: null,
  resourceErrors: {}
};

export function workflowReducer(
  state: WorkflowMachineState,
  action: WorkflowMachineAction
): WorkflowMachineState {
  switch (action.type) {
    case "BOOTSTRAP_LOADED":
      return { ...state, summary: action.summary };
    case "PROMPT_CHANGED":
      return {
        ...state,
        phase: state.workflowId ? state.phase : action.prompt.trim() ? "drafting" : "idle",
        prompt: action.prompt,
        error: null
      };
    case "SUBMIT_STARTED":
      if (state.workflowId) {
        return {
          ...state,
          pendingSubmission: true,
          error: null
        };
      }
      return {
        ...state,
        phase: "submitting",
        runtimeMode: "idle",
        pendingSubmission: true,
        error: null,
        transportError: null,
        resourceErrors: {}
      };
    case "DESIGN_CREATED":
      return {
        ...state,
        workflowId: action.workflowId,
        phase: "streaming",
        runtimeMode: "sse",
        pendingSubmission: false,
        status: null,
        currentOperation: null,
        viewerBundle: null,
        timeline: null,
        userIssues: null,
        events: [],
        designQuality: "unknown",
        providerHealth: "unknown",
        artifactReadiness: "waiting",
        error: null,
        transportError: null
      };
    case "WORKFLOW_RESTORED": {
      const live = action.status.status === "pending" || action.status.status === "running";
      return {
        ...state,
        workflowId: action.status.workflow_id,
        status: action.status,
        phase: phaseFromStatus(action.status, null, live ? "running" : "idle"),
        runtimeMode: live ? "sse" : "idle",
        pendingSubmission: false,
        designQuality: qualityFrom(action.status),
        providerHealth: providerHealthFrom(action.status),
        artifactReadiness: artifactsFrom(action.status),
        error: null,
        transportError: null,
        resourceErrors: {},
        events: []
      };
    }
    case "REVISION_STARTED":
      return {
        ...state,
        phase: "running",
        runtimeMode: action.runtimeMode,
        error: null
      };
    case "EVENT_RECEIVED": {
      const next = { ...state, events: appendUniqueEvent(state.events, action.event) };
      if (action.event.event_type === "workflow_failed") {
        return { ...next, phase: "failed", runtimeMode: "idle" };
      }
      if (action.event.event_type === "workflow_completed") {
        return { ...next, phase: "completed", runtimeMode: "idle" };
      }
      return isTerminalPhase(state.phase) ? next : { ...next, phase: "running" };
    }
    case "SSE_FAILED":
      return {
        ...state,
        runtimeMode: "polling",
        phase: isTerminalPhase(state.phase) ? state.phase : state.phase === "idle" ? "idle" : "running",
        transportError: action.message
      };
    case "SSE_RECOVERED":
      return {
        ...state,
        runtimeMode: isTerminalPhase(state.phase) ? "idle" : "sse",
        transportError: null
      };
    case "STATUS_LOADED": {
      const phase = phaseFromStatus(action.status, state.viewerBundle, state.phase);
      return {
        ...state,
        status: action.status,
        phase,
        designQuality: qualityFrom(action.status),
        providerHealth: providerHealthFrom(action.status),
        artifactReadiness: artifactsFrom(action.status),
        runtimeMode: isTerminalPhase(phase) ? "idle" : state.runtimeMode,
        error: null
      };
    }
    case "CURRENT_OPERATION_LOADED":
      return { ...state, currentOperation: action.currentOperation };
    case "VIEWER_BUNDLE_LOADED":
      return {
        ...state,
        viewerBundle: action.viewerBundle,
        phase: isDegraded(action.viewerBundle, state.status) ? "degraded" : state.phase,
        designQuality: qualityFrom(action.viewerBundle),
        providerHealth: providerHealthFrom(action.viewerBundle),
        artifactReadiness: artifactsFrom(action.viewerBundle)
      };
    case "TIMELINE_LOADED":
      return { ...state, timeline: action.timeline };
    case "USER_ISSUES_LOADED":
      return { ...state, userIssues: action.userIssues };
    case "RESOURCE_FAILED":
      return {
        ...state,
        resourceErrors: { ...state.resourceErrors, [action.resource]: action.message }
      };
    case "RESOURCE_RECOVERED":
      return {
        ...state,
        resourceErrors: withoutResource(state.resourceErrors, action.resource)
      };
    case "REQUEST_FAILED":
      return {
        ...state,
        error: action.message,
        pendingSubmission: false,
        phase: phaseAfterRequestFailure(state),
        runtimeMode:
          state.status && isTerminalStatus(state.status.status) ? "idle" : state.runtimeMode
      };
    case "RESET":
      return { ...initialWorkflowState, summary: state.summary };
  }
}

export function isDegraded(
  viewerBundle: ViewerBundle | null,
  status: WorkflowStatus | null
): boolean {
  const source = viewerBundle ?? status;
  if (!source) {
    return false;
  }
  if (source.status === "failed") {
    return false;
  }
  if (source.generation_mode && source.generation_mode !== "real_blender") {
    return true;
  }
  if (source.mesh_qa_passed === false) {
    return true;
  }
  if (source.requirement_coverage_passed === false) {
    return true;
  }
  if (source.completion_certificate_status === "rejected") {
    return true;
  }
  if ("primary_glb_url" in source && !source.primary_glb_url) {
    return true;
  }
  const assetSummary = source.asset_import_summary;
  if (
    assetSummary &&
    typeof assetSummary === "object" &&
    Number((assetSummary as Record<string, unknown>).procedural_fallback_count ?? 0) > 0
  ) {
    return true;
  }
  return false;
}

function qualityFrom(source: ViewerBundle | WorkflowStatus): DesignQuality {
  if (source.status === "failed") return "failed";
  if (source.status !== "completed") return "unknown";
  const viewerBundle = isViewerBundle(source) ? source : null;
  const workflowStatus = isViewerBundle(source) ? null : source;
  return isDegraded(viewerBundle, workflowStatus) ? "degraded" : "valid";
}

function providerHealthFrom(source: ViewerBundle | WorkflowStatus): ProviderHealth {
  if (source.llm_fallback_used === true || Boolean(source.rag_reranker_degraded_reason)) {
    return "degraded";
  }
  if (source.llm_provider || source.rag_reranker_status) return "primary";
  return "unknown";
}

function artifactsFrom(source: ViewerBundle | WorkflowStatus): ArtifactReadiness {
  if (isViewerBundle(source)) {
    if (source.primary_glb_url) return "ready";
    return source.status === "completed" || source.status === "failed" ? "missing" : "waiting";
  }
  if (source.status === "pending" || source.status === "running") return "waiting";
  if (source.status === "failed") return "missing";
  return source.artifacts?.glb ? "ready" : "unknown";
}

function isViewerBundle(source: ViewerBundle | WorkflowStatus): source is ViewerBundle {
  return Array.isArray((source as ViewerBundle).viewer_artifacts);
}

export function actionIsSupported(
  action: string,
  unsupportedActions: { action: string }[] | null | undefined
): boolean {
  return !(unsupportedActions ?? []).some((item) => item.action === action);
}

function phaseFromStatus(
  status: WorkflowStatus,
  viewerBundle: ViewerBundle | null,
  currentPhase: WorkflowPhase
): WorkflowPhase {
  if (status.status === "failed") {
    return "failed";
  }
  if (status.status === "completed") {
    return isDegraded(viewerBundle, status) ? "degraded" : "completed";
  }
  if (status.status === "pending" || status.status === "running") {
    return "running";
  }
  return currentPhase;
}

function appendUniqueEvent(
  events: NormalizedWorkflowEvent[],
  event: NormalizedWorkflowEvent
): NormalizedWorkflowEvent[] {
  if (events.some((item) => item.event_id === event.event_id)) {
    return events;
  }
  return [...events, event].slice(-500);
}

function isTerminalPhase(phase: WorkflowPhase): boolean {
  return phase === "completed" || phase === "failed" || phase === "degraded";
}

function isTerminalStatus(status: string): boolean {
  return status === "completed" || status === "failed";
}

function phaseAfterRequestFailure(state: WorkflowMachineState): WorkflowPhase {
  if (state.status) {
    return phaseFromStatus(state.status, state.viewerBundle, state.phase);
  }
  if (state.workflowId) {
    return state.phase;
  }
  return state.prompt.trim() ? "drafting" : "idle";
}

function withoutResource(errors: ResourceErrorMap, resource: string): ResourceErrorMap {
  if (!(resource in errors)) {
    return errors;
  }
  const next = { ...errors };
  delete next[resource];
  return next;
}
