import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StudioShell } from "./StudioShell";

function renderWithQuery() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StudioShell />
    </QueryClientProvider>,
  );
}

describe("StudioShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/health")) {
          return Response.json({ status: "ok", version: "0.2.0" });
        }
        if (url.endsWith("/designs")) {
          return Response.json([]);
        }
        if (url.endsWith("/document-packs")) {
          return Response.json([]);
        }
        if (url.endsWith("/assets/inventory")) {
          return Response.json({
            status: "partial_import_ready",
            asset_count: 0,
            asset_count_by_type: {},
            missing_file_count: 0,
            real_glb_asset_count: 0,
            import_ready_asset_count: 0,
            procedural_fallback_count: 0,
            procedural_generation_required: false,
            entries: [],
            missing_files: [],
          });
        }
        return Response.json({});
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the agentic studio shell without static fake data", async () => {
    renderWithQuery();

    expect(await screen.findByText("Agentic Telecom Studio")).toBeInTheDocument();
    expect(screen.getByText("Agent Command Center")).toBeInTheDocument();
    expect(await screen.findByText("3D Design Stage")).toBeInTheDocument();
    expect(await screen.findByText("No GLB loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate Design/i })).toBeInTheDocument();
    expect(
      await screen.findByText("Upload APD / PDF / DXF / ZIP to generate a 3D design"),
    ).toBeInTheDocument();
  });
});
