import { FileArchive, Layers3, PanelRightOpen, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  AssetInventory,
  ComponentProofs,
  PublicVersionInfo,
  TowerAccessSummary,
  ViewerBundle
} from "../api/schemas";
import { SceneCompositionPanel, sceneInstanceCount } from "./SceneCompositionPanel";
import { ArtifactsPanel } from "./StudioDesignPanels";
import { VersionSummary } from "./StudioEvidencePanels";

export type DrawerId = "scene" | "artifacts" | "versions";
export type DrawerDefinition = { id: DrawerId; label: string; badge?: string; icon: ReactNode };

export function InspectorDock({
  assetInventory = null,
  bundle,
  canRollback,
  componentProofs = null,
  towerAccess = null,
  cognitiveEvidenceError = null,
  cognitiveEvidenceLoading = false,
  toAbsoluteUrl,
  onRollbackVersion,
  onRetryCognitiveEvidence,
  onSelectSceneComponent,
  rollbackBusyVersionId,
  versionMessage,
  versions,
  selectedSemanticRoot = null
}: {
  assetInventory?: AssetInventory | null;
  bundle: ViewerBundle | null;
  canRollback: boolean;
  componentProofs?: ComponentProofs | null;
  towerAccess?: TowerAccessSummary | null;
  cognitiveEvidenceError?: string | null;
  cognitiveEvidenceLoading?: boolean;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  onRollbackVersion: (versionId: string) => void;
  onRetryCognitiveEvidence?: () => void;
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
  const drawers: DrawerDefinition[] = [
    {
      id: "scene",
      label: "Composition",
      badge: componentProofs ? String(sceneInstanceCount(componentProofs)) : undefined,
      icon: <Layers3 size={16} />
    },
    { id: "artifacts", label: "Livrables", icon: <FileArchive size={16} /> },
    {
      id: "versions",
      label: "Versions",
      badge: versions.length ? String(versions.length) : undefined,
      icon: <Layers3 size={16} />
    }
  ];
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
          {activeDrawer === "scene" ? (
            <SceneCompositionPanel
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
          {activeDrawer === "artifacts" ? <ArtifactsPanel bundle={bundle} toAbsoluteUrl={toAbsoluteUrl} /> : null}
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
