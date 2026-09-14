import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentFileComposer, documentSelectionError } from "./DocumentFileComposer";
import { DocumentPackIntake } from "./StudioDocumentIntake";

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
  afterEach(() => cleanup());
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
    fireEvent.click(screen.getByRole("button", { name: "Joindre 2 pièce(s)" }));

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
    ).toContain("ZIP doit être joint seul");
  });

  it("removes one queued file with its explicit close action", () => {
    render(
      <DocumentFileComposer
        busy={false}
        capabilities={capabilities}
        onSubmit={vi.fn().mockResolvedValue(true)}
      />
    );
    fireEvent.change(screen.getByLabelText("Ajouter des pièces techniques"), {
      target: {
        files: [
          new File(["pdf"], "elevation.pdf", { type: "application/pdf" }),
          new File(["image"], "site.jpg", { type: "image/jpeg" })
        ]
      }
    });
    fireEvent.click(screen.getByRole("button", { name: "Retirer elevation.pdf" }));
    expect(screen.queryByText("elevation.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("site.jpg")).toBeInTheDocument();
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

  it("uses neutral busy copy because the same state also covers removal", () => {
    render(
      <DocumentFileComposer
        busy
        capabilities={capabilities}
        onSubmit={vi.fn().mockResolvedValue(true)}
      />
    );

    expect(screen.getByText("Traitement en cours…")).toBeInTheDocument();
    expect(screen.queryByText("Ajout en cours…")).not.toBeInTheDocument();
  });

  it("shows a confirmed removal as information instead of a synchronization error", () => {
    render(
      <DocumentPackIntake
        busy={false}
        capabilities={capabilities}
        message="Le retrait est confirmé. Vous pouvez joindre d’autres pièces."
        messageStatus="removal_confirmed"
        onRetry={vi.fn()}
        onUpload={vi.fn().mockResolvedValue(true)}
        summary={null}
      />
    );

    expect(screen.getByText(/Le retrait est confirmé/)).toBeInTheDocument();
    expect(screen.queryByText(/n’ont pas pu être synchronisées/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Réessayer/ })).not.toBeInTheDocument();
  });

  it("keeps a failed removal in recovery even if its copy resembles a confirmation", () => {
    render(
      <DocumentPackIntake
        busy={false}
        capabilities={capabilities}
        message="Cahier de charge retiré impossible pour le moment."
        messageStatus="error"
        onRetry={vi.fn()}
        onUpload={vi.fn().mockResolvedValue(true)}
        summary={null}
      />
    );

    expect(screen.getByText(/n’ont pas pu être synchronisées/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Réessayer/ })).toBeInTheDocument();
  });
});
