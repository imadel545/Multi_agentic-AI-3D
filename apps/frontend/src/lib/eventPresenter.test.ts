import { describe, expect, it } from "vitest";

import { groupPresentedEvents, presentEvent } from "./eventPresenter";

describe("eventPresenter", () => {
  it("turns backend events into product language", () => {
    const event = presentEvent({
      event_type: "edit_patch_rejected",
      timestamp: "2026-06-09T14:14:37Z",
      payload: {
        reason: "Fallback patch could not interpret prompt",
        agent: "SceneEditAgent",
      },
    });

    expect(event.title).toBe("Modification refusée");
    expect(event.phase).toBe("Versioning");
    expect(event.status).toBe("failed");
    expect(event.summary).toContain("Le design actif reste protégé");
  });

  it("groups events by agentic phase", () => {
    const groups = groupPresentedEvents([
      { event_type: "blender_started", payload: { node: "generate_blender" } },
      { event_type: "workflow_completed", payload: { duration_ms: 6802 } },
    ]);

    expect(groups.map(([phase]) => phase)).toEqual(["Blender", "Workflow"]);
  });
});
