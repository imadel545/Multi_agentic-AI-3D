import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GlbObjectSummary } from "./ViewerStates";

describe("GlbObjectSummary", () => {
  afterEach(() => cleanup());

  it("states the GLB counting boundary without implying professional verification", () => {
    render(
      <GlbObjectSummary
        health="render_visible"
        summary={{
          totalNamedObjects: 24,
          semanticEntityCount: 19,
          physicalEntityCount: 19,
          technicalAidCount: 5,
          evidenceMode: "semantic_extras",
          roles: { tower: 1, antenna: 3 }
        }}
      />
    );

    expect(screen.getByText("Modèle technique 3D")).toBeInTheDocument();
    expect(screen.getByText(/19 ensembles 3D détectés/)).toBeInTheDocument();
    expect(screen.queryByText(/vérifié|composants physiques/i)).not.toBeInTheDocument();
  });
});
