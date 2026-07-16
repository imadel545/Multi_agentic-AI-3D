import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type Dispatch
} from "react";
import {
  api,
  TelecomStudioApi,
  type DocumentPackCorrectionPayload
} from "./api/client";
import { normalizeWorkflowEvent, openWorkflowEventStream } from "./api/sse";
import type {
  AssetInventory,
  DocumentPackCapabilities,
  DocumentPackReview,
  DocumentPackSummary,
  Health,
  ParseRequirementsResponse,
  PublicVersionInfo,
  ViewerBundle,
  WorkflowEvent,
  WorkflowStatus
} from "./api/schemas";
import {
  AgentStageRail,
  BackendStatusBar,
  ChatCommandPanel,
  CurrentOperationStrip,
  InspectorDock
} from "./components/StudioKernel";
import {
  actionIsSupported,
  initialWorkflowState,
  workflowReducer,
  type WorkflowMachineAction,
  type WorkflowPhase
} from "./state/workflowMachine";

const ActivePromptDetail = "high" as const;
const TelecomGlbViewer = lazy(() =>
  import("./features/three-viewer/TelecomGlbViewer").then((module) => ({
    default: module.TelecomGlbViewer
  }))
);

export default function App() {
  const [state, dispatch] = useReducer(workflowReducer, initialWorkflowState);
  const [health, setHealth] = useState<Health | null>(null);
  const [inventory, setInventory] = useState<AssetInventory | null>(null);
  const [documentCapabilities, setDocumentCapabilities] =
    useState<DocumentPackCapabilities | null>(null);
  const [documentPackSummary, setDocumentPackSummary] = useState<DocumentPackSummary | null>(null);
  const [documentPackReview, setDocumentPackReview] = useState<DocumentPackReview | null>(null);
  const [documentPackMessage, setDocumentPackMessage] = useState<string | null>(null);
  const [documentPackBusy, setDocumentPackBusy] = useState(false);
  const [documentCorrectionBusy, setDocumentCorrectionBusy] = useState(false);
  const [requirementsAnalysis, setRequirementsAnalysis] =
    useState<ParseRequirementsResponse | null>(null);
  const [analyzedPrompt, setAnalyzedPrompt] = useState<string | null>(null);
  const [submittedRequirementsHash, setSubmittedRequirementsHash] = useState<string | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [versions, setVersions] = useState<PublicVersionInfo[]>([]);
  const [ragEvidence, setRagEvidence] = useState<unknown | null>(null);
  const [revisionPrompt, setRevisionPrompt] = useState("");
  const [revisionMessage, setRevisionMessage] = useState<string | null>(null);
  const [revisionBusy, setRevisionBusy] = useState(false);
  const [rollbackBusyVersionId, setRollbackBusyVersionId] = useState<string | null>(null);
  const [versionMessage, setVersionMessage] = useState<string | null>(null);
  const apiClient = useMemo(() => api, []);
  const streamRef = useRef<{ close: () => void } | null>(null);
  const streamCursorRef = useRef<string | null>(null);
  const submissionInFlightRef = useRef(false);
  const restoredWorkflowRef = useRef(false);
  const resourceNotice = useMemo(
    () => firstResourceNotice(state.resourceErrors),
    [state.resourceErrors]
  );
  const toArtifactUrl = useCallback(
    (url: string | null | undefined) => apiClient.artifactUrl(url),
    [apiClient]
  );

  useEffect(() => {
    let cancelled = false;
    void apiClient
      .health()
      .then((nextHealth) => {
        if (!cancelled) setHealth(nextHealth);
      })
      .catch((error) => {
        if (!cancelled) dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
      });
    void apiClient
      .studioSummary()
      .then((summary) => {
        if (!cancelled) {
          dispatch({ type: "BOOTSTRAP_LOADED", summary });
          dispatch({ type: "RESOURCE_RECOVERED", resource: "studio_summary" });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "studio_summary",
            message: errorMessage(error)
          });
        }
      });
    void apiClient
      .assetInventory()
      .then((nextInventory) => {
        if (!cancelled) {
          setInventory(nextInventory);
          dispatch({ type: "RESOURCE_RECOVERED", resource: "asset_inventory" });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "asset_inventory",
            message: errorMessage(error)
          });
        }
      });
    void apiClient
      .documentPackCapabilities()
      .then((caps) => {
        if (!cancelled) {
          setDocumentCapabilities(caps);
          dispatch({ type: "RESOURCE_RECOVERED", resource: "document_capabilities" });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "document_capabilities",
            message: errorMessage(error)
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiClient]);

  const loadLiveStatus = useCallback(
    async (workflowId: string) => {
      const status = await apiClient.workflowStatus(workflowId);
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
      try {
        const operation = await apiClient.currentOperation(workflowId);
        dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation });
        dispatch({ type: "RESOURCE_RECOVERED", resource: "current_operation" });
      } catch (error) {
        dispatch({
          type: "RESOURCE_FAILED",
          resource: "current_operation",
          message: errorMessage(error)
        });
      }
      return status;
    },
    [apiClient]
  );

  const loadTerminalBundle = useCallback(
    async (workflowId: string) => {
      const status = await apiClient.workflowStatus(workflowId);
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });

      const [operationResult, bundleResult, timelineResult, issuesResult, versionsResult] =
        await Promise.allSettled([
          apiClient.currentOperation(workflowId),
          apiClient.viewerBundle(workflowId),
          apiClient.timelineSummary(workflowId),
          apiClient.userIssues(workflowId),
          apiClient.versions(workflowId)
        ]);

      applyResourceResult(
        operationResult,
        "current_operation",
        (operation) => dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation }),
        dispatch
      );
      const bundle: ViewerBundle | null =
        bundleResult.status === "fulfilled" ? bundleResult.value : null;
      applyResourceResult(
        bundleResult,
        "viewer_bundle",
        (nextBundle) => dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle: nextBundle }),
        dispatch
      );
      applyResourceResult(
        timelineResult,
        "timeline",
        (timeline) => dispatch({ type: "TIMELINE_LOADED", timeline }),
        dispatch
      );
      applyResourceResult(
        issuesResult,
        "user_issues",
        (issues) => dispatch({ type: "USER_ISSUES_LOADED", userIssues: issues }),
        dispatch
      );
      applyResourceResult(
        versionsResult,
        "versions",
        (nextVersions) => setVersions(nextVersions),
        dispatch
      );

      if (!bundle?.rag_evidence_url) {
        setRagEvidence(null);
        dispatch({ type: "RESOURCE_RECOVERED", resource: "rag_evidence" });
        return;
      }
      try {
        setRagEvidence(await apiClient.artifactJson(bundle.rag_evidence_url));
        dispatch({ type: "RESOURCE_RECOVERED", resource: "rag_evidence" });
      } catch (error) {
        setRagEvidence(null);
        dispatch({
          type: "RESOURCE_FAILED",
          resource: "rag_evidence",
          message: errorMessage(error)
        });
      }
    },
    [apiClient]
  );

  const startEventStream = useCallback(
    (workflowId: string, afterEventId?: string | null) => {
      streamRef.current?.close();
      streamRef.current = openWorkflowEventStream(
        apiClient.streamUrl(workflowId, afterEventId),
        {
          onEvent: (event) => dispatch({ type: "EVENT_RECEIVED", event }),
          onTerminal: (event) => {
            void loadTerminalBundle(event.workflow_id).catch((error) => {
              dispatch({
                type: "RESOURCE_FAILED",
                resource: "terminal_bundle",
                message: errorMessage(error)
              });
            });
          },
          onError: (error) => dispatch({ type: "SSE_FAILED", message: error.message }),
          onRecovered: () => dispatch({ type: "SSE_RECOVERED" })
        }
      );
    },
    [apiClient, loadTerminalBundle]
  );

  const loadPollingSnapshot = useCallback(
    async (workflowId: string) => {
      let status: WorkflowStatus;
      try {
        status = await apiClient.workflowStatus(workflowId);
        dispatch({ type: "STATUS_LOADED", status });
        dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
      } catch (error) {
        dispatch({
          type: "RESOURCE_FAILED",
          resource: "workflow_status",
          message: errorMessage(error)
        });
        return;
      }

      const [operationResult, eventsResult, timelineResult] = await Promise.allSettled([
        apiClient.currentOperation(workflowId),
        apiClient.workflowEvents(workflowId),
        apiClient.timelineSummary(workflowId)
      ]);
      applyResourceResult(
        operationResult,
        "current_operation",
        (operation) => dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation }),
        dispatch
      );
      applyResourceResult(
        eventsResult,
        "events",
        (events) => {
          for (const event of events) {
            dispatch({ type: "EVENT_RECEIVED", event: normalizeWorkflowEvent(event) });
          }
        },
        dispatch
      );
      applyResourceResult(
        timelineResult,
        "timeline",
        (timeline) => dispatch({ type: "TIMELINE_LOADED", timeline }),
        dispatch
      );
      if (status.status === "completed" || status.status === "failed") {
        await loadTerminalBundle(workflowId);
      }
    },
    [apiClient, loadTerminalBundle]
  );

  useEffect(() => {
    if (restoredWorkflowRef.current || state.workflowId || state.phase !== "idle") {
      return;
    }
    let cancelled = false;
    apiClient
      .listDesigns()
      .then((designs) => {
        if (cancelled) {
          return;
        }
        const latest = selectWorkflowToRestore(designs);
        if (!latest) {
          return;
        }
        restoredWorkflowRef.current = true;
        dispatch({ type: "WORKFLOW_RESTORED", status: latest });
        if (latest.status === "pending" || latest.status === "running") {
          void loadLiveStatus(latest.workflow_id)
            .then((status) => {
              if (isTerminalStatus(status.status)) {
                return loadTerminalBundle(latest.workflow_id);
              }
            })
            .catch((error) => {
              dispatch({
                type: "RESOURCE_FAILED",
                resource: "workflow_status",
                message: errorMessage(error)
              });
            });
        } else {
          void loadTerminalBundle(latest.workflow_id).catch((error) => {
            dispatch({
              type: "RESOURCE_FAILED",
              resource: "terminal_bundle",
              message: errorMessage(error)
            });
          });
        }
      })
      .catch(() => {
        // Resume is best-effort; bootstrap health/errors are handled separately.
      });
    return () => {
      cancelled = true;
    };
  }, [apiClient, loadLiveStatus, loadTerminalBundle, state.phase, state.workflowId]);

  const loadDocumentPackReview = useCallback(
    async (packId: string) => {
      const review = await apiClient.documentPackReview(packId);
      setDocumentPackReview(review);
      setDocumentPackSummary(review.summary);
      return review;
    },
    [apiClient]
  );

  const analyzePrompt = useCallback(async () => {
    if (!state.prompt.trim()) {
      return;
    }
    const prompt = state.prompt.trim();
    setSubmittedRequirementsHash(null);
    setAnalysisBusy(true);
    setAnalysisError(null);
    try {
      const analysis = await apiClient.parseRequirements({
        requirements_text: prompt,
        detail_level: ActivePromptDetail,
        use_llm: null
      });
      setRequirementsAnalysis(analysis);
      setAnalyzedPrompt(prompt);
      if (!analysis.requirements) {
        setAnalysisError("Le backend n’a pas produit de RequirementSpec confirmable.");
      }
    } catch (error) {
      setRequirementsAnalysis(null);
      setAnalyzedPrompt(null);
      setAnalysisError(errorMessage(error));
    } finally {
      setAnalysisBusy(false);
    }
  }, [apiClient, state.prompt]);

  const submitPrompt = useCallback(async () => {
    if (submissionInFlightRef.current) {
      return;
    }
    const prompt = state.prompt.trim();
    if (
      !prompt ||
      analyzedPrompt !== prompt ||
      !requirementsAnalysis?.requirements ||
      !requirementsAnalysis.requirements_hash
    ) {
      setAnalysisError("Analysez puis confirmez la demande actuelle avant de générer le design.");
      return;
    }
    if (
      submittedRequirementsHash === requirementsAnalysis.requirements_hash &&
      state.phase !== "failed"
    ) {
      setAnalysisError(
        "Cette compréhension a déjà lancé le design actif. Modifiez ou réanalysez la demande avant de créer un autre workflow."
      );
      return;
    }
    submissionInFlightRef.current = true;
    streamRef.current?.close();
    setRevisionMessage(null);
    setVersionMessage(null);
    dispatch({ type: "SUBMIT_STARTED" });
    try {
      const created = await apiClient.createDesign({
        requirements_text: prompt,
        confirmed_requirements: requirementsAnalysis.requirements,
        confirmed_requirements_hash: requirementsAnalysis.requirements_hash,
        options: { detail_level: ActivePromptDetail, use_llm: null }
      });
      setSubmittedRequirementsHash(requirementsAnalysis.requirements_hash);
      setVersions([]);
      setRagEvidence(null);
      dispatch({ type: "DESIGN_CREATED", workflowId: created.workflow_id });
      const status = await loadLiveStatus(created.workflow_id);
      if (isTerminalStatus(status.status)) {
        await loadTerminalBundle(created.workflow_id);
      }
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
    } finally {
      submissionInFlightRef.current = false;
    }
  }, [
    analyzedPrompt,
    apiClient,
    loadLiveStatus,
    loadTerminalBundle,
    requirementsAnalysis,
    state.phase,
    state.prompt,
    submittedRequirementsHash
  ]);

  const changePrompt = useCallback((prompt: string) => {
    setRequirementsAnalysis(null);
    setAnalyzedPrompt(null);
    setSubmittedRequirementsHash(null);
    setAnalysisError(null);
    dispatch({ type: "PROMPT_CHANGED", prompt });
  }, []);

  const uploadDocumentPack = useCallback(
    async (file: File) => {
      const sizeError = documentPackSizeError(file, documentCapabilities);
      if (sizeError) {
        setDocumentPackMessage(sizeError);
        return;
      }
      setDocumentPackBusy(true);
      setDocumentPackMessage(null);
      setDocumentPackReview(null);
      try {
        const summary = await apiClient.createDocumentPack(file);
        setDocumentPackSummary(summary);
        const review = await loadDocumentPackReview(summary.pack_id);
        setDocumentPackMessage(
          review.summary.can_generate_design
            ? "Pack analysé: génération possible."
            : "Pack analysé: corrigez les champs bloquants avant génération."
        );
      } catch (error) {
        setDocumentPackMessage(errorMessage(error));
      } finally {
        setDocumentPackBusy(false);
      }
    },
    [apiClient, documentCapabilities, loadDocumentPackReview]
  );

  const applyDocumentPackCorrection = useCallback(
    async (field: string, rawValue: string, reason: string) => {
      if (!documentPackSummary) {
        return;
      }
      setDocumentCorrectionBusy(true);
      setDocumentPackMessage(null);
      try {
        const correction: DocumentPackCorrectionPayload = {
          field,
          value: parseCorrectionValue(rawValue),
          reason: reason.trim(),
          corrected_by: "user"
        };
        const summary = await apiClient.applyDocumentPackCorrection(
          documentPackSummary.pack_id,
          correction
        );
        setDocumentPackSummary(summary);
        const review = await loadDocumentPackReview(summary.pack_id);
        setDocumentPackMessage(
          review.summary.can_generate_design
            ? "Correction enregistrée. Le pack est prêt à générer."
            : "Correction enregistrée. D’autres points restent à vérifier."
        );
      } catch (error) {
        setDocumentPackMessage(errorMessage(error));
      } finally {
        setDocumentCorrectionBusy(false);
      }
    },
    [apiClient, documentPackSummary, loadDocumentPackReview]
  );

  const generateFromDocumentPack = useCallback(async () => {
    if (!documentPackSummary) {
      return;
    }
    streamRef.current?.close();
    setDocumentPackBusy(true);
    setRevisionMessage(null);
    dispatch({ type: "SUBMIT_STARTED" });
    try {
      const generated = await apiClient.generateDesignFromDocumentPack(documentPackSummary.pack_id);
      if (!generated.workflow_id) {
        dispatch({
          type: "REQUEST_FAILED",
          message: `Document-pack bloqué: ${generated.status}`
        });
        setDocumentPackMessage("Le backend a refusé la génération depuis ce pack.");
        return;
      }
      setDocumentPackMessage("Workflow lancé depuis le pack documentaire.");
      setVersions([]);
      setRagEvidence(null);
      dispatch({ type: "DESIGN_CREATED", workflowId: generated.workflow_id });
      const status = await loadLiveStatus(generated.workflow_id);
      if (isTerminalStatus(status.status)) {
        await loadTerminalBundle(generated.workflow_id);
      }
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
      setDocumentPackMessage(errorMessage(error));
    } finally {
      setDocumentPackBusy(false);
    }
  }, [apiClient, documentPackSummary, loadLiveStatus, loadTerminalBundle]);

  const submitRevision = useCallback(async () => {
    if (!state.workflowId || !revisionPrompt.trim() || revisionBusy) {
      return;
    }
    const workflowId = state.workflowId;
    setRevisionMessage(null);
    setRevisionBusy(true);
    let streamNotice: string | null = null;
    let runtimeMode: "sse" | "polling" = "polling";
    try {
      try {
        const eventHistory = await apiClient.workflowEvents(workflowId);
        for (const event of eventHistory) {
          dispatch({ type: "EVENT_RECEIVED", event: normalizeWorkflowEvent(event) });
        }
        const cursor = latestEventCursor(eventHistory);
        if (cursor) {
          streamCursorRef.current = cursor;
          runtimeMode = "sse";
        }
      } catch (error) {
        streamNotice = `Streaming live indisponible: ${errorMessage(error)}`;
        setRevisionMessage(streamNotice);
      }
      dispatch({ type: "REVISION_STARTED", runtimeMode });
      const result = await apiClient.editDesign(workflowId, {
        edit_prompt: revisionPrompt
      });
      setRevisionMessage(
        [result.message ?? `Édition ${result.status}`, streamNotice].filter(Boolean).join(" · ")
      );
      if (result.status !== "applied") {
        dispatch({
          type: "REQUEST_FAILED",
          message: result.message ?? "La révision a été refusée par le backend."
        });
        return;
      }
      setRevisionPrompt("");
      await loadTerminalBundle(workflowId);
    } catch (error) {
      setRevisionMessage(errorMessage(error));
    } finally {
      setRevisionBusy(false);
    }
  }, [
    apiClient,
    loadTerminalBundle,
    revisionBusy,
    revisionPrompt,
    state.workflowId
  ]);

  const rollbackVersion = useCallback(
    async (versionId: string) => {
      if (!state.workflowId || rollbackBusyVersionId) {
        return;
      }
      setRollbackBusyVersionId(versionId);
      setVersionMessage(null);
      let runtimeMode: "sse" | "polling" = "polling";
      try {
        try {
          const eventHistory = await apiClient.workflowEvents(state.workflowId);
          const cursor = latestEventCursor(eventHistory);
          streamCursorRef.current = cursor;
          runtimeMode = cursor ? "sse" : "polling";
        } catch (error) {
          setVersionMessage(`Streaming live indisponible: ${errorMessage(error)}`);
        }
        dispatch({
          type: "REVISION_STARTED",
          runtimeMode
        });
        const result = await apiClient.rollbackVersion(state.workflowId, versionId);
        setVersionMessage(result.message);
        await loadTerminalBundle(state.workflowId);
      } catch (error) {
        setVersionMessage(errorMessage(error));
      } finally {
        setRollbackBusyVersionId(null);
      }
    },
    [apiClient, loadTerminalBundle, rollbackBusyVersionId, state.workflowId]
  );

  useEffect(() => {
    if (!state.workflowId || state.runtimeMode !== "sse") {
      return;
    }
    const cursor = streamCursorRef.current;
    streamCursorRef.current = null;
    startEventStream(state.workflowId, cursor);
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
  }, [startEventStream, state.runtimeMode, state.workflowId]);

  useEffect(() => {
    if (!state.workflowId || !needsPolling(state.phase, state.runtimeMode)) {
      return;
    }
    let inFlight = false;
    const poll = () => {
      if (inFlight) return;
      inFlight = true;
      void loadPollingSnapshot(state.workflowId!).finally(() => {
        inFlight = false;
      });
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => window.clearInterval(timer);
  }, [loadPollingSnapshot, state.phase, state.runtimeMode, state.workflowId]);

  const canEditCurrentDesign =
    state.viewerBundle?.status === "completed" &&
    state.viewerBundle.available_actions.includes("edit_design") &&
    actionIsSupported("edit_design", state.viewerBundle.unsupported_actions);
  const analysisIsCurrent =
    analyzedPrompt === state.prompt.trim() &&
    requirementsAnalysis?.requirements != null &&
    requirementsAnalysis.requirements_hash != null;
  const analysisWasSubmitted =
    analysisIsCurrent &&
    submittedRequirementsHash === requirementsAnalysis?.requirements_hash;
  const canRollbackVersions =
    state.viewerBundle?.runtime_capabilities?.can_rollback_versions === true &&
    actionIsSupported("rollback_versions", state.viewerBundle.unsupported_actions);

  return (
    <div className="studio-root">
      <BackendStatusBar
        bundle={state.viewerBundle}
        health={health}
        issues={state.userIssues}
        phase={state.phase}
      />
      <main className="studio-layout">
        <aside className="left-rail">
          <ChatCommandPanel
            analysis={analysisIsCurrent ? requirementsAnalysis : null}
            analysisBusy={analysisBusy}
            analysisError={analysisError}
            analysisSubmitted={analysisWasSubmitted}
            canEdit={canEditCurrentDesign}
            correctionBusy={documentCorrectionBusy}
            documentCapabilities={documentCapabilities}
            documentPackBusy={documentPackBusy}
            documentPackMessage={documentPackMessage}
            documentPackReview={documentPackReview}
            documentPackSummary={documentPackSummary}
            editMessage={revisionMessage}
            error={state.error}
            onAnalyze={analyzePrompt}
            onConfirm={submitPrompt}
            onDocumentPackCorrection={applyDocumentPackCorrection}
            onDocumentPackGenerate={generateFromDocumentPack}
            onDocumentPackUpload={uploadDocumentPack}
            onPromptChange={changePrompt}
            onRevisionPromptChange={setRevisionPrompt}
            onRevisionSubmit={submitRevision}
            phase={state.phase}
            prompt={state.prompt}
            submissionPending={state.pendingSubmission}
            revisionBusy={revisionBusy}
            revisionPrompt={revisionPrompt}
          />
          <CurrentOperationStrip
            notice={state.transportError ?? resourceNotice}
            operation={state.currentOperation}
            phase={state.phase}
            runtimeMode={state.runtimeMode}
          />
          <AgentStageRail events={state.events} phase={state.phase} timeline={state.timeline} />
        </aside>
        <section className="workbench" aria-label="Studio 3D">
          <Suspense fallback={<ViewerLoadingFallback />}>
            <TelecomGlbViewer bundle={state.viewerBundle} toAbsoluteUrl={toArtifactUrl} />
          </Suspense>
          <InspectorDock
            bundle={state.viewerBundle}
            canRollback={canRollbackVersions}
            documentCapabilities={documentCapabilities}
            events={state.events}
            evidence={ragEvidence}
            inventory={inventory}
            issues={state.userIssues}
            summary={state.summary}
            timeline={state.timeline}
            toAbsoluteUrl={toArtifactUrl}
            onRollbackVersion={rollbackVersion}
            rollbackBusyVersionId={rollbackBusyVersionId}
            versionMessage={versionMessage}
            versions={versions}
          />
        </section>
      </main>
    </div>
  );
}

