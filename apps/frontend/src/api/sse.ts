import {
  WorkflowEventSchema,
  parseContract,
  type WorkflowEvent
} from "./schemas";

export type NormalizedWorkflowEvent = {
  event_id: string;
  sequence?: number | null;
  event_type: string;
  workflow_id: string;
  timestamp: string;
  phase: string | null;
  status: string | null;
  node: string | null;
  human_label: string;
  progress_message: string;
  warnings: unknown[];
  errors: unknown[];
  artifact_refs: string[];
  raw: WorkflowEvent;
};

type EventSourceConstructor = new (url: string) => EventSource;

export type StreamCallbacks = {
  onEvent: (event: NormalizedWorkflowEvent) => void;
  onTerminal: (event: NormalizedWorkflowEvent) => void;
  onError: (error: Error) => void;
  onRecovered?: () => void;
};

const TerminalEventTypes = new Set([
  "workflow_completed",
  "workflow_failed",
  "edit_patch_applied",
  "edit_patch_rejected",
  "version_rolled_back"
]);

const BackendEventTypes = [
  "design_created",
  "node_started",
  "node_completed",
  "node_failed",
  "node_skipped",
  "artifact_ready",
  "qa_completed",
  "qa_failed",
  "user_issue_created",
  "validated_requirements_received",
  "edit_patch_created",
  "edit_patch_interpreted",
  "edit_patch_applied",
  "edit_patch_rejected",
  "version_created",
  "version_rolled_back",
  "blender_completed",
  "blender_failed",
  "workflow_completed",
  "workflow_failed"
];

export function normalizeWorkflowEvent(event: WorkflowEvent): NormalizedWorkflowEvent {
  const payload = event.payload ?? {};
  const humanLabel =
    typeof payload.human_label === "string" && payload.human_label
      ? payload.human_label
      : readableEventType(event.event_type);
  const progressMessage =
    typeof payload.progress_message === "string" && payload.progress_message
      ? payload.progress_message
      : humanLabel;
  return {
    event_id: event.event_id,
    sequence: event.sequence ?? null,
    event_type: event.event_type,
    workflow_id: event.workflow_id,
    timestamp: event.timestamp,
    phase: typeof payload.phase === "string" ? payload.phase : null,
    status: typeof payload.status === "string" ? payload.status : null,
    node: typeof payload.node === "string" ? payload.node : null,
    human_label: humanLabel,
    progress_message: progressMessage,
    warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
    errors: Array.isArray(payload.errors) ? payload.errors : [],
    artifact_refs: Array.isArray(payload.artifact_refs) ? payload.artifact_refs : [],
    raw: event
  };
}

export function openWorkflowEventStream(
  url: string,
  callbacks: StreamCallbacks,
  EventSourceImpl: EventSourceConstructor = EventSource
) {
  const source = new EventSourceImpl(url);
  let closed = false;
  let consecutiveErrors = 0;
  let lastSequence: number | null = null;

  const handleMessage = (message: MessageEvent) => {
    if (!message.data) {
      return;
    }
    try {
      const payload = JSON.parse(String(message.data));
      const parsed = parseContract("WorkflowEvent", WorkflowEventSchema, payload);
      const normalized = normalizeWorkflowEvent(parsed);
      if (
        normalized.sequence != null &&
        lastSequence != null &&
        normalized.sequence > lastSequence + 1
      ) {
        callbacks.onError(
          new Error(
            `SSE event gap detected (${lastSequence} -> ${normalized.sequence}); polling reconciliation is active.`
          )
        );
      }
      if (normalized.sequence != null) {
        lastSequence = Math.max(lastSequence ?? 0, normalized.sequence);
      }
      callbacks.onEvent(normalized);
      if (TerminalEventTypes.has(normalized.event_type)) {
        callbacks.onTerminal(normalized);
        closed = true;
        source.close();
      }
    } catch (error) {
      callbacks.onError(error instanceof Error ? error : new Error(String(error)));
    }
  };

  source.onmessage = handleMessage;
  source.onopen = () => {
    const recovered = consecutiveErrors > 0;
    consecutiveErrors = 0;
    if (recovered) callbacks.onRecovered?.();
  };
  for (const eventType of BackendEventTypes) {
    source.addEventListener(eventType, handleMessage as EventListener);
  }
  source.onerror = () => {
    if (closed) {
      return;
    }
    consecutiveErrors += 1;
    callbacks.onError(new Error("SSE stream failed; polling fallback is active."));
    if (consecutiveErrors >= 3) {
      closed = true;
      source.close();
    }
  };

  return {
    close() {
      closed = true;
      source.close();
    }
  };
}

function readableEventType(eventType: string): string {
  return eventType.replaceAll("_", " ");
}
