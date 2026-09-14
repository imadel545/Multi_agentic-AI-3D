import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TelecomStudioApi } from "../api/client";
import type {
  AdaptationCapabilityCatalog,
  AssemblyPlanEvidence,
  AssetInventory,
  AssetLibraryProbe,
  AssetLibrarySearch,
  AssetLibrarySummary,
  ComponentProofs,
  DocumentPackCapabilities,
  Health,
  RequirementSpec,
  SceneAdaptationCapabilities
} from "../api/schemas";
import { userFacingError, type UserActionContext } from "../AppSupport";
import { sectorMechanicalFocusRoots } from "../features/three-viewer/sectorFocus";
import type { WorkflowMachineState } from "../state/workflowMachine";
import type { LoadSurfaceResource, WorkflowDispatch } from "./studioAppTypes";

type UseStudioResourcesOptions = {
  apiClient: TelecomStudioApi;
  dispatch: WorkflowDispatch;
  state: WorkflowMachineState;
};

export function useStudioResources({ apiClient, dispatch, state }: UseStudioResourcesOptions) {
  const [health, setHealth] = useState<Health | null>(null);
  const [assetLibrarySummary, setAssetLibrarySummary] = useState<AssetLibrarySummary | null>(null);
  const [assetInventory, setAssetInventory] = useState<AssetInventory | null>(null);
  const [assetLibrarySearch, setAssetLibrarySearch] = useState<AssetLibrarySearch | null>(null);
  const [assetLibrarySearchBusy, setAssetLibrarySearchBusy] = useState(false);
  const [assetLibrarySearchError, setAssetLibrarySearchError] = useState<string | null>(null);
  const [assetLibraryProbe, setAssetLibraryProbe] = useState<AssetLibraryProbe | null>(null);
  const [assetLibraryProbeBusy, setAssetLibraryProbeBusy] = useState(false);
  const [assetLibraryProbeError, setAssetLibraryProbeError] = useState<string | null>(null);
  const [adaptationCatalog, setAdaptationCatalog] = useState<AdaptationCapabilityCatalog | null>(null);
  const [adaptationCapabilities, setAdaptationCapabilities] = useState<SceneAdaptationCapabilities | null>(null);
  const [qaEvidence, setQaEvidence] = useState<unknown | null>(null);
  const [componentProofs, setComponentProofs] = useState<ComponentProofs | null>(null);
  const [assemblyPlan, setAssemblyPlan] = useState<AssemblyPlanEvidence | null>(null);
  const [activeRequirements, setActiveRequirements] = useState<RequirementSpec | null>(null);
  const [selectedSemanticRoot, setSelectedSemanticRoot] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [documentCapabilities, setDocumentCapabilities] = useState<DocumentPackCapabilities | null>(null);
  const resourceRequestRef = useRef<Record<string, number>>({});
  const mountedRef = useRef(true);
  const lastAssetLibraryQueryRef = useRef<string | null>(null);
  const lastAssetLibraryProbeRef = useRef<string | null>(null);

  const towerAccess = state.viewerBundle?.tower_access_summary ?? null;
  const sectorFocusSemanticRoots = useMemo(
    () => sectorMechanicalFocusRoots(componentProofs, selectedSemanticRoot),
    [componentProofs, selectedSemanticRoot]
  );
  const knownSemanticRoots = useMemo(() => {
    const roots = componentProofs?.components.flatMap((component) =>
      component.instances.map((instance) => instance.semantic_root)
    ) ?? [];
    if (towerAccess) roots.push(towerAccess.semantic_root);
    return Array.from(new Set(roots));
  }, [componentProofs, towerAccess]);
  const selectSemanticRoot = useCallback((root: string | null) => {
    setSelectedSemanticRoot(root);
    setSelectedVersionId(root ? state.viewerBundle?.version_id ?? null : null);
  }, [state.viewerBundle]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      for (const resource of Object.keys(resourceRequestRef.current)) {
        resourceRequestRef.current[resource] += 1;
      }
    };
  }, []);

  const loadSurfaceResource = useCallback(async <T,>(
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
      if (mountedRef.current && resourceRequestRef.current[resource] === requestId) {
        onValue(value);
        dispatch({ type: "RESOURCE_RECOVERED", resource });
      }
      return value;
    } catch (error) {
      if (mountedRef.current && resourceRequestRef.current[resource] === requestId) {
        dispatch({ type: "RESOURCE_FAILED", resource, message: userFacingError(error, context) });
      }
      throw error;
    }
  }, [dispatch]) as LoadSurfaceResource;

  const loadHealth = useCallback(() => loadSurfaceResource(
    "health", () => apiClient.health(), setHealth, "connection", () => setHealth(null)
  ), [apiClient, loadSurfaceResource]);
  const loadStudioSummary = useCallback(() => loadSurfaceResource(
    "studio_summary", () => apiClient.studioSummary(),
    (summary) => dispatch({ type: "BOOTSTRAP_LOADED", summary }), "bootstrap"
  ), [apiClient, dispatch, loadSurfaceResource]);
  const loadAssetLibrarySummary = useCallback(() => loadSurfaceResource(
    "asset_library", () => apiClient.assetLibrarySummary(), setAssetLibrarySummary,
    "assets", () => setAssetLibrarySummary(null)
  ), [apiClient, loadSurfaceResource]);
  const loadAssetInventory = useCallback(() => loadSurfaceResource(
    "asset_inventory", () => apiClient.assetInventory(), setAssetInventory,
    "assets", () => setAssetInventory(null)
  ), [apiClient, loadSurfaceResource]);
  const loadAdaptationCatalog = useCallback(() => loadSurfaceResource(
    "adaptation_catalog", () => apiClient.adaptationCapabilityCatalog(), setAdaptationCatalog,
    "resource", () => setAdaptationCatalog(null)
  ), [apiClient, loadSurfaceResource]);
  const loadDocumentCapabilities = useCallback(() => loadSurfaceResource(
    "document_capabilities", () => apiClient.documentPackCapabilities(), setDocumentCapabilities,
    "documents", () => setDocumentCapabilities(null)
  ), [apiClient, loadSurfaceResource]);

  useEffect(() => {
    void loadHealth().catch(() => undefined);
    void loadStudioSummary().catch(() => undefined);
    void loadAssetInventory().catch(() => undefined);
    void loadAssetLibrarySummary().catch(() => undefined);
    void loadDocumentCapabilities().catch(() => undefined);
  }, [loadAssetInventory, loadAssetLibrarySummary, loadDocumentCapabilities, loadHealth, loadStudioSummary]);

  useEffect(() => {
    const bundle = state.viewerBundle;
    for (const resource of ["assembly_plan", "component_proofs", "qa_evidence", "requirements_context", "llm_provenance", "rag_evidence"]) {
      resourceRequestRef.current[resource] = (resourceRequestRef.current[resource] ?? 0) + 1;
    }
    setAdaptationCapabilities(null);
    setAssemblyPlan(null);
    setComponentProofs(null);
    setQaEvidence(null);
    setActiveRequirements(null);
    setSelectedSemanticRoot(null);
    setSelectedVersionId(null);
    if (!bundle) return;
    if (bundle.assembly_plan_url) {
      void loadSurfaceResource("assembly_plan", () => apiClient.assemblyPlan(bundle.assembly_plan_url), setAssemblyPlan, "resource", () => setAssemblyPlan(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "assembly_plan" });
    if (bundle.component_proofs_url) {
      void loadSurfaceResource("component_proofs", () => apiClient.componentProofs(bundle.component_proofs_url), setComponentProofs, "resource", () => setComponentProofs(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "component_proofs" });
    if (bundle.requirements_spec_url) {
      void loadSurfaceResource("requirements_context", () => apiClient.requirementsSpec(bundle.requirements_spec_url), setActiveRequirements, "resource", () => setActiveRequirements(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "requirements_context" });
    if (bundle.qa_report_url) {
      void loadSurfaceResource("qa_evidence", () => apiClient.artifactJson(bundle.qa_report_url), setQaEvidence, "resource", () => setQaEvidence(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "qa_evidence" });
  }, [apiClient, dispatch, loadSurfaceResource, state.viewerBundle]);

  const searchAssetLibrary = useCallback(async (query: string) => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) return;
    lastAssetLibraryQueryRef.current = normalizedQuery;
    lastAssetLibraryProbeRef.current = null;
    setAssetLibraryProbe(null);
    setAssetLibraryProbeError(null);
    setAssetLibrarySearchBusy(true);
    setAssetLibrarySearchError(null);
    try {
      await loadSurfaceResource("asset_search", () => apiClient.searchAssetLibrary(normalizedQuery), setAssetLibrarySearch, "assets", () => setAssetLibrarySearch(null));
    } catch (error) {
      setAssetLibrarySearchError(userFacingError(error, "assets"));
    } finally {
      setAssetLibrarySearchBusy(false);
    }
  }, [apiClient, loadSurfaceResource]);

  const probeAssetLibrary = useCallback(async (fileId: string) => {
    lastAssetLibraryProbeRef.current = fileId;
    setAssetLibraryProbeBusy(true);
    setAssetLibraryProbeError(null);
    try {
      await loadSurfaceResource("asset_library_probe", () => apiClient.probeAssetLibrary(fileId), setAssetLibraryProbe, "assets", () => setAssetLibraryProbe(null));
    } catch (error) {
      setAssetLibraryProbeError(userFacingError(error, "assets"));
    } finally {
      setAssetLibraryProbeBusy(false);
    }
  }, [apiClient, loadSurfaceResource]);

  const reloadViewerBundle = useCallback(async () => {
    if (!state.workflowId) return;
    await loadSurfaceResource("viewer_bundle", () => apiClient.viewerBundle(state.workflowId!),
      (viewerBundle) => dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle }));
  }, [apiClient, dispatch, loadSurfaceResource, state.workflowId]);
  const retryAssetSurfaces = useCallback(async () => {
    await Promise.allSettled([loadAssetInventory(), loadAssetLibrarySummary()]);
  }, [loadAssetInventory, loadAssetLibrarySummary]);
  const retryAdaptationSurfaces = useCallback(async () => {
    const requests: Promise<unknown>[] = [loadAdaptationCatalog()];
    if (state.workflowId) {
      requests.push(loadSurfaceResource("adaptation_scene", () => apiClient.designAdaptationCapabilities(state.workflowId!), setAdaptationCapabilities, "resource", () => setAdaptationCapabilities(null)));
    }
    await Promise.allSettled(requests);
  }, [apiClient, loadAdaptationCatalog, loadSurfaceResource, state.workflowId]);
  const retryAssetSearch = useCallback(async () => {
    if (lastAssetLibraryQueryRef.current) await searchAssetLibrary(lastAssetLibraryQueryRef.current);
  }, [searchAssetLibrary]);
  const retryAssetProbe = useCallback(async () => {
    if (lastAssetLibraryProbeRef.current) await probeAssetLibrary(lastAssetLibraryProbeRef.current);
  }, [probeAssetLibrary]);
  const retryQaEvidence = useCallback(async () => {
    const url = state.viewerBundle?.qa_report_url;
    if (!url) return;
    await loadSurfaceResource("qa_evidence", () => apiClient.artifactJson(url), setQaEvidence, "resource", () => setQaEvidence(null));
  }, [apiClient, loadSurfaceResource, state.viewerBundle?.qa_report_url]);
  const retryCognitiveEvidence = useCallback(async () => {
    const bundle = state.viewerBundle;
    if (!bundle) return;
    const requests: Promise<unknown>[] = [];
    if (bundle.assembly_plan_url) requests.push(loadSurfaceResource("assembly_plan", () => apiClient.assemblyPlan(bundle.assembly_plan_url), setAssemblyPlan, "resource", () => setAssemblyPlan(null)));
    if (bundle.component_proofs_url) requests.push(loadSurfaceResource("component_proofs", () => apiClient.componentProofs(bundle.component_proofs_url), setComponentProofs, "resource", () => setComponentProofs(null)));
    if (bundle.requirements_spec_url) requests.push(loadSurfaceResource("requirements_context", () => apiClient.requirementsSpec(bundle.requirements_spec_url), setActiveRequirements, "resource", () => setActiveRequirements(null)));
    await Promise.allSettled(requests);
  }, [apiClient, loadSurfaceResource, state.viewerBundle]);

  return {
    activeRequirements, adaptationCapabilities, adaptationCatalog, assemblyPlan, assetInventory,
    assetLibraryProbe, assetLibraryProbeBusy, assetLibraryProbeError, assetLibrarySearch,
    assetLibrarySearchBusy, assetLibrarySearchError, assetLibrarySummary, componentProofs,
    documentCapabilities, health, knownSemanticRoots, loadDocumentCapabilities, loadHealth,
    loadStudioSummary, loadSurfaceResource, probeAssetLibrary, qaEvidence, reloadViewerBundle,
    retryAdaptationSurfaces, retryAssetProbe, retryAssetSearch, retryAssetSurfaces,
    retryCognitiveEvidence, retryQaEvidence, searchAssetLibrary, sectorFocusSemanticRoots,
    selectedSemanticRoot, selectedVersionId, selectSemanticRoot, towerAccess
  };
}
