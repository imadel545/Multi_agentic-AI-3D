import { describe, expect, it, vi } from "vitest";
import { ContractValidationError } from "./schemas";
import { ApiClientError, TelecomStudioApi } from "./client";

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
    ...init
  });
}

describe("TelecomStudioApi", () => {
  it("posts designs to the existing /designs contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ workflow_id: "wf_1", status: "pending" }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.createDesign({ requirements_text: "site 5G" });

    expect(result.workflow_id).toBe("wf_1");
    expect(fetcher).toHaveBeenCalledWith(new URL("/designs", "http://127.0.0.1:8000"), {
      body: JSON.stringify({ requirements_text: "site 5G" }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
  });

  it("turns HTTP errors into readable client errors", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ detail: "Backend unavailable" }, { status: 503 }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.health()).rejects.toMatchObject({
      endpoint: "/health",
      message: "Backend unavailable",
      name: "ApiClientError",
      status: 503
    });
  });

  it("rejects invalid backend payloads before UI consumption", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ workflow_id: "wf_1" }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.createDesign({ requirements_text: "site 5G" })).rejects.toBeInstanceOf(
      ContractValidationError
    );
  });

  it("blocks artifact URLs that expose local paths", () => {
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetch);

    expect(() => client.artifactUrl("/Users/imad/output/design.glb")).toThrow(ApiClientError);
  });

  it("prepares edit and rollback calls on the existing /designs contract", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          workflow_id: "wf_1",
          edit_id: "edit_1",
          status: "applied",
          edit_status: "applied",
          message: "Version créée",
          version_id: "v2",
          artifacts: { glb: "/designs/wf_1/artifacts/glb?version_id=v2" },
          available_actions: ["open_viewer"]
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          workflow_id: "wf_1",
          version_id: "v1",
          active_version_id: "v1",
          rolled_back: true,
          status: "rolled_back",
          message: "Version restaurée",
          viewer_bundle_url: "/designs/wf_1/viewer-bundle",
          timeline_url: "/designs/wf_1/timeline-summary",
          user_issues_url: "/designs/wf_1/user-issues",
          current_operation_url: "/designs/wf_1/current-operation",
          available_actions: ["open_viewer"]
        })
      );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.editDesign("wf_1", { edit_prompt: "monte les antennes à 26m" })).resolves.toMatchObject({
      edit_status: "applied",
      version_id: "v2"
    });
    await expect(client.rollbackVersion("wf_1", "v1")).resolves.toMatchObject({
      active_version_id: "v1",
      rolled_back: true
    });
    expect(fetcher).toHaveBeenNthCalledWith(1, new URL("/designs/wf_1/edit", "http://127.0.0.1:8000"), {
      body: JSON.stringify({ edit_prompt: "monte les antennes à 26m" }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      new URL("/designs/wf_1/versions/v1/rollback", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({}),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });

  it("uploads document-pack ZIPs without creating a new product entity", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_1",
        status: "ready",
        document_count: 3,
        can_generate_design: true
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);
    const file = new File(["zip-bytes"], "cahier-charge.zip", { type: "application/zip" });

    const result = await client.createDocumentPack(file);

    expect(result.pack_id).toBe("pack_1");
    expect(result.can_generate_design).toBe(true);
    expect(fetcher).toHaveBeenCalledWith(new URL("/document-packs", "http://127.0.0.1:8000"), {
      body: file,
      headers: {
        "content-type": "application/zip",
        "x-filename": "cahier-charge.zip"
      },
      method: "POST"
    });
  });

  it("starts document-pack generation through the existing workflow_id contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_1",
        status: "started",
        workflow_id: "wf_from_pack"
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.generateDesignFromDocumentPack("pack_1")).resolves.toMatchObject({
      workflow_id: "wf_from_pack"
    });
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/document-packs/pack_1/generate-design", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({}),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });
});
