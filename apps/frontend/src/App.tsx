import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type Dispatch
} from "react";
import { CheckCircle2 } from "lucide-react";
import {
  ApiClientError,
  api,
  TelecomStudioApi,
  type DocumentPackCorrectionPayload
} from "./api/client";
import { normalizeWorkflowEvent, openWorkflowEventStream } from "./api/sse";
import type {
  AdaptationCapabilityCatalog,
  AssemblyPlanEvidence,
  DocumentPackCapabilities,
  DocumentPackReview,
  DocumentPackSummary,
  Health,
  LLMDecisionProvenance,
  MultimodalConsent,
  AssetInventory,
  AssetLibrarySearch,
  AssetLibrarySummary,
  ParseRequirementsResponse,
  ComponentProofs,
  PublicVersionInfo,
  RequirementSpec,
  SceneAdaptationCapabilities,
  ViewerBundle,
  EditDesignResponse,
  WorkflowEvent,
  WorkflowStatus
} from "./api/schemas";
import {
  BackendStatusBar,
  ChatCommandPanel,
  CurrentOperationStrip,
  InspectorDock,
  LiveGenerationOverlay
} from "./components/StudioKernel";
import {
  actionIsSupported,
  initialWorkflowState,
  workflowReducer,
  type WorkflowMachineAction,
  type WorkflowPhase
} from "./state/workflowMachine";
import {
  clearDocumentPackSession,
  readDocumentPackSession,
  writeDocumentPackSession
} from "./state/documentPackSession";

const ActivePromptDetail = "high" as const;
const TelecomGlbViewer = lazy(() =>
  import("./features/three-viewer/TelecomGlbViewer").then((module) => ({
    default: module.TelecomGlbViewer
  }))
);

type AppProps = {
  apiClient?: TelecomStudioApi;
};

