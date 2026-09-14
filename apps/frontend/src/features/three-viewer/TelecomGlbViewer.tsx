import { Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { AlertTriangle, Box, Image as ImageIcon, Layers3, Loader2, Maximize2, Minimize2, RotateCcw } from "lucide-react";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { ACESFilmicToneMapping, Box3, Box3Helper, Color, SRGBColorSpace, WebGLRenderTarget } from "three";
import type { Camera, Object3D, PerspectiveCamera, Scene, WebGLRenderer } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { ViewerBundle } from "../../api/schemas";
import {
  hasUsableWebGL,
  resolveViewerSource,
  viewerBadges
} from "./viewerRules";
import {
  fitCameraToObject,
  physicalSceneBounds,
  prepareViewerScene,
  probeRenderVisibility,
  summarizeObjects,
  type ModelObjectSummary,
  type RenderSample
} from "./viewerMath";

const EMPTY_FOCUS_SEMANTIC_ROOTS: readonly string[] = [];
type CameraScope = "initial" | "global";

type TelecomGlbViewerProps = {
  bundle: ViewerBundle | null;
  loadError?: string | null;
  loading?: boolean;
  onReloadBundle?: () => void | Promise<void>;
  probeWebGL?: () => boolean;
  selectedSemanticRoot?: string | null;
  selectedComponentLabel?: string | null;
  focusSemanticRoots?: readonly string[];
  knownSemanticRoots?: readonly string[];
  onSelectSemanticRoot?: (root: string | null) => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
};

type ViewerHealth =
  | "idle"
  | "loading_glb"
  | "model_loaded"
  | "camera_fitted"
  | "render_visible"
  | "render_blank"
  | "glb_error";

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
  const badges = viewerBadges(bundle).filter((badge) =>
    badge.includes("Fallback") || badge.includes("dégradé") || badge.includes("attention") || badge.includes("rejetée")
  );
  const [resetKey, setResetKey] = useState(0);
  const [cameraScope, setCameraScope] = useState<CameraScope>("initial");
  const [objectSummary, setObjectSummary] = useState<ModelObjectSummary | null>(null);
  const [viewerHealth, setViewerHealth] = useState<ViewerHealth>("idle");
  const [showTechnicalAids, setShowTechnicalAids] = useState(false);
  const [webglSupported, setWebglSupported] = useState<boolean | null>(() =>
    source.kind === "glb" ? probeWebGL() : null
  );
  const sourceIdentity = "url" in source ? `${source.kind}:${source.url}` : source.kind;
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const previousSelectionRef = useRef<string | null>(selectedSemanticRoot);
  const sourceIdentityRef = useRef(sourceIdentity);
  const renderIsBlank = source.kind === "glb" && viewerHealth === "render_blank";
  const retryViewer = () => {
    if (loading) {
      return;
    }
    if (source.kind === "glb") {
      const supported = probeWebGL();
      setWebglSupported(supported);
      if (supported) {
        useGLTF.clear(source.url);
        setViewerHealth("loading_glb");
        setResetKey((value) => value + 1);
      }
      if (loadError) {
        void onReloadBundle?.();
      }
      return;
    }
    void onReloadBundle?.();
  };
  const showWholeDesign = () => {
    onSelectSemanticRoot?.(null);
    setCameraScope("global");
    setResetKey((value) => value + 1);
  };

  useEffect(() => {
    if (sourceIdentityRef.current !== sourceIdentity) {
      sourceIdentityRef.current = sourceIdentity;
      previousSelectionRef.current = selectedSemanticRoot;
      setCameraScope("initial");
    }
  }, [selectedSemanticRoot, sourceIdentity]);

  useEffect(() => {
    if (previousSelectionRef.current && !selectedSemanticRoot) {
      setCameraScope("global");
    }
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
            aria-label={
              showTechnicalAids
                ? "Masquer les aides techniques"
                : "Afficher les aides techniques"
            }
            className={`viewer-aids-toggle${showTechnicalAids ? " active" : ""}`}
            disabled={source.kind !== "glb"}
            onClick={() => setShowTechnicalAids((value) => !value)}
            type="button"
          >
            <Layers3 size={15} aria-hidden="true" /> <span>Aides techniques</span>
          </button>
          {badges.map((badge) => (
            <span className="status-badge" key={badge}>
              {badge}
            </span>
          ))}
        </div>
      </div>

      {source.kind === "empty" && loadError ? (
        <ViewerError busy={loading} message={loadError} previewUrl={null} onRetry={retryViewer} />
      ) : source.kind === "empty" ? (
        loading ? <ViewerEmpty message="Synchronisation du design vérifié…" /> : <ViewerEmpty message={source.message} />
      ) : source.kind === "preview" ? (
        <PreviewFallback busy={loading} url={source.url} message={source.message} onRetry={retryViewer} />
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
                ? "WebGL indisponible dans ce navigateur. Preview backend affichée."
                : "WebGL indisponible et aucune preview backend n'est disponible."}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            />
          ) : renderIsBlank ? (
            <ViewerError
              busy={loading}
              message={source.previewUrl
                ? "GLB chargé mais rendu viewer non visible. Preview backend affichée."
                : "GLB chargé mais rendu viewer non visible, sans preview disponible."}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            />
          ) : (
            <GlbObjectSummary health={viewerHealth} summary={objectSummary} />
          )}
          {webglSupported === false ? null : (
            <GlbErrorBoundary
              key={`${source.url}-${resetKey}`}
              onError={() => setViewerHealth("glb_error")}
              onRetry={retryViewer}
              previewUrl={source.previewUrl}
            >
              <Canvas
                dpr={[1, 1.5]}
                frameloop="demand"
                gl={{ alpha: false, antialias: true }}
                key={resetKey}
                camera={{ fov: 38, position: [42, 20, 46] }}
                style={{ background: "#16242a" }}
                onCreated={({ gl, scene }) => {
                  const background = new Color("#182329");
                  gl.setClearColor(background, 1);
                  gl.outputColorSpace = SRGBColorSpace;
                  gl.toneMapping = ACESFilmicToneMapping;
                  gl.toneMappingExposure = 1.08;
                  scene.background = background;
                }}
              >
                <ambientLight intensity={1.7} />
                <hemisphereLight args={["#f5f9ff", "#4c5f64", 1.3]} />
                <directionalLight position={[22, 42, 26]} intensity={2.4} />
                <Suspense fallback={<ViewerLoading />}>
                  <ModelScene
                    controlsRef={controlsRef}
                    cameraScope={cameraScope}
                    onHealth={setViewerHealth}
                    onLoaded={setObjectSummary}
                    focusSemanticRoots={focusSemanticRoots}
                    knownSemanticRoots={knownSemanticRoots}
                    onSelectSemanticRoot={onSelectSemanticRoot}
                    selectedSemanticRoot={selectedSemanticRoot}
                    showTechnicalAids={showTechnicalAids}
                    url={source.url}
                  />
                </Suspense>
                <RenderHealthProbe
                  enabled={viewerHealth === "camera_fitted"}
                  onResult={(visible) =>
                    setViewerHealth(visible ? "render_visible" : "render_blank")
                  }
                />
                {viewerHealth === "render_visible" && showTechnicalAids ? (
                  <Grid
                    args={[42, 42]}
                    cellColor="#52656d"
                    sectionColor="#7c929a"
                    fadeDistance={80}
                    fadeStrength={1.4}
                    position={[0, -0.04, 0]}
                  />
                ) : null}
                <OrbitControls
                  ref={controlsRef}
                  makeDefault
                  enableDamping
                  maxDistance={500}
                  minDistance={2}
                />
              </Canvas>
            </GlbErrorBoundary>
          )}
        </div>
      )}
    </section>
  );
}

