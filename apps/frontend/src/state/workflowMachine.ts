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

export type WorkflowMachineState = {
  phase: WorkflowPhase;
  runtimeMode: RuntimeMode;
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
};

export type WorkflowMachineAction =
  | { type: "BOOTSTRAP_LOADED"; summary: StudioSummary }
  | { type: "PROMPT_CHANGED"; prompt: string }
  | { type: "SUBMIT_STARTED" }
  | { type: "DESIGN_CREATED"; workflowId: string }
  | { type: "WORKFLOW_RESTORED"; workflowId: string }
  | { type: "REVISION_STARTED" }
  | { type: "EVENT_RECEIVED"; event: NormalizedWorkflowEvent }
  | { type: "SSE_FAILED"; message: string }
  | { type: "STATUS_LOADED"; status: WorkflowStatus }
  | { type: "CURRENT_OPERATION_LOADED"; currentOperation: CurrentOperation }
  | { type: "VIEWER_BUNDLE_LOADED"; viewerBundle: ViewerBundle }
  | { type: "TIMELINE_LOADED"; timeline: TimelineSummary }
  | { type: "USER_ISSUES_LOADED"; userIssues: UserIssues }
  | { type: "REQUEST_FAILED"; message: string }
  | { type: "RESET" };

export const initialWorkflowState: WorkflowMachineState = {
  phase: "idle",
  runtimeMode: "idle",
  prompt: "",
  workflowId: null,
  summary: null,
  status: null,
  currentOperation: null,
  viewerBundle: null,
  timeline: null,
  userIssues: null,
  events: [],
  error: null
};

export function workflowReducer(
  state: WorkflowMachineState,
  action: WorkflowMachineAction
): WorkflowMachineState {
  switch (action.type) {
    case "BOOTSTRAP_LOADED":
      return { ...state, summary: action.summary, error: null };
    case "PROMPT_CHANGED":
      return {
        ...state,
        phase: "drafting",
        runtimeMode: "idle",
        prompt: action.prompt,
        workflowId: null,
        status: null,
        currentOperation: null,
        viewerBundle: null,
        timeline: null,
        userIssues: null,
        events: [],
        error: null
      };
    case "SUBMIT_STARTED":
      return {
        ...state,
        phase: "submitting",
        runtimeMode: "idle",
        workflowId: null,
        status: null,
        currentOperation: null,
        viewerBundle: null,
        timeline: null,
        userIssues: null,
        events: [],
        error: null
      };
    case "DESIGN_CREATED":
      return { ...state, workflowId: action.workflowId, phase: "streaming", runtimeMode: "sse" };
    case "WORKFLOW_RESTORED":
      return {
        ...state,
        workflowId: action.workflowId,
        phase: "running",
        runtimeMode: "polling",
        error: null,
        events: []
      };
    case "REVISION_STARTED":
      return {
        ...state,
        phase: "running",
        runtimeMode: "polling",
        error: null
      };
    case "EVENT_RECEIVED": {
      const next = { ...state, events: appendUniqueEvent(state.events, action.event) };
      if (action.event.event_type === "workflow_failed") {
        return { ...next, phase: "failed" };
      }
      if (action.event.event_type === "workflow_completed") {
        return { ...next, phase: "completed" };
      }
      return { ...next, phase: "running" };
    }
    case "SSE_FAILED":
      return {
        ...state,
        runtimeMode: "polling",
        phase: state.phase === "idle" ? "idle" : "running",
        error: action.message
      };
    case "STATUS_LOADED":
      return {
        ...state,
        status: action.status,
        phase: phaseFromStatus(action.status, state.viewerBundle, state.phase),
        error: null
      };
    case "CURRENT_OPERATION_LOADED":
      return { ...state, currentOperation: action.currentOperation };
    case "VIEWER_BUNDLE_LOADED":
      return {
        ...state,
        viewerBundle: action.viewerBundle,
        phase: isDegraded(action.viewerBundle, state.status) ? "degraded" : state.phase
      };
    case "TIMELINE_LOADED":
      return { ...state, timeline: action.timeline };
    case "USER_ISSUES_LOADED":
      return { ...state, userIssues: action.userIssues };
    case "REQUEST_FAILED":
      return { ...state, error: action.message, phase: state.workflowId ? "failed" : "idle" };
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
  if (source.llm_fallback_used === true) {
    return true;
  }
  if (source.rag_reranker_degraded_reason) {
    return true;
  }
  if ("primary_glb_url" in source && !source.primary_glb_url) {
    return true;
  }
  return false;
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
  return [...events, event];
}
