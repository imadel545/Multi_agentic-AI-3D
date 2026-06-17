import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ViewerBundle } from "../api/schemas";
import {
  AgentStageRail,
  AgentTimeline,
  ChatCommandPanel,
  InspectorDock,
  IssuesPanel,
  RagEvidencePanel,
  RuntimeCapabilitiesPanel,
  SummaryPanel,
  summarizeTimelineRows,
  summarizeUserIssues
} from "./StudioKernel";

const bundle: ViewerBundle = {
  workflow_id: "wf_1",
  status: "completed",
  generation_mode: "real_blender",
  generation_strategy: "parametric_scene_spec",
  geometry_source: "scene_spec",
  mesh_qa_level: "mesh_level_basic",
  mesh_qa_passed: false,
  qa_score: 0.67,
  asset_import_summary: null,
  human_warnings_count: 1,
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
  rag_context_count: 0,
  rag_planning_summary: null,
  rag_reranker_provider: "nvidia",
  rag_reranker_model: "nvidia/llama-3.2-nv-rerankqa-1b-v2",
  rag_reranker_status: "passthrough",
  rag_reranker_degraded_reason: "NVIDIA reranker unavailable",
  memory_context_count: 0,
  qa_summary: {},
  viewer_artifacts: [],
  limitations: [],
  unsupported_actions: [{ action: "download_artifacts", reason: "missing artifact" }],
  available_actions: []
};

const commandDefaults = {
  canEdit: false,
  documentCapabilities: null,
  documentPackBusy: false,
  documentPackMessage: null,
  documentPackSummary: null,
  editMessage: null,
  error: null,
  onDocumentPackGenerate: vi.fn(),
  onDocumentPackUpload: vi.fn(),
  onPromptChange: vi.fn(),
  onRevisionPromptChange: vi.fn(),
  onRevisionSubmit: vi.fn(),
  onSubmit: vi.fn(),
  phase: "idle" as const,
  prompt: "",
  revisionPrompt: ""
};

afterEach(() => cleanup());

