import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TelecomStudioApi } from "../api/client";
import { initialWorkflowState } from "../state/workflowMachine";
import { useDesignRevisions } from "./useDesignRevisions";

afterEach(() => vi.restoreAllMocks());

function revisionHarness(editDesign: ReturnType<typeof vi.fn>) {
  const terminalRefresh = new Promise<void>(() => undefined);
  const loadTerminalBundle = vi.fn(() => terminalRefresh);
  const dispatch = vi.fn();
  const apiClient = {
    editDesign,
    workflowEvents: vi.fn().mockResolvedValue([])
  } as unknown as TelecomStudioApi;
  const options = {
    apiClient,
    clearAnalysis: vi.fn(),
    dispatch,
    initialPrompt: "diminue la hauteur à 20 mètres",
    initialWorkflowId: "wf_1",
    loadTerminalBundle,
    onDraftChange: vi.fn(),
    rememberEventSequence: vi.fn(),
    selectedSemanticRoot: null,
    selectedVersionId: "v12345678",
    state: {
      ...initialWorkflowState,
      workflowId: "wf_1",
      phase: "completed" as const
    },
    streamCursorRef: { current: null },
    towerAccess: null
  };
  return { dispatch, loadTerminalBundle, options };
}

describe("useDesignRevisions", () => {
  it("releases the composer when a refused revision starts a pending refresh", async () => {
    const editDesign = vi.fn().mockResolvedValue({
      workflow_id: "wf_1",
      edit_id: "edit_1",
      status: "rejected",
      available_actions: [],
      unsupported_actions: [],
      errors: [],
      warnings: []
    });
    const { dispatch, loadTerminalBundle, options } = revisionHarness(editDesign);
    const { result } = renderHook(() => useDesignRevisions(options));

    await act(async () => {
      await result.current.submitRevision();
    });

    expect(result.current.revisionBusy).toBe(false);
    expect(result.current.revisionMessage).toContain("Modification non appliquée");
    expect(dispatch).toHaveBeenCalledWith({ type: "REVISION_FINISHED" });
    expect(loadTerminalBundle).toHaveBeenCalledWith("wf_1");
  });

  it("releases the composer when a failed request starts reconciliation", async () => {
    const editDesign = vi.fn().mockRejectedValue(new Error("request failed"));
    const { dispatch, loadTerminalBundle, options } = revisionHarness(editDesign);
    const { result } = renderHook(() => useDesignRevisions(options));

    await act(async () => {
      await result.current.submitRevision();
    });

    expect(result.current.revisionBusy).toBe(false);
    expect(dispatch).toHaveBeenCalledWith({ type: "REVISION_FINISHED" });
    expect(loadTerminalBundle).toHaveBeenCalledWith("wf_1");
  });
});
