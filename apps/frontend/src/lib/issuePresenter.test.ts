import { describe, expect, it } from "vitest";

import { explainMutationError, presentIssues } from "./issuePresenter";

describe("issuePresenter", () => {
  it("translates asset warnings into user-facing guidance", () => {
    const issues = presentIssues([
      {
        code: "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
        message: "ANT_PANEL_5G_001: INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
        severity: "warning",
      },
    ]);

    expect(issues[0]?.title).toBe("Asset interne minimal");
    expect(issues[0]?.impact).toContain("pipeline technique");
    expect(issues[0]?.action).toContain("vendor-grade");
  });

  it("keeps invalid edit feedback actionable", () => {
    expect(
      explainMutationError(
        new Error("Fallback patch could not interpret prompt: rends le resultat plus beau"),
      ),
    ).toContain("commande plus précise");
  });
});
