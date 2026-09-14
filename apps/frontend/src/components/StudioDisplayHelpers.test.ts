import { describe, expect, it } from "vitest";
import { serviceStatusLabel } from "./StudioDisplayHelpers";

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
