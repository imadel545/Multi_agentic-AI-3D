import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { TelecomStudioApi } from "../api/client";
import { normalizeWorkflowEvent, openWorkflowEventStream } from "../api/sse";
import type { PublicVersionInfo, WorkflowEvent, WorkflowStatus } from "../api/schemas";
import {
  applyResourceResult,
  isAbortError,
  isTerminalStatus,
  latestEventCursor,
  latestEventSequence,
  needsPolling,
  selectWorkflowToRestore,
  userFacingError
} from "../AppSupport";
import type { WorkflowMachineState } from "../state/workflowMachine";
import type { LoadSurfaceResource, WorkflowDispatch } from "./studioAppTypes";

type UseWorkflowLifecycleOptions = {
  apiClient: TelecomStudioApi;
  dispatch: WorkflowDispatch;
  initialWorkflowId?: string | null;
  loadSurfaceResource: LoadSurfaceResource;
  state: WorkflowMachineState;
  submissionInFlightRef: MutableRefObject<boolean>;
};

export function useWorkflowLifecycle({
  apiClient,
  dispatch,
  initialWorkflowId,
  loadSurfaceResource,
  state,
  submissionInFlightRef
}: UseWorkflowLifecycleOptions) {
  const [versions, setVersions] = useState<PublicVersionInfo[]>([]);
  const streamRef = useRef<{ close: () => void } | null>(null);
  const streamCursorRef = useRef<string | null>(null);
  const eventSequenceCursorRef = useRef<number | null>(null);
  const restoredWorkflowRef = useRef(false);
  const bootstrapRestoreEpochRef = useRef(0);
  const activeWorkflowRef = useRef<string | null>(null);
  const terminalBundleRequestRef = useRef(0);
  const terminalBundleAbortRef = useRef<AbortController | null>(null);

  const activateWorkflow = useCallback((workflowId: string) => {
    if (activeWorkflowRef.current !== workflowId) {
      terminalBundleAbortRef.current?.abort();
      terminalBundleAbortRef.current = null;
      activeWorkflowRef.current = workflowId;
      terminalBundleRequestRef.current += 1;
    }
  }, []);
  const isActiveWorkflow = useCallback(
    (workflowId: string) => activeWorkflowRef.current === workflowId,
    []
  );
  const invalidateBootstrapRestore = useCallback(() => {
    bootstrapRestoreEpochRef.current += 1;
  }, []);
  const rememberEventSequence = useCallback((sequence: number | null | undefined) => {
    if (sequence != null) {
      eventSequenceCursorRef.current = Math.max(eventSequenceCursorRef.current ?? 0, sequence);
    }
  }, []);
  const receiveWorkflowEvents = useCallback((events: WorkflowEvent[]) => {
    const matching = events.filter((event) => isActiveWorkflow(event.workflow_id));
    const normalized = matching.map(normalizeWorkflowEvent);
    rememberEventSequence(latestEventSequence(matching));
    if (normalized.length) dispatch({ type: "EVENTS_RECEIVED", events: normalized });
  }, [dispatch, isActiveWorkflow, rememberEventSequence]);

  useEffect(() => () => {
    terminalBundleAbortRef.current?.abort();
    terminalBundleAbortRef.current = null;
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  const loadLiveStatus = useCallback(async (workflowId: string) => {
    if (isActiveWorkflow(workflowId)) dispatch({ type: "RESOURCE_LOADING", resource: "workflow_status" });
    let status: WorkflowStatus;
    try {
      status = await apiClient.workflowStatus(workflowId);
    } catch (error) {
      if (isActiveWorkflow(workflowId)) {
        dispatch({ type: "RESOURCE_FAILED", resource: "workflow_status", message: userFacingError(error, "resource") });
      }
      throw error;
    }
    if (isActiveWorkflow(workflowId)) {
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
    }
    try {
      if (isActiveWorkflow(workflowId)) dispatch({ type: "RESOURCE_LOADING", resource: "current_operation" });
      const operation = await apiClient.currentOperation(workflowId);
      if (isActiveWorkflow(workflowId)) {
        dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation });
        dispatch({ type: "RESOURCE_RECOVERED", resource: "current_operation" });
      }
    } catch (error) {
      if (isActiveWorkflow(workflowId)) {
        dispatch({ type: "RESOURCE_FAILED", resource: "current_operation", message: userFacingError(error, "resource") });
      }
    }
    return status;
  }, [apiClient, dispatch, isActiveWorkflow]);

  const loadTerminalBundle = useCallback(async (workflowId: string) => {
    if (!isActiveWorkflow(workflowId)) return;
    terminalBundleAbortRef.current?.abort();
    const controller = new AbortController();
    terminalBundleAbortRef.current = controller;
    const requestId = terminalBundleRequestRef.current + 1;
    terminalBundleRequestRef.current = requestId;
    const requestIsCurrent = () => !controller.signal.aborted &&
      isActiveWorkflow(workflowId) && terminalBundleRequestRef.current === requestId;
    dispatch({ type: "RESOURCE_LOADING", resource: "terminal_bundle", workflowId });
    dispatch({ type: "RESOURCE_LOADING", resource: "workflow_status", workflowId });
    let status: WorkflowStatus;
    try {
      status = await apiClient.workflowStatus(workflowId, { signal: controller.signal });
    } catch (error) {
      if (isAbortError(error)) return;
      if (requestIsCurrent()) {
        const message = userFacingError(error, "resource");
        dispatch({ type: "RESOURCE_FAILED", resource: "workflow_status", message, workflowId });
        dispatch({ type: "RESOURCE_FAILED", resource: "terminal_bundle", message, workflowId });
      }
      throw error;
    }
    if (!requestIsCurrent() || status.workflow_id !== workflowId) return;
    dispatch({ type: "STATUS_LOADED", status });
    dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status", workflowId });
    for (const resource of ["current_operation", "viewer_bundle", "timeline", "user_issues", "versions", "studio_summary"]) {
      dispatch({ type: "RESOURCE_LOADING", resource, workflowId });
    }
    const [operationResult, bundleResult, timelineResult, issuesResult, versionsResult, summaryResult] =
      await Promise.allSettled([
        apiClient.currentOperation(workflowId, { signal: controller.signal }),
        apiClient.viewerBundle(workflowId, { signal: controller.signal }),
        apiClient.timelineSummary(workflowId, { signal: controller.signal }),
        apiClient.userIssues(workflowId, { signal: controller.signal }),
        apiClient.versions(workflowId, { signal: controller.signal }),
        apiClient.studioSummary({ signal: controller.signal })
      ]);
    if (!requestIsCurrent()) return;
    applyResourceResult(operationResult, "current_operation", (currentOperation) => dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation }), dispatch);
    applyResourceResult(bundleResult, "viewer_bundle", (viewerBundle) => dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle }), dispatch);
    applyResourceResult(timelineResult, "timeline", (timeline) => dispatch({ type: "TIMELINE_LOADED", timeline }), dispatch);
    applyResourceResult(issuesResult, "user_issues", (userIssues) => dispatch({ type: "USER_ISSUES_LOADED", userIssues }), dispatch);
    applyResourceResult(versionsResult, "versions", (nextVersions) => {
      if (requestIsCurrent()) setVersions(nextVersions);
    }, dispatch);
    applyResourceResult(summaryResult, "studio_summary", (summary) => dispatch({ type: "BOOTSTRAP_LOADED", summary }), dispatch);
    dispatch({ type: "RESOURCE_RECOVERED", resource: "terminal_bundle", workflowId });
    if (terminalBundleAbortRef.current === controller) terminalBundleAbortRef.current = null;
  }, [apiClient, dispatch, isActiveWorkflow]);

  const startEventStream = useCallback((workflowId: string, afterEventId?: string | null) => {
    streamRef.current?.close();
    streamRef.current = openWorkflowEventStream(apiClient.streamUrl(workflowId, afterEventId), {
      onEvent: (event) => {
        if (!isActiveWorkflow(workflowId)) return;
        rememberEventSequence(event.sequence);
        dispatch({ type: "EVENT_RECEIVED", event });
      },
      onTerminal: (event) => {
        if (!isActiveWorkflow(workflowId)) return;
        void loadTerminalBundle(event.workflow_id).catch((error) => dispatch({
          type: "RESOURCE_FAILED", resource: "terminal_bundle", message: userFacingError(error, "resource")
        }));
      },
      onError: (reason) => {
        if (isActiveWorkflow(workflowId)) dispatch({ type: "SSE_FAILED", reason });
      },
      onRecovered: () => {
        if (isActiveWorkflow(workflowId)) dispatch({ type: "SSE_RECOVERED" });
      }
    });
  }, [apiClient, dispatch, isActiveWorkflow, loadTerminalBundle, rememberEventSequence]);

  const loadPollingSnapshot = useCallback(async (workflowId: string) => {
    if (!isActiveWorkflow(workflowId)) return;
    let status: WorkflowStatus;
    try {
      status = await apiClient.workflowStatus(workflowId);
      if (!isActiveWorkflow(workflowId) || status.workflow_id !== workflowId) return;
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
    } catch (error) {
      if (isActiveWorkflow(workflowId)) dispatch({ type: "RESOURCE_FAILED", resource: "workflow_status", message: userFacingError(error, "resource") });
      return;
    }
    const [operationResult, eventsResult, timelineResult] = await Promise.allSettled([
      apiClient.currentOperation(workflowId),
      apiClient.workflowEvents(workflowId, eventSequenceCursorRef.current),
      apiClient.timelineSummary(workflowId)
    ]);
    applyResourceResult(operationResult, "current_operation", (currentOperation) => dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation }), dispatch);
    applyResourceResult(eventsResult, "events", receiveWorkflowEvents, dispatch);
    applyResourceResult(timelineResult, "timeline", (timeline) => dispatch({ type: "TIMELINE_LOADED", timeline }), dispatch);
    if (isTerminalStatus(status.status)) await loadTerminalBundle(workflowId);
  }, [apiClient, dispatch, isActiveWorkflow, loadTerminalBundle, receiveWorkflowEvents]);

  const restoreTarget = useRef(initialWorkflowId);
  const restoreLatestDesign = useCallback(async () => {
    const targetWorkflowId = restoreTarget.current;
    if (targetWorkflowId === null || restoredWorkflowRef.current || state.workflowId || state.phase !== "idle") return;
    const restoreEpoch = bootstrapRestoreEpochRef.current;
    const restoreRequestIsCurrent = () => !restoredWorkflowRef.current &&
      !submissionInFlightRef.current && activeWorkflowRef.current === null &&
      bootstrapRestoreEpochRef.current === restoreEpoch;
    if (!restoreRequestIsCurrent()) return;
    const restoreWorkflow = (latest: WorkflowStatus) => {
      if (!restoreRequestIsCurrent()) return;
      restoredWorkflowRef.current = true;
      eventSequenceCursorRef.current = null;
      activateWorkflow(latest.workflow_id);
      dispatch({ type: "WORKFLOW_RESTORED", status: latest });
      if (latest.status === "pending" || latest.status === "running") {
        void loadLiveStatus(latest.workflow_id).then((status) => {
          if (isTerminalStatus(status.status)) return loadTerminalBundle(latest.workflow_id);
        }).catch((error) => dispatch({ type: "RESOURCE_FAILED", resource: "workflow_status", message: userFacingError(error, "resource") }));
      } else {
        void loadTerminalBundle(latest.workflow_id).catch((error) => dispatch({ type: "RESOURCE_FAILED", resource: "terminal_bundle", message: userFacingError(error, "resource") }));
      }
    };
    if (targetWorkflowId) {
      await loadSurfaceResource("workflow_status", () => apiClient.workflowStatus(targetWorkflowId), restoreWorkflow, "bootstrap");
      return;
    }
    await loadSurfaceResource("design_list", () => apiClient.listDesigns(), (designs) => {
      const latest = selectWorkflowToRestore(designs);
      if (latest) restoreWorkflow(latest);
    }, "bootstrap");
  }, [activateWorkflow, apiClient, dispatch, loadLiveStatus, loadSurfaceResource, loadTerminalBundle, state.phase, state.workflowId, submissionInFlightRef]);

  useEffect(() => {
    if (restoreTarget.current !== initialWorkflowId) {
      bootstrapRestoreEpochRef.current += 1;
      restoreTarget.current = initialWorkflowId;
    }
    void restoreLatestDesign().catch(() => undefined);
  }, [initialWorkflowId, restoreLatestDesign]);
  useEffect(() => {
    if (!state.workflowId || state.runtimeMode !== "sse") return;
    const cursor = streamCursorRef.current;
    streamCursorRef.current = null;
    startEventStream(state.workflowId, cursor);
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
  }, [startEventStream, state.runtimeMode, state.workflowId]);
  useEffect(() => {
    if (!state.workflowId || !needsPolling(state.phase, state.runtimeMode)) return;
    let inFlight = false;
    const poll = () => {
      if (inFlight) return;
      inFlight = true;
      void loadPollingSnapshot(state.workflowId!).catch((error) => dispatch({
        type: "RESOURCE_FAILED", resource: "terminal_bundle", message: userFacingError(error, "resource")
      })).finally(() => { inFlight = false; });
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => window.clearInterval(timer);
  }, [dispatch, loadPollingSnapshot, state.phase, state.runtimeMode, state.workflowId]);

  const closeEventStream = useCallback(() => streamRef.current?.close(), []);
  const beginCreatedWorkflow = useCallback(async (workflowId: string) => {
    setVersions([]);
    eventSequenceCursorRef.current = null;
    activateWorkflow(workflowId);
    dispatch({ type: "DESIGN_CREATED", workflowId });
    const status = await loadLiveStatus(workflowId);
    if (isTerminalStatus(status.status)) await loadTerminalBundle(workflowId);
  }, [activateWorkflow, dispatch, loadLiveStatus, loadTerminalBundle]);

  return {
    activateWorkflow,
    beginCreatedWorkflow,
    closeEventStream,
    eventSequenceCursorRef,
    invalidateBootstrapRestore,
    loadLiveStatus,
    loadTerminalBundle,
    rememberEventSequence,
    restoreLatestDesign,
    setVersions,
    streamCursorRef,
    versions
  };
}
