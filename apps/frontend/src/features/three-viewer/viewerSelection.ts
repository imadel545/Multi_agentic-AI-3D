import { Box3 } from "three";
import type { Object3D } from "three";

const NON_SELECTABLE_ROLES = new Set([
  "azimuth_arrow",
  "beam",
  "height_marker",
  "label",
  "ground",
  "terrain"
]);
const NON_SELECTABLE_NAME = /azimuth_arrow|sector_beam|height_marker|label_|technical_ground_plane/;

/** Resolve a click only against identities published by the backend for this scene. */
export function semanticRootForPick(
  hit: Object3D,
  knownRoots: readonly string[],
  pointerTravel: number,
  button = 0
): string | null {
  if (button !== 0 || !Number.isFinite(pointerTravel) || pointerTravel > 4) {
    return null;
  }

  const ancestors: Object3D[] = [];
  for (let current: Object3D | null = hit; current; current = current.parent) {
    if (!current.visible) {
      return null;
    }
    const role = String(current.userData.role ?? current.userData.object_role ?? "").toLowerCase();
    if (NON_SELECTABLE_ROLES.has(role) || NON_SELECTABLE_NAME.test(current.name.toLowerCase())) {
      return null;
    }
    ancestors.push(current);
  }

  for (const object of ancestors) {
    const declared = object.userData.semantic_root ?? object.userData.semanticRoot;
    if (typeof declared === "string" && knownRoots.includes(declared)) {
      return declared;
    }
    if (knownRoots.includes(object.name)) {
      return object.name;
    }
  }

  for (const object of ancestors) {
    const matches = knownRoots.filter((root) => root && object.name.startsWith(`${root}_`));
    if (matches.length === 1) {
      return matches[0];
    }
    if (matches.length > 1) {
      return null;
    }
  }
  return null;
}

/** Exported assemblies often carry one identity on several sibling meshes. */
export function semanticSelectionBounds(scene: Object3D, root: string | null): Box3 | null {
  return root ? semanticRootsBounds(scene, [root]) : null;
}

/** Build one camera box from real, published semantic identities only. */
export function semanticRootsBounds(scene: Object3D, roots: readonly string[]): Box3 | null {
  if (!roots.length) {
    return null;
  }
  scene.updateWorldMatrix(true, true);
  const bounds = new Box3();
  scene.traverse((object) => {
    if (
      (object as Object3D & { isMesh?: boolean }).isMesh &&
      semanticRootForPick(object, roots, 0) !== null
    ) {
      bounds.union(new Box3().setFromObject(object));
    }
  });
  return bounds.isEmpty() ? null : bounds;
}
