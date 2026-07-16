import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewFallback } from "./TelecomGlbViewer";

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
});
