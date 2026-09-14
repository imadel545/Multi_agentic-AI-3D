import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TelecomStudioApi } from "../api/client";
import type { DocumentPackSummary } from "../api/schemas";
import { initialWorkflowState } from "../state/workflowMachine";
import type { LoadSurfaceResource } from "./studioAppTypes";
import { useDocumentDesignFlow } from "./useDocumentDesignFlow";

const summary = (packId: string): DocumentPackSummary => ({
  pack_id: packId,
  status: "processed",
  document_count: 1,
  high_priority_count: 0,
  missing_blocking_count: 0,
  blocking_fields: [],
  conflict_count: 0,
  can_generate_design: false,
  qa_score: 1,
  processing_warning_count: 0,
  tool_status: {}
});

const loadSurfaceResource: LoadSurfaceResource = async (_resource, loader, onValue) => {
  const value = await loader();
  onValue(value);
  return value;
};

describe("useDocumentDesignFlow attachments", () => {
  it("restores, replaces and removes a chat attachment without starting generation", async () => {
    const restored = summary("pack_restored");
    const uploaded = summary("pack_uploaded");
    const apiClient = {
      documentPackSummary: vi.fn().mockResolvedValue(restored),
      createDocumentPack: vi.fn().mockResolvedValue(uploaded),
      deleteDocumentPack: vi.fn().mockResolvedValue(undefined),
      createDesign: vi.fn()
    } as unknown as TelecomStudioApi;
    const onDocumentPackDetached = vi.fn().mockResolvedValue(undefined);
    const onDocumentPackLinked = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() => useDocumentDesignFlow({
      apiClient,
      beginCreatedWorkflow: vi.fn(),
      chatId: "chat_1",
      clearRevisionMessages: vi.fn(),
      closeEventStream: vi.fn(),
      dispatch: vi.fn(),
      documentCapabilities: null,
      initialDocumentPackId: restored.pack_id,
      initialWorkflowId: null,
      invalidateBootstrapRestore: vi.fn(),
      loadSurfaceResource,
      onDocumentPackDetached,
      onDocumentPackLinked,
      state: initialWorkflowState,
      submissionInFlightRef: { current: false }
    }));

    await waitFor(() => expect(result.current.documentPackSummary?.pack_id).toBe("pack_restored"));
    expect(result.current.documentPackMessage).toContain("pièce jointe restaurée");
    expect(result.current.documentPackMessageStatus).toBe("info");

    await act(async () => {
      await result.current.uploadDocumentPack([
        new File(["plan"], "plan.pdf", { type: "application/pdf" })
      ]);
    });
    expect(result.current.documentPackSummary?.pack_id).toBe("pack_uploaded");
    expect(onDocumentPackLinked).toHaveBeenCalledWith("pack_uploaded");
    expect(apiClient.createDesign).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.detachDocumentPack();
    });
    expect(apiClient.deleteDocumentPack).toHaveBeenCalledWith("pack_uploaded", "chat_1");
    expect(onDocumentPackDetached).toHaveBeenCalledWith("pack_uploaded");
    expect(result.current.documentPackSummary).toBeNull();
    expect(result.current.documentPackMessage).toContain("retiré de cette conversation");
    expect(result.current.documentPackMessageStatus).toBe("removal_confirmed");
    expect(apiClient.createDesign).not.toHaveBeenCalled();
  });

  it("keeps the attachment visible when server removal fails", async () => {
    const restored = summary("pack_retained");
    const apiClient = {
      documentPackSummary: vi.fn().mockResolvedValue(restored),
      deleteDocumentPack: vi.fn().mockRejectedValue(new Error("storage unavailable"))
    } as unknown as TelecomStudioApi;

    const { result } = renderHook(() => useDocumentDesignFlow({
      apiClient,
      beginCreatedWorkflow: vi.fn(),
      chatId: "chat_1",
      clearRevisionMessages: vi.fn(),
      closeEventStream: vi.fn(),
      dispatch: vi.fn(),
      documentCapabilities: null,
      initialDocumentPackId: restored.pack_id,
      initialWorkflowId: null,
      invalidateBootstrapRestore: vi.fn(),
      loadSurfaceResource,
      state: initialWorkflowState,
      submissionInFlightRef: { current: false }
    }));

    await waitFor(() => expect(result.current.documentPackSummary?.pack_id).toBe("pack_retained"));
    await act(async () => {
      await result.current.detachDocumentPack();
    });

    expect(result.current.documentPackSummary?.pack_id).toBe("pack_retained");
    expect(result.current.documentPackMessage).toBeTruthy();
    expect(result.current.documentPackMessageStatus).toBe("error");
  });
});
