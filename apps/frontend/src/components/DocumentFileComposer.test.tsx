import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentFileComposer, documentSelectionError } from "./DocumentFileComposer";

const capabilities = {
  document_pack_status: "limited",
  supported_upload_format: "zip_or_multiple_files",
  supported_extensions: [".pdf", ".jpg", ".dxf"],
  limitations: [],
  limits: {
    max_zip_size_mb: 80,
    max_member_size_mb: 15,
    max_member_count: 256,
    max_uncompressed_size_mb: 200
  },
  truth: {},
  capabilities: {}
};

describe("DocumentFileComposer", () => {
  it("queues several technical files and submits them together", async () => {
    const onSubmit = vi.fn().mockResolvedValue(true);
    render(
      <DocumentFileComposer
        busy={false}
        capabilities={capabilities}
        onSubmit={onSubmit}
      />
    );
    const input = screen.getByLabelText("Ajouter des pièces techniques");
    const files = [
      new File(["pdf"], "APD.pdf", { type: "application/pdf" }),
      new File(["image"], "site.jpg", { type: "image/jpeg" })
    ];

    fireEvent.change(input, { target: { files } });
    expect(screen.getByText("APD.pdf")).toBeInTheDocument();
    expect(screen.getByText("site.jpg")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Analyser 2 pièce(s)" }));

    expect(onSubmit).toHaveBeenCalledWith(files);
  });

  it("rejects mixing a ZIP with direct files", () => {
    expect(
      documentSelectionError(
        [
          { name: "pack.zip", size: 10 },
          { name: "plan.pdf", size: 10 }
        ],
        capabilities
      )
    ).toContain("ZIP doit être analysé seul");
  });

  it("rejects duplicate names before the backend archive is assembled", () => {
    expect(
      documentSelectionError(
        [
          { name: "Plan.DXF", size: 10 },
          { name: "plan.dxf", size: 20 }
        ],
        capabilities
      )
    ).toContain("Deux pièces portent le nom");
  });
});
