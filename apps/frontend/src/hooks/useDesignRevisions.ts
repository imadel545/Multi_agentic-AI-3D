import { useCallback, useRef, useState, type MutableRefObject } from "react";
import type { TelecomStudioApi } from "../api/client";
import type { TowerAccessSummary } from "../api/schemas";
import {
  latestEventCursor,
  latestEventSequence,
  reconcileAfterAmbiguousMutation,
  revisionOutcomeMessage,
  userFacingError
} from "../AppSupport";
import { actionIsSupported, type WorkflowMachineState } from "../state/workflowMachine";
import type { WorkflowDispatch } from "./studioAppTypes";

type UseDesignRevisionsOptions = {
  apiClient: TelecomStudioApi;
  clearAnalysis: () => void;
  dispatch: WorkflowDispatch;
  initialPrompt: string;
  initialWorkflowId?: string | null;
  loadTerminalBundle: (workflowId: string) => Promise<void>;
  onDraftChange?: (value: string) => void;
  rememberEventSequence: (sequence: number | null | undefined) => void;
  selectedSemanticRoot: string | null;
  selectedVersionId: string | null;
  state: WorkflowMachineState;
  streamCursorRef: MutableRefObject<string | null>;
  towerAccess: TowerAccessSummary | null;
};

export function useDesignRevisions({
  apiClient,
  clearAnalysis,
  dispatch,
  initialPrompt,
  initialWorkflowId,
  loadTerminalBundle,
  onDraftChange,
  rememberEventSequence,
  selectedSemanticRoot,
  selectedVersionId,
  state,
  streamCursorRef,
  towerAccess
}: UseDesignRevisionsOptions) {
  const [revisionPrompt, setRevisionPrompt] = useState(initialWorkflowId ? initialPrompt : "");
  const [revisionMessage, setRevisionMessage] = useState<string | null>(null);
  const [revisionBusy, setRevisionBusy] = useState(false);
  const [rollbackBusyVersionId, setRollbackBusyVersionId] = useState<string | null>(null);
  const [versionMessage, setVersionMessage] = useState<string | null>(null);
  const revisionInFlightRef = useRef(false);

  const clearRevisionMessages = useCallback(() => {
    setRevisionMessage(null);
    setVersionMessage(null);
  }, []);

  const changeRevisionPrompt = useCallback((value: string) => {
    setRevisionPrompt(value);
    onDraftChange?.(value);
  }, [onDraftChange]);

  const submitRevision = useCallback(async () => {
    if (!state.workflowId || !revisionPrompt.trim() || revisionBusy || revisionInFlightRef.current) return;
    revisionInFlightRef.current = true;
    const workflowId = state.workflowId;
    const submittedRevisionPrompt = revisionPrompt.trim();
    if (selectedSemanticRoot && selectedSemanticRoot === towerAccess?.semantic_root) {
      revisionInFlightRef.current = false;
      setRevisionMessage("Cet ensemble est vérifié pour inspection. Sa modification ciblée n’est pas encore disponible. Désélectionnez-le pour demander une révision générale.");
      return;
    }
    if (selectedSemanticRoot && !selectedVersionId) {
      revisionInFlightRef.current = false;
      setRevisionMessage("La version de cette sélection n’est pas vérifiée. Rechargez le design avant de modifier ce composant.");
      return;
    }
    const target = selectedSemanticRoot && selectedVersionId
      ? { target_semantic_root: selectedSemanticRoot, expected_version_id: selectedVersionId }
      : {};
    setRevisionMessage(null);
    setRevisionBusy(true);
    let streamNotice: string | null = null;
    let runtimeMode: "sse" | "polling" = "polling";
    try {
      try {
        const eventHistory = await apiClient.workflowEvents(workflowId);
        rememberEventSequence(latestEventSequence(eventHistory));
        const cursor = latestEventCursor(eventHistory);
        if (cursor) {
          streamCursorRef.current = cursor;
          runtimeMode = "sse";
        }
      } catch (error) {
        streamNotice = "Le suivi temps réel n’a pas pu reprendre; la synchronisation de secours reste active.";
        setRevisionMessage(streamNotice);
      }
      dispatch({ type: "REVISION_STARTED", runtimeMode });
      const result = await apiClient.editDesign(workflowId, { edit_prompt: submittedRevisionPrompt, ...target });
      const outcome = revisionOutcomeMessage(result, submittedRevisionPrompt);
      setRevisionMessage([outcome, streamNotice].filter(Boolean).join(" · "));
      if (result.status !== "applied") {
        dispatch({ type: "REVISION_FINISHED" });
        await loadTerminalBundle(workflowId);
        return;
      }
      setRevisionPrompt("");
      onDraftChange?.("");
      clearAnalysis();
      dispatch({ type: "REVISION_FINISHED" });
      await loadTerminalBundle(workflowId);
    } catch (error) {
      const message = userFacingError(error, "edit");
      setRevisionMessage(message);
      dispatch({ type: "REQUEST_FAILED", message });
      await reconcileAfterAmbiguousMutation(() => loadTerminalBundle(workflowId));
    } finally {
      revisionInFlightRef.current = false;
      setRevisionBusy(false);
    }
  }, [apiClient, clearAnalysis, dispatch, loadTerminalBundle, onDraftChange, rememberEventSequence, revisionBusy, revisionPrompt, selectedSemanticRoot, selectedVersionId, state.workflowId, streamCursorRef, towerAccess?.semantic_root]);

  const rollbackVersion = useCallback(async (versionId: string) => {
    if (!state.workflowId || rollbackBusyVersionId) return;
    setRollbackBusyVersionId(versionId);
    setVersionMessage(null);
    let runtimeMode: "sse" | "polling" = "polling";
    try {
      try {
        const eventHistory = await apiClient.workflowEvents(state.workflowId);
        rememberEventSequence(latestEventSequence(eventHistory));
        const cursor = latestEventCursor(eventHistory);
        streamCursorRef.current = cursor;
        runtimeMode = cursor ? "sse" : "polling";
      } catch (error) {
        setVersionMessage("Le suivi direct n’est pas disponible; la restauration reste synchronisée.");
      }
      dispatch({ type: "REVISION_STARTED", runtimeMode });
      const result = await apiClient.rollbackVersion(state.workflowId, versionId);
      setVersionMessage(result.message);
      dispatch({ type: "REVISION_FINISHED" });
      await loadTerminalBundle(state.workflowId);
    } catch (error) {
      setVersionMessage(userFacingError(error, "rollback"));
      dispatch({ type: "REVISION_FINISHED" });
      await reconcileAfterAmbiguousMutation(() => loadTerminalBundle(state.workflowId!));
    } finally {
      setRollbackBusyVersionId(null);
    }
  }, [apiClient, dispatch, loadTerminalBundle, rememberEventSequence, rollbackBusyVersionId, state.workflowId, streamCursorRef]);

  const canRollbackVersions = state.viewerBundle?.runtime_capabilities?.can_rollback_versions === true &&
    state.viewerBundle.available_actions.includes("rollback_version") &&
    actionIsSupported("rollback_version", state.viewerBundle.unsupported_actions) &&
    !revisionBusy && rollbackBusyVersionId === null &&
    (state.phase === "completed" || state.phase === "degraded");

  return {
    canRollbackVersions,
    changeRevisionPrompt,
    clearRevisionMessages,
    revisionBusy,
    revisionMessage,
    revisionPrompt,
    rollbackBusyVersionId,
    rollbackVersion,
    submitRevision,
    versionMessage
  };
}
