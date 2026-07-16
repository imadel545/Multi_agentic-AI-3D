import { Box3, BoxGeometry, Color, Mesh, MeshBasicMaterial, Object3D, PerspectiveCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import {
  computeTelecomCameraFit,
  fitCameraToObject,
  isRenderVisiblyDifferent,
  prepareViewerScene,
  probeRenderVisibility,
  summarizeObjects
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

    prepareViewerScene(scene);
    const fit = fitCameraToObject(camera, scene, null);

    expect(ground.visible).toBe(false);
    expect(fit?.box.getSize(new Vector3()).x).toBeLessThan(30);
    expect(fit?.box.getSize(new Vector3()).y).toBeGreaterThan(80);
  });

  it("keeps long visual aids out of the initial physical-site framing", () => {
    const scene = new Object3D();
    const tower = new Mesh(new BoxGeometry(4, 30, 4), new MeshBasicMaterial());
    tower.name = "tower_site";
    tower.userData = { role: "tower", semantic_root: "tower_site" };
    tower.position.set(0, 15, 0);
    const arrow = new Mesh(new BoxGeometry(100, 0.2, 0.2), new MeshBasicMaterial());
    arrow.name = "azimuth_arrow_S1";
    arrow.userData = { role: "azimuth_arrow", semantic_root: "azimuth_arrow_S1" };
    arrow.position.set(50, 24, 0);
    scene.add(tower, arrow);
    const camera = new PerspectiveCamera(38, 1.4, 0.1, 1000);

    const fit = fitCameraToObject(camera, scene, null);

    expect(arrow.visible).toBe(true);
    expect(fit?.box.getSize(new Vector3()).x).toBeLessThan(10);
    expect(fit?.box.getSize(new Vector3()).y).toBeGreaterThan(29);
  });

  it("keeps the backend material truth and leaves the requested foundation visible", () => {
    const scene = new Object3D();
    const sharedMaterial = new MeshBasicMaterial({ color: "#f8f8f8" });
    const tower = new Mesh(new BoxGeometry(1, 30, 1), sharedMaterial);
    tower.name = "tower_TOWER_LATTICE_30M";
    const foundation = new Mesh(new BoxGeometry(6, 0.5, 6), sharedMaterial);
    foundation.name = "foundation_concrete_pad";
    scene.add(tower, foundation);

    prepareViewerScene(scene);

    expect(tower.material).toBe(sharedMaterial);
    expect(foundation.material).toBe(sharedMaterial);
    expect(foundation.visible).toBe(true);
    expect(sharedMaterial.color.getHexString()).toBe("f8f8f8");
  });

  it("uses the actual camera aspect ratio when fitting wide telecom scenes", () => {
    const box = new Box3(new Vector3(-30, 0, -5), new Vector3(30, 30, 5));

    const portrait = computeTelecomCameraFit(box, 38, 0.6);
    const landscape = computeTelecomCameraFit(box, 38, 1.8);

    expect(portrait.distance).toBeGreaterThan(landscape.distance);
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

  it("treats a readPixels failure as non-visible instead of claiming success", () => {
    expect(
      probeRenderVisibility(() => {
        throw new Error("readPixels unavailable");
      })
    ).toBe(false);
  });

  it("counts Blender semantic roots instead of imported sub-mesh names", () => {
    const scene = new Object3D();
    for (const name of ["tower_leg", "tower_brace", "tower_brace.001"]) {
      const mesh = new Object3D();
      mesh.name = name;
      mesh.userData = {
        role: "tower",
        semantic_root: "tower_TOWER_LATTICE_30M"
      };
      scene.add(mesh);
    }
    for (const name of ["cabinet_body", "cabinet_door", "power_handle"]) {
      const mesh = new Object3D();
      mesh.name = name;
      mesh.userData = {
        role: "cabinet",
        semantic_root: "power_cabinet_POWER_CABINET_001"
      };
      scene.add(mesh);
    }
    const radio = new Object3D();
    radio.name = "radio_S1";
    radio.userData = { role: "radio", semantic_root: "radio_S1_RRU_SMALL_001" };
    scene.add(radio);

    const summary = summarizeObjects(scene);

    expect(summary.evidenceMode).toBe("semantic_extras");
    expect(summary.totalNamedObjects).toBe(7);
    expect(summary.semanticEntityCount).toBe(3);
    expect(summary.roles.tower).toBe(1);
    expect(summary.roles.cabinet).toBe(1);
    expect(summary.roles.rru).toBe(1);
  });

  it("labels old GLBs as a name-based fallback instead of semantic truth", () => {
    const scene = new Object3D();
    const tower = new Object3D();
    tower.name = "tower_legacy";
    scene.add(tower);

    const summary = summarizeObjects(scene);

    expect(summary.evidenceMode).toBe("legacy_name_fallback");
    expect(summary.roles.tower).toBe(1);
  });
});
