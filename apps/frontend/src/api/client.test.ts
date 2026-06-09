import { describe, expect, it } from "vitest";

import { artifactUrl } from "./client";

describe("artifactUrl", () => {
  it("builds active artifact URLs through the backend", () => {
    expect(artifactUrl("wf_123", "glb")).toBe(
      "http://127.0.0.1:8000/designs/wf_123/artifacts/glb",
    );
  });

  it("builds version-scoped artifact URLs", () => {
    expect(artifactUrl("wf_123", "scene_spec", "v1")).toBe(
      "http://127.0.0.1:8000/designs/wf_123/artifacts/scene_spec?version_id=v1",
    );
  });

  it("does not build artifact URLs without a workflow", () => {
    expect(artifactUrl(undefined, "glb")).toBeUndefined();
  });
});
