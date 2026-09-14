import { Suspense, lazy, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import type { TelecomStudioApi } from "./api/client";
import { ChatProgress } from "./components/ChatProgress";
import { DurableConversation } from "./components/DurableConversation";
import {
  ActiveWorkflowContext,
  BackendStatusBar,
  ChatCommandPanel,
  CurrentOperationStrip,
  InspectorDock,
  LiveGenerationOverlay
} from "./components/StudioKernel";
import { humanComponentInstanceLabel } from "./components/StudioDisplayHelpers";
import { ViewerLoadingFallback, isTerminalStatus, selectViewerBundleForDisplay } from "./AppSupport";
import { useDesignRevisions } from "./hooks/useDesignRevisions";
import { useDocumentDesignFlow } from "./hooks/useDocumentDesignFlow";
import { useStudioResources } from "./hooks/useStudioResources";
import { useWorkflowLifecycle } from "./hooks/useWorkflowLifecycle";
import { actionIsSupported, initialWorkflowState, workflowReducer } from "./state/workflowMachine";
import { useViewerExpansion } from "./features/three-viewer/useViewerExpansion";
import type { AppProps } from "./StudioApp.types";

const TelecomGlbViewer = lazy(() =>
  import("./features/three-viewer/TelecomGlbViewer").then((module) => ({ default: module.TelecomGlbViewer }))
);

type StudioAppProps = Omit<AppProps, "apiClient"> & { apiClient: TelecomStudioApi };

export function StudioApp({
  apiClient,
  chatId,
  initialWorkflowId,
  initialPrompt = "",
  initialDocumentPackId,
  onDraftChange,
  onWorkflowCreated,
  onDocumentPackLinked,
  onDocumentPackDetached,
  onBusyChange,
  onMutationBusyChange,
  onNewChat
}: StudioAppProps) {
  const [state, dispatch] = useReducer(workflowReducer, { ...initialWorkflowState, prompt: initialPrompt });
  const submissionInFlightRef = useRef(false);
  const [viewerExpanded, setViewerExpanded] = useState(false);
  const [lastCertifiedBundle, setLastCertifiedBundle] = useState(state.viewerBundle);
  const workbenchRef = useRef<HTMLElement | null>(null);
  const clearAnalysisRef = useRef<() => void>(() => undefined);
  const closeExpandedViewer = useCallback(() => setViewerExpanded(false), []);
  useViewerExpansion(workbenchRef, viewerExpanded, closeExpandedViewer);

  const resources = useStudioResources({ apiClient, dispatch, state });
  const workflow = useWorkflowLifecycle({
    apiClient,
    dispatch,
    initialWorkflowId,
    loadSurfaceResource: resources.loadSurfaceResource,
    state,
    submissionInFlightRef
  });
  const revisions = useDesignRevisions({
    apiClient,
    clearAnalysis: () => clearAnalysisRef.current(),
    dispatch,
    initialPrompt,
    initialWorkflowId,
    loadTerminalBundle: workflow.loadTerminalBundle,
    onDraftChange,
    rememberEventSequence: workflow.rememberEventSequence,
    selectedSemanticRoot: resources.selectedSemanticRoot,
    selectedVersionId: resources.selectedVersionId,
    state,
    streamCursorRef: workflow.streamCursorRef,
    towerAccess: resources.towerAccess
  });
  const documents = useDocumentDesignFlow({
    apiClient,
    beginCreatedWorkflow: workflow.beginCreatedWorkflow,
    chatId,
    clearRevisionMessages: revisions.clearRevisionMessages,
    closeEventStream: workflow.closeEventStream,
    dispatch,
    documentCapabilities: resources.documentCapabilities,
    initialDocumentPackId,
    initialWorkflowId,
    invalidateBootstrapRestore: workflow.invalidateBootstrapRestore,
    loadSurfaceResource: resources.loadSurfaceResource,
    onDocumentPackDetached,
    onDocumentPackLinked,
    onDraftChange,
    onWorkflowCreated,
    state,
    submissionInFlightRef
  });
  clearAnalysisRef.current = documents.clearAnalysis;

  const toArtifactUrl = useCallback((url: string | null | undefined) => apiClient.artifactUrl(url), [apiClient]);
  const retryWorkflowSynchronization = useCallback(async () => {
    if (!state.workflowId) {
      await workflow.restoreLatestDesign();
      return;
    }
    const status = await workflow.loadLiveStatus(state.workflowId);
    if (isTerminalStatus(status.status)) await workflow.loadTerminalBundle(state.workflowId);
  }, [state.workflowId, workflow.loadLiveStatus, workflow.loadTerminalBundle, workflow.restoreLatestDesign]);
  const retryBootstrap = useCallback(async () => {
    await Promise.allSettled([resources.loadHealth(), resources.loadStudioSummary(), retryWorkflowSynchronization()]);
  }, [resources.loadHealth, resources.loadStudioSummary, retryWorkflowSynchronization]);
  const retryViewerSurface = useCallback(async () => {
    if (state.workflowId) await resources.reloadViewerBundle();
    else await retryWorkflowSynchronization();
  }, [resources.reloadViewerBundle, retryWorkflowSynchronization, state.workflowId]);

  const canEditCurrentDesign = state.viewerBundle?.status === "completed" &&
    state.viewerBundle.available_actions.includes("edit_design") &&
    actionIsSupported("edit_design", state.viewerBundle.unsupported_actions);
  const persistedInputAnalysis = state.viewerBundle?.input_analysis ?? state.status?.input_analysis ?? null;
  const persistedInputAnalysisStatus = state.viewerBundle?.input_analysis_status ??
    state.status?.input_analysis_status ?? "unavailable";
  const operationNotice = Array.from(new Set([
    state.transportError,
    state.resourceErrors.workflow_status,
    state.resourceErrors.current_operation,
    state.resourceErrors.terminal_bundle,
    state.resourceErrors.timeline,
    state.resourceErrors.events
  ].filter((value): value is string => Boolean(value)))).join(" · ");
  const workflowActive = state.phase === "submitting" || state.phase === "streaming" || state.phase === "running";
  const bootstrapError = state.viewerBundle ? null : Array.from(new Set([
    state.resourceErrors.studio_summary,
    !state.workflowId ? state.resourceErrors.design_list : null,
    state.resourceErrors.workflow_status,
    state.resourceErrors.terminal_bundle
  ].filter((message): message is string => Boolean(message)))).join(" · ") || null;
  const bootstrapLoading = ["studio_summary", "design_list", "workflow_status", "terminal_bundle"]
    .some((resource) => state.resourceLoads[resource]?.status === "loading");
  const viewerSurfaceError = state.resourceErrors.viewer_bundle ??
    (!state.workflowId ? state.resourceErrors.design_list : null) ?? null;
  const viewerSurfaceLoading = state.resourceLoads.viewer_bundle?.status === "loading" ||
    (!state.workflowId && state.resourceLoads.design_list?.status === "loading");
  const displayedViewerBundle = selectViewerBundleForDisplay(state.phase, state.viewerBundle, lastCertifiedBundle);

  useEffect(() => {
    const bundle = state.viewerBundle;
    if (bundle?.status === "completed" && bundle.generation_mode === "real_blender" &&
      bundle.mesh_qa_passed === true && bundle.completion_certificate_status === "issued") {
      setLastCertifiedBundle(bundle);
    }
  }, [state.viewerBundle]);

  const busyCallback = useRef(onBusyChange);
  busyCallback.current = onBusyChange;
  const mutationBusyCallback = useRef(onMutationBusyChange);
  mutationBusyCallback.current = onMutationBusyChange;
  const mutationBusy = documents.submissionBusy || revisions.revisionBusy || documents.analysisBusy ||
    documents.documentPackBusy || Boolean(revisions.rollbackBusyVersionId);
  useEffect(() => {
    busyCallback.current?.(workflowActive || mutationBusy);
    mutationBusyCallback.current?.(mutationBusy);
  }, [workflowActive, mutationBusy]);

  const activeContext = useMemo(() => state.workflowId ? (
    <ActiveWorkflowContext
      activeRequirements={state.prompt.trim() ? null : resources.activeRequirements}
      currentPrompt={documents.analysisIsCurrent || documents.analysisWasSubmitted ? state.prompt : ""}
      versions={workflow.versions}
    />
  ) : null, [documents.analysisIsCurrent, documents.analysisWasSubmitted, resources.activeRequirements, state.prompt, state.workflowId, workflow.versions]);

  return (
    <div className="studio-root">
      <BackendStatusBar
        bundle={state.viewerBundle}
        health={resources.health}
        healthError={state.resourceErrors.health ?? null}
        healthLoading={state.resourceLoads.health?.status === "loading"}
        issues={state.userIssues}
        onRetryHealth={() => void resources.loadHealth().catch(() => undefined)}
        phase={state.phase}
      />
      <main className="studio-layout">
        <aside className="left-rail">
          <ChatCommandPanel
            activity={<ChatProgress events={state.events} phase={state.phase} editing={revisions.revisionBusy} />}
            onNewChat={onNewChat}
            conversation={state.workflowId ? (
              <DurableConversation
                activeContext={activeContext}
                apiClient={apiClient}
                componentProofs={resources.componentProofs}
                workflowId={state.workflowId}
                busy={revisions.revisionBusy}
                revision={state.events.filter((event) => [
                  "design_created", "edit_requested", "edit_outcome", "workflow_completed",
                  "workflow_failed", "version_rolled_back"
                ].includes(event.event_type)).at(-1)?.event_id ?? state.phase}
              />
            ) : undefined}
            activeRequirements={resources.activeRequirements}
            analysis={documents.analysisIsCurrent ? documents.requirementsAnalysis : null}
            analysisBusy={documents.analysisBusy}
            analysisError={documents.analysisError}
            analysisSubmitted={documents.analysisWasSubmitted}
            bootstrapError={bootstrapError}
            bootstrapLoading={bootstrapLoading}
            canEdit={canEditCurrentDesign}
            documentCapabilities={resources.documentCapabilities}
            documentCapabilitiesError={state.resourceErrors.document_capabilities ?? null}
            documentCapabilitiesLoading={state.resourceLoads.document_capabilities?.status === "loading"}
            documentPackBusy={documents.documentPackBusy}
            documentPackMessage={documents.documentPackMessage}
            documentPackSummary={documents.documentPackSummary}
            editMessage={revisions.revisionMessage}
            error={state.error}
            failureIssue={state.userIssues?.human_readable_issues.find((issue) => issue.severity === "error") ?? state.userIssues?.human_readable_issues[0] ?? null}
            onAnalyze={documents.analyzePrompt}
            onFreeDesign={documents.freeDesignAvailable ? documents.submitFreeIntent : undefined}
            onConfirm={documents.submitPrompt}
            onDocumentPackDetach={documents.detachDocumentPack}
            onDocumentPackRetry={documents.retryDocumentPackSummary}
            onDocumentPackUpload={documents.uploadDocumentPack}
            onDocumentCapabilitiesRetry={() => void resources.loadDocumentCapabilities().catch(() => undefined)}
            multimodalConsent={documents.multimodalConsent}
            multimodalIntelligence={documents.multimodalIntelligence}
            onMultimodalConsentChange={documents.setMultimodalConsent}
            onPromptChange={documents.changePrompt}
            onRevisionPromptChange={revisions.changeRevisionPrompt}
            onRevisionSubmit={revisions.submitRevision}
            onRetryBootstrap={() => void retryBootstrap()}
            phase={state.phase}
            prompt={state.prompt}
            submissionPending={state.pendingSubmission}
            revisionBusy={revisions.revisionBusy}
            revisionPrompt={revisions.revisionPrompt}
            versions={workflow.versions}
          />
          {workflowActive && operationNotice ? (
            <CurrentOperationStrip notice={operationNotice} operation={state.currentOperation} phase={state.phase} runtimeMode={state.runtimeMode} />
          ) : null}
        </aside>
        <section ref={workbenchRef} className={`workbench${viewerExpanded ? " viewer-expanded" : ""}`} aria-label="Studio 3D">
          <Suspense fallback={<ViewerLoadingFallback />}>
            <TelecomGlbViewer
              bundle={displayedViewerBundle}
              loadError={viewerSurfaceError}
              loading={viewerSurfaceLoading}
              onReloadBundle={() => void retryViewerSurface().catch(() => undefined)}
              selectedSemanticRoot={resources.selectedSemanticRoot}
              selectedComponentLabel={humanComponentInstanceLabel(resources.componentProofs, resources.selectedSemanticRoot)}
              focusSemanticRoots={resources.sectorFocusSemanticRoots}
              knownSemanticRoots={resources.knownSemanticRoots}
              onSelectSemanticRoot={resources.selectSemanticRoot}
              expanded={viewerExpanded}
              onToggleExpanded={() => setViewerExpanded((value) => !value)}
              toAbsoluteUrl={toArtifactUrl}
            />
          </Suspense>
          {state.phase === "failed" && lastCertifiedBundle ? (
            <div className="retained-design-notice" role="status">
              <CheckCircle2 size={16} aria-hidden="true" />
              <div><strong>Dernier résultat vérifié conservé</strong><span>La nouvelle demande a échoué; elle n’a pas remplacé ce modèle validé.</span></div>
            </div>
          ) : null}
          <LiveGenerationOverlay
            events={state.events}
            operation={state.currentOperation}
            phase={state.phase}
            runtimeMode={state.runtimeMode}
            timeline={state.timeline}
            intent={revisions.rollbackBusyVersionId ? "rollback" : revisions.revisionBusy ? "revision" : "generation"}
          />
          <InspectorDock
            adaptationCapabilities={resources.adaptationCapabilities}
            adaptationCapabilitiesError={state.resourceErrors.adaptation_scene ?? null}
            adaptationLoading={state.resourceLoads.adaptation_scene?.status === "loading" || state.resourceLoads.adaptation_catalog?.status === "loading"}
            adaptationCatalog={resources.adaptationCatalog}
            adaptationCatalogError={state.resourceErrors.adaptation_catalog ?? null}
            assetInventory={resources.assetInventory}
            assetInventoryError={state.resourceErrors.asset_inventory ?? null}
            assetLibraryLoading={state.resourceLoads.asset_inventory?.status === "loading" || state.resourceLoads.asset_library?.status === "loading"}
            assetLibrarySearch={resources.assetLibrarySearch}
            assetLibrarySearchBusy={resources.assetLibrarySearchBusy}
            assetLibrarySearchError={resources.assetLibrarySearchError}
            assetLibraryProbe={resources.assetLibraryProbe}
            assetLibraryProbeBusy={resources.assetLibraryProbeBusy}
            assetLibraryProbeError={resources.assetLibraryProbeError}
            assetLibrarySummary={resources.assetLibrarySummary}
            assetLibrarySummaryError={state.resourceErrors.asset_library ?? null}
            bundle={state.viewerBundle}
            assemblyPlan={resources.assemblyPlan}
            canRollback={revisions.canRollbackVersions}
            events={state.events}
            componentProofs={resources.componentProofs}
            towerAccess={resources.towerAccess}
            cognitiveEvidenceError={[state.resourceErrors.assembly_plan, state.resourceErrors.component_proofs, state.resourceErrors.requirements_context].filter(Boolean).join(" ") || null}
            cognitiveEvidenceLoading={state.resourceLoads.assembly_plan?.status === "loading" || state.resourceLoads.component_proofs?.status === "loading" || state.resourceLoads.requirements_context?.status === "loading"}
            documentCapabilities={resources.documentCapabilities}
            issues={state.userIssues}
            qaEvidence={resources.qaEvidence}
            qaEvidenceError={state.resourceErrors.qa_evidence ?? null}
            qaEvidenceLoading={state.resourceLoads.qa_evidence?.status === "loading"}
            inputAnalysis={persistedInputAnalysis}
            inputAnalysisStatus={persistedInputAnalysisStatus}
            viewerBundleError={state.resourceErrors.viewer_bundle ?? null}
            viewerBundleLoading={state.resourceLoads.viewer_bundle?.status === "loading"}
            summary={state.summary}
            timeline={state.timeline}
            toAbsoluteUrl={toArtifactUrl}
            onRollbackVersion={revisions.rollbackVersion}
            onSelectSceneComponent={resources.selectSemanticRoot}
            onRetryAdaptation={() => void resources.retryAdaptationSurfaces()}
            onRetryAssets={() => void resources.retryAssetSurfaces()}
            onRetryAssetSearch={() => void resources.retryAssetSearch()}
            onRetryAssetProbe={() => void resources.retryAssetProbe()}
            onRetryQaEvidence={() => void resources.retryQaEvidence().catch(() => undefined)}
            onRetryCognitiveEvidence={() => void resources.retryCognitiveEvidence()}
            onRetryViewerBundle={() => void resources.reloadViewerBundle().catch(() => undefined)}
            onSearchAssetLibrary={resources.searchAssetLibrary}
            onProbeAssetLibrary={resources.probeAssetLibrary}
            onReviewAsset={(assetId) => apiClient.assetProvenance(assetId)}
            rollbackBusyVersionId={revisions.rollbackBusyVersionId}
            selectedSemanticRoot={resources.selectedSemanticRoot}
            versionMessage={revisions.versionMessage}
            versions={workflow.versions}
          />
        </section>
      </main>
    </div>
  );
}
