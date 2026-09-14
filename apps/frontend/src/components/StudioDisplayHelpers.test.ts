import { describe, expect, it } from "vitest";
import { humanSemanticRole, serviceStatusLabel } from "./StudioDisplayHelpers";

describe("semantic role labels", () => {
  it.each([
    ["ground_equipment", "équipement au sol"],
    ["timing_antenna", "antenne de synchronisation"],
    ["antenna_support", "support d’antenne"]
  ])("translates %s for the user", (role, label) => {
    expect(humanSemanticRole(role)).toBe(label);
  });
});

describe("service availability labels", () => {
  it.each(["unavailable", "reranker_unavailable", "disabled", "missing", "available_with_error"])(
    "does not claim availability for %s",
    (status) => expect(serviceStatusLabel(status)).toBe("indisponible")
  );
  it.each(["available_degraded", "ready_with_fallback", "limited"])(
    "preserves limits for %s",
    (status) => expect(serviceStatusLabel(status)).toBe("disponible avec limites")
  );
  it("distinguishes confirmed, available and unknown states", () => {
    expect(serviceStatusLabel("primary_vector")).toBe("opérationnel");
    expect(serviceStatusLabel("available")).toBe("disponible");
    expect(serviceStatusLabel(null)).toBe("état non confirmé");
  });
});