export function PreviewFallback({
  busy = false,
  url,
  message,
  onRetry
}: {
  busy?: boolean;
  url: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="preview-fallback">
      <BackendPreviewImage src={url} />
      <p>
        <ImageIcon size={16} aria-hidden="true" /> {message}
      </p>
      {onRetry ? (
        <button className="viewer-retry" disabled={busy} onClick={onRetry} type="button">
          {busy ? "Resynchronisation…" : "Rechercher le GLB"}
        </button>
      ) : null}
    </div>
  );
}

function ModelScene({
  url,
  controlsRef,
  cameraScope,
  onHealth,
  onLoaded,
  focusSemanticRoots,
  selectedSemanticRoot,
  knownSemanticRoots,
  onSelectSemanticRoot,
  showTechnicalAids
}: {
  url: string;
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
  cameraScope: CameraScope;
  onHealth: (health: ViewerHealth) => void;
  onLoaded: (summary: ModelObjectSummary) => void;
  focusSemanticRoots: readonly string[];
  selectedSemanticRoot: string | null;
  knownSemanticRoots: readonly string[];
  onSelectSemanticRoot?: (root: string | null) => void;
  showTechnicalAids: boolean;
}) {
  const gltf = useGLTF(url);
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);
  const { camera, invalidate, size } = useThree();
  const fitted = useRef(false);
  const selectedBox = useMemo(
    () => semanticSelectionBounds(scene, selectedSemanticRoot),
    [scene, selectedSemanticRoot]
  );
  const focusBox = useMemo(
    () => semanticRootsBounds(scene, focusSemanticRoots),
    [scene, focusSemanticRoots]
  );
  const wholeSiteBox = useMemo(
    () => cameraScope === "global" ? physicalSceneBounds(scene) : null,
    [cameraScope, scene]
  );
  const selectionHelper = useMemo(
    () => selectedBox ? new Box3Helper(selectedBox, new Color("#70e1d2")) : null,
    [selectedBox]
  );
  useEffect(() => () => selectionHelper?.dispose(), [selectionHelper]);
  useEffect(() => {
    prepareViewerScene(scene, showTechnicalAids);
    onLoaded(summarizeObjects(scene));
    fitted.current = false;
    onHealth("model_loaded");
    invalidate();
  }, [invalidate, onHealth, onLoaded, scene, showTechnicalAids, size.height, size.width]);
  useEffect(() => {
    fitted.current = false;
    invalidate();
  }, [cameraScope, focusSemanticRoots, invalidate, selectedSemanticRoot]);
  useFrame(() => {
    if (fitted.current || !controlsRef.current) {
      return;
    }
    fitted.current = true;
    const fit = fitCameraToObject(
      camera as PerspectiveCamera,
      scene,
      controlsRef.current,
      focusBox ?? selectedBox ?? wholeSiteBox ?? undefined
    );
    onHealth(fit ? "camera_fitted" : "glb_error");
  });
  return (
    <>
      <primitive object={scene} onClick={(event: ThreeEvent<MouseEvent>) => {
        // Ignore an aid/unknown foreground hit without selecting equipment behind it.
        event.stopPropagation();
        const root = semanticRootForPick(event.object, knownSemanticRoots, event.delta, event.button);
        if (root && onSelectSemanticRoot) {
          onSelectSemanticRoot(root);
        }
      }} />
      {selectionHelper ? <primitive object={selectionHelper} /> : null}
    </>
  );
}

