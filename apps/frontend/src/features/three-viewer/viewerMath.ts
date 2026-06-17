import {
  Box3,
  Color,
  DoubleSide,
  Material,
  Mesh,
  Object3D,
  PerspectiveCamera,
  Vector3
} from "three";

export type CameraFit = {
  box: Box3;
  center: Vector3;
  position: Vector3;
  target: Vector3;
  near: number;
  far: number;
  radius: number;
  distance: number;
};

export type RenderSample = [number, number, number, number];

const ViewerBackground = new Color("#182329");
const IgnoredViewerObjectTokens = ["technical_ground_plane", "foundation_concrete_pad"];

export function computeTelecomCameraFit(box: Box3, fovDeg = 38): CameraFit {
  const center = box.getCenter(new Vector3());
  const size = box.getSize(new Vector3());
  const height = Math.max(size.y, 2);
  const horizontal = Math.max(size.x, size.z, 2);
  const fovRad = (fovDeg * Math.PI) / 180;
  const fitDistance = Math.max(
    (height * 0.5) / Math.tan(fovRad * 0.5),
    (horizontal * 0.5) / Math.tan(fovRad * 0.5),
    10
  );
  const radius = Math.max(height, horizontal);
  const distanceMultiplier = height > 50 ? 0.88 : 1.15;
  const distance = fitDistance * distanceMultiplier;
  const direction = new Vector3(0.72, 0.42, 0.88).normalize();
  const target = new Vector3(center.x, box.min.y + height * 0.52, center.z);
  const position = target.clone().add(direction.multiplyScalar(distance));

  return {
    box,
    center,
    position,
    target,
    near: Math.max(0.05, distance / 800),
    far: Math.max(distance + radius * 3, 250),
    radius,
    distance
  };
}

export function fitCameraToObject(
  camera: PerspectiveCamera,
  object: Object3D,
  controls: { target: Vector3; update: () => void } | null
): CameraFit | null {
  const inspectableBox = inspectableObjectBox(object);
  const box = inspectableBox ?? new Box3().setFromObject(object);
  if (box.isEmpty()) {
    return null;
  }
  const fit = computeTelecomCameraFit(box, camera.fov);
  camera.position.copy(fit.position);
  camera.near = fit.near;
  camera.far = fit.far;
  camera.lookAt(fit.target);
  camera.updateProjectionMatrix();
  if (controls) {
    controls.target.copy(fit.target);
    controls.update();
  }
  return fit;
}

export function enhanceViewerMaterials(scene: Object3D) {
  scene.traverse((object) => {
    if (shouldIgnoreForViewer(object)) {
      object.visible = false;
      return;
    }
    if (!(object instanceof Mesh)) {
      return;
    }
    const sourceMaterials = Array.isArray(object.material) ? object.material : [object.material];
    const materials = sourceMaterials.map(cloneMaterialForViewer);
    object.material = Array.isArray(object.material) ? materials : materials[0];
    const roleColor = viewerRoleColor(object.name);
    for (const material of materials) {
      const editable = material as {
        color?: Color;
        metalness?: number;
        needsUpdate?: boolean;
        opacity?: number;
        roughness?: number;
        side?: number;
        transparent?: boolean;
      };
      if (!(editable.color instanceof Color)) {
        continue;
      }
      editable.side = DoubleSide;
      if (typeof editable.roughness === "number") {
        editable.roughness = Math.max(editable.roughness, 0.68);
      }
      if (typeof editable.metalness === "number") {
        editable.metalness = Math.min(editable.metalness, 0.18);
      }
      if (typeof editable.opacity === "number") {
        editable.opacity = Math.max(editable.opacity, 0.92);
        editable.transparent = editable.opacity < 1;
      }
      if (roleColor) {
        editable.color.copy(roleColor);
      } else {
        const luminance = editable.color.r * 0.2126 + editable.color.g * 0.7152 + editable.color.b * 0.0722;
        if (luminance > 0.82) {
          editable.color.lerp(new Color("#26333a"), 0.58);
        }
      }
      editable.needsUpdate = true;
    }
  });
}

