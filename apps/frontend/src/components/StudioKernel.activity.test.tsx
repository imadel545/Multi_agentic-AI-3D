import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AgentStageRail,
  AgentTimeline,
  IssuesPanel,
  VersionSummary,
  summarizeTimelineRows,
  summarizeUserIssues
} from "./StudioKernel";

afterEach(() => cleanup());

describe("studio kernel versions and workflow activity", () => {
  it("bounds version history and confirms a real rollback action", () => {
    const onRollback = vi.fn();
    render(
      <VersionSummary
        busyVersionId={null}
        canRollback
        message={null}
        onRollback={onRollback}
        versions={[
          {
            version_id: "v2",
            created_at: "2026-07-15T11:00:00Z",
            active: true,
            artifacts: {},
            status: "completed"
          },
          {
            version_id: "v1",
            created_at: "2026-07-15T10:00:00Z",
            active: false,
            artifacts: {},
            status: "completed"
          }
        ]}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Restaurer" }));
    expect(onRollback).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(onRollback).toHaveBeenCalledWith("v1");
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

    expect(screen.getByText("Conception du plan 3D")).toBeInTheDocument();
    expect(screen.queryByText("Construction du SceneSpec")).not.toBeInTheDocument();
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

    expect(summarized[0]?.title).toBe("Modèles non constructeur: 2 éléments");
    expect(summarized[1]?.title).toBe("Beamwidth warning");
    expect(summarized).toHaveLength(2);
  });

  it("translates inferred radio, azimuth mismatch, and degraded RAG issues", () => {
    const summarized = summarizeUserIssues([
      {
        title: "Mechanical tilt inferred as 3 degrees",
        severity: "warning",
        impact: "Mechanical tilt inferred as 3 degrees.",
        recommended_action: "Review.",
        technical_code: "RF_MECHANICAL_TILT_INFERRED"
      },
      {
        title: "sector_count_azimuth_mismatch",
        severity: "warning",
        impact: "sector_count_azimuth_mismatch: 2 azimuths for 3 sectors",
        recommended_action: "Review.",
        technical_code: "SECTOR_COUNT_AZIMUTH_MISMATCH"
      },
      {
        title: "Recherche RAG en mode dégradé",
        severity: "warning",
        impact: "Error code: 500",
        recommended_action: "Check Qdrant.",
        technical_code: "RAG_RERANKER_DEGRADED"
      },
      {
        title: "Extraction déterministe",
        severity: "warning",
        impact: "Raison: deterministic_extraction_requested.",
        recommended_action: "Configure GROQ_API_KEY.",
        technical_code: "LLM_FALLBACK"
      },
      {
        title: "No antenna model was confirmed in the document pack",
        severity: "warning",
        impact: "A generic network antenna family is used.",
        recommended_action: "Review.",
        technical_code: "DOCUMENT_DEFAULT"
      }
    ]);

    expect(summarized.map((issue) => issue.title)).toEqual([
      "Inclinaison mécanique proposée",
      "Azimuts complétés",
      "Recherche documentaire temporairement dégradée",
      "Compréhension en mode de secours",
      "Famille d’antenne générique"
    ]);
    expect(summarized.map((issue) => issue.impact).join(" ")).not.toContain("Error code");
    expect(summarized.map((issue) => issue.impact).join(" ")).not.toContain(
      "sector_count_azimuth_mismatch"
    );
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
      "Modèles non constructeur : 2 éléments"
    ]);
  });

  it("translates proof certification wording in the agent timeline", () => {
    const rows = summarizeTimelineRows([
      {
        id: "proof",
        label: "Certification des preuves",
        message: "Étape terminée : Certification des preuves.",
        phase: "workflow",
        status: "completed"
      }
    ]);

    expect(rows[0]?.label).toBe("Vérification des preuves");
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

  it("keeps historical revision failures visible as alerts on a restored design", () => {
    render(
      <AgentStageRail
        events={[]}
        phase="completed"
        timeline={{
          workflow_id: "wf_restored",
          status: "completed",
          event_source: "timeline_summary",
          timeline_steps: [
            {
              step: "generate_blender",
              label: "Blender",
              human_label: "Génération Blender",
              progress_message: "Révision interrompue.",
              phase: "blender",
              node: "generate_blender",
              status: "failed",
              timestamp: null,
              duration_ms: null,
              warnings_count: 0,
              errors_count: 1,
              artifact_refs: [],
              human_readable: "La version active reste disponible."
            }
          ]
        }}
      />
    );

    expect(screen.getByText("terminé avec alerte")).toBeVisible();
    expect(screen.queryByText("échec")).not.toBeInTheDocument();
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

    expect(screen.getByText("Compréhension de la demande").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Conception du plan 3D").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Construction du modèle 3D").closest("article")).toHaveTextContent("terminé");
  });

});
