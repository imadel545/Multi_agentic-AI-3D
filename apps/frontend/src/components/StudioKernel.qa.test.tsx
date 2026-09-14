import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  BackendStatusBar,
  QaPanel,
  conversationHistoryEntries,
  meshQaLevelLabel
} from "./StudioKernel";
import { bundle, parsedRequirements } from "./StudioKernel.testFixtures";

afterEach(() => cleanup());

describe("studio kernel QA and design truth", () => {
  it("restores user-authored version instructions chronologically as user messages", () => {
    const entries = conversationHistoryEntries({
      activeRequirements: parsedRequirements.requirements,
      currentPrompt: "",
      versions: [{
        version_id: "v3",
        parent_version_id: "v2",
        created_at: "2026-08-02T11:00:00Z",
        active: true,
        artifacts: {},
        qa_score: 1,
        generation_mode: "real_blender",
        llm_decision_provenance: null,
        edit_description: "Orienter le secteur nord à 15 degrés",
        diff_summary: null,
        status: "completed"
      }, {
        version_id: "v2",
        parent_version_id: "v1",
        created_at: "2026-08-02T10:00:00Z",
        active: false,
        artifacts: {},
        qa_score: 1,
        generation_mode: "real_blender",
        llm_decision_provenance: null,
        edit_description: "Ajouter un cabinet au sol",
        diff_summary: null,
        status: "completed"
      }, {
        version_id: "v1",
        parent_version_id: null,
        created_at: "2026-08-02T09:00:00Z",
        active: false,
        artifacts: {},
        qa_score: 1,
        generation_mode: "real_blender",
        llm_decision_provenance: null,
        edit_description: "initial from confirmed_requirement_spec",
        diff_summary: null,
        status: "completed"
      }]
    });

    expect(entries).toMatchObject([
      {
        label: "Contexte actif restauré",
        message: "5G · pylône treillis · 30 m · 3 secteur(s)",
        role: "system"
      },
      {
        label: "Vous · modification enregistrée",
        message: "Ajouter un cabinet au sol",
        role: "user"
      },
      {
        label: "Vous · modification active",
        message: "Orienter le secteur nord à 15 degrés",
        role: "user"
      }
    ]);
  });
  it("keeps component geometry fidelity visible independently from QA proof", () => {
    render(
      <BackendStatusBar
        bundle={{
          ...bundle,
          generation_mode: "real_blender",
          mesh_qa_passed: true,
          completion_certificate_status: "issued",
          geometry_fidelity_summary: {
            component_count: 7,
            counts: {
              schematic: 1,
              technical_generic: 6,
              vendor_qualified: 0
            },
            roles: {
              schematic: ["tower"],
              technical_generic: ["antenna", "radio"],
              vendor_qualified: []
            }
          }
        }}
        health={{
          status: "ok",
          service: "agentic_telecom_3d_studio_api",
          version: "1.0.0",
          api_contract_version: "2026-07-29"
        }}
        issues={null}
        phase="completed"
      />
    );

    expect(screen.getByText("Fidélité technique générique")).toHaveAttribute(
      "data-geometry-fidelity",
      "technical_generic"
    );
    expect(screen.queryByText(/Modèle fournisseur qualifié/)).not.toBeInTheDocument();
  });

  it("translates spatial QA codes into operator language", () => {
    expect(meshQaLevelLabel("mesh_level_spatial_basic")).toBe("QA spatiale AABB");
    render(
      <QaPanel
        bundle={{
          ...bundle,
          mesh_qa_level: "mesh_level_spatial_basic",
          mesh_qa_passed: true,
          completion_certificate_status: "issued"
        }}
      />
    );

    expect(screen.getByText("QA spatiale AABB")).toBeInTheDocument();
    expect(screen.getByText("interférences contrôlées")).toBeInTheDocument();
    expect(screen.getByText("vérifiée localement")).toBeInTheDocument();
    expect(screen.queryByText("mesh_level_spatial_basic")).not.toBeInTheDocument();
  });

  it("states that QA did not run when generation was blocked before Blender", () => {
    render(
      <QaPanel
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
      />
    );

    expect(screen.getByText("Validation 3D non exécutée")).toBeInTheDocument();
    expect(screen.getByText(/bloquée avant la QA/)).toBeInTheDocument();
    expect(screen.queryByText("Aucun échec QA remonté.")).not.toBeInTheDocument();
    expect(screen.queryByText("GEOMETRY_PROGRAM_GENERATION_FAILED")).not.toBeInTheDocument();
  });

  it("separates deterministic framing from advisory visual review", () => {
    render(
      <QaPanel
        bundle={{
          ...bundle,
          qa_summary: {
            ...bundle.qa_summary,
            checks_passed: bundle.qa_summary?.checks_passed ?? [],
            checks_failed: bundle.qa_summary?.checks_failed ?? [],
            warnings: bundle.qa_summary?.warnings ?? [],
            errors: bundle.qa_summary?.errors ?? [],
            upstream_errors: bundle.qa_summary?.upstream_errors ?? [],
            limitations: bundle.qa_summary?.limitations ?? [],
            preview_pixel_framing_qa: true,
            preview_subject_framing_valid: true,
            preview_subject_bbox_width_ratio: 0.62,
            preview_subject_bbox_height_ratio: 0.84,
            preview_subject_min_edge_margin_ratio: 0.08
          },
          visual_review: {
            status: "review_required",
            advisory_only: true,
            summary: "Un support est partiellement masqué.",
            findings: ["Vérifier la lisibilité du support"],
            limitations: []
          }
        }}
      />
    );

    expect(screen.getByRole("region", { name: "Cadrage technique" })).toHaveTextContent("conforme");
    expect(screen.getByRole("region", { name: "Revue visuelle assistée" })).toHaveTextContent(
      "consultative"
    );
    expect(screen.queryByText(/QA visuelle 100/i)).not.toBeInTheDocument();
  });

  it("explains post-export assembly measurements without claiming professional validation", () => {
    render(
      <QaPanel
        bundle={{
          ...bundle,
          assembly_constraint_summary: {
            status: "passed",
            measurement_scope: "exported_glb_anchor_frames",
            required_connection_count: 8,
            measured_instance_count: 14,
            resolved_support_count: 3,
            max_position_error_m: 0.012,
            max_angular_error_deg: 0.45,
            limitations: [
              "Required non-mechanical connections are reported but are not geometrically evaluated by AssemblyConstraintEvidence v1."
            ]
          },
          constraint_evidence_url: "/designs/wf_1/artifacts/constraint_evidence"
        }}
        toAbsoluteUrl={(url) => url ? `http://127.0.0.1:8000${url}` : null}
      />
    );

    const assembly = screen.getByRole("region", { name: "Assemblage post-export" });
    expect(assembly).toHaveTextContent("contrôle passé");
    expect(assembly).toHaveTextContent("8");
    expect(assembly).toHaveTextContent("14");
    expect(assembly).toHaveTextContent("Supports d’adaptation observés");
    expect(assembly).toHaveTextContent("3");
    expect(assembly).toHaveTextContent("0,012 m");
    expect(assembly).toHaveTextContent("0,45°");
    expect(assembly).toHaveTextContent(
      "Les connexions requises non mécaniques sont signalées, mais ne sont pas encore mesurées géométriquement."
    );
    expect(assembly).toHaveTextContent(/ne constitue ni une validation d.ingénierie ni une preuve professionnelle/i);
    expect(screen.getByRole("link", { name: "Consulter la preuve de mesure" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/designs/wf_1/artifacts/constraint_evidence"
    );
  });

  it("does not invent post-export assembly evidence when the backend omits it", () => {
    render(<QaPanel bundle={bundle} />);

    expect(screen.queryByRole("region", { name: "Assemblage post-export" })).not.toBeInTheDocument();
  });

  it("does not present placeholder counts as measurements when assembly evidence is unavailable", () => {
    render(
      <QaPanel
        bundle={{
          ...bundle,
          assembly_constraint_summary: {
            status: "not_available",
            measurement_scope: "exported_glb_anchor_frames",
            required_connection_count: 0,
            measured_instance_count: 0,
            resolved_support_count: 0,
            max_position_error_m: 0,
            max_angular_error_deg: 0,
            limitations: ["Le rapport de mesure n’a pas été produit."]
          }
        }}
      />
    );

    const assembly = screen.getByRole("region", { name: "Assemblage post-export" });
    expect(assembly).toHaveTextContent("mesure indisponible");
    expect(assembly).toHaveTextContent("Le rapport de mesure n’a pas été produit.");
    expect(assembly).not.toHaveTextContent("Erreur de position max.");
    expect(assembly).not.toHaveTextContent("Instances mesurées");
  });

});
