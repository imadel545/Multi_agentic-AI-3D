import { Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, type MutableRefObject } from "react";
import {
  ACESFilmicToneMapping,
  Box3Helper,
  Color,
  SRGBColorSpace,
  WebGLRenderTarget
} from "three";
import type { Camera, PerspectiveCamera, Scene, WebGLRenderer } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import {
  fitCameraToObject,
  physicalSceneBounds,
  prepareViewerScene,
  probeRenderVisibility,
  summarizeObjects,
  type ModelObjectSummary,
  type RenderSample
} from "./viewerMath";
import {
  semanticRootForPick,
  semanticRootsBounds,
  semanticSelectionBounds
} from "./viewerSelection";
import { GlbErrorBoundary, ViewerLoading } from "./ViewerStates";
import type { CameraScope, ViewerHealth } from "./viewerTypes";

type TelecomCanvasProps = {
  cameraScope: CameraScope;
  focusSemanticRoots: readonly string[];
  cameraFitRequest: number;
  knownSemanticRoots: readonly string[];
  onHealth: (health: ViewerHealth) => void;
  onLoaded: (summary: ModelObjectSummary) => void;
  onRetry: () => void;
  onSelectSemanticRoot?: (root: string | null) => void;
  previewUrl: string | null;
  resetKey: number;
  selectedSemanticRoot: string | null;
  showTechnicalAids: boolean;
  url: string;
  viewerHealth: ViewerHealth;
};

export function TelecomCanvas({
  cameraScope,
  cameraFitRequest,
  focusSemanticRoots,
  knownSemanticRoots,
  onHealth,
  onLoaded,
  onRetry,
  onSelectSemanticRoot,
  previewUrl,
  resetKey,
  selectedSemanticRoot,
  showTechnicalAids,
  url,
  viewerHealth
}: TelecomCanvasProps) {
  const controlsRef = useRef<OrbitControlsImpl | null>(null);

  return (
    <GlbErrorBoundary
      key={`${url}-${resetKey}`}
      onError={() => onHealth("glb_error")}
      onRetry={onRetry}
      previewUrl={previewUrl}
    >
      <Canvas
        dpr={[1, 1.5]}
        frameloop="demand"
        gl={{ alpha: false, antialias: true }}
        key={resetKey}
        camera={{ fov: 38, position: [42, 20, 46] }}
        style={{ background: "#16242a" }}
        onCreated={({ gl, scene }) => configureRenderer(gl, scene)}
      >
        <ambientLight intensity={1.7} />
        <hemisphereLight args={["#f5f9ff", "#4c5f64", 1.3]} />
        <directionalLight position={[22, 42, 26]} intensity={2.4} />
        <Suspense fallback={<ViewerLoading />}>
          <ModelScene
            controlsRef={controlsRef}
            cameraScope={cameraScope}
            cameraFitRequest={cameraFitRequest}
            onHealth={onHealth}
            onLoaded={onLoaded}
            focusSemanticRoots={focusSemanticRoots}
            knownSemanticRoots={knownSemanticRoots}
            onSelectSemanticRoot={onSelectSemanticRoot}
            selectedSemanticRoot={selectedSemanticRoot}
            showTechnicalAids={showTechnicalAids}
            url={url}
          />
        </Suspense>
        <RenderHealthProbe
          enabled={viewerHealth === "camera_fitted"}
          onResult={(visible) => onHealth(visible ? "render_visible" : "render_blank")}
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
  );
}

function configureRenderer(renderer: WebGLRenderer, scene: Scene) {
  const background = new Color("#182329");
  renderer.setClearColor(background, 1);
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  scene.background = background;
}

function ModelScene({
  url,
  controlsRef,
  cameraScope,
  cameraFitRequest,
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
  cameraFitRequest: number;
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
  }, [cameraFitRequest, cameraScope, focusSemanticRoots, invalidate, selectedSemanticRoot]);

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
    onHealth(fit ? "camera_fitted" : "camera_fit_error");
  });

  return (
    <>
      <primitive
        object={scene}
        onClick={(event: ThreeEvent<MouseEvent>) => {
          event.stopPropagation();
          const root = semanticRootForPick(
            event.object,
            knownSemanticRoots,
            event.delta,
            event.button
          );
          if (root && onSelectSemanticRoot) {
            onSelectSemanticRoot(root);
          }
        }}
      />
      {selectionHelper ? <primitive object={selectionHelper} /> : null}
    </>
  );
}

export type RenderHealthProbeState = {
  frames: number;
  sampled: boolean;
};

const RENDER_HEALTH_PROBE_FRAME_COUNT = 10;

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
  if (state.frames < RENDER_HEALTH_PROBE_FRAME_COUNT) {
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
