import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BoxGeometry, Group, Mesh, MeshBasicMaterial, Object3D, Vector3 } from "three";
import type { ViewerBundle } from "../../api/schemas";
import {
  advanceRenderHealthProbe,
  semanticRootForPick,
  semanticRootsBounds,
  semanticSelectionBounds,
  PreviewFallback,
  TelecomGlbViewer
} from "./TelecomGlbViewer";

describe("TelecomGlbViewer fallbacks", () => {
  it("replaces a broken backend preview with an explicit product error", () => {
    const view = render(
      <PreviewFallback
        message="GLB indisponible; affichage de la preview backend."
        url="http://127.0.0.1:8000/designs/wf_1/artifacts/preview"
      />
    );

    fireEvent.error(screen.getByRole("img"));

    expect(screen.getByRole("status")).toHaveTextContent(
      "La preview backend n’a pas pu être chargée."
    );

    view.rerender(
      <PreviewFallback
        message="GLB indisponible; affichage de la preview backend."
        url="http://127.0.0.1:8000/designs/wf_1/artifacts/preview?version=v2"
      />
    );
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8000/designs/wf_1/artifacts/preview?version=v2"
    );
  });

  it("reissues the backend bundle operation from a preview fallback", () => {
    const onRetry = vi.fn();
    render(
      <PreviewFallback
        message="GLB indisponible; affichage de la preview backend."
        onRetry={onRetry}
        url="http://127.0.0.1:8000/designs/wf_1/artifacts/preview"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Rechercher le GLB" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("rechecks WebGL support when the user retries instead of keeping a stale failure", () => {
    const probeWebGL = vi.fn(() => false);
    const bundle = {
      workflow_id: "wf_1",
      status: "completed",
      human_warnings_count: 0,
      human_errors_count: 0,
      primary_glb_url: "/designs/wf_1/artifacts/design.glb",
      preview_url: "/designs/wf_1/artifacts/preview.png",
      viewer_artifacts: [],
      available_actions: [],
      unsupported_actions: [],
      mesh_qa_passed: true,
      qa_summary: {
        qa_status: "passed",
        qa_executed: true,
        blocked_before_qa: false,
        checks_passed: ["glb_structure"],
        checks_failed: [],
        warnings: [],
        errors: [],
        upstream_errors: [],
        limitations: []
      },
      limitations: []
    } as ViewerBundle;
    render(
      <TelecomGlbViewer
        bundle={bundle}
        probeWebGL={probeWebGL}
        toAbsoluteUrl={(url) => url ?? null}
      />
    );
    const callsBeforeRetry = probeWebGL.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Réessayer la 3D" }));

    expect(probeWebGL).toHaveBeenCalledTimes(callsBeforeRetry + 1);
    expect(screen.getByText(/WebGL indisponible/)).toBeInTheDocument();
  });

  it("returns to the complete design when the toolbar is used after a selection", () => {
    const onSelectSemanticRoot = vi.fn();
    const bundle = {
      workflow_id: "wf_1",
      status: "completed",
      human_warnings_count: 0,
      human_errors_count: 0,
      primary_glb_url: "/designs/wf_1/artifacts/design.glb",
      preview_url: "/designs/wf_1/artifacts/preview.png",
      viewer_artifacts: [],
      available_actions: [],
      unsupported_actions: [],
      mesh_qa_passed: true,
      qa_summary: {
        qa_status: "passed",
        qa_executed: true,
        blocked_before_qa: false,
        checks_passed: ["glb_structure"],
        checks_failed: [],
        warnings: [],
        errors: [],
        upstream_errors: [],
        limitations: []
      },
      limitations: []
    } as ViewerBundle;
    const view = render(
      <TelecomGlbViewer
        bundle={bundle}
        onSelectSemanticRoot={onSelectSemanticRoot}
        probeWebGL={() => false}
        selectedSemanticRoot="antenna_S2"
        toAbsoluteUrl={(url) => url ?? null}
      />
    );

    const wholeSiteButton = view.container.querySelector<HTMLButtonElement>(
      'button[aria-label="Afficher tout le site et recentrer la caméra 3D"]'
    );
    expect(wholeSiteButton).not.toBeNull();
    fireEvent.click(wholeSiteButton!);

    expect(onSelectSemanticRoot).toHaveBeenCalledWith(null);
  });

  it("invalidates demand rendering until the visibility sample is ready", () => {
    const invalidate = vi.fn();
    const sample = vi.fn(() => true);
    const onResult = vi.fn();
    const state = { frames: 0, sampled: false };

    for (let frame = 0; frame < 9; frame += 1) {
      advanceRenderHealthProbe(state, invalidate, sample, onResult);
    }

    expect(invalidate).toHaveBeenCalledTimes(9);
    expect(sample).not.toHaveBeenCalled();
    expect(onResult).not.toHaveBeenCalled();

    advanceRenderHealthProbe(state, invalidate, sample, onResult);

    expect(sample).toHaveBeenCalledOnce();
    expect(onResult).toHaveBeenCalledWith(true);

    advanceRenderHealthProbe(state, invalidate, sample, onResult);
    expect(sample).toHaveBeenCalledOnce();
    expect(onResult).toHaveBeenCalledOnce();
  });
});


