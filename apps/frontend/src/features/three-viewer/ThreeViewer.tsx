import { Environment, Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Box, Cable, Crosshair, LocateFixed, Radar, RotateCcw, SatelliteDish } from "lucide-react";
import { Component, Suspense, useEffect, useMemo, type ReactNode } from "react";
import { Box3, Group, Vector3 } from "three";
import type { Material, Mesh, Object3D } from "three";

import { artifactUrl, useArtifactJson } from "../../api/hooks";
import type { AssetImportRecord, WorkflowStatus } from "../../api/types";
import { Badge, StatusBadge } from "../../components/Badge";
import { ActionButton, EmptyState } from "../../components/Primitives";
import { useStudioStore, type ViewerFocus } from "../../stores/studioStore";

type ThreeViewerProps = {
  workflow?: WorkflowStatus;
};

type SceneMetadata = {
  generation_mode?: string;
  assets_used?: string[];
  procedural_objects_created?: string[];
  asset_imports?: AssetImportRecord[];
  [key: string]: unknown;
};

const focusButtons: Array<{ focus: ViewerFocus; label: string; icon: typeof LocateFixed }> = [
  { focus: "fit", label: "Fit", icon: LocateFixed },
  { focus: "tower", label: "Tower", icon: Radar },
  { focus: "sectors", label: "Sectors", icon: Crosshair },
  { focus: "accessories", label: "GPS / cabinet", icon: SatelliteDish },
  { focus: "reset", label: "Reset", icon: RotateCcw },
];

