import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState
} from "react";
import { api, TelecomStudioApi } from "./api/client";
import { openWorkflowEventStream } from "./api/sse";
import type {
  AssetInventory,
  DocumentPackSummary,
  DocumentPackCapabilities,
  Health,
  PublicVersionInfo,
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
  const [documentPackMessage, setDocumentPackMessage] = useState<string | null>(null);
  const [documentPackBusy, setDocumentPackBusy] = useState(false);
  const [versions, setVersions] = useState<PublicVersionInfo[]>([]);
  const [ragEvidence, setRagEvidence] = useState<unknown | null>(null);
  const [revisionPrompt, setRevisionPrompt] = useState("");
  const [revisionMessage, setRevisionMessage] = useState<string | null>(null);
  const apiClient = useMemo(() => api, []);
  const streamRef = useRef<{ close: () => void } | null>(null);
  const restoredWorkflowRef = useRef(false);
  const toArtifactUrl = useCallback(
    (url: string | null | undefined) => apiClient.artifactUrl(url),
    [apiClient]
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiClient.health(),
      apiClient.studioSummary(),
      apiClient.assetInventory(),
      apiClient.documentPackCapabilities()
    ])
      .then(([nextHealth, summary, nextInventory, caps]) => {
        if (cancelled) {
          return;
        }
        setHealth(nextHealth);
        setInventory(nextInventory);
        setDocumentCapabilities(caps);
        dispatch({ type: "BOOTSTRAP_LOADED", summary });
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiClient]);

  const loadLiveStatus = useCallback(
    async (workflowId: string) => {
      const [status, operation] = await Promise.all([
        apiClient.workflowStatus(workflowId),
        apiClient.currentOperation(workflowId)
      ]);
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation });
      return status;
    },
    [apiClient]
  );

  const loadTerminalBundle = useCallback(
    async (workflowId: string) => {
      const [status, operation, bundle, timeline, issues, nextVersions] = await Promise.all([
        apiClient.workflowStatus(workflowId),
        apiClient.currentOperation(workflowId),
        apiClient.viewerBundle(workflowId),
        apiClient.timelineSummary(workflowId),
        apiClient.userIssues(workflowId),
        apiClient.versions(workflowId)
      ]);
      dispatch({ type: "STATUS_LOADED", status });
      dispatch({ type: "CURRENT_OPERATION_LOADED", currentOperation: operation });
      dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle: bundle });
      dispatch({ type: "TIMELINE_LOADED", timeline });
      dispatch({ type: "USER_ISSUES_LOADED", userIssues: issues });
      setVersions(nextVersions);
      setRagEvidence(await apiClient.artifactJson(bundle.rag_evidence_url));
    },
    [apiClient]
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
        const latest = latestTerminalDesign(designs);
        if (!latest) {
          return;
        }
        restoredWorkflowRef.current = true;
        dispatch({ type: "WORKFLOW_RESTORED", workflowId: latest.workflow_id });
        dispatch({ type: "STATUS_LOADED", status: latest });
        void loadTerminalBundle(latest.workflow_id).catch((error) => {
          dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
        });
      })
      .catch(() => {
        // Resume is best-effort; bootstrap health/errors are handled separately.
      });
    return () => {
      cancelled = true;
    };
  }, [apiClient, loadTerminalBundle, state.phase, state.workflowId]);

  const submitPrompt = useCallback(async () => {
    if (!state.prompt.trim()) {
      return;
    }
    streamRef.current?.close();
    setVersions([]);
    setRagEvidence(null);
    setRevisionMessage(null);
    dispatch({ type: "SUBMIT_STARTED" });
    try {
      const created = await apiClient.createDesign({
        requirements_text: state.prompt,
        options: { detail_level: ActivePromptDetail, use_llm: null }
      });
      dispatch({ type: "DESIGN_CREATED", workflowId: created.workflow_id });
      await loadLiveStatus(created.workflow_id);
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
    }
  }, [apiClient, loadLiveStatus, state.prompt]);

  const changePrompt = useCallback((prompt: string) => {
    streamRef.current?.close();
    setVersions([]);
    setRagEvidence(null);
    setRevisionMessage(null);
    dispatch({ type: "PROMPT_CHANGED", prompt });
  }, []);

  const uploadDocumentPack = useCallback(
    async (file: File) => {
      setDocumentPackBusy(true);
      setDocumentPackMessage(null);
      try {
        const summary = await apiClient.createDocumentPack(file);
        setDocumentPackSummary(summary);
        setDocumentPackMessage(
          summary.can_generate_design
            ? "Pack analysé: génération possible."
            : "Pack analysé: corrigez les champs bloquants avant génération."
        );
      } catch (error) {
        setDocumentPackMessage(errorMessage(error));
      } finally {
        setDocumentPackBusy(false);
      }
    },
    [apiClient]
  );

  const generateFromDocumentPack = useCallback(async () => {
    if (!documentPackSummary) {
      return;
    }
    streamRef.current?.close();
    setDocumentPackBusy(true);
    setVersions([]);
    setRagEvidence(null);
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
      dispatch({ type: "DESIGN_CREATED", workflowId: generated.workflow_id });
      await loadLiveStatus(generated.workflow_id);
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
      setDocumentPackMessage(errorMessage(error));
    } finally {
      setDocumentPackBusy(false);
    }
  }, [apiClient, documentPackSummary, loadLiveStatus]);

  const submitRevision = useCallback(async () => {
    if (!state.workflowId || !revisionPrompt.trim()) {
      return;
    }
    setRevisionMessage(null);
    dispatch({ type: "REVISION_STARTED" });
    try {
      const result = await apiClient.editDesign(state.workflowId, {
        edit_prompt: revisionPrompt
      });
      setRevisionMessage(result.message ?? `Édition ${result.status}`);
      if (result.status !== "applied") {
        dispatch({
          type: "REQUEST_FAILED",
          message: result.message ?? "La révision a été refusée par le backend."
        });
        return;
      }
      setRevisionPrompt("");
      await loadTerminalBundle(state.workflowId);
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
    }
  }, [apiClient, loadTerminalBundle, revisionPrompt, state.workflowId]);

  useEffect(() => {
    if (!state.workflowId || state.runtimeMode !== "sse") {
      return;
    }
    streamRef.current?.close();
    streamRef.current = openWorkflowEventStream(apiClient.streamUrl(state.workflowId), {
      onEvent: (event) => dispatch({ type: "EVENT_RECEIVED", event }),
      onTerminal: (event) => {
        void loadTerminalBundle(event.workflow_id).catch((error) => {
          dispatch({ type: "REQUEST_FAILED", message: errorMessage(error) });
        });
      },
      onError: (error) => dispatch({ type: "SSE_FAILED", message: error.message })
    });
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
  }, [apiClient, loadTerminalBundle, state.runtimeMode, state.workflowId]);

  useEffect(() => {
    if (!state.workflowId || !needsPolling(state.phase, state.runtimeMode)) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadLiveStatus(state.workflowId!).then((status) => {
        if (status.status === "completed" || status.status === "failed") {
          void loadTerminalBundle(state.workflowId!);
        }
      });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [loadLiveStatus, loadTerminalBundle, state.phase, state.runtimeMode, state.workflowId]);

  const canEditCurrentDesign =
    state.viewerBundle?.status === "completed" &&
    state.viewerBundle.available_actions.includes("edit_design") &&
    actionIsSupported("edit_design", state.viewerBundle.unsupported_actions);

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
            canEdit={canEditCurrentDesign}
            documentCapabilities={documentCapabilities}
            documentPackBusy={documentPackBusy}
            documentPackMessage={documentPackMessage}
            documentPackSummary={documentPackSummary}
            editMessage={revisionMessage}
            error={state.error}
            onDocumentPackGenerate={generateFromDocumentPack}
            onDocumentPackUpload={uploadDocumentPack}
            onPromptChange={changePrompt}
            onRevisionPromptChange={setRevisionPrompt}
            onRevisionSubmit={submitRevision}
            onSubmit={submitPrompt}
            phase={state.phase}
            prompt={state.prompt}
            revisionPrompt={revisionPrompt}
          />
          <CurrentOperationStrip
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
            documentCapabilities={documentCapabilities}
            events={state.events}
            evidence={ragEvidence}
            inventory={inventory}
            issues={state.userIssues}
            summary={state.summary}
            timeline={state.timeline}
            toAbsoluteUrl={toArtifactUrl}
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

function needsPolling(phase: WorkflowPhase, runtimeMode: string): boolean {
  if (runtimeMode === "polling") {
    return phase === "running" || phase === "streaming";
  }
  return phase === "running";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function latestTerminalDesign(designs: WorkflowStatus[]): WorkflowStatus | null {
  const terminal = designs.filter((design) => design.status === "completed" || design.status === "failed");
  if (!terminal.length) {
    return null;
  }
  return [...terminal].sort((left, right) => timestamp(right.created_at) - timestamp(left.created_at))[0] ?? null;
}

function timestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function createTestApi(baseUrl = "http://127.0.0.1:8000", fetcher = fetch) {
  return new TelecomStudioApi(baseUrl, fetcher);
}