/** Select only identities published by the backend for this scene. */
export function semanticRootForPick(
  hit: Object3D,
  knownRoots: readonly string[],
  pointerTravel: number,
  button = 0
): string | null {
  if (button !== 0 || !Number.isFinite(pointerTravel) || pointerTravel > 4) return null;
  const ancestors: Object3D[] = [];
  for (let current: Object3D | null = hit; current; current = current.parent) {
    if (!current.visible) return null;
    const role = String(current.userData.role ?? current.userData.object_role ?? "").toLowerCase();
    if (["azimuth_arrow", "beam", "height_marker", "label", "ground", "terrain"].includes(role) ||
      /azimuth_arrow|sector_beam|height_marker|label_|technical_ground_plane/.test(current.name.toLowerCase())) return null;
    ancestors.push(current);
  }
  for (const object of ancestors) {
    const declared = object.userData.semantic_root ?? object.userData.semanticRoot;
    if (typeof declared === "string" && knownRoots.includes(declared)) return declared;
    if (knownRoots.includes(object.name)) return object.name;
  }
  for (const object of ancestors) {
    const matches = knownRoots.filter((root) => root && object.name.startsWith(`${root}_`));
    if (matches.length === 1) return matches[0];
    if (matches.length > 1) return null;
  }
  return null;
}