export function ThreeViewer({ workflow }: ThreeViewerProps) {
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const selectedObject = useStudioStore((state) => state.selectedObject);
  const setSelectedObject = useStudioStore((state) => state.setSelectedObject);
  const viewerFocus = useStudioStore((state) => state.viewerFocus);
  const setViewerFocus = useStudioStore((state) => state.setViewerFocus);
  const toggles = useStudioStore((state) => state.viewerToggles);
  const toggleViewerLayer = useStudioStore((state) => state.toggleViewerLayer);
  const activeVersionId = selectedVersionId ?? workflow?.active_version_id ?? workflow?.version_id;
  const glbUrl = artifactUrl(workflow?.workflow_id, "glb", activeVersionId);
  const previewUrl = artifactUrl(workflow?.workflow_id, "preview", activeVersionId);
  const metadata = useArtifactJson<SceneMetadata>(workflow?.workflow_id, "metadata", activeVersionId);
  const imports = metadata.data?.asset_imports ?? workflow?.asset_imports ?? [];
  const qualityNotice = buildAssetNotice(imports, workflow);

  return (
    <main className="viewer-shell design-stage">
      <div className="viewer-stage-header">
        <div className="viewer-title">
          <Box size={18} />
          <div>
            <span>3D Design Stage</span>
            <strong>{workflow?.generation_mode ?? "waiting for real GLB"}</strong>
          </div>
        </div>
        <div className="viewer-focus-actions">
          {focusButtons.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={viewerFocus === item.focus ? "tool active" : "tool"}
                key={item.focus}
                type="button"
                onClick={() => setViewerFocus(item.focus)}
                title={`Camera ${item.label}`}
              >
                <Icon size={14} />
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="viewer-canvas-frame">
        {qualityNotice ? <div className="asset-quality-banner">{qualityNotice}</div> : null}
        {previewUrl ? (
          <a className="stage-preview-card" href={previewUrl} target="_blank" rel="noreferrer">
            <span>Real Blender preview artifact · zoomed</span>
            <img src={previewUrl} alt="Real Blender preview artifact" />
          </a>
        ) : null}
        <div className="viewer-overlay-tools">
          {(["beams", "cables", "labels", "boundingBoxes", "sectors"] as const).map((layer) => (
            <button
              className={toggles[layer] ? "tool active" : "tool"}
              key={layer}
              type="button"
              onClick={() => toggleViewerLayer(layer)}
              title={`Toggle ${layer}`}
            >
              {layer === "cables" ? <Cable size={14} /> : <Crosshair size={14} />}
              {layer}
            </button>
          ))}
        </div>

        {glbUrl ? (
          <ViewerErrorBoundary resetKey={glbUrl}>
            <Canvas
              camera={{ position: [14, -18, 12], fov: 28, near: 0.1, far: 1000 }}
              gl={{ antialias: true, preserveDrawingBuffer: true }}
              shadows
              dpr={[1, 1.6]}
            >
              <color attach="background" args={["#081018"]} />
              <fog attach="fog" args={["#081018", 24, 64]} />
              <ambientLight intensity={1.55} />
              <hemisphereLight args={["#ecfbff", "#15242b", 1.8]} />
              <directionalLight position={[10, -12, 16]} intensity={3.8} castShadow />
              <directionalLight position={[-9, 10, 12]} intensity={1.5} />
              <Suspense fallback={null}>
                <CameraPreset focus={viewerFocus} />
                <SceneModel
                  url={glbUrl}
                  toggles={toggles}
                  onSelect={(name) => setSelectedObject(name)}
                />
                <Grid
                  args={[34, 34]}
                  cellColor="#15313d"
                  sectionColor="#2a7084"
                  fadeDistance={34}
                  fadeStrength={1.8}
                  position={[0, -12.8, 0]}
                />
                <Environment preset="city" />
              </Suspense>
              <OrbitControls
                makeDefault
                target={[0, 0, 0]}
                minDistance={4}
                maxDistance={54}
                enableDamping
                dampingFactor={0.08}
              />
            </Canvas>
          </ViewerErrorBoundary>
        ) : (
          <EmptyState
            title="No GLB loaded"
            description="Generate a design or select a completed workflow to load the real Blender artifact."
          />
        )}

        <SceneObjectRail imports={imports} selectedObject={selectedObject} onSelect={setSelectedObject} />
      </div>

      <div className="selection-strip">
        <span>Selected object</span>
        <strong>{selectedObject ?? "none"}</strong>
        <span>Active version</span>
        <strong>{activeVersionId ?? "active root"}</strong>
        <span>Imports</span>
        <strong>{imports.length || Number(workflow?.asset_import_summary?.asset_count ?? 0)}</strong>
      </div>
    </main>
  );
}

class ViewerErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { error: Error | null }
> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="viewer-empty">
          <Box size={34} />
          <strong>GLB artifact unavailable</strong>
          <p>The selected workflow does not expose a readable GLB artifact.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

type SceneModelProps = {
  url: string;
  toggles: {
    beams: boolean;
    cables: boolean;
    labels: boolean;
    boundingBoxes: boolean;
    sectors: boolean;
  };
  onSelect: (name: string) => void;
};

function SceneModel({ url, toggles, onSelect }: SceneModelProps) {
  const gltf = useGLTF(url);
  const { group, framedScene } = useMemo(() => {
    const scene = gltf.scene.clone(true);
    const frame = new Group();
    frame.add(scene);
    const box = new Box3().setFromObject(scene);
    const size = box.getSize(new Vector3());
    const center = box.getCenter(new Vector3());
    const dominantVertical = Math.max(size.y, size.z, 1);
    const broadAxis = Math.max(size.x, size.y, size.z, 1);
    const scale = Math.min(26 / dominantVertical, 22 / broadAxis);
    scene.position.set(-center.x, -center.y, -center.z);
    frame.scale.setScalar(scale);
    return { group: frame, framedScene: scene };
  }, [gltf.scene]);

  useEffect(() => {
    framedScene.traverse((object: Object3D) => {
      const name = object.name.toLowerCase();
      if (name.includes("beam")) object.visible = toggles.beams;
      if (name.includes("cable")) object.visible = toggles.cables;
      if (name.includes("label")) object.visible = toggles.labels;
      if (name.includes("sector")) object.visible = toggles.sectors;
      if (name.includes("bounding")) object.visible = toggles.boundingBoxes;
      const mesh = object as Mesh;
      if (mesh.isMesh && mesh.material) {
        normalizeMaterial(mesh.material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
  }, [framedScene, toggles]);

  return (
    <primitive
      object={group}
      onClick={(event: { stopPropagation: () => void; object: Object3D }) => {
        event.stopPropagation();
        onSelect(event.object.name || event.object.parent?.name || "unnamed_object");
      }}
    />
  );
}

function normalizeMaterial(material: Material | Material[]) {
  const materials = Array.isArray(material) ? material : [material];
  for (const item of materials) {
    const editable = item as Material & {
      color?: { r: number; g: number; b: number; setRGB: (r: number, g: number, b: number) => void };
      metalness?: number;
      roughness?: number;
      needsUpdate?: boolean;
    };
    if (editable.color) {
      const luminance = editable.color.r + editable.color.g + editable.color.b;
      if (luminance < 0.36) {
        editable.color.setRGB(0.54, 0.61, 0.64);
      }
    }
    if (typeof editable.metalness === "number") editable.metalness = Math.min(editable.metalness, 0.22);
    if (typeof editable.roughness === "number") editable.roughness = Math.max(editable.roughness, 0.34);
    editable.needsUpdate = true;
  }
}

function CameraPreset({ focus }: { focus: ViewerFocus }) {
  const camera = useThree((state) => state.camera);
  useEffect(() => {
    const presets: Record<ViewerFocus, { position: [number, number, number]; target: [number, number, number] }> = {
      fit: { position: [13, -18, 13], target: [0, 0, 0] },
      tower: { position: [8, -13, 10], target: [0, 0, 2] },
      sectors: { position: [6, -9, 8.5], target: [0, 0, 5] },
      accessories: { position: [14, -15, 5.5], target: [0, 0, -2] },
      reset: { position: [14, -18, 12], target: [0, 0, 0] },
    };
    const preset = presets[focus];
    camera.position.set(...preset.position);
    camera.lookAt(...preset.target);
    camera.updateProjectionMatrix();
  }, [camera, focus]);
  return null;
}

function SceneObjectRail({
  imports,
  selectedObject,
  onSelect,
}: {
  imports: AssetImportRecord[];
  selectedObject?: string;
  onSelect: (objectName?: string) => void;
}) {
  if (!imports.length) return null;
  return (
    <aside className="scene-object-rail">
      <header>
        <span>Scene objects</span>
        <Badge tone="idle">{imports.length}</Badge>
      </header>
      <div>
        {imports.slice(0, 12).map((record, index) => {
          const objectName = String(record.object_name ?? record.asset_id ?? `object_${index}`);
          return (
            <button
              className={selectedObject === objectName ? "active" : ""}
              key={`${objectName}-${index}`}
              type="button"
              onClick={() => onSelect(objectName)}
            >
              <span>{objectName}</span>
              <StatusBadge status={record.import_mode} />
            </button>
          );
        })}
      </div>
      <ActionButton variant="ghost" onClick={() => onSelect(undefined)}>
        Clear selection
      </ActionButton>
    </aside>
  );
}

function buildAssetNotice(imports: AssetImportRecord[], workflow?: WorkflowStatus) {
  const fallbackCount =
    Number(workflow?.asset_import_summary?.procedural_fallback_count ?? 0) ||
    imports.filter((item) => item.import_mode === "procedural_fallback").length;
  const internalCount = imports.filter((item) =>
    (item.warnings ?? []).some((warning) => String(warning).includes("NOT_VENDOR_GRADE")),
  ).length;
  if (fallbackCount > 0) {
    return `${fallbackCount} object(s) use explicit procedural fallback. The scene is real, but not fully vendor-asset backed.`;
  }
  if (internalCount > 0) {
    return `${internalCount} imported GLB object(s) are internal/minimal or non-vendor-grade.`;
  }
  return undefined;
}
