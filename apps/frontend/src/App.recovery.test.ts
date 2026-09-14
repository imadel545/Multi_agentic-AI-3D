import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App, { userFacingError } from "./App";
import { ApiClientError } from "./api/client";
import { bootstrapApi } from "./App.testSupport";
import { writeDocumentPackSession } from "./state/documentPackSession";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("frontend runtime recovery", () => {
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

  it("recovers an initial backend error through the visible retry action", async () => {
    const health = vi
      .fn()
      .mockRejectedValueOnce(new ApiClientError(503, "/health", "temporary outage"))
      .mockResolvedValue({
        status: "ok",
        service: "agentic_telecom_3d_studio_api",
        version: "1.0.0",
        api_contract_version: "2026-07-29"
      });
    const apiClient = bootstrapApi({ health });

    render(createElement(App, { apiClient }));

    expect(
      await screen.findByRole("button", { name: "Réessayer la connexion" })
    ).toBeInTheDocument();
    expect(screen.getByText("Studio indisponible")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Réessayer la connexion" }));

    await waitFor(() =>
      expect(screen.queryByText("Studio indisponible")).not.toBeInTheDocument()
    );
    expect(screen.queryByText("Studio local connecté")).not.toBeInTheDocument();
    expect(health).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByRole("button", { name: "Réessayer la connexion" })
    ).not.toBeInTheDocument();
  });

  it("does not present an empty viewer when design restoration failed and recovers on retry", async () => {
    const listDesigns = vi
      .fn()
      .mockRejectedValueOnce(new ApiClientError(503, "/designs", "temporary outage"))
      .mockResolvedValue([]);
    const apiClient = bootstrapApi({ listDesigns });

    render(createElement(App, { apiClient }));

    const viewer = await screen.findByRole(
      "region",
      { name: "3D viewer" },
      { timeout: 5_000 }
    );
    expect(within(viewer).getByText(/synchronisation initiale du studio/i)).toBeInTheDocument();
    expect(within(viewer).queryByText("Aucun design généré pour le moment.")).not.toBeInTheDocument();

    fireEvent.click(within(viewer).getByRole("button", { name: "Réessayer" }));

    await waitFor(() =>
      expect(within(viewer).getByText("Aucun design généré pour le moment.")).toBeInTheDocument()
    );
    expect(listDesigns).toHaveBeenCalledTimes(2);
    expect(within(viewer).queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
  });

  it("restores attached files under React strict effects without exposing extracted data", async () => {
    writeDocumentPackSession(window.localStorage, "pack_strict");
    const summary = {
      pack_id: "pack_strict",
      status: "processed",
      document_count: 1,
      high_priority_count: 1,
      missing_blocking_count: 0,
      blocking_fields: [],
      conflict_count: 0,
      can_generate_design: false,
      qa_score: 0.8,
      processing_warning_count: 0,
      tool_status: {}
    };
    const documentPackSummary = vi.fn().mockResolvedValue(summary);
    const apiClient = bootstrapApi({ documentPackSummary });

    render(
      createElement(
        StrictMode,
        null,
        createElement(App, { apiClient })
      )
    );

    const attachmentButton = await screen.findByRole("button", {
      name: "Ajouter des pièces jointes"
    });
    fireEvent.click(attachmentButton);
    expect(await screen.findByText(/les pièces jointes servent de contexte/i)).toBeInTheDocument();
    expect(screen.queryByText(/informations extraites/i)).not.toBeInTheDocument();
    expect(documentPackSummary.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
