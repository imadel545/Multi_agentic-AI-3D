import { describe, expect, it } from "vitest";
import type { ViewerBundle } from "../../api/schemas";
import {
  hasUsableWebGL,
  resolveViewerSource,
  viewerBadges
} from "./viewerRules";

const toAbsolute = (url: string | null | undefined) => (url ? `http://127.0.0.1:8000${url}` : null);

const bundle: ViewerBundle = {
  workflow_id: "wf_1",
  status: "completed",
  generation_mode: "real_blender",
  generation_strategy: "parametric_scene_spec",
  geometry_source: "scene_spec",
  mesh_qa_level: "mesh_level_basic",
  mesh_qa_passed: true,
  qa_score: 0.88,
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

describe("viewer source rules", () => {
  it("uses only the backend primary GLB URL for 3D loading", () => {
    expect(resolveViewerSource(bundle, toAbsolute)).toMatchObject({
      kind: "glb",
      url: "http://127.0.0.1:8000/designs/wf_1/artifacts/design.glb"
    });
  });

  it("falls back to preview when GLB is absent", () => {
    expect(resolveViewerSource({ ...bundle, primary_glb_url: null }, toAbsolute)).toMatchObject({
      kind: "preview",
      url: "http://127.0.0.1:8000/designs/wf_1/artifacts/preview.png"
    });
  });

  it("shows workflow failure without loading unavailable preview artifacts", () => {
    expect(
      resolveViewerSource(
        {
          ...bundle,
          status: "failed",
          viewer_artifacts: [
            {
              name: "preview.png",
              url: "/designs/wf_1/artifacts/preview.png",
              content_type: "image/png",
              available: false
            }
          ]
        },
        toAbsolute
      )
    ).toMatchObject({
      kind: "error",
      previewUrl: null
    });
  });

  it("does not load GLB when the viewer artifact is explicitly unavailable", () => {
    expect(
      resolveViewerSource(
        {
          ...bundle,
          viewer_artifacts: [
            {
              name: "design.glb",
              url: "/designs/wf_1/artifacts/glb",
              content_type: "model/gltf-binary",
              available: false
            },
            {
              name: "preview.png",
              url: "/designs/wf_1/artifacts/preview.png",
              content_type: "image/png",
              available: true
            }
          ]
        },
        toAbsolute
      )
    ).toMatchObject({
      kind: "preview",
      url: "http://127.0.0.1:8000/designs/wf_1/artifacts/preview.png"
    });
  });

  it("surfaces QA and degraded badges honestly", () => {
    expect(
      viewerBadges({
        ...bundle,
        mesh_qa_passed: false,
        llm_fallback_used: true,
        rag_reranker_degraded_reason: "passthrough"
      })
    ).toEqual(
      expect.arrayContaining([
        "Blender réel",
        "mesh_level_basic",
        "QA attention",
        "Fallback LLM",
        "RAG dégradé"
      ])
    );
  });

  it("detects unavailable WebGL before mounting the Three.js canvas", () => {
    const fakeDocument = {
      createElement: () => ({
        getContext: () => null
      })
    } as unknown as Document;
    const fakeWindow = { WebGLRenderingContext: function WebGLRenderingContext() {} } as unknown as Window;

    expect(hasUsableWebGL(fakeDocument, fakeWindow)).toBe(false);
  });

  it("accepts WebGL when the browser can create a rendering context", () => {
    const fakeDocument = {
      createElement: () => ({
        getContext: (kind: string) => (kind === "webgl" ? {} : null)
      })
    } as unknown as Document;
    const fakeWindow = { WebGLRenderingContext: function WebGLRenderingContext() {} } as unknown as Window;

    expect(hasUsableWebGL(fakeDocument, fakeWindow)).toBe(true);
  });
});
