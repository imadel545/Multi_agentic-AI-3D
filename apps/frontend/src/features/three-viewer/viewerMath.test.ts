import { Box3, BoxGeometry, Color, Mesh, MeshBasicMaterial, Object3D, PerspectiveCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import {
  computeTelecomCameraFit,
  enhanceViewerMaterials,
  fitCameraToObject,
  isRenderVisiblyDifferent
} from "./viewerMath";

describe("viewer math", () => {
  it("fits the camera for a 30m telecom tower bounding box", () => {
    const box = new Box3(new Vector3(-9, -0.3, -9), new Vector3(9, 30.6, 9));

    const fit = computeTelecomCameraFit(box);

    expect(fit.target.y).toBeGreaterThan(12);
    expect(fit.target.y).toBeLessThan(20);
    expect(fit.distance).toBeGreaterThan(35);
    expect(fit.near).toBeLessThan(1);
    expect(fit.far).toBeGreaterThan(90);
  });

  it("applies camera target and clipping planes to a loaded scene", () => {
    const scene = new Object3D();
    const child = new Mesh(new BoxGeometry(18, 30, 18), new MeshBasicMaterial());
    child.position.set(0, 15, 0);
    scene.add(child);
    const camera = new PerspectiveCamera(38, 1.4, 0.1, 1000);
    const controls = {
      target: new Vector3(),
      update: () => undefined
    };

    const fitted = fitCameraToObject(camera, scene, controls);

    expect(fitted).not.toBeNull();
    expect(camera.near).toBeLessThan(1);
    expect(camera.far).toBeGreaterThan(80);
    expect(controls.target.y).toBeGreaterThan(12);
    expect(controls.target.y).toBeLessThan(20);
  });

  it("ignores the technical ground plane for viewer fitting", () => {
    const scene = new Object3D();
    const ground = new Mesh(new BoxGeometry(300, 0.1, 300), new MeshBasicMaterial());
    ground.name = "technical_ground_plane";
    const tower = new Mesh(new BoxGeometry(18, 90, 18), new MeshBasicMaterial());
    tower.name = "tower_TOWER_LATTICE_30M";
    tower.position.set(0, 45, 0);
    scene.add(ground, tower);
    const camera = new PerspectiveCamera(38, 1.4, 0.1, 1000);

    enhanceViewerMaterials(scene);
    const fit = fitCameraToObject(camera, scene, null);

    expect(ground.visible).toBe(false);
    expect(fit?.box.getSize(new Vector3()).x).toBeLessThan(30);
    expect(fit?.box.getSize(new Vector3()).y).toBeGreaterThan(80);
  });

  it("clones shared materials and applies role colors for inspection visibility", () => {
    const scene = new Object3D();
    const sharedMaterial = new MeshBasicMaterial({ color: "#f8f8f8" });
    const tower = new Mesh(new BoxGeometry(1, 30, 1), sharedMaterial);
    tower.name = "tower_TOWER_LATTICE_30M";
    const antenna = new Mesh(new BoxGeometry(1, 2, 0.2), sharedMaterial);
    antenna.name = "antenna_S1_ANT_PANEL_5G_001";
    scene.add(tower, antenna);

    enhanceViewerMaterials(scene);

    expect(tower.material).not.toBe(sharedMaterial);
    expect(antenna.material).not.toBe(sharedMaterial);
    expect((tower.material as MeshBasicMaterial).color.getHexString()).toBe("d1d5db");
    expect((antenna.material as MeshBasicMaterial).color.getHexString()).toBe("22d3ee");
  });

  it("detects blank render samples so the preview fallback can take over", () => {
    const background = new Color("#182329");
    const blankSamples: Array<[number, number, number, number]> = Array.from({ length: 16 }, () => [
      Math.round(background.r * 255),
      Math.round(background.g * 255),
      Math.round(background.b * 255),
      255
    ]);
    const visibleSamples: Array<[number, number, number, number]> = [...blankSamples, [220, 230, 236, 255]];
    const whiteSamples: Array<[number, number, number, number]> = Array.from({ length: 16 }, () => [
      248,
      248,
      248,
      255
    ]);
    const mostlyWhiteSamples: Array<[number, number, number, number]> = [
      ...Array.from({ length: 48 }, () => [248, 248, 248, 255] as [number, number, number, number]),
      [24, 35, 41, 255]
    ];

    expect(isRenderVisiblyDifferent(blankSamples)).toBe(false);
    expect(isRenderVisiblyDifferent(whiteSamples)).toBe(false);
    expect(isRenderVisiblyDifferent(mostlyWhiteSamples)).toBe(false);
    expect(isRenderVisiblyDifferent(visibleSamples)).toBe(true);
  });
});