export default function App({ apiClient = api }: AppProps) {
  const [state, dispatch] = useReducer(workflowReducer, initialWorkflowState);
  const [health, setHealth] = useState<Health | null>(null);
  const [assetLibrarySummary, setAssetLibrarySummary] =
    useState<AssetLibrarySummary | null>(null);
  const [assetInventory, setAssetInventory] = useState<AssetInventory | null>(null);
  const [assetLibrarySearch, setAssetLibrarySearch] =
    useState<AssetLibrarySearch | null>(null);
  const [assetLibrarySearchBusy, setAssetLibrarySearchBusy] = useState(false);
  const [assetLibrarySearchError, setAssetLibrarySearchError] = useState<string | null>(null);
  const [adaptationCatalog, setAdaptationCatalog] =
    useState<AdaptationCapabilityCatalog | null>(null);
  const [adaptationCapabilities, setAdaptationCapabilities] =
    useState<SceneAdaptationCapabilities | null>(null);
  const [qaEvidence, setQaEvidence] = useState<unknown | null>(null);
  const [llmProvenance, setLlmProvenance] = useState<LLMDecisionProvenance | null>(null);
  const [componentProofs, setComponentProofs] = useState<ComponentProofs | null>(null);
  const [assemblyPlan, setAssemblyPlan] = useState<AssemblyPlanEvidence | null>(null);
  const [activeRequirements, setActiveRequirements] = useState<RequirementSpec | null>(null);
  const [selectedSemanticRoot, setSelectedSemanticRoot] = useState<string | null>(null);
  const [ragEvidence, setRagEvidence] = useState<unknown | null>(null);
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
  const [multimodalConsent, setMultimodalConsent] =
    useState<MultimodalConsent>("disabled");
  const [versions, setVersions] = useState<PublicVersionInfo[]>([]);
  const [lastCertifiedBundle, setLastCertifiedBundle] = useState<ViewerBundle | null>(null);
  const [revisionPrompt, setRevisionPrompt] = useState("");
  const [revisionMessage, setRevisionMessage] = useState<string | null>(null);
  const [revisionBusy, setRevisionBusy] = useState(false);
  const [rollbackBusyVersionId, setRollbackBusyVersionId] = useState<string | null>(null);
  const [versionMessage, setVersionMessage] = useState<string | null>(null);
  const streamRef = useRef<{ close: () => void } | null>(null);
  const streamCursorRef = useRef<string | null>(null);
  const eventSequenceCursorRef = useRef<number | null>(null);
  const submissionInFlightRef = useRef(false);
  const revisionInFlightRef = useRef(false);
  const restoredWorkflowRef = useRef(false);
  const resourceRequestRef = useRef<Record<string, number>>({});
  const activeWorkflowRef = useRef<string | null>(null);
  const terminalBundleRequestRef = useRef(0);
  const terminalBundleAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const lastAssetLibraryQueryRef = useRef<string | null>(null);
  const toArtifactUrl = useCallback(
    (url: string | null | undefined) => apiClient.artifactUrl(url),
    [apiClient]
  );
  const multimodalIntelligence =
    state.summary?.runtime_capabilities?.multimodal_intelligence ??
    state.viewerBundle?.runtime_capabilities?.multimodal_intelligence ??
    null;
  const multimodalConsentAvailable =
    multimodalIntelligence?.enabled === true &&
    (multimodalIntelligence.status === "configured_unverified" ||
      multimodalIntelligence.status === "operational");
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

  useEffect(() => {
    if (!multimodalConsentAvailable && multimodalConsent !== "disabled") {
      setMultimodalConsent("disabled");
    }
  }, [multimodalConsent, multimodalConsentAvailable]);
  const rememberEventSequence = useCallback((sequence: number | null | undefined) => {
    if (sequence != null) {
      eventSequenceCursorRef.current = Math.max(
        eventSequenceCursorRef.current ?? 0,
        sequence
      );
    }
  }, []);
  const receiveWorkflowEvents = useCallback(
    (events: WorkflowEvent[]) => {
      const matching = events.filter((event) => isActiveWorkflow(event.workflow_id));
      const normalized = matching.map(normalizeWorkflowEvent);
      rememberEventSequence(latestEventSequence(matching));
      if (normalized.length) {
        dispatch({ type: "EVENTS_RECEIVED", events: normalized });
      }
    },
    [isActiveWorkflow, rememberEventSequence]
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      for (const resource of Object.keys(resourceRequestRef.current)) {
        resourceRequestRef.current[resource] += 1;
      }
      terminalBundleAbortRef.current?.abort();
      terminalBundleAbortRef.current = null;
    };
  }, []);

  const loadSurfaceResource = useCallback(
    async <T,>(
      resource: string,
      loader: () => Promise<T>,
      onValue: (value: T) => void,
      context: UserActionContext = "resource",
      onStart?: () => void
    ): Promise<T> => {
      const requestId = (resourceRequestRef.current[resource] ?? 0) + 1;
      resourceRequestRef.current[resource] = requestId;
      dispatch({ type: "RESOURCE_LOADING", resource });
      onStart?.();
      try {
        const value = await loader();
        if (
          mountedRef.current &&
          resourceRequestRef.current[resource] === requestId
        ) {
          onValue(value);
          dispatch({ type: "RESOURCE_RECOVERED", resource });
        }
        return value;
      } catch (error) {
        if (
          mountedRef.current &&
          resourceRequestRef.current[resource] === requestId
        ) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource,
            message: userFacingError(error, context)
          });
        }
        throw error;
      }
    },
    []
  );

  const loadHealth = useCallback(
    () =>
      loadSurfaceResource(
        "health",
        () => apiClient.health(),
        setHealth,
        "connection",
        () => setHealth(null)
      ),
    [apiClient, loadSurfaceResource]
  );
  const loadStudioSummary = useCallback(
    () =>
      loadSurfaceResource(
        "studio_summary",
        () => apiClient.studioSummary(),
        (summary) => dispatch({ type: "BOOTSTRAP_LOADED", summary }),
        "bootstrap"
      ),
    [apiClient, loadSurfaceResource]
  );
  const loadAssetLibrarySummary = useCallback(
    () =>
      loadSurfaceResource(
        "asset_library",
        () => apiClient.assetLibrarySummary(),
        setAssetLibrarySummary,
        "assets",
        () => setAssetLibrarySummary(null)
      ),
    [apiClient, loadSurfaceResource]
  );
  const loadAssetInventory = useCallback(
    () =>
      loadSurfaceResource(
        "asset_inventory",
        () => apiClient.assetInventory(),
        setAssetInventory,
        "assets",
        () => setAssetInventory(null)
      ),
    [apiClient, loadSurfaceResource]
  );
  const loadAdaptationCatalog = useCallback(
    () =>
      loadSurfaceResource(
        "adaptation_catalog",
        () => apiClient.adaptationCapabilityCatalog(),
        setAdaptationCatalog,
        "resource",
        () => setAdaptationCatalog(null)
      ),
    [apiClient, loadSurfaceResource]
  );
  const loadDocumentCapabilities = useCallback(
    () =>
      loadSurfaceResource(
        "document_capabilities",
        () => apiClient.documentPackCapabilities(),
        setDocumentCapabilities,
        "documents",
        () => setDocumentCapabilities(null)
      ),
    [apiClient, loadSurfaceResource]
  );

  useEffect(() => {
    void loadHealth().catch(() => undefined);
    void loadStudioSummary().catch(() => undefined);
    void loadAssetInventory().catch(() => undefined);
    void loadDocumentCapabilities().catch(() => undefined);
  }, [
    loadAssetInventory,
    loadDocumentCapabilities,
    loadHealth,
    loadStudioSummary
  ]);

  useEffect(() => {
    const bundle = state.viewerBundle;
    for (const resource of [
      "assembly_plan",
      "component_proofs",
      "qa_evidence",
      "requirements_context",
      "llm_provenance",
      "rag_evidence"
    ]) {
      resourceRequestRef.current[resource] =
        (resourceRequestRef.current[resource] ?? 0) + 1;
    }
    setAdaptationCapabilities(null);
    setAssemblyPlan(null);
    setComponentProofs(null);
    setQaEvidence(null);
    setLlmProvenance(null);
    setRagEvidence(null);
    setActiveRequirements(null);
    setSelectedSemanticRoot(null);
    if (!bundle) {
      return;
    }
    if (bundle.assembly_plan_url) {
      void loadSurfaceResource(
        "assembly_plan",
        () => apiClient.assemblyPlan(bundle.assembly_plan_url),
        setAssemblyPlan,
        "resource",
        () => setAssemblyPlan(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "assembly_plan" });
    }
    if (bundle.component_proofs_url) {
      void loadSurfaceResource(
        "component_proofs",
        () => apiClient.componentProofs(bundle.component_proofs_url),
        setComponentProofs,
        "resource",
        () => setComponentProofs(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "component_proofs" });
    }
    if (bundle.requirements_spec_url) {
      void loadSurfaceResource(
        "requirements_context",
        () => apiClient.requirementsSpec(bundle.requirements_spec_url),
        setActiveRequirements,
        "resource",
        () => setActiveRequirements(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "requirements_context" });
    }
    if (bundle.qa_report_url) {
      void loadSurfaceResource(
        "qa_evidence",
        () => apiClient.artifactJson(bundle.qa_report_url),
        setQaEvidence,
        "resource",
        () => setQaEvidence(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "qa_evidence" });
    }
    if (bundle.llm_decision_provenance) {
      setLlmProvenance(bundle.llm_decision_provenance);
      dispatch({ type: "RESOURCE_RECOVERED", resource: "llm_provenance" });
    } else if (bundle.llm_decision_provenance_url) {
      void loadSurfaceResource(
        "llm_provenance",
        () => apiClient.llmDecisionProvenance(bundle.llm_decision_provenance_url!),
        setLlmProvenance,
        "resource",
        () => setLlmProvenance(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "llm_provenance" });
    }
    if (bundle.rag_evidence_url) {
      void loadSurfaceResource(
        "rag_evidence",
        () => apiClient.artifactJson(bundle.rag_evidence_url!),
        setRagEvidence,
        "resource",
        () => setRagEvidence(null)
      ).catch(() => undefined);
    } else {
      dispatch({ type: "RESOURCE_RECOVERED", resource: "rag_evidence" });
    }
  }, [apiClient, loadSurfaceResource, state.viewerBundle]);

  const searchAssetLibrary = useCallback(
    async (query: string) => {
      const normalizedQuery = query.trim();
      if (!normalizedQuery) return;
      lastAssetLibraryQueryRef.current = normalizedQuery;
      setAssetLibrarySearchBusy(true);
      setAssetLibrarySearchError(null);
      try {
        await loadSurfaceResource(
          "asset_search",
          () => apiClient.searchAssetLibrary(normalizedQuery),
          setAssetLibrarySearch,
          "assets",
          () => setAssetLibrarySearch(null)
        );
      } catch (error) {
        setAssetLibrarySearchError(userFacingError(error, "assets"));
      } finally {
        setAssetLibrarySearchBusy(false);
      }
    },
    [apiClient, loadSurfaceResource]
  );

  const loadLiveStatus = useCallback(
    async (workflowId: string) => {
      if (isActiveWorkflow(workflowId)) {
        dispatch({ type: "RESOURCE_LOADING", resource: "workflow_status" });
      }
      let status: WorkflowStatus;
      try {
        status = await apiClient.workflowStatus(workflowId);
      } catch (error) {
        if (isActiveWorkflow(workflowId)) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "workflow_status",
            message: userFacingError(error, "resource")
          });
        }
        throw error;
      }
      if (isActiveWorkflow(workflowId)) {
        dispatch({ type: "STATUS_LOADED", status });
        dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
      }
      try {
        if (isActiveWorkflow(workflowId)) {
          dispatch({ type: "RESOURCE_LOADING", resource: "current_operation" });
        }
        const operation = await apiClient.currentOperation(workflowId);
        if (isActiveWorkflow(workflowId)) {
          dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation });
          dispatch({ type: "RESOURCE_RECOVERED", resource: "current_operation" });
        }
      } catch (error) {
        if (isActiveWorkflow(workflowId)) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "current_operation",
            message: userFacingError(error, "resource")
          });
        }
      }
      return status;
    },
    [apiClient, isActiveWorkflow]
  );

  const loadTerminalBundle = useCallback(
    async (workflowId: string) => {
      if (!isActiveWorkflow(workflowId)) return;
      terminalBundleAbortRef.current?.abort();
      const controller = new AbortController();
      terminalBundleAbortRef.current = controller;
      const requestId = terminalBundleRequestRef.current + 1;
      terminalBundleRequestRef.current = requestId;
      const requestIsCurrent = () =>
        !controller.signal.aborted &&
        isActiveWorkflow(workflowId) &&
        terminalBundleRequestRef.current === requestId;
      dispatch({ type: "RESOURCE_LOADING", resource: "terminal_bundle", workflowId });
      dispatch({ type: "RESOURCE_LOADING", resource: "workflow_status", workflowId });
      let status: WorkflowStatus;
      try {
        status = await apiClient.workflowStatus(workflowId, { signal: controller.signal });
      } catch (error) {
        if (isAbortError(error)) return;
        if (requestIsCurrent()) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "workflow_status",
            message: userFacingError(error, "resource"),
            workflowId
          });
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "terminal_bundle",
            message: userFacingError(error, "resource"),
            workflowId
          });
        }
        throw error;
      }
      if (!requestIsCurrent() || status.workflow_id !== workflowId) return;
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status", workflowId });

      for (const resource of [
        "current_operation",
        "viewer_bundle",
        "timeline",
        "user_issues",
        "versions",
        "studio_summary"
      ]) {
        dispatch({ type: "RESOURCE_LOADING", resource, workflowId });
      }
      const [
        operationResult,
        bundleResult,
        timelineResult,
        issuesResult,
        versionsResult,
        summaryResult
      ] = await Promise.allSettled([
          apiClient.currentOperation(workflowId, { signal: controller.signal }),
          apiClient.viewerBundle(workflowId, { signal: controller.signal }),
          apiClient.timelineSummary(workflowId, { signal: controller.signal }),
          apiClient.userIssues(workflowId, { signal: controller.signal }),
          apiClient.versions(workflowId, { signal: controller.signal }),
          apiClient.studioSummary({ signal: controller.signal })
        ]);

      if (!requestIsCurrent()) return;

      applyResourceResult(
        operationResult,
        "current_operation",
        (operation) => dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation }),
        dispatch
      );
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
        (nextVersions) => {
          if (requestIsCurrent()) setVersions(nextVersions);
        },
        dispatch
      );
      applyResourceResult(
        summaryResult,
        "studio_summary",
        (summary) => dispatch({ type: "BOOTSTRAP_LOADED", summary }),
        dispatch
      );
      dispatch({ type: "RESOURCE_RECOVERED", resource: "terminal_bundle", workflowId });
      if (terminalBundleAbortRef.current === controller) {
        terminalBundleAbortRef.current = null;
      }
    },
    [apiClient, isActiveWorkflow]
  );

  const reloadViewerBundle = useCallback(async () => {
    if (!state.workflowId) {
      return;
    }
    await loadSurfaceResource(
      "viewer_bundle",
      () => apiClient.viewerBundle(state.workflowId!),
      (viewerBundle) => dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle })
    );
  }, [apiClient, loadSurfaceResource, state.workflowId]);

  const startEventStream = useCallback(
    (workflowId: string, afterEventId?: string | null) => {
      streamRef.current?.close();
      streamRef.current = openWorkflowEventStream(
        apiClient.streamUrl(workflowId, afterEventId),
        {
          onEvent: (event) => {
            if (!isActiveWorkflow(workflowId)) return;
            rememberEventSequence(event.sequence);
            dispatch({ type: "EVENT_RECEIVED", event });
          },
          onTerminal: (event) => {
            if (!isActiveWorkflow(workflowId)) return;
            void loadTerminalBundle(event.workflow_id).catch((error) => {
              dispatch({
                type: "RESOURCE_FAILED",
                resource: "terminal_bundle",
                message: userFacingError(error, "resource")
              });
            });
          },
          onError: (reason) => {
            if (isActiveWorkflow(workflowId)) dispatch({ type: "SSE_FAILED", reason });
          },
          onRecovered: () => {
            if (isActiveWorkflow(workflowId)) dispatch({ type: "SSE_RECOVERED" });
          }
        }
      );
    },
    [apiClient, isActiveWorkflow, loadTerminalBundle, rememberEventSequence]
  );

  const loadPollingSnapshot = useCallback(
    async (workflowId: string) => {
      if (!isActiveWorkflow(workflowId)) return;
      let status: WorkflowStatus;
      try {
        status = await apiClient.workflowStatus(workflowId);
        if (!isActiveWorkflow(workflowId) || status.workflow_id !== workflowId) return;
        dispatch({ type: "STATUS_LOADED", status });
        dispatch({ type: "RESOURCE_RECOVERED", resource: "workflow_status" });
      } catch (error) {
        if (isActiveWorkflow(workflowId)) {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "workflow_status",
            message: userFacingError(error, "resource")
          });
        }
        return;
      }

      const [operationResult, eventsResult, timelineResult] = await Promise.allSettled([
        apiClient.currentOperation(workflowId),
        apiClient.workflowEvents(workflowId, eventSequenceCursorRef.current),
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
        receiveWorkflowEvents,
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
    [apiClient, isActiveWorkflow, loadTerminalBundle, receiveWorkflowEvents]
  );

  const restoreLatestDesign = useCallback(async () => {
    if (restoredWorkflowRef.current || state.workflowId || state.phase !== "idle") {
      return;
    }
    await loadSurfaceResource(
      "design_list",
      () => apiClient.listDesigns(),
      (designs) => {
        const latest = selectWorkflowToRestore(designs);
        if (!latest) {
          return;
        }
        restoredWorkflowRef.current = true;
        eventSequenceCursorRef.current = null;
        activateWorkflow(latest.workflow_id);
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
                message: userFacingError(error, "resource")
              });
            });
        } else {
          void loadTerminalBundle(latest.workflow_id).catch((error) => {
            dispatch({
              type: "RESOURCE_FAILED",
              resource: "terminal_bundle",
              message: userFacingError(error, "resource")
              });
          });
        }
      },
      "bootstrap"
    );
  }, [
    apiClient,
    loadLiveStatus,
    activateWorkflow,
    loadSurfaceResource,
    loadTerminalBundle,
    state.phase,
    state.workflowId
  ]);

  useEffect(() => {
    void restoreLatestDesign().catch(() => undefined);
  }, [restoreLatestDesign]);

  const loadDocumentPackReview = useCallback(
    async (packId: string) => {
      return loadSurfaceResource(
        "document_review",
        () => apiClient.documentPackReview(packId),
        (review) => {
          setDocumentPackReview(review);
          if (review.summary) {
            setDocumentPackSummary(review.summary);
          }
          const storage = documentPackBrowserStorage();
          if (storage) writeDocumentPackSession(storage, review.summary?.pack_id ?? packId);
        },
        "documents"
      );
    },
    [apiClient, loadSurfaceResource]
  );

  useEffect(() => {
    const storage = documentPackBrowserStorage();
    const packId = storage ? readDocumentPackSession(storage) : null;
    if (!packId) return;
    let cancelled = false;
    setDocumentPackBusy(true);
    void loadDocumentPackReview(packId)
      .then((review) => {
        if (!cancelled) {
          setDocumentPackMessage(
            documentPackReviewIsComplete(review)
              ? review.summary?.can_generate_design
                ? "Revue documentaire restaurée; le pack est prêt à générer."
                : "Revue documentaire restaurée; des points restent à confirmer."
              : "Revue documentaire partiellement restaurée. Les sections indisponibles restent signalées et peuvent être rechargées."
          );
        }
      })
      .catch((error) => {
        const missingPack = shouldForgetDocumentPackSession(error);
        if (missingPack && storage) clearDocumentPackSession(storage);
        if (!cancelled) {
          setDocumentPackReview(null);
          setDocumentPackMessage(
            missingPack
              ? "La revue documentaire précédente n’est plus disponible. Importez de nouveau les pièces."
              : "La revue documentaire n’a pas pu être resynchronisée. Le pack est conservé; utilisez Réessayer pour reprendre la synchronisation."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDocumentPackBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadDocumentPackReview]);

  const retryDocumentPackReview = useCallback(async () => {
    const storage = documentPackBrowserStorage();
    const packId =
      documentPackSummary?.pack_id ??
      documentPackReview?.packId ??
      (storage ? readDocumentPackSession(storage) : null);
    if (!packId) {
      return;
    }
    setDocumentPackBusy(true);
    setDocumentPackMessage(null);
    try {
      const review = await loadDocumentPackReview(packId);
      setDocumentPackMessage(
        documentPackReviewIsComplete(review)
          ? "Revue documentaire resynchronisée."
          : "Certaines sections restent indisponibles; les données chargées sont conservées sans inventer le reste."
      );
    } catch (error) {
      setDocumentPackMessage(userFacingError(error, "documents"));
    } finally {
      setDocumentPackBusy(false);
    }
  }, [documentPackReview?.packId, documentPackSummary?.pack_id, loadDocumentPackReview]);

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
      setAnalysisError(userFacingError(error, "analysis"));
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
    if (requirementsAnalysis.requirements.requires_confirmation) {
      setAnalysisError(
        "La demande contient des valeurs contradictoires. Corrigez les champs signalés puis relancez l’analyse."
      );
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
        options: {
          detail_level: ActivePromptDetail,
          use_llm: null,
          multimodal_consent: multimodalConsentAvailable ? multimodalConsent : "disabled"
        }
      });
      setSubmittedRequirementsHash(requirementsAnalysis.requirements_hash);
      setVersions([]);
      eventSequenceCursorRef.current = null;
      activateWorkflow(created.workflow_id);
      dispatch({ type: "DESIGN_CREATED", workflowId: created.workflow_id });
      const status = await loadLiveStatus(created.workflow_id);
      if (isTerminalStatus(status.status)) {
        await loadTerminalBundle(created.workflow_id);
      }
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: userFacingError(error, "generation") });
    } finally {
      submissionInFlightRef.current = false;
    }
  }, [
    analyzedPrompt,
    activateWorkflow,
    apiClient,
    loadLiveStatus,
    loadTerminalBundle,
    multimodalConsent,
    multimodalConsentAvailable,
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
    async (files: File[]) => {
      const sizeError = documentPackFilesSizeError(files, documentCapabilities);
      if (sizeError) {
        setDocumentPackMessage(sizeError);
        return false;
      }
      setDocumentPackBusy(true);
      setDocumentPackMessage(null);
      setDocumentPackReview(null);
      try {
        const summary = await apiClient.createDocumentPack(files);
        setDocumentPackSummary(summary);
        const review = await loadDocumentPackReview(summary.pack_id);
        setDocumentPackMessage(
          documentPackReviewIsComplete(review)
            ? review.summary?.can_generate_design
              ? "Pack analysé: génération possible."
              : "Pack analysé: corrigez les champs bloquants avant génération."
            : "Pack créé, mais sa revue est partielle. Rechargez les sections indisponibles avant de générer."
        );
        return true;
      } catch (error) {
        setDocumentPackMessage(userFacingError(error, "documents"));
        return false;
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
          documentPackReviewIsComplete(review)
            ? review.summary?.can_generate_design
              ? "Correction enregistrée. Le pack est prêt à générer."
              : "Correction enregistrée. D’autres points restent à vérifier."
            : "Correction enregistrée, mais la revue n’est que partiellement resynchronisée."
        );
      } catch (error) {
        setDocumentPackMessage(
          isSafeCorrectionError(error)
            ? error.message
            : userFacingError(error, "documents")
        );
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
      const generated = await apiClient.generateDesignFromDocumentPack(
        documentPackSummary.pack_id,
        multimodalConsentAvailable ? multimodalConsent : "disabled"
      );
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
      eventSequenceCursorRef.current = null;
      activateWorkflow(generated.workflow_id);
      dispatch({ type: "DESIGN_CREATED", workflowId: generated.workflow_id });
      const status = await loadLiveStatus(generated.workflow_id);
      if (isTerminalStatus(status.status)) {
        await loadTerminalBundle(generated.workflow_id);
      }
    } catch (error) {
      const message = userFacingError(error, "documents");
      dispatch({ type: "REQUEST_FAILED", message });
      setDocumentPackMessage(message);
    } finally {
      setDocumentPackBusy(false);
    }
  }, [
    apiClient,
    activateWorkflow,
    documentPackSummary,
    loadLiveStatus,
    loadTerminalBundle,
    multimodalConsent,
    multimodalConsentAvailable
  ]);

  const submitRevision = useCallback(async () => {
    if (
      !state.workflowId ||
      !revisionPrompt.trim() ||
      revisionBusy ||
      revisionInFlightRef.current
    ) {
      return;
    }
    revisionInFlightRef.current = true;
    const workflowId = state.workflowId;
    const submittedRevisionPrompt = revisionPrompt.trim();
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
        streamNotice =
          "Le suivi temps réel n’a pas pu reprendre; la synchronisation de secours reste active.";
        setRevisionMessage(streamNotice);
      }
      dispatch({ type: "REVISION_STARTED", runtimeMode });
      const result = await apiClient.editDesign(workflowId, {
        edit_prompt: submittedRevisionPrompt
      });
      const outcome = revisionOutcomeMessage(result, submittedRevisionPrompt);
      setRevisionMessage([outcome, streamNotice].filter(Boolean).join(" · "));
      if (result.status !== "applied") {
        dispatch({ type: "REVISION_FINISHED" });
        await loadTerminalBundle(workflowId);
        return;
      }
      setRevisionPrompt("");
      setRequirementsAnalysis(null);
      setAnalyzedPrompt(null);
      setSubmittedRequirementsHash(null);
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
  }, [
    apiClient,
    loadTerminalBundle,
    rememberEventSequence,
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
          rememberEventSequence(latestEventSequence(eventHistory));
          const cursor = latestEventCursor(eventHistory);
          streamCursorRef.current = cursor;
          runtimeMode = cursor ? "sse" : "polling";
        } catch (error) {
          setVersionMessage(
            "Le suivi direct n’est pas disponible; la restauration reste synchronisée."
          );
        }
        dispatch({
          type: "REVISION_STARTED",
          runtimeMode
        });
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
    },
    [
      apiClient,
      loadTerminalBundle,
      rememberEventSequence,
      rollbackBusyVersionId,
      state.workflowId
    ]
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
      void loadPollingSnapshot(state.workflowId!)
        .catch((error) => {
          dispatch({
            type: "RESOURCE_FAILED",
            resource: "terminal_bundle",
            message: userFacingError(error, "resource")
          });
        })
        .finally(() => {
          inFlight = false;
        });
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => window.clearInterval(timer);
  }, [loadPollingSnapshot, state.phase, state.runtimeMode, state.workflowId]);

  const retryWorkflowSynchronization = useCallback(async () => {
    if (!state.workflowId) {
      await restoreLatestDesign();
      return;
    }
    const status = await loadLiveStatus(state.workflowId);
    if (isTerminalStatus(status.status)) {
      await loadTerminalBundle(state.workflowId);
    }
  }, [loadLiveStatus, loadTerminalBundle, restoreLatestDesign, state.workflowId]);
  const retryBootstrap = useCallback(async () => {
    await Promise.allSettled([
      loadHealth(),
      loadStudioSummary(),
      retryWorkflowSynchronization()
    ]);
  }, [loadHealth, loadStudioSummary, retryWorkflowSynchronization]);
  const retryViewerSurface = useCallback(async () => {
    if (state.workflowId) {
      await reloadViewerBundle();
      return;
    }
    await retryWorkflowSynchronization();
  }, [reloadViewerBundle, retryWorkflowSynchronization, state.workflowId]);
  const retryAssetSurfaces = useCallback(async () => {
    await Promise.allSettled([loadAssetInventory(), loadAssetLibrarySummary()]);
  }, [loadAssetInventory, loadAssetLibrarySummary]);
  const retryAdaptationSurfaces = useCallback(async () => {
    const requests: Promise<unknown>[] = [loadAdaptationCatalog()];
    if (state.workflowId) {
      requests.push(
        loadSurfaceResource(
          "adaptation_scene",
          () => apiClient.designAdaptationCapabilities(state.workflowId!),
          setAdaptationCapabilities,
          "resource",
          () => setAdaptationCapabilities(null)
        )
      );
    }
    await Promise.allSettled(requests);
  }, [apiClient, loadAdaptationCatalog, loadSurfaceResource, state.workflowId]);
  const retryAssetSearch = useCallback(async () => {
    if (lastAssetLibraryQueryRef.current) {
      await searchAssetLibrary(lastAssetLibraryQueryRef.current);
    }
  }, [searchAssetLibrary]);
  const retryQaEvidence = useCallback(async () => {
    const url = state.viewerBundle?.qa_report_url;
    if (!url) return;
    await loadSurfaceResource(
      "qa_evidence",
      () => apiClient.artifactJson(url),
      setQaEvidence,
      "resource",
      () => setQaEvidence(null)
    );
  }, [apiClient, loadSurfaceResource, state.viewerBundle?.qa_report_url]);
  const retryLlmProvenance = useCallback(async () => {
    const inline = state.viewerBundle?.llm_decision_provenance;
    if (inline) {
      setLlmProvenance(inline);
      dispatch({ type: "RESOURCE_RECOVERED", resource: "llm_provenance" });
      return;
    }
    const url = state.viewerBundle?.llm_decision_provenance_url;
    if (!url) return;
    await loadSurfaceResource(
      "llm_provenance",
      () => apiClient.llmDecisionProvenance(url),
      setLlmProvenance,
      "resource",
      () => setLlmProvenance(null)
    );
  }, [apiClient, loadSurfaceResource, state.viewerBundle]);
  const retryRagEvidence = useCallback(async () => {
    const url = state.viewerBundle?.rag_evidence_url;
    if (!url) return;
    await loadSurfaceResource(
      "rag_evidence",
      () => apiClient.artifactJson(url),
      setRagEvidence,
      "resource",
      () => setRagEvidence(null)
    );
  }, [apiClient, loadSurfaceResource, state.viewerBundle?.rag_evidence_url]);
  const retryCognitiveEvidence = useCallback(async () => {
    const bundle = state.viewerBundle;
    if (!bundle) return;
    const requests: Promise<unknown>[] = [];
    if (bundle.assembly_plan_url) {
      requests.push(
        loadSurfaceResource(
          "assembly_plan",
          () => apiClient.assemblyPlan(bundle.assembly_plan_url),
          setAssemblyPlan,
          "resource",
          () => setAssemblyPlan(null)
        )
      );
    }
    if (bundle.component_proofs_url) {
      requests.push(
        loadSurfaceResource(
          "component_proofs",
          () => apiClient.componentProofs(bundle.component_proofs_url),
          setComponentProofs,
          "resource",
          () => setComponentProofs(null)
        )
      );
    }
    if (bundle.requirements_spec_url) {
      requests.push(
        loadSurfaceResource(
          "requirements_context",
          () => apiClient.requirementsSpec(bundle.requirements_spec_url),
          setActiveRequirements,
          "resource",
          () => setActiveRequirements(null)
        )
      );
    }
    await Promise.allSettled(requests);
  }, [apiClient, loadSurfaceResource, state.viewerBundle]);

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
    state.viewerBundle.available_actions.includes("rollback_version") &&
    actionIsSupported("rollback_version", state.viewerBundle.unsupported_actions) &&
    !revisionBusy &&
    rollbackBusyVersionId === null &&
    (state.phase === "completed" || state.phase === "degraded");
  const operationNotice = Array.from(
    new Set([
      state.transportError,
      state.resourceErrors.workflow_status,
      state.resourceErrors.current_operation,
      state.resourceErrors.terminal_bundle,
      state.resourceErrors.timeline,
      state.resourceErrors.events
    ].filter((value): value is string => Boolean(value)))
  ).join(" · ");
  const workflowActive =
    state.phase === "submitting" ||
    state.phase === "streaming" ||
    state.phase === "running";
  const bootstrapError = state.viewerBundle
    ? null
    : Array.from(
        new Set([
          state.resourceErrors.studio_summary,
          !state.workflowId ? state.resourceErrors.design_list : null,
          state.resourceErrors.workflow_status,
          state.resourceErrors.terminal_bundle
        ].filter((message): message is string => Boolean(message)))
      ).join(" · ") || null;
  const bootstrapLoading = ["studio_summary", "design_list", "workflow_status", "terminal_bundle"].some(
    (resource) => state.resourceLoads[resource]?.status === "loading"
  );
  const viewerSurfaceError =
    state.resourceErrors.viewer_bundle ??
    (!state.workflowId ? state.resourceErrors.design_list : null) ??
    null;
  const viewerSurfaceLoading =
    state.resourceLoads.viewer_bundle?.status === "loading" ||
    (!state.workflowId && state.resourceLoads.design_list?.status === "loading");
  const displayedViewerBundle = selectViewerBundleForDisplay(
    state.phase,
    state.viewerBundle,
    lastCertifiedBundle
  );

  useEffect(() => {
    const bundle = state.viewerBundle;
    if (
      bundle?.status === "completed" &&
      bundle.generation_mode === "real_blender" &&
      bundle.mesh_qa_passed === true &&
      bundle.completion_certificate_status === "issued"
    ) {
      setLastCertifiedBundle(bundle);
    }
  }, [state.viewerBundle]);

  return (
    <div className="studio-root">
      <BackendStatusBar
        bundle={state.viewerBundle}
        health={health}
        healthError={state.resourceErrors.health ?? null}
        healthLoading={state.resourceLoads.health?.status === "loading"}
        issues={state.userIssues}
        onRetryHealth={() => void loadHealth().catch(() => undefined)}
        phase={state.phase}
      />
      <main className="studio-layout">
        <aside className="left-rail">
          <ChatCommandPanel
            activeRequirements={activeRequirements}
            analysis={analysisIsCurrent ? requirementsAnalysis : null}
            analysisBusy={analysisBusy}
            analysisError={analysisError}
            analysisSubmitted={analysisWasSubmitted}
            bootstrapError={bootstrapError}
            bootstrapLoading={bootstrapLoading}
            canEdit={canEditCurrentDesign}
            correctionBusy={documentCorrectionBusy}
            documentCapabilities={documentCapabilities}
            documentCapabilitiesError={state.resourceErrors.document_capabilities ?? null}
            documentCapabilitiesLoading={state.resourceLoads.document_capabilities?.status === "loading"}
            documentPackBusy={documentPackBusy}
            documentPackMessage={documentPackMessage}
            documentPackReview={documentPackReview}
            documentPackReviewError={state.resourceErrors.document_review ?? null}
            documentPackReviewLoading={state.resourceLoads.document_review?.status === "loading"}
            documentPackSummary={documentPackSummary}
            editMessage={revisionMessage}
            error={state.error}
            failureIssue={
              state.userIssues?.human_readable_issues.find((issue) => issue.severity === "error") ??
              state.userIssues?.human_readable_issues[0] ??
              null
            }
            onAnalyze={analyzePrompt}
            onConfirm={submitPrompt}
            onDocumentPackCorrection={applyDocumentPackCorrection}
            onDocumentPackGenerate={generateFromDocumentPack}
            onDocumentPackReviewRetry={retryDocumentPackReview}
            onDocumentPackUpload={uploadDocumentPack}
            onDocumentCapabilitiesRetry={() => void loadDocumentCapabilities().catch(() => undefined)}
            multimodalConsent={multimodalConsent}
            multimodalIntelligence={multimodalIntelligence}
            onMultimodalConsentChange={setMultimodalConsent}
            onPromptChange={changePrompt}
            onRevisionPromptChange={setRevisionPrompt}
            onRevisionSubmit={submitRevision}
            onRetryBootstrap={() => void retryBootstrap()}
            phase={state.phase}
            prompt={state.prompt}
            submissionPending={state.pendingSubmission}
            revisionBusy={revisionBusy}
            revisionPrompt={revisionPrompt}
            versions={versions}
          />
          {workflowActive && operationNotice ? (
            <CurrentOperationStrip
              notice={operationNotice}
              operation={state.currentOperation}
              phase={state.phase}
              runtimeMode={state.runtimeMode}
            />
          ) : null}
        </aside>
        <section className="workbench" aria-label="Studio 3D">
          <Suspense fallback={<ViewerLoadingFallback />}>
            <TelecomGlbViewer
              bundle={displayedViewerBundle}
              loadError={viewerSurfaceError}
              loading={viewerSurfaceLoading}
              onReloadBundle={() => void retryViewerSurface().catch(() => undefined)}
              selectedSemanticRoot={selectedSemanticRoot}
              toAbsoluteUrl={toArtifactUrl}
            />
          </Suspense>
          {state.phase === "failed" && lastCertifiedBundle ? (
            <div className="retained-design-notice" role="status">
              <CheckCircle2 size={16} aria-hidden="true" />
              <div>
                <strong>Dernier résultat vérifié conservé</strong>
                <span>La nouvelle demande a échoué; elle n’a pas remplacé ce modèle validé.</span>
              </div>
            </div>
          ) : null}
          <LiveGenerationOverlay
            events={state.events}
            operation={state.currentOperation}
            phase={state.phase}
            runtimeMode={state.runtimeMode}
            timeline={state.timeline}
            intent={
              rollbackBusyVersionId
                ? "rollback"
                : revisionBusy
                  ? "revision"
                  : "generation"
            }
          />
          <InspectorDock
            adaptationCapabilities={adaptationCapabilities}
            adaptationCapabilitiesError={state.resourceErrors.adaptation_scene ?? null}
            adaptationLoading={
              state.resourceLoads.adaptation_scene?.status === "loading" ||
              state.resourceLoads.adaptation_catalog?.status === "loading"
            }
            adaptationCatalog={adaptationCatalog}
            adaptationCatalogError={state.resourceErrors.adaptation_catalog ?? null}
            assetInventory={assetInventory}
            assetInventoryError={state.resourceErrors.asset_inventory ?? null}
            assetLibraryLoading={
              state.resourceLoads.asset_inventory?.status === "loading" ||
              state.resourceLoads.asset_library?.status === "loading"
            }
            assetLibrarySearch={assetLibrarySearch}
            assetLibrarySearchBusy={assetLibrarySearchBusy}
            assetLibrarySearchError={assetLibrarySearchError}
            assetLibrarySummary={assetLibrarySummary}
            assetLibrarySummaryError={state.resourceErrors.asset_library ?? null}
            bundle={state.viewerBundle}
            assemblyPlan={assemblyPlan}
            canRollback={canRollbackVersions}
            events={state.events}
            componentProofs={componentProofs}
            cognitiveEvidenceError={[
              state.resourceErrors.assembly_plan,
              state.resourceErrors.component_proofs,
              state.resourceErrors.requirements_context
            ].filter(Boolean).join(" ") || null}
            cognitiveEvidenceLoading={
              state.resourceLoads.assembly_plan?.status === "loading" ||
              state.resourceLoads.component_proofs?.status === "loading" ||
              state.resourceLoads.requirements_context?.status === "loading"
            }
            documentCapabilities={documentCapabilities}
            issues={state.userIssues}
            ragEvidence={ragEvidence}
            ragEvidenceError={state.resourceErrors.rag_evidence ?? null}
            ragEvidenceLoading={state.resourceLoads.rag_evidence?.status === "loading"}
            qaEvidence={qaEvidence}
            qaEvidenceError={state.resourceErrors.qa_evidence ?? null}
            qaEvidenceLoading={state.resourceLoads.qa_evidence?.status === "loading"}
            llmProvenance={llmProvenance}
            llmProvenanceError={state.resourceErrors.llm_provenance ?? null}
            llmProvenanceLoading={state.resourceLoads.llm_provenance?.status === "loading"}
            viewerBundleError={state.resourceErrors.viewer_bundle ?? null}
            viewerBundleLoading={state.resourceLoads.viewer_bundle?.status === "loading"}
            summary={state.summary}
            timeline={state.timeline}
            toAbsoluteUrl={toArtifactUrl}
            onRollbackVersion={rollbackVersion}
            onSelectSceneComponent={setSelectedSemanticRoot}
            onRetryAdaptation={() => void retryAdaptationSurfaces()}
            onRetryAssets={() => void retryAssetSurfaces()}
            onRetryAssetSearch={() => void retryAssetSearch()}
            onRetryLlmProvenance={() => void retryLlmProvenance().catch(() => undefined)}
            onRetryQaEvidence={() => void retryQaEvidence().catch(() => undefined)}
            onRetryRagEvidence={() => void retryRagEvidence().catch(() => undefined)}
            onRetryCognitiveEvidence={() => void retryCognitiveEvidence()}
            onRetryViewerBundle={() => void reloadViewerBundle().catch(() => undefined)}
            onSearchAssetLibrary={searchAssetLibrary}
            rollbackBusyVersionId={rollbackBusyVersionId}
            selectedSemanticRoot={selectedSemanticRoot}
            versionMessage={versionMessage}
            versions={versions}
          />
        </section>
      </main>
    </div>
  );
}

