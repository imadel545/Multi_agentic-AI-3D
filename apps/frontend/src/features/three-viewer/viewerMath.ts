import {
  Box3,
  Color,
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

export type ModelObjectSummary = {
  totalNamedObjects: number;
  semanticEntityCount: number;
  evidenceMode: "semantic_extras" | "legacy_name_fallback";
  roles: Record<string, number>;
};

const ViewerBackground = new Color("#182329");
const HiddenTechnicalObjectTokens = ["technical_ground_plane"];
const CameraFitExcludedRoles = new Set([
  "azimuth_arrow",
  "beam",
  "height_marker",
  "label"
]);
const CameraFitExcludedNameTokens = ["azimuth_arrow", "sector_beam", "height_marker", "label_"];

export function computeTelecomCameraFit(box: Box3, fovDeg = 38, aspect = 1): CameraFit {
  const center = box.getCenter(new Vector3());
  const size = box.getSize(new Vector3());
  const height = Math.max(size.y, 2);
  const horizontal = Math.max(size.x, size.z, 2);
  const verticalFovRad = (fovDeg * Math.PI) / 180;
  const horizontalFovRad = 2 * Math.atan(Math.tan(verticalFovRad * 0.5) * Math.max(aspect, 0.25));
  const fitDistance = Math.max(
    (height * 0.5) / Math.tan(verticalFovRad * 0.5),
    (horizontal * 0.5) / Math.tan(horizontalFovRad * 0.5),
    10
  );
  const radius = Math.max(height, horizontal);
  const distance = fitDistance * 1.18;
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
  const fit = computeTelecomCameraFit(box, camera.fov, camera.aspect);
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

export function prepareViewerScene(scene: Object3D) {
  scene.traverse((object) => {
    if (shouldHideTechnicalObject(object)) {
      object.visible = false;
    }
  });
}

export function probeRenderVisibility(sample: () => RenderSample[]): boolean {
  try {
    return isRenderVisiblyDifferent(sample());
  } catch {
    return false;
  }
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

export function summarizeObjects(scene: Object3D): ModelObjectSummary {
  const roles: Record<string, number> = {
    antenna: 0,
    azimuth_arrow: 0,
    beam: 0,
    cable: 0,
    cabinet: 0,
    foundation: 0,
    gps: 0,
    label: 0,
    mount_bracket: 0,
    rru: 0,
    tower: 0
  };
  let totalNamedObjects = 0;
  const semanticEntities = new Set<string>();
  scene.traverse((object) => {
    if (!object.name || shouldHideTechnicalObject(object)) {
      return;
    }
    totalNamedObjects += 1;
    const role = canonicalSemanticRole(object.userData.role ?? object.userData.object_role);
    const identity = object.userData.semantic_id ?? object.userData.semantic_root;
    if (role && identity) {
      semanticEntities.add(`${role}:${String(identity)}`);
    }
  });

  if (semanticEntities.size) {
    for (const entity of semanticEntities) {
      const role = entity.slice(0, entity.indexOf(":"));
      roles[role] = (roles[role] ?? 0) + 1;
    }
    return {
      roles,
      totalNamedObjects,
      semanticEntityCount: semanticEntities.size,
      evidenceMode: "semantic_extras"
    };
  }

  scene.traverse((object) => {
    if (!object.name || shouldHideTechnicalObject(object)) {
      return;
    }
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
  return {
    roles,
    totalNamedObjects,
    semanticEntityCount: Object.values(roles).reduce((sum, count) => sum + count, 0),
    evidenceMode: "legacy_name_fallback"
  };
}

function canonicalSemanticRole(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  return {
    antenna_panel: "antenna",
    power_cabinet: "cabinet",
    radio: "rru",
    rru: "rru"
  }[normalized] ?? normalized;
}

function inspectableObjectBox(scene: Object3D): Box3 | null {
  scene.updateWorldMatrix(true, true);
  const box = new Box3();
  let hasInspectableMesh = false;
  scene.traverse((object) => {
    if (
      shouldHideTechnicalObject(object) ||
      shouldExcludeFromCameraFit(object) ||
      !(object instanceof Mesh) ||
      !object.visible
    ) {
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

function shouldExcludeFromCameraFit(object: Object3D): boolean {
  let current: Object3D | null = object;
  while (current) {
    const role = canonicalSemanticRole(current.userData.role ?? current.userData.object_role);
    if (role && CameraFitExcludedRoles.has(role)) {
      return true;
    }
    const name = current.name.toLowerCase();
    if (CameraFitExcludedNameTokens.some((token) => name.includes(token))) {
      return true;
    }
    current = current.parent;
  }
  return false;
}

function shouldHideTechnicalObject(object: Object3D): boolean {
  const name = object.name.toLowerCase();
  return HiddenTechnicalObjectTokens.some((token) => name.includes(token));
}