describe("verified scene picking", () => {
  it("frames all exported sibling meshes of a selected assembly, excluding its labels", () => {
    const scene = new Group();
    for (const height of [1, 29]) {
      const mesh = new Mesh(new BoxGeometry(2, 2, 2), new MeshBasicMaterial());
      mesh.position.y = height;
      mesh.userData.semantic_root = "tower_actual";
      scene.add(mesh);
    }
    const label = new Mesh(new BoxGeometry(100, 100, 100), new MeshBasicMaterial());
    label.userData = { semantic_root: "tower_actual", role: "label" };
    scene.add(label);
    const bounds = semanticSelectionBounds(scene, "tower_actual");
    expect(bounds?.min.y).toBe(0);
    expect(bounds?.max.y).toBe(30);
    expect(bounds?.max.x).toBe(1);
    expect(semanticSelectionBounds(scene, "unknown")).toBeNull();
  });

  it("uses published sector roots for focus without pulling the cable descent into the camera box", () => {
    const scene = new Group();
    const antenna = new Mesh(new BoxGeometry(1, 3, 1), new MeshBasicMaterial());
    antenna.position.set(0, 24, 0);
    antenna.userData.semantic_root = "antenna_S2";
    const mount = new Mesh(new BoxGeometry(2, 1, 1), new MeshBasicMaterial());
    mount.position.set(0, 23, 0);
    mount.userData.semantic_root = "mount_S2";
    const radio = new Mesh(new BoxGeometry(1, 2, 1), new MeshBasicMaterial());
    radio.position.set(1, 22, 0);
    radio.userData.semantic_root = "radio_S2";
    const cable = new Mesh(new BoxGeometry(0.2, 24, 0.2), new MeshBasicMaterial());
    cable.position.set(0, 12, 0);
    cable.userData.semantic_root = "cable_S2_to_base";
    scene.add(antenna, mount, radio, cable);

    const bounds = semanticRootsBounds(scene, ["antenna_S2", "mount_S2", "radio_S2"]);

    expect(bounds?.min.y).toBeGreaterThanOrEqual(21);
    expect(bounds?.max.y).toBeLessThan(26);
    expect(bounds?.getSize(new Vector3()).y).toBeLessThan(5);
  });

  it("maps a nested mesh to its backend-declared ancestor identity", () => {
    const parent = new Group();
    parent.userData.semantic_root = "rru_S1_REAL_1";
    const mesh = new Object3D();
    mesh.name = "body_mesh";
    parent.add(mesh);
    expect(semanticRootForPick(mesh, ["rru_S1_REAL_1"], 0)).toBe("rru_S1_REAL_1");
    expect(semanticRootForPick(mesh, [], 0)).toBeNull();
  });

  it("supports only unambiguous bounded exported name prefixes", () => {
    const mesh = new Object3D();
    mesh.name = "rru_S1_REAL_1_body";
    expect(semanticRootForPick(mesh, ["rru_S1_REAL_1"], 1)).toBe("rru_S1_REAL_1");
    expect(semanticRootForPick(mesh, ["rru", "rru_S1_REAL_1"], 1)).toBeNull();
    mesh.name = "rru_S1_REAL_10_body";
    expect(semanticRootForPick(mesh, ["rru_S1_REAL_1"], 0)).toBeNull();
  });

  it("ignores drag gestures, secondary clicks, aids, invisible ancestors and unknown ground", () => {
    const parent = new Group();
    parent.name = "antenna_S1_REAL_1";
    const mesh = new Object3D();
    parent.add(mesh);
    const roots = [parent.name];
    expect(semanticRootForPick(mesh, roots, 5)).toBeNull();
    expect(semanticRootForPick(mesh, roots, 0, 2)).toBeNull();
    mesh.userData.object_role = "label";
    expect(semanticRootForPick(mesh, roots, 0)).toBeNull();
    mesh.userData.object_role = "antenna";
    parent.visible = false;
    expect(semanticRootForPick(mesh, roots, 0)).toBeNull();
    expect(semanticRootForPick(new Object3D(), roots, 0)).toBeNull();
  });
});
