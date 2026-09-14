import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LiveGenerationOverlay,
  InspectorDock,
  displayIssueCount
} from "./StudioKernel";
import { bundle } from "./StudioKernel.testFixtures";

afterEach(() => cleanup());

describe("studio kernel contextual inspection", () => {
  it("keeps inspector content behind contextual drawers", () => {
    render(
      <InspectorDock
        bundle={bundle}
        canRollback={false}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    expect(screen.queryByLabelText("Composition de la scène")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ouvrir le panneau d’inspection" }));
    expect(screen.getByRole("dialog")).not.toHaveAttribute("aria-modal");
    expect(screen.getByLabelText("Composition de la scène")).toHaveTextContent("Aucun élément 3D disponible");
    expect(screen.getAllByRole("button").filter((button) =>
      ["Composition", "Livrables", "Versions"].includes(button.textContent ?? "")
    )).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Vue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vérification" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bibliothèque" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the inspector limited to composition, deliverables and versions when inventory is loaded", () => {
    render(
      <InspectorDock
        assetInventory={{
          status: "qualified_mixed_catalog",
          asset_count: 0,
          missing_file_count: 0,
          real_glb_asset_count: 0,
          import_qualified_glb_count: 0,
          generation_eligible_asset_count: 0,
          professional_evidence_asset_count: 0,
          reference_only_asset_count: 0,
          qualified_integrity_failure_count: 0,
          entries: [],
          missing_files: []
        }}
        bundle={{
          ...bundle,
          rag_evidence_url: "/designs/wf_1/artifacts/rag_evidence",
          rag_retrieval_status: "degraded_local_lexical"
        }}
        canRollback={false}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Ouvrir le panneau d’inspection" }));
    expect(screen.getByRole("button", { name: "Composition" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Livrables" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Versions" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bibliothèque" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vérification" })).not.toBeInTheDocument();
  });

  it("does not turn workflow limits into a global inspector section", () => {
    const repeatedFailure = "La géométrie demandée hors catalogue n'a pas pu être produite; Blender n'a pas été lancé.";
    render(
      <InspectorDock
        bundle={{
          ...bundle,
          status: "failed",
          generation_mode: "not_generated",
          mesh_qa_passed: false,
          qa_summary: {
            qa_status: "not_started",
            qa_executed: false,
            blocked_before_qa: true,
            checks_passed: [],
            checks_failed: [],
            warnings: [],
            errors: [],
            upstream_errors: ["GEOMETRY_PROGRAM_GENERATION_FAILED"],
            limitations: []
          }
        }}
        canRollback={false}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    expect(screen.queryByText(repeatedFailure)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ouvrir le panneau d’inspection" }));
    expect(screen.queryByRole("button", { name: /Vérification/ })).not.toBeInTheDocument();
    expect(screen.queryByText(repeatedFailure)).not.toBeInTheDocument();
    expect(screen.queryByText("GEOMETRY_PROGRAM_GENERATION_FAILED")).not.toBeInTheDocument();
  });

  it("groups repeated asset warnings in the displayed issue count", () => {
    expect(
      displayIssueCount(
        {
          workflow_id: "wf_1",
          status: "completed",
          human_readable_issues: [
            {
              title: "Asset warning",
              severity: "warning",
              impact: "NOT_VENDOR_GRADE",
              recommended_action: "Review",
              technical_code: "ASSET_NOT_VENDOR_GRADE"
            },
            {
              title: "Asset warning",
              severity: "warning",
              impact: "NOT_VENDOR_GRADE",
              recommended_action: "Review",
              technical_code: "ASSET_NOT_VENDOR_GRADE"
            }
          ]
        },
        bundle
      )
    ).toBe(1);
  });

  it("announces real workflow activity without inventing progress", () => {
    render(
      <LiveGenerationOverlay
        events={[]}
        operation={{
          has_current_operation: true,
          workflow_id: "wf_1",
          status: "running",
          current_operation: "assemble_scene",
          is_running: true,
          is_terminal: false,
          unsupported_actions: [],
          available_actions: [],
          human_label: "Assemblage Blender",
          progress_message: "Positionnement des composants sélectionnés.",
          event_source: "push_sse",
          last_event_id: null,
          updated_at: "2026-07-31T10:00:00Z",
          polling_hint_seconds: 2,
          warnings_count: 0,
          errors_count: 0
        }}
        phase="running"
        runtimeMode="sse"
        timeline={null}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent("Construction du modèle 3D");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Le modèle est construit puis vérifié avant de devenir la version active."
    );
    expect(screen.getByRole("status")).not.toHaveTextContent("Blender");
    expect(screen.getByRole("status")).not.toHaveTextContent("%");
  });

  it("does not reuse a terminal operation as live revision progress", () => {
    render(
      <LiveGenerationOverlay
        events={[]}
        intent="revision"
        operation={{
          has_current_operation: false,
          workflow_id: "wf_1",
          status: "completed",
          current_operation: "Le design est terminé.",
          is_running: false,
          is_terminal: true,
          unsupported_actions: [],
          available_actions: [],
          human_label: "Workflow terminé",
          progress_message: "Le design est terminé.",
          event_source: "push_sse",
          last_event_id: "evt_old",
          updated_at: "2026-07-31T10:00:00Z",
          polling_hint_seconds: 2,
          warnings_count: 0,
          errors_count: 0
        }}
        phase="running"
        runtimeMode="sse"
        timeline={null}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent("Modification du design");
    expect(screen.getByRole("status")).not.toHaveTextContent("Workflow terminé");
  });
});
