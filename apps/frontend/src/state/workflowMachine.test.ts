import { describe, expect, it } from "vitest";
import { actionIsSupported, initialWorkflowState, workflowReducer } from "./workflowMachine";
import type { ViewerBundle, WorkflowStatus } from "../api/schemas";

const runningStatus: WorkflowStatus = {
  workflow_id: "wf_1",
  status: "running",
  artifacts: {},
  warnings: [],
  errors: [],
  available_actions: [],
  unsupported_actions: []
};

const baseBundle: ViewerBundle = {
  workflow_id: "wf_1",
  status: "completed",
  generation_mode: "real_blender",
  generation_strategy: "parametric_scene_spec",
  geometry_source: "scene_spec",
  mesh_qa_level: "mesh_level_transform_basic",
  mesh_qa_passed: true,
  qa_score: 0.9,
  asset_import_summary: null,
  human_warnings_count: 0,
  human_errors_count: 0,
  primary_glb_url: "/designs/wf_1/artifacts/design.glb",
  preview_url: "/designs/wf_1/artifacts/preview.png",
  report_url: null,
  metadata_url: null,
  scene_spec_url: null,
  qa_report_url: null,
  generation_report_url: null,
  geometry_validation_url: null,
  rag_evidence_url: null,
  requirements_spec_url: null,
  extraction_report_url: null,
  llm_provider: "groq",
  llm_available: true,
  llm_fallback_used: false,
  llm_fallback_reason: null,
  rag_context_count: 1,
  rag_planning_summary: null,
  rag_reranker_provider: "nvidia",
  rag_reranker_model: "nvidia/llama-3.2-nv-rerankqa-1b-v2",
  rag_reranker_status: "available",
  rag_reranker_degraded_reason: null,
  memory_context_count: 0,
  qa_summary: {},
  viewer_artifacts: [],
  limitations: [],
  unsupported_actions: [],
  available_actions: []
};