export function selectViewerBundleForDisplay(
  phase: WorkflowPhase,
  current: ViewerBundle | null,
  lastCertified: ViewerBundle | null
): ViewerBundle | null {
  const preserveCertified =
    lastCertified &&
    (phase === "submitting" || phase === "streaming" || phase === "running" || phase === "failed") &&
    (!current || current.status === "failed");
  return preserveCertified ? lastCertified : current;
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

export async function reconcileAfterAmbiguousMutation(
  reloadVerifiedState: () => Promise<void>
): Promise<boolean> {
  try {
    await reloadVerifiedState();
    return true;
  } catch {
    return false;
  }
}

type UserActionContext =
  | "analysis"
  | "assets"
  | "bootstrap"
  | "connection"
  | "documents"
  | "edit"
  | "generation"
  | "resource"
  | "rollback";

export function userFacingError(error: unknown, context: UserActionContext): string {
  const action = {
    analysis: "L’analyse de la demande",
    assets: "La recherche de composants",
    bootstrap: "La synchronisation initiale du studio",
    connection: "La connexion au studio",
    documents: "L’analyse documentaire",
    edit: "La modification du design",
    generation: "La génération du design",
    resource: "Une information secondaire",
    rollback: "La restauration de version"
  }[context];
  if (error instanceof ApiClientError) {
    if (error.status === 0) return `${action} ne peut pas joindre le studio local.`;
    if (error.status === 404) return `${action} n’est plus disponible pour cet élément.`;
    if (error.status === 409) return `${action} doit être resynchronisée avant de continuer.`;
    if (error.status === 422) return `${action} nécessite des informations à corriger.`;
    if (error.status === 429) return "Le studio termine déjà une opération. Réessayez ensuite.";
    if (error.status === 507) {
      return "L’espace disque local est insuffisant. Libérez de la place avant de réessayer.";
    }
    if (error.status >= 500) return `${action} a rencontré un problème interne. Réessayez.`;
  }
  return `${action} n’a pas abouti. Réessayez ou rechargez l’état vérifié.`;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function isSafeCorrectionError(error: unknown): error is Error {
  return (
    error instanceof Error &&
    (error.message.startsWith("La valeur de correction") ||
      error.message.startsWith("Type de correction"))
  );
}

function documentPackBrowserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function selectWorkflowToRestore(designs: WorkflowStatus[]): WorkflowStatus | null {
  for (const statuses of [
    new Set(["pending", "running"]),
    new Set(["completed"]),
    new Set(["failed", "legacy_unverified", "integrity_failed"])
  ]) {
    const candidates = designs.filter(
      (design) =>
        statuses.has(design.status) &&
        (design.status !== "completed" ||
          design.completion_certificate_status === "issued")
    );
    if (candidates.length) {
      return [...candidates].sort(
        (left, right) => timestamp(right.created_at) - timestamp(left.created_at)
      )[0] ?? null;
    }
  }
  return null;
}

export function shouldForgetDocumentPackSession(error: unknown): boolean {
  return error instanceof ApiClientError && error.status === 404;
}

export function documentPackReviewIsComplete(review: DocumentPackReview): boolean {
  return (
    review.summary !== null &&
    review.conflicts !== null &&
    review.missingFields !== null &&
    review.qa !== null &&
    review.documents !== null &&
    review.extractions !== null &&
    review.provenance !== null &&
    review.processing !== null &&
    review.consolidatedSpec !== null &&
    Object.keys(review.sectionErrors ?? {}).length === 0
  );
}

export function latestEventCursor(
  events: Array<Pick<WorkflowEvent, "event_id">>
): string | null {
  return events.at(-1)?.event_id ?? null;
}

export function latestEventSequence(
  events: Array<Pick<WorkflowEvent, "sequence">>
): number | null {
  let latest: number | null = null;
  for (const event of events) {
    if (event.sequence != null) {
      latest = Math.max(latest ?? 0, event.sequence);
    }
  }
  return latest;
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

export function documentPackFilesSizeError(
  files: Array<Pick<File, "name" | "size">>,
  capabilities: DocumentPackCapabilities | null
): string | null {
  if (!files.length) {
    return "Ajoutez au moins une pièce technique.";
  }
  if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
    return documentPackSizeError(files[0], capabilities);
  }
  const maxCount = capabilities?.limits?.max_member_count;
  if (maxCount && files.length > maxCount) {
    return `Le cahier de charge dépasse la limite de ${maxCount} fichiers.`;
  }
  const maxMemberSizeMb = capabilities?.limits?.max_member_size_mb;
  const oversized = maxMemberSizeMb
    ? files.find((file) => file.size > maxMemberSizeMb * 1024 * 1024)
    : null;
  if (oversized) {
    return `${oversized.name} dépasse la limite de ${maxMemberSizeMb} Mo par fichier.`;
  }
  const maxTotalSizeMb = capabilities?.limits?.max_uncompressed_size_mb;
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (maxTotalSizeMb && total > maxTotalSizeMb * 1024 * 1024) {
    return `Les pièces dépassent la limite totale de ${maxTotalSizeMb} Mo.`;
  }
  return null;
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
  return (
    status === "completed" ||
    status === "failed" ||
    status === "legacy_unverified" ||
    status === "integrity_failed"
  );
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
    message: userFacingError(result.reason, "resource")
  });
}

