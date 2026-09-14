import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ViewerBundle } from "../api/schemas";
import type { TelecomStudioApi } from "../api/client";
import type {
  AssetInventory,
  ComponentProofs,
  DocumentPackCapabilities,
  Health,
  RequirementSpec
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
  const [assetInventory, setAssetInventory] = useState<AssetInventory | null>(null);
  const [componentProofs, setComponentProofs] = useState<ComponentProofs | null>(null);
  const [activeRequirements, setActiveRequirements] = useState<RequirementSpec | null>(null);
  const [selectedSemanticRoot, setSelectedSemanticRoot] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [documentCapabilities, setDocumentCapabilities] = useState<DocumentPackCapabilities | null>(null);
  const resourceRequestRef = useRef<Record<string, number>>({});
  const mountedRef = useRef(true);

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
  const loadAssetInventory = useCallback(() => loadSurfaceResource(
    "asset_inventory", () => apiClient.assetInventory(), setAssetInventory,
    "assets", () => setAssetInventory(null)
  ), [apiClient, loadSurfaceResource]);
  const loadDocumentCapabilities = useCallback(() => loadSurfaceResource(
    "document_capabilities", () => apiClient.documentPackCapabilities(), setDocumentCapabilities,
    "documents", () => setDocumentCapabilities(null)
  ), [apiClient, loadSurfaceResource]);

  useEffect(() => {
    void loadHealth().catch(() => undefined);
    void loadStudioSummary().catch(() => undefined);
    void loadAssetInventory().catch(() => undefined);
    void loadDocumentCapabilities().catch(() => undefined);
  }, [loadAssetInventory, loadDocumentCapabilities, loadHealth, loadStudioSummary]);

  const viewerBundleRef = useRef(state.viewerBundle);
  viewerBundleRef.current = state.viewerBundle;
  const evidenceKey = viewerEvidenceKey(state.viewerBundle);
  useEffect(() => {
    const bundle = viewerBundleRef.current;
    for (const resource of ["component_proofs", "requirements_context"]) {
      resourceRequestRef.current[resource] = (resourceRequestRef.current[resource] ?? 0) + 1;
    }
    setComponentProofs(null);
    setActiveRequirements(null);
    setSelectedSemanticRoot(null);
    setSelectedVersionId(null);
    if (!bundle) return;
    if (bundle.component_proofs_url) {
      void loadSurfaceResource("component_proofs", () => apiClient.componentProofs(bundle.component_proofs_url), setComponentProofs, "resource", () => setComponentProofs(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "component_proofs" });
    if (bundle.requirements_spec_url) {
      void loadSurfaceResource("requirements_context", () => apiClient.requirementsSpec(bundle.requirements_spec_url), setActiveRequirements, "resource", () => setActiveRequirements(null)).catch(() => undefined);
    } else dispatch({ type: "RESOURCE_RECOVERED", resource: "requirements_context" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- evidence follows the bundle identity, not its object reference
  }, [apiClient, dispatch, loadSurfaceResource, evidenceKey]);

  const reloadViewerBundle = useCallback(async () => {
    if (!state.workflowId) return;
    await loadSurfaceResource("viewer_bundle", () => apiClient.viewerBundle(state.workflowId!),
      (viewerBundle) => dispatch({ type: "VIEWER_BUNDLE_LOADED", viewerBundle }));
  }, [apiClient, dispatch, loadSurfaceResource, state.workflowId]);
  const retryCognitiveEvidence = useCallback(async () => {
    const bundle = state.viewerBundle;
    if (!bundle) return;
    const requests: Promise<unknown>[] = [];
    if (bundle.component_proofs_url) requests.push(loadSurfaceResource("component_proofs", () => apiClient.componentProofs(bundle.component_proofs_url), setComponentProofs, "resource", () => setComponentProofs(null)));
    if (bundle.requirements_spec_url) requests.push(loadSurfaceResource("requirements_context", () => apiClient.requirementsSpec(bundle.requirements_spec_url), setActiveRequirements, "resource", () => setActiveRequirements(null)));
    await Promise.allSettled(requests);
  }, [apiClient, loadSurfaceResource, state.viewerBundle]);

  return {
    activeRequirements, assetInventory, componentProofs,
    documentCapabilities, health, knownSemanticRoots, loadDocumentCapabilities, loadHealth,
    loadStudioSummary, loadSurfaceResource, reloadViewerBundle, retryCognitiveEvidence, sectorFocusSemanticRoots,
    selectedSemanticRoot, selectedVersionId, selectSemanticRoot, towerAccess
  };
}


/** Evidence artifacts are keyed by what they describe, so re-receiving an identical bundle never refetches them. */
export function viewerEvidenceKey(bundle: ViewerBundle | null): string {
  if (!bundle) return "";
  return [
    bundle.workflow_id,
    bundle.version_id ?? "",
    bundle.status,
    bundle.component_proofs_url ?? "",
    bundle.requirements_spec_url ?? ""
  ].join("|");
}
