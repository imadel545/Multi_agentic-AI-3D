import { describe, expect, it } from "vitest";
import { ApiClientError } from "./api/client";
import type { WorkflowStatus } from "./api/schemas";
import {
  documentPackFilesSizeError,
  documentPackSizeError,
  latestEventCursor,
  needsPolling,
  parseCorrectionValue,
  selectWorkflowToRestore,
  userFacingError
} from "./App";

function workflow(
  workflowId: string,
  status: string,
  createdAt: string
): WorkflowStatus {
  return {
    workflow_id: workflowId,
    status,
    created_at: createdAt,
    artifacts: {},
    warnings: [],
    errors: [],
    available_actions: [],
    unsupported_actions: []
  };
}

describe("frontend runtime selection", () => {
  it("resumes a running workflow before selecting terminal history", () => {
    const selected = selectWorkflowToRestore([
      workflow("wf_completed", "completed", "2026-07-15T10:00:00Z"),
      workflow("wf_running", "running", "2026-07-15T09:00:00Z")
    ]);

    expect(selected?.workflow_id).toBe("wf_running");
  });

  it("prefers the newest completed design over a newer failed workflow", () => {
    const selected = selectWorkflowToRestore([
      workflow("wf_completed_old", "completed", "2026-07-15T08:00:00Z"),
      workflow("wf_failed_new", "failed", "2026-07-15T11:00:00Z"),
      workflow("wf_completed_new", "completed", "2026-07-15T10:00:00Z")
    ]);

    expect(selected?.workflow_id).toBe("wf_completed_new");
  });

  it("polls only after the runtime explicitly falls back from SSE", () => {
    expect(needsPolling("running", "sse")).toBe(false);
    expect(needsPolling("streaming", "sse")).toBe(false);
    expect(needsPolling("running", "polling")).toBe(true);
    expect(needsPolling("completed", "polling")).toBe(false);
  });

  it("uses the latest durable event as the revision SSE cursor", () => {
    expect(
      latestEventCursor([
        { event_id: "evt_1" },
        { event_id: "evt_terminal" }
      ])
    ).toBe("evt_terminal");
    expect(latestEventCursor([])).toBeNull();
  });

  it("normalizes simple user correction values without inventing structure", () => {
    expect(parseCorrectionValue("24, 24, 24")).toEqual([24, 24, 24]);
    expect(parseCorrectionValue("true")).toBe(true);
    expect(parseCorrectionValue("lattice_tower")).toBe("lattice_tower");
    expect(() => parseCorrectionValue('{"unsupported":true}')).toThrow(/non supporté/);
  });

  it("rejects an oversized document pack before upload", () => {
    const capabilities = {
      document_pack_status: "limited",
      supported_upload_format: "zip",
      supported_extensions: [".pdf"],
      limitations: [],
      limits: {
        max_zip_size_mb: 10,
        max_member_size_mb: 5,
        max_member_count: 2,
        max_uncompressed_size_mb: 8
      },
      truth: {},
      capabilities: {}
    };

    expect(documentPackSizeError({ size: 11 * 1024 * 1024 }, capabilities)).toContain("10 Mo");
    expect(documentPackSizeError({ size: 10 * 1024 * 1024 }, capabilities)).toBeNull();
    expect(
      documentPackFilesSizeError(
        [{ name: "large.pdf", size: 6 * 1024 * 1024 }],
        capabilities
      )
    ).toContain("large.pdf");
    expect(
      documentPackFilesSizeError(
        [
          { name: "one.pdf", size: 4 * 1024 * 1024 },
          { name: "two.jpg", size: 4 * 1024 * 1024 }
        ],
        capabilities
      )
    ).toBeNull();
  });

  it("maps backend edit failures to product language without leaking internals", () => {
    const internal = new ApiClientError(
      500,
      "/designs/wf_1/edit",
      "RuntimeError: blender subprocess exited with code 139"
    );
    const message = userFacingError(internal, "edit");

    expect(message).toBe("La modification du design a rencontré un problème interne. Réessayez.");
    expect(message).not.toContain("RuntimeError");
    expect(message).not.toContain("139");
  });

  it("gives an actionable message for local storage pressure", () => {
    expect(
      userFacingError(new ApiClientError(507, "/designs", "free disk 10MB"), "generation")
    ).toContain("Libérez de la place");
  });
});
