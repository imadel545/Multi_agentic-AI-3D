import { Environment, Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Box, Cable, Crosshair, RotateCcw } from "lucide-react";
import { Suspense, useEffect, useMemo } from "react";
import { Box3, Group, Vector3 } from "three";
import type { Material, Mesh, Object3D } from "three";

import { artifactUrl } from "../../api/hooks";
import type { WorkflowStatus } from "../../api/types";
import { Badge } from "../../components/Badge";
import { useStudioStore } from "../../stores/studioStore";

type ThreeViewerProps = {
  workflow?: WorkflowStatus;
};

export function ThreeViewer({ workflow }: ThreeViewerProps) {
  const selectedVersionId = useStudioStore((state) => state.selectedVersionId);
  const selectedObject = useStudioStore((state) => state.selectedObject);
  const setSelectedObject = useStudioStore((state) => state.setSelectedObject);
  const toggles = useStudioStore((state) => state.viewerToggles);
  const toggleViewerLayer = useStudioStore((state) => state.toggleViewerLayer);
  const glbUrl = artifactUrl(workflow?.workflow_id, "glb", selectedVersionId);

  return (
    <main className="viewer-shell">
      <div className="viewer-toolbar">
        <div className="viewer-title">
          <Box size={17} />
          <span>GLB Scene Viewer</span>
          <Badge tone={glbUrl ? "good" : "idle"}>{workflow?.generation_mode ?? "waiting"}</Badge>
        </div>
        <div className="tool-group">
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
          <button className="tool" type="button" onClick={() => setSelectedObject(undefined)}>
            <RotateCcw size={14} />
            clear
          </button>
        </div>
      </div>

      <div className="viewer-canvas-frame">
        {glbUrl ? (
          <Canvas camera={{ position: [14, -18, 12], fov: 46 }} shadows>
            <color attach="background" args={["#111820"]} />
            <ambientLight intensity={1.4} />
            <hemisphereLight args={["#dff8ff", "#1c2a31", 1.6]} />
            <directionalLight position={[8, -8, 14]} intensity={3.2} />
            <directionalLight position={[-6, 8, 10]} intensity={1.6} />
            <Suspense fallback={<Loading3D />}>
              <CameraAim />
              <SceneModel
                url={glbUrl}
                toggles={toggles}
                onSelect={(name) => setSelectedObject(name)}
              />
              <Grid
                args={[42, 42]}
                cellColor="#26313a"
                sectionColor="#376572"
                fadeDistance={42}
                position={[0, -4.6, 0]}
              />
              <Environment preset="city" />
            </Suspense>
            <OrbitControls makeDefault target={[0, 0, 0]} />
          </Canvas>
        ) : (
          <div className="viewer-empty">
            <Box size={34} />
            <strong>No GLB loaded</strong>
            <p>Generate a design or select a completed workflow to load the real artifact.</p>
          </div>
        )}
      </div>

      <div className="selection-strip">
        <span>Selected object</span>
        <strong>{selectedObject ?? "none"}</strong>
        <span>Active version</span>
        <strong>{selectedVersionId ?? workflow?.active_version_id ?? "active root"}</strong>
      </div>
    </main>
  );
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
    const maxAxis = Math.max(size.x, size.y, size.z, 1);
    const scale = 5.8 / maxAxis;
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
      if (luminance < 0.42) {
        editable.color.setRGB(0.42, 0.48, 0.5);
      }
    }
    if (typeof editable.metalness === "number") editable.metalness = Math.min(editable.metalness, 0.25);
    if (typeof editable.roughness === "number") editable.roughness = Math.max(editable.roughness, 0.38);
    editable.needsUpdate = true;
  }
}

function Loading3D() {
  return (
    <Html center>
      <div className="viewer-loading">Loading GLB...</div>
    </Html>
  );
}

function CameraAim() {
  const camera = useThree((state) => state.camera);
  useEffect(() => {
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [camera]);
  return null;
}