function ViewerLoadingFallback() {
  return (
    <section className="viewer-shell viewer-loading" aria-label="Viewer 3D loading">
      <div className="viewer-toolbar">
        <div>
          <span className="eyebrow">Viewer 3D</span>
          <h2>Chargement du viewer</h2>
        </div>
      </div>
      <div className="viewer-fallback dark">
        <strong>Préparation WebGL</strong>
        <p>Le moteur 3D se charge séparément pour garder le studio réactif.</p>
      </div>
    </section>
  );
}

export function needsPolling(phase: WorkflowPhase, runtimeMode: string): boolean {
  return runtimeMode === "polling" && (phase === "running" || phase === "streaming");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function selectWorkflowToRestore(designs: WorkflowStatus[]): WorkflowStatus | null {
  for (const statuses of [
    new Set(["pending", "running"]),
    new Set(["completed"]),
    new Set(["failed"])
  ]) {
    const candidates = designs.filter((design) => statuses.has(design.status));
    if (candidates.length) {
      return [...candidates].sort(
        (left, right) => timestamp(right.created_at) - timestamp(left.created_at)
      )[0] ?? null;
    }
  }
  return null;
}

export function latestEventCursor(
  events: Array<Pick<WorkflowEvent, "event_id">>
): string | null {
  return events.at(-1)?.event_id ?? null;
}

export function documentPackSizeError(
  file: Pick<File, "size">,
  capabilities: DocumentPackCapabilities | null
): string | null {
  const maxZipSizeMb = capabilities?.limits?.max_zip_size_mb;
  if (!maxZipSizeMb || file.size <= maxZipSizeMb * 1024 * 1024) {
    return null;
  }
  return `Le ZIP dépasse la limite locale de ${maxZipSizeMb} Mo. Réduisez le pack avant l’analyse.`;
}

export function parseCorrectionValue(
  rawValue: string
): DocumentPackCorrectionPayload["value"] {
  const value = rawValue.trim();
  if (!value) {
    throw new Error("La valeur de correction est obligatoire.");
  }

  try {
    return normalizeCorrectionValue(JSON.parse(value));
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("Type de correction")) {
      throw error;
    }
  }

  if (value.includes(",")) {
    const items = value.split(",").map((item) => item.trim()).filter(Boolean);
    const numbers = items.map(Number);
    return numbers.every(Number.isFinite) ? numbers : items;
  }
  return value;
}

