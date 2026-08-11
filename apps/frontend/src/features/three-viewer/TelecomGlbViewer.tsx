import { Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AlertTriangle, Box, Image as ImageIcon, Layers3, Loader2, RotateCcw } from "lucide-react";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { ACESFilmicToneMapping, BoxHelper, Color, SRGBColorSpace, WebGLRenderTarget } from "three";
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
  prepareViewerScene,
  probeRenderVisibility,
  summarizeObjects,
  type ModelObjectSummary,
  type RenderSample
} from "./viewerMath";

type TelecomGlbViewerProps = {
  bundle: ViewerBundle | null;
  loadError?: string | null;
  loading?: boolean;
  onReloadBundle?: () => void | Promise<void>;
  probeWebGL?: () => boolean;
  selectedSemanticRoot?: string | null;
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
  toAbsoluteUrl
}: TelecomGlbViewerProps) {
  const source = resolveViewerSource(bundle, toAbsoluteUrl);
  const badges = viewerBadges(bundle).filter((badge) =>
    badge.includes("Fallback") || badge.includes("dégradé") || badge.includes("attention") || badge.includes("rejetée")
  );
  const [resetKey, setResetKey] = useState(0);
  const [objectSummary, setObjectSummary] = useState<ModelObjectSummary | null>(null);
  const [viewerHealth, setViewerHealth] = useState<ViewerHealth>("idle");
  const [showTechnicalAids, setShowTechnicalAids] = useState(false);
  const [webglSupported, setWebglSupported] = useState<boolean | null>(() =>
    source.kind === "glb" ? probeWebGL() : null
  );
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const sourceIdentity = "url" in source ? `${source.kind}:${source.url}` : source.kind;
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
          <button
            className="icon-action"
            disabled={source.kind !== "glb"}
            onClick={() => setResetKey((value) => value + 1)}
            aria-label="Recentrer la caméra 3D"
            title="Recentrer la caméra"
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
              <Layers3 size={15} aria-hidden="true" /> Composant sélectionné : {humanizeSemanticRoot(selectedSemanticRoot)}
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
                    onHealth={setViewerHealth}
                    onLoaded={setObjectSummary}
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
  onHealth,
  onLoaded,
  selectedSemanticRoot,
  showTechnicalAids
}: {
  url: string;
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
  onHealth: (health: ViewerHealth) => void;
  onLoaded: (summary: ModelObjectSummary) => void;
  selectedSemanticRoot: string | null;
  showTechnicalAids: boolean;
}) {
  const gltf = useGLTF(url);
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);
  const { camera, invalidate, size } = useThree();
  const fitted = useRef(false);
  const selectedObject = useMemo(
    () => findSemanticObject(scene, selectedSemanticRoot),
    [scene, selectedSemanticRoot]
  );
  const selectionHelper = useMemo(
    () => selectedObject ? new BoxHelper(selectedObject, new Color("#70e1d2")) : null,
    [selectedObject]
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
  }, [selectedSemanticRoot]);
  useFrame(() => {
    if (fitted.current || !controlsRef.current) {
      return;
    }
    fitted.current = true;
    const fit = fitCameraToObject(
      camera as PerspectiveCamera,
      selectedObject ?? scene,
      controlsRef.current
    );
    selectionHelper?.update();
    onHealth(fit ? "camera_fitted" : "glb_error");
  });
  return (
    <>
      <primitive object={scene} />
      {selectionHelper ? <primitive object={selectionHelper} /> : null}
    </>
  );
}

export function findSemanticObject(scene: Object3D, semanticRoot: string | null): Object3D | null {
  if (!semanticRoot) return null;
  let prefixMatch: Object3D | null = null;
  let exactMatch: Object3D | null = null;
  scene.traverse((object) => {
    const declaredRoot = object.userData.semantic_root ?? object.userData.semanticRoot;
    if (!exactMatch && (object.name === semanticRoot || declaredRoot === semanticRoot)) {
      exactMatch = object;
    }
    if (!prefixMatch && object.name.startsWith(`${semanticRoot}_`)) {
      prefixMatch = object;
    }
  });
  return exactMatch ?? prefixMatch;
}

function humanizeSemanticRoot(value: string): string {
  return value.replaceAll("_", " ");
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