export function isRenderVisiblyDifferent(samples: RenderSample[], tolerance = 18): boolean {
  if (!samples.length) {
    return false;
  }
  const background = [
    Math.round(ViewerBackground.r * 255),
    Math.round(ViewerBackground.g * 255),
    Math.round(ViewerBackground.b * 255)
  ];
  const allLuminanceValues = samples
    .filter(([, , , alpha]) => alpha !== 0)
    .map(([red, green, blue]) => (red * 0.2126) + (green * 0.7152) + (blue * 0.0722));
  if (!allLuminanceValues.length) {
    return false;
  }
  const allMean =
    allLuminanceValues.reduce((sum, value) => sum + value, 0) / allLuminanceValues.length;
  if (allMean > 220) {
    return false;
  }
  const backgroundLikeCount = samples.filter(([red, green, blue, alpha]) => {
    if (alpha === 0) {
      return false;
    }
    const delta =
      Math.abs(red - background[0]) + Math.abs(green - background[1]) + Math.abs(blue - background[2]);
    return delta <= tolerance;
  }).length;
  if (backgroundLikeCount < Math.max(1, samples.length * 0.1) && allMean > 150) {
    return false;
  }
  const visibleSamples = samples.filter(([red, green, blue, alpha]) => {
    if (alpha === 0) {
      return false;
    }
    const delta =
      Math.abs(red - background[0]) + Math.abs(green - background[1]) + Math.abs(blue - background[2]);
    return delta > tolerance;
  });
  if (!visibleSamples.length) {
    return false;
  }
  const luminanceValues = visibleSamples.map(
    ([red, green, blue]) => (red * 0.2126) + (green * 0.7152) + (blue * 0.0722)
  );
  const mean = luminanceValues.reduce((sum, value) => sum + value, 0) / luminanceValues.length;
  const variance =
    luminanceValues.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / luminanceValues.length;
  const stddev = Math.sqrt(variance);
  if (mean > 235 && stddev < 6) {
    return false;
  }
  return true;
}

export function summarizeObjects(scene: Object3D) {
  const roles: Record<string, number> = {
    antenna: 0,
    cable: 0,
    cabinet: 0,
    foundation: 0,
    gps: 0,
    label: 0,
    rru: 0,
    tower: 0
  };
  let totalNamedObjects = 0;
  scene.traverse((object) => {
    if (!object.name || shouldIgnoreForViewer(object)) {
      return;
    }
    totalNamedObjects += 1;
    const name = object.name.toLowerCase();
    if (name.includes("antenna") || name.includes("panel")) roles.antenna += 1;
    if (name.includes("cable")) roles.cable += 1;
    if (name.includes("cabinet") || name.includes("power")) roles.cabinet += 1;
    if (name.includes("foundation") || name.includes("concrete") || name.includes("pad")) roles.foundation += 1;
    if (name.includes("gps")) roles.gps += 1;
    if (name.includes("label")) roles.label += 1;
    if (name.includes("rru") || name.includes("radio")) roles.rru += 1;
    if (name.includes("tower") || name.includes("lattice") || name.includes("monopole")) roles.tower += 1;
  });
  return { roles, totalNamedObjects };
}

function inspectableObjectBox(scene: Object3D): Box3 | null {
  scene.updateWorldMatrix(true, true);
  const box = new Box3();
  let hasInspectableMesh = false;
  scene.traverse((object) => {
    if (shouldIgnoreForViewer(object) || !(object instanceof Mesh) || !object.visible) {
      return;
    }
    const meshBox = new Box3().setFromObject(object);
    if (!meshBox.isEmpty()) {
      box.union(meshBox);
      hasInspectableMesh = true;
    }
  });
  return hasInspectableMesh ? box : null;
}

function shouldIgnoreForViewer(object: Object3D): boolean {
  const name = object.name.toLowerCase();
  return IgnoredViewerObjectTokens.some((token) => name.includes(token));
}

function cloneMaterialForViewer(material: Material): Material {
  return typeof material.clone === "function" ? material.clone() : material;
}

function viewerRoleColor(name: string): Color | null {
  const normalized = name.toLowerCase();
  if (normalized.includes("antenna") || normalized.includes("panel")) {
    return new Color("#22d3ee");
  }
  if (normalized.includes("rru") || normalized.includes("radio")) {
    return new Color("#f59e0b");
  }
  if (normalized.includes("cable")) {
    return new Color("#f8fafc");
  }
  if (normalized.includes("cabinet") || normalized.includes("power")) {
    return new Color("#94a3b8");
  }
  if (normalized.includes("gps")) {
    return new Color("#facc15");
  }
  if (normalized.includes("label")) {
    return new Color("#c084fc");
  }
  if (normalized.includes("beam")) {
    return new Color("#22c55e");
  }
  if (normalized.includes("tower") || normalized.includes("lattice") || normalized.includes("monopole")) {
    return new Color("#d1d5db");
  }
  return null;
}
