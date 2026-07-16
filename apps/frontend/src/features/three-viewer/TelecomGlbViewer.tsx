import { Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AlertTriangle, Box, Image as ImageIcon, Layers3, Loader2, RotateCcw } from "lucide-react";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { ACESFilmicToneMapping, Color, SRGBColorSpace, WebGLRenderTarget } from "three";
import type { Camera, PerspectiveCamera, Scene, WebGLRenderer } from "three";
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

export function TelecomGlbViewer({ bundle, toAbsoluteUrl }: TelecomGlbViewerProps) {
  const source = resolveViewerSource(bundle, toAbsoluteUrl);
  const badges = viewerBadges(bundle);
  const [resetKey, setResetKey] = useState(0);
  const [objectSummary, setObjectSummary] = useState<ModelObjectSummary | null>(null);
  const [viewerHealth, setViewerHealth] = useState<ViewerHealth>("idle");
  const [webglSupported, setWebglSupported] = useState<boolean | null>(null);
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const sourceIdentity = "url" in source ? `${source.kind}:${source.url}` : source.kind;
  const renderIsBlank = source.kind === "glb" && viewerHealth === "render_blank";

  useEffect(() => {
    setObjectSummary(null);
    setViewerHealth(source.kind === "glb" ? "loading_glb" : "idle");
    setWebglSupported(source.kind === "glb" ? hasUsableWebGL() : null);
  }, [sourceIdentity]);

  return (
    <section className="viewer-shell" aria-label="3D viewer">
      <div className="viewer-toolbar">
        <div>
          <span className="eyebrow">Viewer 3D</span>
          <h2>{bundle ? "Design 3D telecom" : "En attente d'un design"}</h2>
          {bundle ? <small>{bundle.workflow_id}</small> : null}
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
          {badges.map((badge) => (
            <span className="status-badge" key={badge}>
              {badge}
            </span>
          ))}
        </div>
      </div>

      {source.kind === "empty" ? (
        <ViewerEmpty message={source.message} />
      ) : source.kind === "preview" ? (
        <PreviewFallback url={source.url} message={source.message} />
      ) : source.kind === "error" ? (
        <ViewerError message={source.message} previewUrl={source.previewUrl} />
      ) : (
        <div className="canvas-frame">
          {webglSupported === false ? (
            source.previewUrl ? (
              <PreviewVisibilityFallback
                message="WebGL indisponible dans ce navigateur. Preview backend affichée."
                url={source.previewUrl}
              />
            ) : (
              <ViewerError
                message="WebGL indisponible et aucune preview backend n'est disponible."
                previewUrl={null}
              />
            )
          ) : renderIsBlank ? (
            source.previewUrl ? (
              <PreviewVisibilityFallback
                message="GLB chargé mais rendu viewer non visible. Preview backend affichée."
                url={source.previewUrl}
              />
            ) : (
              <ViewerError
                message="GLB chargé mais rendu viewer non visible, sans preview disponible."
                previewUrl={null}
              />
            )
          ) : (
            <GlbObjectSummary health={viewerHealth} summary={objectSummary} />
          )}
          {webglSupported === false ? null : (
            <GlbErrorBoundary
              key={`${source.url}-${resetKey}`}
              onError={() => setViewerHealth("glb_error")}
              previewUrl={source.previewUrl}
            >
              <Canvas
                dpr={[1, 1.5]}
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
                <fog attach="fog" args={["#182329", 85, 190]} />
                <ambientLight intensity={1.7} />
                <hemisphereLight args={["#f5f9ff", "#4c5f64", 1.3]} />
                <directionalLight position={[22, 42, 26]} intensity={2.4} />
                <Suspense fallback={<ViewerLoading />}>
                  <ModelScene
                    controlsRef={controlsRef}
                    onHealth={setViewerHealth}
                    onLoaded={setObjectSummary}
                    url={source.url}
                  />
                </Suspense>
                <RenderHealthProbe
                  enabled={viewerHealth === "camera_fitted"}
                  onResult={(visible) =>
                    setViewerHealth(visible ? "render_visible" : "render_blank")
                  }
                />
                {viewerHealth === "render_visible" ? (
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

export function PreviewFallback({ url, message }: { url: string; message: string }) {
  return (
    <div className="preview-fallback">
      <BackendPreviewImage src={url} />
      <p>
        <ImageIcon size={16} aria-hidden="true" /> {message}
      </p>
    </div>
  );
}

function ModelScene({
  url,
  controlsRef,
  onHealth,
  onLoaded
}: {
  url: string;
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
  onHealth: (health: ViewerHealth) => void;
  onLoaded: (summary: ModelObjectSummary) => void;
}) {
  const gltf = useGLTF(url);
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);
  const { camera, size } = useThree();
  const fitted = useRef(false);
  useEffect(() => {
    prepareViewerScene(scene);
    onLoaded(summarizeObjects(scene));
    fitted.current = false;
    onHealth("model_loaded");
  }, [onHealth, onLoaded, scene, size.height, size.width]);
  useFrame(() => {
    if (fitted.current || !controlsRef.current) {
      return;
    }
    fitted.current = true;
    const fit = fitCameraToObject(camera as PerspectiveCamera, scene, controlsRef.current);
    onHealth(fit ? "camera_fitted" : "glb_error");
  });
  return <primitive object={scene} />;
}

function ViewerEmpty({ message }: { message: string }) {
  return (
    <div className="viewer-empty">
      <Box size={32} aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

function ViewerError({ message, previewUrl }: { message: string; previewUrl: string | null }) {
  return (
    <div className="viewer-empty viewer-error">
      <AlertTriangle size={32} aria-hidden="true" />
      <p>{message}</p>
      {previewUrl ? <BackendPreviewImage src={previewUrl} /> : null}
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

function PreviewVisibilityFallback({ message, url }: { message: string; url: string }) {
  return (
    <div className="viewer-preview-overlay">
      <BackendPreviewImage src={url} />
      <p>
        <AlertTriangle size={16} aria-hidden="true" />
        {message}
      </p>
    </div>
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
    <div className="viewer-object-summary" aria-label="GLB object summary">
      <strong>
        <Layers3 size={14} aria-hidden="true" /> Scène GLB réelle
      </strong>
      <small>
        {summary.evidenceMode === "semantic_extras"
          ? `${summary.semanticEntityCount} équipements vérifiables dans ${summary.totalNamedObjects} nœuds GLB`
          : `${summary.totalNamedObjects} nœuds GLB · comptage hérité par nom`} · {viewerHealthLabel(health)}
      </small>
      <div>
        {rows.map(([role, count]) => (
          <span key={role}>
            {role}: {count}
          </span>
        ))}
      </div>
    </div>
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

function RenderHealthProbe({
  enabled,
  onResult
}: {
  enabled: boolean;
  onResult: (visible: boolean) => void;
}) {
  const { camera, gl, scene } = useThree();
  const frames = useRef(0);
  const sampled = useRef(false);
  useEffect(() => {
    if (!enabled) {
      frames.current = 0;
      sampled.current = false;
    }
  }, [enabled]);
  useFrame(() => {
    if (!enabled || sampled.current) {
      return;
    }
    frames.current += 1;
    if (frames.current < 10) {
      return;
    }
    sampled.current = true;
    onResult(isRendererVisible(gl, scene, camera));
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
  { children: ReactNode; previewUrl: string | null; onError: () => void },
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
          previewUrl={this.props.previewUrl}
        />
      );
    }
    return this.props.children;
  }
}

function BackendPreviewImage({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
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