describe("workflow reducer", () => {
  it("starts without a demo prompt baked into state", () => {
    expect(initialWorkflowState.prompt).toBe("");
  });

  it("keeps workflow tracking intact while the user drafts the next prompt", () => {
    const state = workflowReducer(
      {
        ...initialWorkflowState,
        phase: "completed",
        workflowId: "wf_old",
        viewerBundle: baseBundle,
        status: { ...runningStatus, status: "completed" },
        userIssues: {
          workflow_id: "wf_old",
          status: "completed",
          human_readable_issues: []
        },
        timeline: {
          workflow_id: "wf_old",
          status: "completed",
          event_source: "timeline_summary",
          timeline_steps: []
        }
      },
      { type: "PROMPT_CHANGED", prompt: "nouveau cahier de charge" }
    );

    expect(state.phase).toBe("completed");
    expect(state.prompt).toBe("nouveau cahier de charge");
    expect(state.workflowId).toBe("wf_old");
    expect(state.viewerBundle).toBe(baseBundle);
    expect(state.status?.status).toBe("completed");
    expect(state.userIssues?.workflow_id).toBe("wf_old");
    expect(state.timeline?.workflow_id).toBe("wf_old");
  });

  it("moves through submit, stream and completed states", () => {
    let state = workflowReducer(initialWorkflowState, { type: "SUBMIT_STARTED" });
    expect(state.phase).toBe("submitting");

    state = workflowReducer(state, { type: "DESIGN_CREATED", workflowId: "wf_1" });
    expect(state.phase).toBe("streaming");
    expect(state.runtimeMode).toBe("sse");

    state = workflowReducer(state, {
      type: "STATUS_LOADED",
      status: runningStatus
    });
    expect(state.phase).toBe("running");

    state = workflowReducer(state, {
      type: "EVENT_RECEIVED",
      event: {
        event_id: "evt_done",
        event_type: "workflow_completed",
        workflow_id: "wf_1",
        timestamp: "2026-06-16T10:00:00Z",
        phase: "completion",
        status: "completed",
        node: null,
        human_label: "Design prêt",
        progress_message: "Artefacts disponibles.",
        warnings: [],
        errors: [],
        artifact_refs: [],
        raw: {
          event_id: "evt_done",
          event_type: "workflow_completed",
          workflow_id: "wf_1",
          timestamp: "2026-06-16T10:00:00Z",
          payload: { artifact_refs: [], errors: [], warnings: [] }
        }
      }
    });
    expect(state.phase).toBe("completed");
  });

  it("keeps the active design until a new workflow is accepted", () => {
    const active = {
      ...initialWorkflowState,
      phase: "completed" as const,
      workflowId: "wf_active",
      viewerBundle: baseBundle,
      status: { ...runningStatus, status: "completed" }
    };

    const submitting = workflowReducer(active, { type: "SUBMIT_STARTED" });

    expect(submitting.pendingSubmission).toBe(true);
    expect(submitting.workflowId).toBe("wf_active");
    expect(submitting.viewerBundle).toBe(baseBundle);
    expect(submitting.phase).toBe("completed");

    const accepted = workflowReducer(submitting, {
      type: "DESIGN_CREATED",
      workflowId: "wf_new"
    });
    expect(accepted.pendingSubmission).toBe(false);
    expect(accepted.workflowId).toBe("wf_new");
    expect(accepted.viewerBundle).toBeNull();
  });

  it("restores an existing workflow without opening a new SSE submission", () => {
    const state = workflowReducer(initialWorkflowState, {
      type: "WORKFLOW_RESTORED",
      status: { ...runningStatus, workflow_id: "wf_existing" }
    });

    expect(state.workflowId).toBe("wf_existing");
    expect(state.phase).toBe("running");
    expect(state.runtimeMode).toBe("sse");
    expect(state.events).toEqual([]);
  });

  it("restores a completed workflow without reopening a live transport", () => {
    const state = workflowReducer(initialWorkflowState, {
      type: "WORKFLOW_RESTORED",
      status: { ...runningStatus, workflow_id: "wf_completed", status: "completed" }
    });

    expect(state.phase).toBe("completed");
    expect(state.runtimeMode).toBe("idle");
  });

  it("keeps provider degradation separate from 3D design quality", () => {
    const state = workflowReducer(
      {
        ...initialWorkflowState,
        phase: "completed",
        status: { ...runningStatus, status: "completed" }
      },
      {
        type: "VIEWER_BUNDLE_LOADED",
        viewerBundle: {
          ...baseBundle,
          llm_fallback_used: true
        }
      }
    );

    expect(state.phase).toBe("completed");
    expect(state.designQuality).toBe("valid");
    expect(state.providerHealth).toBe("degraded");
  });

  it("activates polling mode when SSE fails", () => {
    const state = workflowReducer(
      { ...initialWorkflowState, phase: "streaming", workflowId: "wf_1" },
      { type: "SSE_FAILED", message: "stream failed" }
    );

    expect(state.runtimeMode).toBe("polling");
    expect(state.phase).toBe("running");
    expect(state.transportError).toBe("stream failed");
  });

  it("keeps secondary resource failures separate from workflow truth", () => {
    const state = workflowReducer(
      {
        ...initialWorkflowState,
        phase: "completed",
        status: { ...runningStatus, status: "completed" },
        workflowId: "wf_1"
      },
      { type: "RESOURCE_FAILED", resource: "rag_evidence", message: "404" }
    );

    expect(state.phase).toBe("completed");
    expect(state.error).toBeNull();
    expect(state.resourceErrors.rag_evidence).toBe("404");
  });

  it("does not turn a completed workflow into failed when a command request fails", () => {
    const state = workflowReducer(
      {
        ...initialWorkflowState,
        phase: "completed",
        status: { ...runningStatus, status: "completed" },
        workflowId: "wf_1"
      },
      { type: "REQUEST_FAILED", message: "revision refused" }
    );

    expect(state.phase).toBe("completed");
    expect(state.error).toBe("revision refused");
  });

  it("keeps the active workflow while a revision is generated", () => {
    const state = workflowReducer(
      { ...initialWorkflowState, phase: "completed", workflowId: "wf_1" },
      { type: "REVISION_STARTED", runtimeMode: "sse" }
    );

    expect(state.workflowId).toBe("wf_1");
    expect(state.phase).toBe("running");
    expect(state.runtimeMode).toBe("sse");
  });

  it("starts a revision in explicit polling mode when no durable SSE cursor is available", () => {
    const state = workflowReducer(
      { ...initialWorkflowState, phase: "completed", workflowId: "wf_1" },
      { type: "REVISION_STARTED", runtimeMode: "polling" }
    );

    expect(state.phase).toBe("running");
    expect(state.runtimeMode).toBe("polling");
  });

  it("does not expose unsupported actions as available", () => {
    expect(actionIsSupported("rollback", [{ action: "rollback" }])).toBe(false);
    expect(actionIsSupported("download_artifacts", [{ action: "rollback" }])).toBe(true);
  });
});
