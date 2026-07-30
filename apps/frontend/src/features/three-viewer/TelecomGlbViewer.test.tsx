import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  advanceRenderHealthProbe,
  PreviewFallback
} from "./TelecomGlbViewer";

describe("TelecomGlbViewer fallbacks", () => {
  it("replaces a broken backend preview with an explicit product error", () => {
    render(
      <PreviewFallback
        message="GLB indisponible; affichage de la preview backend."
        url="http://127.0.0.1:8000/designs/wf_1/artifacts/preview"
      />
    );

    fireEvent.error(screen.getByRole("img"));

    expect(screen.getByRole("status")).toHaveTextContent(
      "La preview backend n’a pas pu être chargée."
    );
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