function normalizeCorrectionValue(value: unknown): DocumentPackCorrectionPayload["value"] {
  if (typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (Array.isArray(value) && value.length > 0) {
    if (value.every((item): item is number => typeof item === "number" && Number.isFinite(item))) {
      return value;
    }
    if (value.every((item): item is string => typeof item === "string")) {
      return value;
    }
  }
  throw new Error("Type de correction non supporté. Utilisez texte, nombre, booléen ou liste.");
}

function timestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isTerminalStatus(status: string): boolean {
  return status === "completed" || status === "failed";
}

export function createTestApi(baseUrl = "http://127.0.0.1:8000", fetcher = fetch) {
  return new TelecomStudioApi(baseUrl, fetcher);
}

function applyResourceResult<T>(
  result: PromiseSettledResult<T>,
  resource: string,
  onValue: (value: T) => void,
  send: Dispatch<WorkflowMachineAction>
) {
  if (result.status === "fulfilled") {
    onValue(result.value);
    send({ type: "RESOURCE_RECOVERED", resource });
    return;
  }
  send({
    type: "RESOURCE_FAILED",
    resource,
    message: errorMessage(result.reason)
  });
}

function firstResourceNotice(errors: Record<string, string>): string | null {
  const first = Object.entries(errors)[0];
  return first ? `Donnée secondaire indisponible (${first[0]}): ${first[1]}` : null;
}
