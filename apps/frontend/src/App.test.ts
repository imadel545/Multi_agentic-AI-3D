import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, TelecomStudioApi } from "./api/client";
import type { EditDesignResponse, ViewerBundle, WorkflowStatus } from "./api/schemas";
import App, {
  documentPackFilesSizeError,
  documentPackSizeError,
  latestEventCursor,
  latestEventSequence,
  needsPolling,
  parseCorrectionValue,
  reconcileAfterAmbiguousMutation,
  revisionOutcomeMessage,
  selectViewerBundleForDisplay,
  selectWorkflowToRestore,
  shouldForgetDocumentPackSession,
  userFacingError
} from "./App";
import { writeDocumentPackSession } from "./state/documentPackSession";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function workflow(
  workflowId: string,
  status: WorkflowStatus["status"],
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
    unsupported_actions: [],
    completion_certificate_status: status === "completed" ? "issued" : null
  };
}

function bootstrapApi(overrides: Record<string, unknown> = {}): TelecomStudioApi {
  return {
    health: vi.fn().mockResolvedValue({
      status: "ok",
      service: "agentic_telecom_3d_studio_api",
      version: "1.0.0",
      api_contract_version: "2026-07-29"
    }),
    studioSummary: vi.fn().mockResolvedValue({
      status: "ok",
      available_actions: [],
      unsupported_actions: []
    }),
    assetLibrarySummary: vi.fn().mockResolvedValue({
      status: "catalogued_quarantined",
      schema_version: "1.1.0",
      catalog_available: false,
      file_count: 0,
      generation_eligible_count: 0,
      limitations: []
    }),
    assetInventory: vi.fn().mockResolvedValue({
      status: "qualified_mixed_catalog",
      entries: [],
      generation_eligible_asset_count: 0,
      real_glb_asset_count: 0,
      import_qualified_glb_count: 0,
      reference_only_asset_count: 0
    }),
    adaptationCapabilityCatalog: vi.fn().mockResolvedValue({
      schema_version: "1.0.0",
      catalog_hash: "a".repeat(64),
      profiles: []
    }),
    documentPackCapabilities: vi.fn().mockResolvedValue({
      document_pack_status: "limited",
      supported_upload_format: "zip_or_multipart",
      supported_extensions: [".pdf"],
      limitations: [],
      truth: {},
      capabilities: {}
    }),
    listDesigns: vi.fn().mockResolvedValue([]),
    artifactUrl: vi.fn((url: string | null | undefined) => url ?? null),
    ...overrides
  } as unknown as TelecomStudioApi;
}

function deferredPromise<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