export function revisionOutcomeMessage(
  result: EditDesignResponse,
  submittedPrompt?: string
): string {
  const patch = result.patch as Record<string, unknown> | null | undefined;
  const unsupported = Array.isArray(patch?.unsupported_requests)
    ? patch.unsupported_requests.filter(
        (item): item is string => typeof item === "string" && Boolean(item.trim())
      ).map(humanUnsupportedEditRequest)
    : [];
  const description = submittedPrompt?.trim()
    || (typeof patch?.edit_description === "string" && patch.edit_description.trim()
      ? patch.edit_description.trim()
      : null);
  if (result.status === "applied") {
    const applied = description
      ? `Modification appliquée : ${description}`
      : "Modification appliquée et revalidée.";
    return unsupported.length
      ? `${applied} Non réalisé : ${unsupported.join(" ")}`
      : applied;
  }
  const errorCodes = (result.errors ?? [])
    .map((error) => String(error.code ?? "").toUpperCase())
    .join(" ");
  if (errorCodes.includes("GEOMETRY_VALIDATION")) {
    return "La nouvelle version a été refusée par le contrôle géométrique. La version vérifiée précédente reste active.";
  }
  if (unsupported.length) {
    return `Modification non appliquée. Capacité indisponible : ${unsupported.join(" ")}`;
  }
  return "Modification non appliquée. La version vérifiée précédente reste active.";
}

function humanUnsupportedEditRequest(message: string): string {
  const normalized = message.toLowerCase();
  if (
    (normalized.includes("door") || normalized.includes("porte")) &&
    (normalized.includes("green space") || normalized.includes("espace vert"))
  ) {
    return "L’ajout d’une porte ou barrière au sol pour délimiter un espace vert n’est pas encore disponible.";
  }
  if (normalized.includes("not supported") || normalized.includes("is not supported")) {
    return "Une partie de la demande n’est pas disponible dans les capacités d’édition actuelles.";
  }
  return message;
}