/** Exported assemblies often carry one identity on many sibling meshes. */
export function semanticSelectionBounds(scene: Object3D, root: string | null): Box3 | null {
  return root ? semanticRootsBounds(scene, [root]) : null;
}

/** Return one camera box for real, published semantic identities only. */
export function semanticRootsBounds(scene: Object3D, roots: readonly string[]): Box3 | null {
  if (!roots.length) return null;
  scene.updateWorldMatrix(true, true);
  const bounds = new Box3();
  scene.traverse((object) => {
    if ((object as Object3D & { isMesh?: boolean }).isMesh &&
      semanticRootForPick(object, roots, 0) !== null) {
      bounds.union(new Box3().setFromObject(object));
    }
  });
  return bounds.isEmpty() ? null : bounds;
}

function ViewerEmpty({ message }: { message: string }) {
  return (
    <div className="viewer-empty">
      <Box size={32} aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

function ViewerError({
  busy = false,
  message,
  onRetry,
  previewUrl
}: {
  busy?: boolean;
  message: string;
  onRetry?: () => void;
  previewUrl: string | null;
}) {
  if (previewUrl) {
    return (
      <div className="viewer-degraded-preview">
        <BackendPreviewImage src={previewUrl} />
        <div className="viewer-state-banner" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>Aperçu backend actif</strong>
            <span>{message}</span>
          </div>
          {onRetry ? (
            <button disabled={busy} onClick={onRetry} type="button">
              {busy ? "Resynchronisation…" : "Réessayer la 3D"}
            </button>
          ) : null}
        </div>
      </div>
    );
  }
  return (
    <div className="viewer-empty viewer-error">
      <AlertTriangle size={32} aria-hidden="true" />
      <p>{message}</p>
      {onRetry ? (
        <button className="viewer-retry" disabled={busy} onClick={onRetry} type="button">
          {busy ? "Resynchronisation…" : "Réessayer"}
        </button>
      ) : null}
    </div>
  );
}

function ViewerLoading() {
  return (
    <Html center>
      <div className="viewer-loading viewer-loading-overlay">
        <Loader2 size={22} aria-hidden="true" />
        <span>Chargement du GLB backend...</span>
      </div>
    </Html>
  );
}

function GlbObjectSummary({
  health,
  summary
}: {
  health: ViewerHealth;
  summary: ModelObjectSummary | null;
}) {
  if (!summary) {
    return null;
  }
  const rows = Object.entries(summary.roles).filter(([, count]) => count > 0);
  return (
    <details className="viewer-object-summary" aria-label="Résumé du modèle 3D">
      <summary>
        <strong>
          <Layers3 size={14} aria-hidden="true" /> Modèle 3D vérifié
        </strong>
        <small>
          {summary.evidenceMode === "semantic_extras"
            ? `${summary.physicalEntityCount} composants physiques${
                summary.technicalAidCount ? ` · ${summary.technicalAidCount} aides d’inspection` : ""
              }`
            : "Structure 3D inspectable"} · {viewerHealthLabel(health)}
        </small>
      </summary>
      <div>
        {rows.map(([role, count]) => (
          <span key={role}>
            {role}: {count}
          </span>
        ))}
      </div>
    </details>
  );
}

function viewerHealthLabel(health: ViewerHealth): string {
  if (health === "render_visible") {
    return "rendu visible";
  }
  if (health === "render_blank") {
    return "preview fallback";
  }
  if (health === "camera_fitted") {
    return "caméra cadrée";
  }
  if (health === "loading_glb") {
    return "chargement";
  }
  return "chargé";
}

type RenderHealthProbeState = {
  frames: number;
  sampled: boolean;
};

const RenderHealthProbeFrameCount = 10;

export function advanceRenderHealthProbe(
  state: RenderHealthProbeState,
  invalidate: () => void,
  sample: () => boolean,
  onResult: (visible: boolean) => void
) {
  if (state.sampled) {
    return;
  }
  state.frames += 1;
  if (state.frames < RenderHealthProbeFrameCount) {
    invalidate();
    return;
  }
  state.sampled = true;
  onResult(sample());
}

function RenderHealthProbe({
  enabled,
  onResult
}: {
  enabled: boolean;
  onResult: (visible: boolean) => void;
}) {
  const { camera, gl, invalidate, scene } = useThree();
  const probe = useRef<RenderHealthProbeState>({ frames: 0, sampled: false });
  useEffect(() => {
    probe.current = { frames: 0, sampled: false };
    if (enabled) {
      invalidate();
    }
  }, [enabled, invalidate]);
  useFrame(() => {
    if (!enabled) {
      return;
    }
    advanceRenderHealthProbe(
      probe.current,
      invalidate,
      () => isRendererVisible(gl, scene, camera),
      onResult
    );
  });
  return null;
}

function isRendererVisible(renderer: WebGLRenderer, scene: Scene, camera: Camera): boolean {
  return probeRenderVisibility(() => sampleRenderer(renderer, scene, camera));
}

function sampleRenderer(renderer: WebGLRenderer, scene: Scene, camera: Camera): RenderSample[] {
  const width = 96;
  const height = 96;
  const target = new WebGLRenderTarget(width, height, { depthBuffer: true });
  const previousTarget = renderer.getRenderTarget();
  const previousClearColor = renderer.getClearColor(new Color()).clone();
  const previousClearAlpha = renderer.getClearAlpha();
  const pixels = new Uint8Array(width * height * 4);
  const samples: RenderSample[] = [];
  try {
    renderer.setRenderTarget(target);
    renderer.setClearColor(new Color("#182329"), 1);
    renderer.clear(true, true, true);
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, width, height, pixels);
    for (let y = 2; y < height; y += 4) {
      for (let x = 2; x < width; x += 4) {
        const offset = (y * width + x) * 4;
        samples.push([
          pixels[offset],
          pixels[offset + 1],
          pixels[offset + 2],
          pixels[offset + 3]
        ]);
      }
    }
  } finally {
    renderer.setRenderTarget(previousTarget);
    renderer.setClearColor(previousClearColor, previousClearAlpha);
    target.dispose();
  }
  return samples;
}

class GlbErrorBoundary extends Component<
  { children: ReactNode; previewUrl: string | null; onError: () => void; onRetry: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    if (this.state.failed) {
      return (
        <ViewerError
          message="Le GLB backend n'a pas pu être chargé; fallback preview affiché."
          onRetry={this.props.onRetry}
          previewUrl={this.props.previewUrl}
        />
      );
    }
    return this.props.children;
  }
}

function BackendPreviewImage({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [src]);
  if (failed) {
    return (
      <div className="preview-image-error" role="status">
        <AlertTriangle size={20} aria-hidden="true" />
        <span>La preview backend n’a pas pu être chargée.</span>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt="Preview du design générée par le backend"
      onError={() => setFailed(true)}
    />
  );
}
