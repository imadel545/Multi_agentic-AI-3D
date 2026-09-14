import { useGLTF } from "@react-three/drei";
import { AlertTriangle, Layers3, Loader2, Maximize2, Minimize2, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { TelecomCanvas, advanceRenderHealthProbe } from "./ViewerCanvas";
import { GlbObjectSummary, PreviewFallback, ViewerEmpty, ViewerError } from "./ViewerStates";
import { hasUsableWebGL, resolveViewerSource, viewerBadges } from "./viewerRules";
import { semanticRootForPick, semanticRootsBounds, semanticSelectionBounds } from "./viewerSelection";
import type { ModelObjectSummary } from "./viewerMath";
import type { CameraScope, TelecomGlbViewerProps, ViewerHealth } from "./viewerTypes";

const EMPTY_FOCUS_SEMANTIC_ROOTS: readonly string[] = [];

export function TelecomGlbViewer({
  bundle,
  loadError = null,
  loading = false,
  onReloadBundle,
  probeWebGL = hasUsableWebGL,
  selectedSemanticRoot = null,
  selectedComponentLabel = null,
  focusSemanticRoots = EMPTY_FOCUS_SEMANTIC_ROOTS,
  knownSemanticRoots = [],
  onSelectSemanticRoot,
  expanded = false,
  onToggleExpanded,
  toAbsoluteUrl
}: TelecomGlbViewerProps) {
  const source = resolveViewerSource(bundle, toAbsoluteUrl);
  const badges = viewerBadges(bundle).filter(isProductWarningBadge);
  const [resetKey, setResetKey] = useState(0);
  const [cameraFitRequest, setCameraFitRequest] = useState(0);
  const [cameraScope, setCameraScope] = useState<CameraScope>("initial");
  const [objectSummary, setObjectSummary] = useState<ModelObjectSummary | null>(null);
  const [viewerHealth, setViewerHealth] = useState<ViewerHealth>("idle");
  const [showTechnicalAids, setShowTechnicalAids] = useState(false);
  const [webglSupported, setWebglSupported] = useState<boolean | null>(() =>
    source.kind === "glb" ? probeWebGL() : null
  );
  const sourceIdentity = "url" in source ? `${source.kind}:${source.url}` : source.kind;
  const previousSelectionRef = useRef<string | null>(selectedSemanticRoot);
  const sourceIdentityRef = useRef(sourceIdentity);
  const renderIsBlank = source.kind === "glb" && viewerHealth === "render_blank";

  const retryViewer = () => {
    if (loading) return;
    if (source.kind === "glb") {
      const supported = probeWebGL();
      setWebglSupported(supported);
      if (supported) {
        useGLTF.clear(source.url);
        setViewerHealth("loading_glb");
        setResetKey((value) => value + 1);
      }
      if (loadError) void onReloadBundle?.();
      return;
    }
    void onReloadBundle?.();
  };

  const showWholeDesign = () => {
    onSelectSemanticRoot?.(null);
    setCameraScope("global");
    setCameraFitRequest((value) => value + 1);
  };

  useEffect(() => {
    if (sourceIdentityRef.current !== sourceIdentity) {
      sourceIdentityRef.current = sourceIdentity;
      previousSelectionRef.current = selectedSemanticRoot;
      setCameraScope("initial");
    }
  }, [selectedSemanticRoot, sourceIdentity]);

  useEffect(() => {
    if (previousSelectionRef.current && !selectedSemanticRoot) setCameraScope("global");
    previousSelectionRef.current = selectedSemanticRoot;
  }, [selectedSemanticRoot]);

  useEffect(() => {
    setObjectSummary(null);
    setViewerHealth(source.kind === "glb" ? "loading_glb" : "idle");
    setWebglSupported(source.kind === "glb" ? probeWebGL() : null);
  }, [probeWebGL, sourceIdentity]);

  return (
    <section className="viewer-shell" aria-label="3D viewer">
      <div className="viewer-toolbar">
        <div>
          <span className="eyebrow">Viewer 3D</span>
          <h2>{bundle ? "Design 3D telecom" : "En attente d'un design"}</h2>
        </div>
        <div className="badge-row">
          {onToggleExpanded ? (
            <button
              aria-label={expanded ? "Quitter le plein écran du viewer 3D" : "Afficher le viewer 3D en plein écran"}
              aria-pressed={expanded}
              data-viewer-expansion
              className="icon-action"
              onClick={onToggleExpanded}
              title={expanded ? "Quitter le plein écran" : "Plein écran"}
              type="button"
            >
              {expanded ? <Minimize2 size={15} aria-hidden="true" /> : <Maximize2 size={15} aria-hidden="true" />}
            </button>
          ) : null}
          <button
            className="icon-action"
            disabled={source.kind !== "glb"}
            onClick={showWholeDesign}
            aria-label="Afficher tout le site et recentrer la caméra 3D"
            title="Afficher tout le site"
            type="button"
          >
            <RotateCcw size={15} aria-hidden="true" />
          </button>
          <button
            aria-pressed={showTechnicalAids}
            aria-label={showTechnicalAids ? "Masquer les aides techniques" : "Afficher les aides techniques"}
            className={`viewer-aids-toggle${showTechnicalAids ? " active" : ""}`}
            disabled={source.kind !== "glb"}
            onClick={() => setShowTechnicalAids((value) => !value)}
            type="button"
          >
            <Layers3 size={15} aria-hidden="true" /> <span>Aides techniques</span>
          </button>
          {badges.map((badge) => <span className="status-badge" key={badge}>{badge}</span>)}
        </div>
      </div>

      {source.kind === "empty" && loadError ? (
        <ViewerError busy={loading} message={loadError} previewUrl={null} onRetry={retryViewer} />
      ) : source.kind === "empty" ? (
        loading ? <ViewerEmpty message="Synchronisation du design vérifié…" /> : <ViewerEmpty message={source.message} />
      ) : source.kind === "preview" ? (
        <PreviewFallback
          busy={loading}
          url={source.url}
          message="Le modèle 3D interactif n’est pas disponible. L’aperçu du design reste affiché."
          onRetry={retryViewer}
        />
      ) : source.kind === "error" ? (
        <ViewerError busy={loading} message={source.message} previewUrl={source.previewUrl} onRetry={retryViewer} />
      ) : (
        <div className="canvas-frame">
          {selectedSemanticRoot ? (
            <div className="viewer-selection" aria-live="polite">
              <Layers3 size={15} aria-hidden="true" /> Composant sélectionné : {selectedComponentLabel ?? "composant 3D"}
              {focusSemanticRoots.length > 1 ? <span> · Cadrage du sous-assemblage mécanique vérifié</span> : null}
              {onSelectSemanticRoot ? <button type="button" onClick={showWholeDesign}>Désélectionner</button> : null}
            </div>
          ) : null}
          {loading ? (
            <div className="viewer-refresh-alert loading" aria-live="polite" role="status">
              <Loader2 className="spin" size={16} aria-hidden="true" />
              <span>Resynchronisation du dernier résultat vérifié…</span>
            </div>
          ) : loadError ? (
            <div className="viewer-refresh-alert" role="alert">
              <AlertTriangle size={16} aria-hidden="true" />
              <span>{loadError} Le dernier résultat vérifié reste affiché.</span>
              <button onClick={retryViewer} type="button">Resynchroniser</button>
            </div>
          ) : null}
          {webglSupported === false ? (
            <ViewerError
              busy={loading}
              message={source.previewUrl
                ? "La 3D interactive n’est pas disponible dans ce navigateur. L’aperçu du design reste affiché."
                : "La 3D interactive n’est pas disponible dans ce navigateur et aucun aperçu n’est disponible."}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            />
          ) : viewerHealth === "camera_fit_error" ? (
            <ViewerError
              busy={loading}
              message={source.previewUrl
                ? "Le modèle 3D ne contient pas de scène cadrable. L’aperçu du design reste affiché."
                : "Le modèle 3D ne contient pas de scène cadrable et aucun aperçu n’est disponible."}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            />
          ) : renderIsBlank ? (
            <ViewerError
              busy={loading}
              message={source.previewUrl
                ? "Le modèle est chargé mais son rendu n’est pas visible. L’aperçu du design reste affiché."
                : "Le modèle est chargé mais son rendu n’est pas visible, et aucun aperçu n’est disponible."}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            />
          ) : (
            <GlbObjectSummary health={viewerHealth} summary={objectSummary} />
          )}
          {webglSupported === false ? null : (
            <TelecomCanvas
              cameraFitRequest={cameraFitRequest}
              cameraScope={cameraScope}
              focusSemanticRoots={focusSemanticRoots}
              knownSemanticRoots={knownSemanticRoots}
              onHealth={setViewerHealth}
              onLoaded={setObjectSummary}
              onRetry={retryViewer}
              onSelectSemanticRoot={onSelectSemanticRoot}
              previewUrl={source.previewUrl}
              resetKey={resetKey}
              selectedSemanticRoot={selectedSemanticRoot}
              showTechnicalAids={showTechnicalAids}
              url={source.url}
              viewerHealth={viewerHealth}
            />
          )}
        </div>
      )}
    </section>
  );
}

function isProductWarningBadge(badge: string) {
  return badge.includes("Fallback") || badge.includes("dégradé") ||
    badge.includes("attention") || badge.includes("rejetée");
}

export { PreviewFallback, advanceRenderHealthProbe, semanticRootForPick, semanticRootsBounds, semanticSelectionBounds };
export type { TelecomGlbViewerProps, ViewerHealth };
