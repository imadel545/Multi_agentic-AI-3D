import { describe, expect, it } from "vitest";
import {
  ContractValidationError,
  ViewerBundleSchema,
  WorkflowEventSchema,
  parseContract
} from "./schemas";

const viewerBundlePayload = {
  workflow_id: "wf_123",
  status: "completed",
  generation_mode: "real_blender",
  mesh_qa_level: "mesh_level_transform_basic",
  mesh_qa_passed: true,
  qa_score: 0.91,
  primary_glb_url: "/designs/wf_123/artifacts/design.glb",
  preview_url: "/designs/wf_123/artifacts/preview.png",
  rag_context_count: 3,
  viewer_artifacts: [
    {
      name: "design.glb",
      url: "/designs/wf_123/artifacts/design.glb",
      content_type: "model/gltf-binary",
      available: true
    }
  ],
  limitations: [],
  unsupported_actions: []
};

describe("frontend contract schemas", () => {
  it("accepts real backend style viewer payloads", () => {
    const parsed = parseContract("ViewerBundle", ViewerBundleSchema, viewerBundlePayload);

    expect(parsed.primary_glb_url).toBe("/designs/wf_123/artifacts/design.glb");
    expect(parsed.viewer_artifacts).toHaveLength(1);
  });

  it("rejects local filesystem paths in public payloads", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        primary_glb_url: "/Users/imad/Desktop/output.glb"
      })
    ).toThrow(ContractValidationError);
  });

  it("rejects internal path fields even when nested", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        viewer_artifacts: [
          {
            name: "design.glb",
            url: "/designs/wf_123/artifacts/design.glb",
            content_type: "model/gltf-binary",
            available: true,
            local_path: "/tmp/design.glb"
          }
        ]
      })
    ).toThrow(ContractValidationError);
  });

  it("accepts normalized event fields from the backend", () => {
    const parsed = parseContract("WorkflowEvent", WorkflowEventSchema, {
      event_id: "evt_1",
      event_type: "node_started",
      workflow_id: "wf_123",
      timestamp: "2026-06-16T10:00:00Z",
      event_source: "langgraph",
      payload: {
        phase: "planning",
        node: "scene_planner",
        human_label: "Construction SceneSpec",
        progress_message: "Le planner structure la scène.",
        status: "running",
        warnings: [],
        errors: [],
        artifact_refs: []
      }
    });

    expect(parsed.payload.human_label).toBe("Construction SceneSpec");
  });
});