describe("frontend runtime selection", () => {
  it("sends the picked component and captured version, then clears targeting for the next revision", async () => {
    const status = { ...workflow("wf_123456abcdef", "completed", "2026-09-09T10:00:00Z"),
      generation_mode: "real_blender", mesh_qa_passed: true, requirement_coverage_passed: true,
      artifacts: { glb: "/designs/wf_123456abcdef/artifacts/design.glb" } };
    let versionId = "v12345678";
    const bundle = () => ({ ...status, version_id: versionId, available_actions: ["edit_design"],
      viewer_artifacts: [], limitations: [], component_proofs_url: "/designs/wf_123456abcdef/artifacts/component_proofs.json" });
    const editDesign = vi.fn().mockImplementation(async () => {
      versionId = "v87654321";
      return { workflow_id: status.workflow_id, status: "applied", message: "Modification appliquée", warnings: [], unsupported_operations: [] };
    });
    const apiClient = bootstrapApi({
      listDesigns: vi.fn().mockResolvedValue([status]),
      workflowStatus: vi.fn().mockResolvedValue(status),
      viewerBundle: vi.fn().mockImplementation(async () => bundle()),
      currentOperation: vi.fn().mockResolvedValue({ ...status, is_running: false, is_terminal: true }),
      timelineSummary: vi.fn().mockResolvedValue({ ...status, timeline_steps: [] }),
      userIssues: vi.fn().mockResolvedValue({ ...status, human_readable_issues: [] }),
      versions: vi.fn().mockResolvedValue([]),
      workflowEvents: vi.fn().mockResolvedValue([]),
      componentProofs: vi.fn().mockResolvedValue({ components: [{ component_id: "radio", role_id: "rru", origin: "asset", strategy: "adapt", generation_strategy: "parametric", quantity: 1,
        instances: [{ instance_id: "radio1", semantic_root: "rru_S1_REAL_1", object_role: "rru", geometry_source: "parametric" }] }], geometry_programs: [] }),
      editDesign
    });
    render(createElement(App, { apiClient }));
    await waitFor(() => expect(screen.getByLabelText("Revision prompt")).toBeEnabled());
    fireEvent.click(await screen.findByRole("button", { name: /Composition/ }));
    fireEvent.click(await screen.findByRole("treeitem"));
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.change(screen.getByLabelText("Revision prompt"), { target: { value: "Monter de 20 cm" } });
    fireEvent.click(screen.getByRole("button", { name: "Appliquer la révision" }));
    await waitFor(() => expect(editDesign).toHaveBeenCalledWith(status.workflow_id, {
      edit_prompt: "Monter de 20 cm", target_semantic_root: "rru_S1_REAL_1", expected_version_id: "v12345678"
    }));
    await waitFor(() => expect(screen.getByLabelText("Revision prompt")).toHaveValue(""));
    await waitFor(() => expect(apiClient.viewerBundle).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText(/Composant sélectionné/)).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Revision prompt"), { target: { value: "Augmenter la hauteur du pylône" } });
    fireEvent.click(screen.getByRole("button", { name: "Appliquer la révision" }));
    await waitFor(() => expect(editDesign).toHaveBeenLastCalledWith(status.workflow_id, {
      edit_prompt: "Augmenter la hauteur du pylône"
    }));
  });

  it("loads the governed asset inventory during bootstrap", async () => {
    const assetInventory = vi.fn().mockResolvedValue({
      status: "qualified_mixed_catalog",
      asset_count: 13,
      missing_file_count: 0,
      real_glb_asset_count: 12,
      import_qualified_glb_count: 3,
      generation_eligible_asset_count: 13,
      professional_evidence_asset_count: 0,
      reference_only_asset_count: 0,
      qualified_integrity_failure_count: 0,
      entries: [],
      missing_files: []
    });

    render(createElement(App, { apiClient: bootstrapApi({ assetInventory }) }));

    await waitFor(() => expect(assetInventory).toHaveBeenCalledTimes(1));
  });

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

  it("keeps the last certified model visible when a new workflow fails", () => {
    const certified = { workflow_id: "wf_certified", status: "completed" } as ViewerBundle;
    const failed = { workflow_id: "wf_failed", status: "failed" } as ViewerBundle;

    expect(selectViewerBundleForDisplay("failed", failed, certified)).toBe(certified);
    expect(selectViewerBundleForDisplay("running", null, certified)).toBe(certified);
    expect(selectViewerBundleForDisplay("completed", certified, null)).toBe(certified);
  });

  it("ignores a superseded terminal bundle that resolves after the new workflow", async () => {
    const workflowA = workflow("wf_a", "completed", "2026-07-15T08:00:00Z");
    const workflowB = workflow("wf_b", "completed", "2026-07-15T09:00:00Z");
    const lateVersionsA = deferredPromise<Array<{
      version_id: string;
      created_at: string;
      active: boolean;
      artifacts: Record<string, string>;
      edit_description: string;
    }>>();
    let workflowAVersionsSignal: AbortSignal | undefined;
    const terminalResource = (workflowId: string) => ({
      workflow_id: workflowId,
      status: "completed",
      available_actions: [],
      unsupported_actions: []
    });
    const versions = vi.fn((workflowId: string, options?: { signal?: AbortSignal }) => {
      if (workflowId === "wf_a") {
        workflowAVersionsSignal = options?.signal;
        return lateVersionsA.promise;
      }
      return Promise.resolve([{
        version_id: "v_b",
        created_at: "2026-07-15T09:00:00Z",
        active: true,
        artifacts: {},
        edit_description: "VERSION B ACTIVE"
      }]);
    });
    const apiClient = bootstrapApi({
      listDesigns: vi.fn().mockResolvedValue([workflowA]),
      workflowStatus: vi.fn((workflowId: string) =>
        Promise.resolve(workflowId === "wf_a" ? workflowA : workflowB)
      ),
      currentOperation: vi.fn((workflowId: string) => Promise.resolve({
        ...terminalResource(workflowId),
        current_operation: "Design terminé",
        is_running: false,
        is_terminal: true
      })),
      viewerBundle: vi.fn((workflowId: string) => Promise.resolve({
        ...terminalResource(workflowId),
        viewer_artifacts: [],
        limitations: []
      })),
      timelineSummary: vi.fn((workflowId: string) => Promise.resolve({
        ...terminalResource(workflowId),
        timeline_steps: []
      })),
      userIssues: vi.fn((workflowId: string) => Promise.resolve({
        ...terminalResource(workflowId),
        human_readable_issues: []
      })),
      versions,
      parseRequirements: vi.fn().mockResolvedValue({
        requirements: {
          network_type: "5G",
          site_type: "telecom_site",
          tower_type: "lattice_tower",
          tower_height_m: 30,
          tower_characteristics: { structure: "lattice" },
          sector_count: 3,
          antenna_type: "panel_5g",
          antenna_install_height_m: 24,
          azimuths_deg: [0, 120, 240],
          mechanical_tilt_deg: 3,
          electrical_tilt_deg: 0,
          beamwidth_deg: 65,
          include_rru: true,
          include_cables: true,
          include_beams: true,
          include_labels: true,
          include_power_cabinet: true,
          include_gps_antenna: true,
          geometry_requests: [],
          detail_level: "high",
          warnings: [],
          repair_events: [],
          field_evidence: {},
          conflicts: [],
          assumptions: [],
          requires_confirmation: false,
          confirmation_fields: []
        },
        requirements_hash: "b".repeat(64),
        warnings: [],
        errors: [],
        provider: "deterministic",
        extraction_provider: "deterministic",
        fallback_used: true,
        llm_fallback_reason: "provider_unavailable"
      }),
      createDesign: vi.fn().mockResolvedValue({ workflow_id: "wf_b", status: "completed" })
    });

    render(createElement(App, { apiClient }));

    await waitFor(() => expect(versions).toHaveBeenCalledWith("wf_a", expect.anything()));
    fireEvent.change(screen.getByRole("textbox", { name: "Design prompt" }), {
      target: { value: "Créer le nouveau site B" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyser la demande" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirmer et générer" }));

    expect(await screen.findByText("VERSION B ACTIVE")).toBeInTheDocument();
    expect(workflowAVersionsSignal?.aborted).toBe(true);

    await act(async () => {
      lateVersionsA.resolve([{
        version_id: "v_a",
        created_at: "2026-07-15T08:00:00Z",
        active: true,
        artifacts: {},
        edit_description: "VERSION A OBSOLÈTE"
      }]);
      await lateVersionsA.promise;
    });

    await waitFor(() => expect(screen.queryByText("VERSION A OBSOLÈTE")).not.toBeInTheDocument());
    expect(screen.getByText("VERSION B ACTIVE")).toBeInTheDocument();
  });

  it("does not auto-restore an uncertified completed design", () => {
    const legacy = {
      ...workflow("wf_legacy", "completed", "2026-07-15T12:00:00Z"),
      completion_certificate_status: null
    };
    const selected = selectWorkflowToRestore([
      legacy,
      workflow("wf_failed", "failed", "2026-07-15T11:00:00Z")
    ]);

    expect(selected?.workflow_id).toBe("wf_failed");
  });

  it("polls only after the runtime explicitly falls back from SSE", () => {
    expect(needsPolling("running", "sse")).toBe(false);
    expect(needsPolling("streaming", "sse")).toBe(false);
    expect(needsPolling("running", "polling")).toBe(true);
    expect(needsPolling("completed", "polling")).toBe(false);
  });

  it("reconciles verified state after an ambiguous mutation response without replacing its error", async () => {
    const reloadVerifiedState = vi.fn().mockResolvedValue(undefined);

    await expect(reconcileAfterAmbiguousMutation(reloadVerifiedState)).resolves.toBe(true);
    expect(reloadVerifiedState).toHaveBeenCalledOnce();

    const unavailableReload = vi.fn().mockRejectedValue(new Error("offline"));
    await expect(reconcileAfterAmbiguousMutation(unavailableReload)).resolves.toBe(false);
    expect(unavailableReload).toHaveBeenCalledOnce();
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

  it("keeps the highest durable sequence as the polling delta cursor", () => {
    expect(
      latestEventSequence([
        { sequence: 4 },
        { sequence: null },
        { sequence: 9 },
        { sequence: 7 }
      ])
    ).toBe(9);
    expect(latestEventSequence([{ sequence: null }])).toBeNull();
  });

  it("explains a controlled edit rejection without exposing backend internals", () => {
    const message = revisionOutcomeMessage({
      workflow_id: "wf_1",
      edit_id: "edit_1",
      status: "failed",
      available_actions: [],
      unsupported_actions: [],
      warnings: [],
      errors: [
        {
          code: "GEOMETRY_VALIDATION_VALID",
          message: "QA check failed: geometry_validation_valid",
          severity: "error"
        }
      ],
      patch: null
    } as EditDesignResponse);

    expect(message).toContain("contrôle géométrique");
    expect(message).toContain("version vérifiée précédente");
    expect(message).not.toContain("geometry_validation_valid");
  });

  it("reports the applied part and translates an unsupported edit request", () => {
    const message = revisionOutcomeMessage({
      workflow_id: "wf_1",
      edit_id: "edit_1",
      status: "applied",
      available_actions: [],
      unsupported_actions: [],
      warnings: [],
      errors: [],
      patch: {
        edit_description: "Ajout d’une armoire d’alimentation.",
        unsupported_requests: [
          "Ground door addition to delimit green space is not supported by available capabilities"
        ]
      }
    } as EditDesignResponse);

    expect(message).toContain("Ajout d’une armoire d’alimentation");
    expect(message).toContain("porte ou barrière au sol");
    expect(message).not.toContain("Ground door");
  });

  it("keeps the user's revision wording instead of an internal LLM paraphrase", () => {
    const message = revisionOutcomeMessage({
      workflow_id: "wf_1",
      edit_id: "edit_1",
      status: "applied",
      available_actions: [],
      unsupported_actions: [],
      warnings: [],
      errors: [],
      patch: {
        edit_description: "Reduce tower height to 47 meters.",
        unsupported_requests: []
      }
    } as EditDesignResponse, "Réduis la hauteur du pylône à 47 m.");

    expect(message).toContain("Réduis la hauteur du pylône à 47 m.");
    expect(message).not.toContain("Reduce tower height");
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

  it("keeps the document-pack pointer on transient failures and forgets only a missing pack", () => {
    expect(
      shouldForgetDocumentPackSession(
        new ApiClientError(503, "/document-packs/pack_1", "temporarily unavailable")
      )
    ).toBe(false);
    expect(
      shouldForgetDocumentPackSession(
        new ApiClientError(404, "/document-packs/pack_1", "not found")
      )
    ).toBe(true);
    expect(shouldForgetDocumentPackSession(new TypeError("network failure"))).toBe(false);
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

    await waitFor(() => expect(screen.getByText("Studio local connecté")).toBeInTheDocument());
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

  it("restores a document review under React strict effects instead of cancelling it silently", async () => {
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
    const documentPackReview = vi.fn().mockResolvedValue({
      packId: "pack_strict",
      summary,
      conflicts: [],
      missingFields: [],
      qa: null,
      documents: [],
      extractions: [],
      provenance: {},
      processing: null,
      consolidatedSpec: null,
      sectionErrors: { qa: { status: 503, retryable: true } }
    });
    const apiClient = bootstrapApi({ documentPackReview });

    render(
      createElement(
        StrictMode,
        null,
        createElement(App, { apiClient })
      )
    );

    expect(await screen.findByText("pack_strict")).toBeInTheDocument();
    expect(documentPackReview.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
