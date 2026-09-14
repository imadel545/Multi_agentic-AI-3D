import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TelecomStudioApi } from "../api/client";
import type { WorkflowStatus } from "../api/schemas";
import { initialWorkflowState } from "../state/workflowMachine";
import type { LoadSurfaceResource } from "./studioAppTypes";
import { useWorkflowLifecycle } from "./useWorkflowLifecycle";

afterEach(() => vi.restoreAllMocks());

describe("useWorkflowLifecycle", () => {
  it("restores a workflow linked after the chat first renders", async () => {
    const status = {
      workflow_id: "wf_linked",
      status: "completed",
      artifacts: {},
      warnings: [],
      errors: [],
      unsupported_actions: [],
      available_actions: []
    } as WorkflowStatus;
    const apiClient = {
      workflowStatus: vi.fn().mockResolvedValue(status),
      currentOperation: vi.fn().mockResolvedValue({ workflow_id: status.workflow_id }),
      viewerBundle: vi.fn().mockResolvedValue({ workflow_id: status.workflow_id }),
      timelineSummary: vi.fn().mockResolvedValue({ workflow_id: status.workflow_id }),
      userIssues: vi.fn().mockResolvedValue({ workflow_id: status.workflow_id }),
      versions: vi.fn().mockResolvedValue([]),
      studioSummary: vi.fn().mockResolvedValue({})
    } as unknown as TelecomStudioApi;
    const dispatch = vi.fn();
    const loadSurfaceResource = (async (_resource, loader, onValue) => {
      const value = await loader();
      onValue(value);
      return value;
    }) as LoadSurfaceResource;
    const submissionInFlightRef = { current: false };

    const { rerender } = renderHook(
      ({ initialWorkflowId }: { initialWorkflowId: string | null }) => useWorkflowLifecycle({
        apiClient,
        dispatch,
        initialWorkflowId,
        loadSurfaceResource,
        state: initialWorkflowState,
        submissionInFlightRef
      }),
      { initialProps: { initialWorkflowId: null as string | null } }
    );

    expect(apiClient.workflowStatus).not.toHaveBeenCalled();

    rerender({ initialWorkflowId: status.workflow_id });

    await waitFor(() => expect(dispatch).toHaveBeenCalledWith({
      type: "WORKFLOW_RESTORED",
      status
    }));
    expect(apiClient.workflowStatus).toHaveBeenCalledWith(status.workflow_id);
  });
});
