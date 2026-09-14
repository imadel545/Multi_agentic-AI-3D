import { CheckCircle2, FileArchive, Layers3, LibraryBig, PanelRightOpen, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  AdaptationCapabilityCatalog,
  AssemblyPlanEvidence,
  AssetInventory,
  AssetLibraryProbe,
  AssetLibrarySearch,
  AssetLibrarySummary,
  AssetProvenance,
  ComponentProofs,
  DocumentPackCapabilities,
  InputAnalysisStatus,
  PublicVersionInfo,
  RequirementAnalysisReceipt,
  SceneAdaptationCapabilities,
  StudioSummary,
  TimelineSummary,
  TowerAccessSummary,
  UserIssues,
  ViewerBundle
} from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import { AssetLibraryPanel } from "./AssetLibraryPanel";
import { SceneCompositionPanel, sceneInstanceCount } from "./SceneCompositionPanel";
import { ArtifactsPanel, IssuesPanel, QaPanel, SummaryPanel } from "./StudioDesignPanels";
import { VersionSummary } from "./StudioEvidencePanels";
import { ResourceRecovery } from "./StudioPrimitives";
import { displayIssueCount } from "./StudioWorkflowDisplay";

export type DrawerId =
  | "summary"
  | "scene"
  | "quality"
  | "artifacts"
  | "library"
  | "versions";
export type DrawerDefinition = { id: DrawerId; label: string; badge?: string; icon: ReactNode };

