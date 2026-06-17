import { Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AlertTriangle, Box, Image as ImageIcon, Layers3, Loader2, RotateCcw } from "lucide-react";
import { Component, Suspense, useEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { Color } from "three";
import type { PerspectiveCamera, WebGLRenderer } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { ViewerBundle } from "../../api/schemas";
import {
  hasUsableWebGL,
  resolveViewerSource,
  viewerBadges
} from "./viewerRules";
import {
  enhanceViewerMaterials,
  fitCameraToObject,
  isRenderVisiblyDifferent,
  summarizeObjects,
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
  const sourceIdentity = source.kind === "glb" ? source.url : source.kind;
  const blankPreviewUrl =
    source.kind === "glb" && viewerHealth === "render_blank" ? source.previewUrl : null;

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
          {source.previewUrl && objectSummary && webglSupported !== false && !blankPreviewUrl ? (
            <BackendPreviewCompanion url={source.previewUrl} />
          ) : null}
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
          ) : blankPreviewUrl ? (
            <PreviewVisibilityFallback
              message="GLB chargé mais rendu viewer non visible. Preview backend affichée."
              url={blankPreviewUrl}
            />
          ) : (
            <GlbObjectSummary health={viewerHealth} summary={objectSummary} />
          )}
          {webglSupported === false ? null : (
            <GlbErrorBoundary key={`${source.url}-${resetKey}`} previewUrl={source.previewUrl}>
              <Suspense fallback={<ViewerLoading />}>
                <Canvas
                  dpr={[1, 2]}
                  gl={{ alpha: true, antialias: true, preserveDrawingBuffer: true }}
                  key={resetKey}
                  camera={{ fov: 38, position: [42, 20, 46] }}
                  style={{ background: "#16242a" }}
                  onCreated={({ gl, scene }) => {
                    const background = new Color("#182329");
                    gl.setClearColor(background, 0);
                    scene.background = null;
                  }}
                >
                  <fog attach="fog" args={["#182329", 85, 190]} />
                  <ambientLight intensity={1.7} />
                  <hemisphereLight args={["#f5f9ff", "#4c5f64", 1.3]} />
                  <directionalLight position={[22, 42, 26]} intensity={2.4} />
                  <ModelScene
                    controlsRef={controlsRef}
                    onHealth={setViewerHealth}
                    onLoaded={setObjectSummary}
                    url={source.url}
                  />
                  <RenderHealthProbe
                    enabled={viewerHealth === "camera_fitted"}
                    onResult={(visible) =>
                      setViewerHealth(visible ? "render_visible" : "render_blank")
                    }
                  />
                  <Grid
                    args={[42, 42]}
                    cellColor="#52656d"
                    sectionColor="#7c929a"
                    fadeDistance={80}
                    fadeStrength={1.4}
                    position={[0, -0.04, 0]}
                  />
                  <OrbitControls
                    ref={controlsRef}
                    makeDefault
                    enableDamping
                    maxDistance={160}
                    minDistance={5}
                  />
                </Canvas>
              </Suspense>
            </GlbErrorBoundary>
          )}
        </div>
      )}
    </section>
  );
}

export type ModelObjectSummary = {
  totalNamedObjects: number;
  roles: Record<string, number>;
};

export function PreviewFallback({ url, message }: { url: string; message: string }) {
  return (
    <div className="preview-fallback">
      <img src={url} alt="Backend generated preview" />
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
  const { camera } = useThree();
  useEffect(() => {
    enhanceViewerMaterials(gltf.scene);
    onLoaded(summarizeObjects(gltf.scene));
    const fit = fitCameraToObject(camera as PerspectiveCamera, gltf.scene, controlsRef.current);
    onHealth(fit ? "camera_fitted" : "model_loaded");
  }, [camera, controlsRef, gltf.scene, onHealth, onLoaded]);
  return <primitive object={gltf.scene} />;
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
      {previewUrl ? <img src={previewUrl} alt="Backend preview fallback" /> : null}
    </div>
  );
}

function ViewerLoading() {
  return (
    <div className="viewer-loading">
      <Loader2 size={22} aria-hidden="true" />
      <span>Chargement du GLB backend...</span>
    </div>
  );
}

function PreviewVisibilityFallback({ message, url }: { message: string; url: string }) {
  return (
    <div className="viewer-preview-overlay">
      <img src={url} alt="Backend preview because the GLB render is not visible" />
      <p>
        <AlertTriangle size={16} aria-hidden="true" />
        {message}
      </p>
    </div>
  );
}

function BackendPreviewCompanion({ url }: { url: string }) {
  return (
    <div className="viewer-preview-companion">
      <img src={url} alt="Backend verified preview of the generated telecom design" />
      <span>Preview backend vérifiée · GLB interactif chargé</span>
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
        {summary.totalNamedObjects} objets nommés · {viewerHealthLabel(health)}
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
  const { gl } = useThree();
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
    onResult(isRendererVisible(gl));
  });
  return null;
}

function isRendererVisible(renderer: WebGLRenderer): boolean {
  try {
    return isRenderVisiblyDifferent(sampleRenderer(renderer));
  } catch {
    return true;
  }
}

function sampleRenderer(renderer: WebGLRenderer): RenderSample[] {
  const context = renderer.getContext();
  const width = renderer.domElement.width;
  const height = renderer.domElement.height;
  const samples: RenderSample[] = [];
  const pixel = new Uint8Array(4);
  for (const xRatio of [0.18, 0.3, 0.42, 0.5, 0.58, 0.7, 0.82]) {
    for (const yRatio of [0.14, 0.26, 0.38, 0.5, 0.62, 0.74, 0.86]) {
      context.readPixels(
        Math.floor(width * xRatio),
        Math.floor(height * yRatio),
        1,
        1,
        context.RGBA,
        context.UNSIGNED_BYTE,
        pixel
      );
      samples.push([pixel[0], pixel[1], pixel[2], pixel[3]]);
    }
  }
  return samples;
}

class GlbErrorBoundary extends Component<
  { children: ReactNode; previewUrl: string | null },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
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