describe("studio kernel components", () => {
  it("submits the real prompt command from the chat panel", async () => {
    const onSubmit = vi.fn();
    const onPromptChange = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        onPromptChange={onPromptChange}
        onSubmit={onSubmit}
        prompt="site 5G"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Générer le design" }));

    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("keeps the command field real and only injects an example when requested", () => {
    const onPromptChange = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        onPromptChange={onPromptChange}
      />
    );

    expect(screen.getByLabelText("Design prompt")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Exemple complet" }));
    expect(onPromptChange).toHaveBeenCalledWith(expect.stringContaining("Créer un site 5G"));
  });

  it("shows a connected revision command only when edit is available", () => {
    const onRevisionSubmit = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        canEdit
        editMessage="Édition appliquée"
        onRevisionSubmit={onRevisionSubmit}
        phase="completed"
        revisionPrompt="ajoute un cabinet"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Appliquer la révision" }));

    expect(onRevisionSubmit).toHaveBeenCalledOnce();
    expect(screen.getByText("Édition appliquée")).toBeInTheDocument();
  });

  it("renders human labels instead of Python node names as the main timeline copy", () => {
    render(
      <AgentTimeline
        events={[
          {
            event_id: "evt_1",
            event_type: "node_started",
            workflow_id: "wf_1",
            timestamp: "2026-06-16T10:00:00Z",
            phase: "planning",
            status: "running",
            node: "scene_planner_node",
            human_label: "Construction du SceneSpec",
            progress_message: "Les contraintes telecom deviennent une scène.",
            warnings: [],
            errors: [],
            artifact_refs: [],
            raw: {
              event_id: "evt_1",
              event_type: "node_started",
              workflow_id: "wf_1",
              timestamp: "2026-06-16T10:00:00Z",
              payload: { artifact_refs: [], errors: [], warnings: [] }
            }
          }
        ]}
        timeline={null}
      />
    );

    expect(screen.getByText("Construction du SceneSpec")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "scene_planner_node" })).not.toBeInTheDocument();
  });

  it("shows user issue impact and recommended action", () => {
    render(
      <IssuesPanel
        issues={{
          workflow_id: "wf_1",
          status: "completed",
          human_readable_issues: [
            {
              title: "QA géométrique limitée",
              severity: "warning",
              impact: "La scène est exploitable mais pas vendor-grade.",
              recommended_action: "Inspecter le GLB avant livraison.",
              technical_code: "MESH_QA_BASIC"
            }
          ]
        }}
      />
    );

    expect(screen.getByText("QA géométrique limitée")).toBeInTheDocument();
    expect(screen.getByText("Inspecter le GLB avant livraison.")).toBeInTheDocument();
  });

  it("groups repeated asset issues into readable product warnings", () => {
    const summarized = summarizeUserIssues([
      {
        title: "Issue asset détectée",
        severity: "warning",
        impact: "ANT_PANEL_5G_001: INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
        recommended_action: "Do not market as vendor-grade.",
        technical_code: "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE"
      },
      {
        title: "Issue asset détectée",
        severity: "warning",
        impact: "RRU_SMALL_001: CC_BY_ASSET_NOT_VENDOR_GRADE",
        recommended_action: "Do not market as vendor-grade.",
        technical_code: "CC_BY_ASSET_NOT_VENDOR_GRADE"
      },
      {
        title: "Beamwidth warning",
        severity: "warning",
        impact: "Beamwidth is narrow for 3 sectors.",
        recommended_action: "Review sector assumptions.",
        technical_code: "BEAMWIDTH_NARROW"
      }
    ]);

    expect(summarized[0]?.title).toBe("Assets non vendor-grade: 2 éléments");
    expect(summarized).toHaveLength(2);
  });

  it("groups repeated asset timeline rows before the terminal workflow row", () => {
    const rows = summarizeTimelineRows([
      {
        id: "asset-1",
        label: "Issue asset détectée",
        message: "ANT_PANEL_5G_001: INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
        phase: "issues",
        status: "completed"
      },
      {
        id: "asset-2",
        label: "Issue asset détectée",
        message: "RRU_SMALL_001: CC_BY_ASSET_NOT_VENDOR_GRADE",
        phase: "issues",
        status: "completed"
      },
      {
        id: "done",
        label: "Design prêt",
        message: "Workflow completed.",
        phase: "workflow",
        status: "completed"
      }
    ]);

    expect(rows.map((row) => row.label)).toEqual([
      "Design prêt",
      "Assets non vendor-grade: 2 éléments"
    ]);
  });

  it("does not leave unreported stages as pending after a completed workflow", () => {
    render(
      <AgentStageRail
        events={[]}
        phase="completed"
        timeline={{
          workflow_id: "wf_1",
          status: "completed",
          event_source: "timeline_summary",
          timeline_steps: [
            {
              step: "qa",
              label: "QA",
              human_label: "QA",
              progress_message: "QA passed.",
              phase: "qa",
              status: "passed",
              timestamp: null,
              duration_ms: null,
              warnings_count: 0,
              errors_count: 0,
              artifact_refs: [],
              human_readable: "QA passed."
            }
          ]
        }}
      />
    );

    expect(screen.getAllByText("non reporté").length).toBeGreaterThan(0);
    expect(screen.getAllByText("terminé").length).toBeGreaterThan(0);
  });

  it("maps real backend nodes to product stages", () => {
    render(
      <AgentStageRail
        events={[]}
        phase="completed"
        timeline={{
          workflow_id: "wf_1",
          status: "completed",
          event_source: "timeline_summary",
          timeline_steps: [
            {
              step: "extract_requirements",
              label: "Extraction",
              human_label: "Analyse du besoin",
              progress_message: "Extraction terminée.",
              phase: "extraction",
              node: "extract_requirements",
              status: "completed",
              timestamp: null,
              duration_ms: null,
              warnings_count: 0,
              errors_count: 0,
              artifact_refs: [],
              human_readable: "Extraction terminée."
            },
            {
              step: "plan_scene",
              label: "SceneSpec",
              human_label: "Construction SceneSpec",
              progress_message: "SceneSpec créé.",
              phase: "planning",
              node: "plan_scene",
              status: "completed",
              timestamp: null,
              duration_ms: null,
              warnings_count: 0,
              errors_count: 0,
              artifact_refs: [],
              human_readable: "SceneSpec créé."
            },
            {
              step: "generate_blender",
              label: "Blender",
              human_label: "Génération Blender",
              progress_message: "GLB exporté.",
              phase: "blender",
              node: "generate_blender",
              status: "completed",
              timestamp: null,
              duration_ms: null,
              warnings_count: 0,
              errors_count: 0,
              artifact_refs: [],
              human_readable: "GLB exporté."
            }
          ]
        }}
      />
    );

    expect(screen.getByText("Compréhension").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Plan SceneSpec").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Génération 3D").closest("article")).toHaveTextContent("terminé");
  });

  it("does not invent RAG evidence when the artifact is absent", () => {
    render(<RagEvidencePanel bundle={bundle} evidence={null} />);

    expect(screen.getByText("Aucune preuve RAG chargée; le frontend n’en invente pas.")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA reranker unavailable")).toBeInTheDocument();
  });

  it("does not present artifact URLs as usable when the workflow failed", () => {
    render(
      <SummaryPanel
        bundle={{ ...bundle, status: "failed", primary_glb_url: "/designs/wf_1/artifacts/glb" }}
        issues={null}
        summary={null}
        versions={[]}
      />
    );

    expect(screen.getByText("Workflow échoué")).toBeInTheDocument();
    expect(screen.getByText("GLB: absent car workflow échoué")).toBeInTheDocument();
  });

  it("summarizes RAG evidence before raw details", () => {
    render(
      <RagEvidencePanel
        bundle={{ ...bundle, rag_reranker_status: "primary_nvidia_reranker" }}
        evidence={{
          rag_used_for_extraction: false,
          rag_used_for_planning: true,
          candidate_hint_fields: ["include_labels", "antenna_install_height_m"],
          limitations: ["RAG is controlled planning context."],
          contexts: [
            {
              filename: "scene_templates.md",
              reason: "Structured planning hints available.",
              score: 12.25
            }
          ]
        }}
      />
    );

    expect(screen.getByText("Hints contrôlés autorisés")).toBeInTheDocument();
    expect(screen.getByText("include_labels")).toBeInTheDocument();
    expect(screen.getByText("scene_templates.md")).toBeInTheDocument();
    expect(screen.getByText("Données RAG techniques")).toBeInTheDocument();
  });

  it("does not render unsupported actions as buttons", () => {
    render(
      <RuntimeCapabilitiesPanel
        bundle={bundle}
        documentCapabilities={null}
        inventory={null}
        summary={null}
      />
    );

    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    expect(screen.getByText(/download_artifacts/)).toBeInTheDocument();
  });

  it("keeps inspector content behind contextual drawers", () => {
    render(
      <InspectorDock
        bundle={bundle}
        documentCapabilities={null}
        events={[]}
        evidence={{
          candidate_hint_fields: ["include_labels"],
          contexts: [],
          limitations: [],
          rag_used_for_extraction: false,
          rag_used_for_planning: true
        }}
        inventory={null}
        issues={null}
        summary={null}
        timeline={null}
        toAbsoluteUrl={(url) => url ?? null}
        versions={[]}
      />
    );

    expect(screen.queryByLabelText("Résumé produit")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Résumé" }));
    expect(screen.getByLabelText("Résumé produit")).toHaveTextContent("Résumé du design");
    fireEvent.click(screen.getByRole("button", { name: /Agents/ }));
    expect(screen.getByLabelText("Timeline agents")).toHaveTextContent("Narration du workflow");
    fireEvent.click(screen.getByRole("button", { name: /RAG/ }));
    expect(screen.getByLabelText("RAG evidence")).toHaveTextContent("include_labels");
  });
});
