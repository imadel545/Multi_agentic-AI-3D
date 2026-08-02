import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Group, Object3D } from "three";
import type { ViewerBundle } from "../../api/schemas";
import {
  advanceRenderHealthProbe,
  findSemanticObject,
  PreviewFallback,
  TelecomGlbViewer
} from "./TelecomGlbViewer";

describe("TelecomGlbViewer fallbacks", () => {
  it("resolves a component from its real GLB semantic root before using a bounded name prefix", () => {
    const scene = new Group();
    const exact = new Object3D();
    exact.name = "generated_mesh";
    exact.userData.semantic_root = "antenna_S1_REAL_1";
    const prefixed = new Object3D();
    prefixed.name = "rru_S1_REAL_1_body";
    scene.add(exact, prefixed);

    expect(findSemanticObject(scene, "antenna_S1_REAL_1")).toBe(exact);
    expect(findSemanticObject(scene, "rru_S1_REAL_1")).toBe(prefixed);
    expect(findSemanticObject(scene, "unknown")).toBeNull();
  });
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
      qa_summary: {},
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