export function InspectorDock({
  assemblyPlan = null,
  adaptationCapabilities = null,
  adaptationCapabilitiesError = null,
  adaptationLoading = false,
  adaptationCatalog = null,
  adaptationCatalogError = null,
  assetInventory = null,
  assetInventoryError = null,
  assetLibrarySearch = null,
  assetLibrarySearchBusy = false,
  assetLibrarySearchError = null,
  assetLibraryProbe = null,
  assetLibraryProbeBusy = false,
  assetLibraryProbeError = null,
  assetLibrarySummary = null,
  assetLibrarySummaryError = null,
  assetLibraryLoading = false,
  bundle,
  canRollback,
  documentCapabilities,
  events,
  componentProofs = null,
  towerAccess = null,
  cognitiveEvidenceError = null,
  cognitiveEvidenceLoading = false,
  issues,
  qaEvidence = null,
  qaEvidenceError = null,
  qaEvidenceLoading = false,
  inputAnalysis = null,
  inputAnalysisStatus = "unavailable",
  viewerBundleError = null,
  viewerBundleLoading = false,
  summary,
  timeline,
  toAbsoluteUrl,
  onRollbackVersion,
  onRetryAdaptation,
  onRetryAssets,
  onRetryAssetProbe,
  onRetryAssetSearch,
  onRetryQaEvidence,
  onRetryCognitiveEvidence,
  onRetryViewerBundle,
  onProbeAssetLibrary,
  onReviewAsset,
  onSearchAssetLibrary,
  onSelectSceneComponent,
  rollbackBusyVersionId,
  versionMessage,
  versions,
  selectedSemanticRoot = null
}: {
  assemblyPlan?: AssemblyPlanEvidence | null;
  adaptationCapabilities?: SceneAdaptationCapabilities | null;
  adaptationCapabilitiesError?: string | null;
  adaptationLoading?: boolean;
  adaptationCatalog?: AdaptationCapabilityCatalog | null;
  adaptationCatalogError?: string | null;
  assetInventory?: AssetInventory | null;
  assetInventoryError?: string | null;
  assetLibrarySearch?: AssetLibrarySearch | null;
  assetLibrarySearchBusy?: boolean;
  assetLibrarySearchError?: string | null;
  assetLibraryProbe?: AssetLibraryProbe | null;
  assetLibraryProbeBusy?: boolean;
  assetLibraryProbeError?: string | null;
  assetLibrarySummary?: AssetLibrarySummary | null;
  assetLibrarySummaryError?: string | null;
  assetLibraryLoading?: boolean;
  bundle: ViewerBundle | null;
  canRollback: boolean;
  documentCapabilities?: DocumentPackCapabilities | null;
  events: NormalizedWorkflowEvent[];
  componentProofs?: ComponentProofs | null;
  towerAccess?: TowerAccessSummary | null;
  cognitiveEvidenceError?: string | null;
  cognitiveEvidenceLoading?: boolean;
  issues: UserIssues | null;
  qaEvidence?: unknown | null;
  qaEvidenceError?: string | null;
  qaEvidenceLoading?: boolean;
  inputAnalysis?: RequirementAnalysisReceipt | null;
  inputAnalysisStatus?: InputAnalysisStatus;
  viewerBundleError?: string | null;
  viewerBundleLoading?: boolean;
  summary: StudioSummary | null;
  timeline: TimelineSummary | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  onRollbackVersion: (versionId: string) => void;
  onRetryAdaptation?: () => void;
  onRetryAssets?: () => void;
  onRetryAssetProbe?: () => void;
  onRetryAssetSearch?: () => void;
  onRetryQaEvidence?: () => void;
  onRetryCognitiveEvidence?: () => void;
  onRetryViewerBundle?: () => void;
  onProbeAssetLibrary?: (fileId: string) => void | Promise<void>;
  onReviewAsset?: (assetId: string) => Promise<AssetProvenance>;
  onSearchAssetLibrary?: (query: string) => void | Promise<void>;
  onSelectSceneComponent?: (semanticRoot: string | null) => void;
  rollbackBusyVersionId: string | null;
  versionMessage: string | null;
  versions: PublicVersionInfo[];
  selectedSemanticRoot?: string | null;
}) {
  const [activeDrawer, setActiveDrawer] = useState<DrawerId | null>(null);
  useEffect(() => {
    if (selectedSemanticRoot) setActiveDrawer("scene");
  }, [selectedSemanticRoot]);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const lastTriggerRef = useRef<HTMLButtonElement | null>(null);
  const issueCount = displayIssueCount(issues, bundle);
  const drawers: DrawerDefinition[] = [];
  if (bundle || viewerBundleError || viewerBundleLoading) drawers.push({ id: "summary", label: "Vue", icon: <CheckCircle2 size={16} /> });
  if (assemblyPlan || componentProofs || towerAccess || cognitiveEvidenceError || cognitiveEvidenceLoading) {
    drawers.push({
      id: "scene",
      label: "Composition",
      badge: componentProofs ? String(sceneInstanceCount(componentProofs)) : undefined,
      icon: <Layers3 size={16} />
    });
  }
  if (bundle || issueCount || viewerBundleError || qaEvidenceError || qaEvidenceLoading) {
    drawers.push({
      id: "quality",
      label: "Vérification",
      badge: issueCount ? String(issueCount) : undefined,
      icon: <ShieldAlert size={16} />
    });
  }
  if (bundle?.viewer_artifacts.length) drawers.push({ id: "artifacts", label: "Livrables", icon: <FileArchive size={16} /> });
  if (assetInventory || assetInventoryError || assetLibraryLoading) {
    drawers.push({ id: "library", label: "Bibliothèque", icon: <LibraryBig size={16} /> });
  }
  if (versions.length) drawers.push({ id: "versions", label: "Versions", badge: String(versions.length), icon: <Layers3 size={16} /> });
  const drawerOpen = activeDrawer !== null;
  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setActiveDrawer(null);
        window.requestAnimationFrame(() => lastTriggerRef.current?.focus());
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  const closeDrawer = () => {
    setActiveDrawer(null);
    window.requestAnimationFrame(() => lastTriggerRef.current?.focus());
  };
  return (
    <aside className="context-dock" aria-label="Drawers contextuels">
      {!activeDrawer && drawers.length ? (
        <button
          aria-controls="studio-context-drawer"
          aria-expanded="false"
          aria-label="Ouvrir le panneau d’inspection"
          className="drawer-launcher"
          ref={lastTriggerRef}
          onClick={(event) => {
            lastTriggerRef.current = event.currentTarget;
            setActiveDrawer(drawers[0].id);
          }}
          title="Ouvrir les détails du design"
          type="button"
        >
          <PanelRightOpen size={18} aria-hidden="true" />
        </button>
      ) : null}
      {activeDrawer ? (
        <div
          aria-label={`Détails : ${drawers.find((drawer) => drawer.id === activeDrawer)?.label ?? "Design"}`}
          className="context-drawer"
          id="studio-context-drawer"
          ref={drawerRef}
          role="dialog"
        >
          <header className="drawer-header">
            <nav aria-label="Sections du panneau" className="drawer-navigation">
              {drawers.map((drawer) => (
                <button
                  aria-current={activeDrawer === drawer.id ? "page" : undefined}
                  className={activeDrawer === drawer.id ? "drawer-action active" : "drawer-action"}
                  key={drawer.id}
                  onClick={() => setActiveDrawer(drawer.id)}
                  type="button"
                >
                  {drawer.icon}
                  <span>{drawer.label}</span>
                  {drawer.badge ? <small>{drawer.badge}</small> : null}
                </button>
              ))}
            </nav>
            <button aria-label="Fermer les détails" className="drawer-close" onClick={closeDrawer} ref={closeButtonRef} title="Fermer" type="button">
              <X size={16} aria-hidden="true" />
            </button>
          </header>
          <div className="drawer-content">
          {activeDrawer === "summary" ? (
            <>
              {viewerBundleError ? <ResourceRecovery busy={viewerBundleLoading} label="Le résumé vérifié du design n’a pas été resynchronisé." message={viewerBundleError} onRetry={onRetryViewerBundle} /> : null}
              <SummaryPanel
                bundle={bundle}
                inputAnalysis={inputAnalysis}
                inputAnalysisStatus={inputAnalysisStatus}
                issues={issues}
                summary={summary}
                versions={versions}
              />
            </>
          ) : null}
          {activeDrawer === "scene" ? (
            <SceneCompositionPanel
              assemblyPlan={assemblyPlan}
              assetDecisionSummary={bundle?.asset_decision_summary}
              assetInventory={assetInventory}
              componentProofs={componentProofs}
              error={cognitiveEvidenceError}
              loading={cognitiveEvidenceLoading}
              onRetry={onRetryCognitiveEvidence}
              onSelect={onSelectSceneComponent}
              selectedSemanticRoot={selectedSemanticRoot}
              sectorPreviews={bundle?.sector_previews}
              towerAccess={towerAccess}
              toAbsoluteUrl={toAbsoluteUrl}
            />
          ) : null}
          {activeDrawer === "quality" ? (
            <>
              <QaPanel
                bundle={bundle}
                evidence={qaEvidence}
                error={qaEvidenceError ?? viewerBundleError}
                loading={qaEvidenceLoading || viewerBundleLoading}
                onRetry={qaEvidenceError ? onRetryQaEvidence : onRetryViewerBundle}
                toAbsoluteUrl={toAbsoluteUrl}
              />
              <IssuesPanel issues={issues} />
            </>
          ) : null}
          {activeDrawer === "artifacts" ? <ArtifactsPanel bundle={bundle} toAbsoluteUrl={toAbsoluteUrl} /> : null}
          {activeDrawer === "library" ? (
            <AssetLibraryPanel
              busy={assetLibrarySearchBusy}
              error={assetLibrarySearchError}
              inventory={assetInventory}
              inventoryError={assetInventoryError}
              loading={assetLibraryLoading}
              onRetry={onRetryAssets}
              onRetryProbe={onRetryAssetProbe}
              onRetrySearch={onRetryAssetSearch}
              onProbe={onProbeAssetLibrary}
              onReview={onReviewAsset}
              onSearch={onSearchAssetLibrary}
              probe={assetLibraryProbe}
              probeBusy={assetLibraryProbeBusy}
              probeError={assetLibraryProbeError}
              search={assetLibrarySearch}
              summary={assetLibrarySummary}
              summaryError={assetLibrarySummaryError}
              toAbsoluteUrl={toAbsoluteUrl}
            />
          ) : null}
          {activeDrawer === "versions" ? (
            <VersionSummary
              busyVersionId={rollbackBusyVersionId}
              canRollback={canRollback}
              message={versionMessage}
              onRollback={onRollbackVersion}
              versions={versions}
            />
          ) : null}
          </div>
        </div>
      ) : null}
    </aside>
  );
}


