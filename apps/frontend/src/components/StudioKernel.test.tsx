import { AssetLibraryPanel } from "./AssetLibraryPanel";
import { SceneCompositionPanel } from "./SceneCompositionPanel";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewerBundleSchema, type ViewerBundle } from "../api/schemas";
import {
  AgentStageRail,
  AgentTimeline,
  ArtifactsPanel,
  BackendStatusBar,
  ChatCommandPanel,
  LiveGenerationOverlay,
  InspectorDock,
  IssuesPanel,
  QaPanel,
  RagEvidencePanel,
  RuntimeCapabilitiesPanel,
  SummaryPanel,
  VersionSummary,
  conversationHistoryEntries,
  displayIssueCount,
  humanRagLimitation,
  humanRequirementWarning,
  meshQaLevelLabel,
  summarizeAdaptationCapabilityGroups,
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
  qa_summary: {
    checks_passed: [],
    checks_failed: [],
    warnings: [],
    errors: [],
    upstream_errors: [],
    limitations: []
  },
  viewer_artifacts: [],
  limitations: [],
  unsupported_actions: [{ action: "download_artifacts", reason: "missing artifact" }],
  available_actions: []
};

const commandDefaults = {
  analysis: null,
  analysisBusy: false,
  analysisError: null,
  analysisSubmitted: false,
  canEdit: false,
  correctionBusy: false,
  documentCapabilities: null,
  documentPackBusy: false,
  documentPackMessage: null,
  documentPackReview: null,
  documentPackSummary: null,
  editMessage: null,
  error: null,
  onAnalyze: vi.fn(),
  onConfirm: vi.fn(),
  onDocumentPackCorrection: vi.fn(),
  onDocumentPackGenerate: vi.fn(),
  onDocumentPackUpload: vi.fn(),
  onPromptChange: vi.fn(),
  onRevisionPromptChange: vi.fn(),
  onRevisionSubmit: vi.fn(),
  phase: "idle" as const,
  prompt: "",
  submissionPending: false,
  revisionBusy: false,
  revisionPrompt: ""
};

const parsedRequirements = {
  requirements: {
    network_type: "5G",
    site_type: "telecom_site",
    tower_type: "lattice_tower",
    tower_height_m: 30,
    tower_characteristics: {
      structure: "lattice",
      leg_count: 4,
      base_width_m: 4,
      top_width_m: 1,
      foundation_type: "concrete_pad",
      material: "galvanized_steel"
    },
    sector_count: 3,
    antenna_type: "panel_5g",
    antenna_install_height_m: 24,
    azimuths_deg: [0, 120, 240],
    mechanical_tilt_deg: 3,
    electrical_tilt_deg: 0,
    beamwidth_deg: 65,
    include_rru: true,
    include_cables: true,
    include_beams: true,
    include_labels: true,
    include_power_cabinet: true,
    include_gps_antenna: true,
    geometry_requests: [],
    detail_level: "high",
    warnings: [],
    repair_events: [],
    field_evidence: {},
    conflicts: [],
    assumptions: [],
    requires_confirmation: false,
    confirmation_fields: []
  },
  requirements_hash: "a".repeat(64),
  warnings: [],
  errors: [],
  provider: "groq:openai/gpt-oss-120b",
  extraction_provider: "llm",
  fallback_used: false,
  llm_fallback_reason: null
};

afterEach(() => cleanup());

describe("studio kernel components", () => {
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

  it("requires real backend analysis before confirming the design", async () => {
    const onAnalyze = vi.fn();
    const onConfirm = vi.fn();
    const onPromptChange = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={parsedRequirements}
        onAnalyze={onAnalyze}
        onConfirm={onConfirm}
        onPromptChange={onPromptChange}
        prompt="site 5G"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Confirmer et générer" }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(screen.getByText(/Source d’analyse : intelligence décisionnelle/)).toBeInTheDocument();
    expect(screen.queryByText(/groq:openai\/gpt-oss-120b/)).not.toBeInTheDocument();
    expect(screen.queryByText("Prélecture locale")).not.toBeInTheDocument();
  });

  it("keeps remote image analysis opt-in and hides it without an eligible capability", () => {
    const onConsentChange = vi.fn();
    const { rerender } = render(
      <ChatCommandPanel
        {...commandDefaults}
        multimodalIntelligence={{
          status: "operational",
          enabled: true,
          requires_project_consent: true,
          max_images_per_request: 3,
          max_image_bytes: 20_000_000,
          remote_processing: true,
          capabilities: ["multimodal_interpretation"],
          visual_design_critic: "disabled_until_m5"
        }}
        onMultimodalConsentChange={onConsentChange}
      />
    );

    const consent = screen.getByRole("checkbox", {
      name: /Autoriser l’analyse assistée des images jointes/i
    });
    expect(consent).not.toBeChecked();
    expect(screen.getByText(/Cocher cette autorisation n’envoie aucun fichier/)).toBeInTheDocument();
    expect(screen.getByText(/flux documentaire actuel ne déclenche pas encore/)).toBeInTheDocument();
    fireEvent.click(consent);
    expect(onConsentChange).toHaveBeenCalledWith("allow_input_analysis");

    rerender(
      <ChatCommandPanel
        {...commandDefaults}
        multimodalIntelligence={{
          status: "failed",
          enabled: true,
          requires_project_consent: true,
          max_images_per_request: 3,
          max_image_bytes: 20_000_000,
          remote_processing: true,
          capabilities: ["multimodal_interpretation"],
          visual_design_critic: "disabled_until_m5"
        }}
        onMultimodalConsentChange={onConsentChange}
      />
    );
    expect(screen.queryByRole("checkbox", { name: /analyse assistée/i })).not.toBeInTheDocument();
  });

  it("shows one actionable recovery message for a failed generation", () => {
    const repeatedFailure = "La géométrie demandée hors catalogue n'a pas pu être produite; Blender n'a pas été lancé.";
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={parsedRequirements}
        analysisSubmitted
        failureIssue={{
          title: repeatedFailure,
          severity: "error",
          impact: repeatedFailure,
          recommended_action: repeatedFailure,
          technical_code: "GEOMETRY_PROGRAM_GENERATION_FAILED"
        }}
        phase="failed"
        prompt="site 5G avec clôture"
      />
    );

    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getAllByText(repeatedFailure)).toHaveLength(1);
    expect(screen.queryByText("GEOMETRY_PROGRAM_GENERATION_FAILED")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Relancer cette demande" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Corriger la demande" }));
    expect(screen.getByRole("textbox", { name: "Design prompt" })).toHaveFocus();
  });

  it("shows new components extracted for typed LLM geometry before generation", () => {
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={{
          ...parsedRequirements,
          requirements: {
            ...parsedRequirements.requirements,
            geometry_requests: [
              {
                request_id: "shelter_1",
                semantic_role: "technical_shelter",
                description: "Shelter technique extérieur placé au sol.",
                quantity: 1,
                placement_context: "À droite du pylône.",
                maximum_dimensions_m: { x: 3, y: 2.2, z: 2.5 }
              }
            ]
          }
        }}
        prompt="site 5G avec shelter"
      />
    );

    expect(screen.getByText("Composants nouveaux compris par l’IA")).toBeInTheDocument();
    expect(screen.getByText("technical shelter")).toBeInTheDocument();
    expect(screen.getByText("Placement demandé : À droite du pylône.")).toBeInTheDocument();
    expect(screen.getByText(/Enveloppe maximale : 3 × 2.2 × 2.5 m/)).toBeInTheDocument();
    expect(
      screen.getByText(/conçus par le spécialiste 3D, puis contrôlés avant la construction/)
    ).toBeInTheDocument();
  });

  it("counts exact reuse separately and does not attribute imported geometry to a generator", () => {
    const raw = {
      ...bundle,
      geometry_program_summary: {
        program_count: 1, generated_component_count: 0, reused_component_count: 1,
        total_node_count: 1, repaired_program_count: 0,
        programs: [{
          program_id: "reuse.antenna", origin: "catalog_asset", semantic_role: "antenna",
          requested_quantity: 1, node_count: 1, authorship: "deterministic_generated",
          generator_provider: "catalog", generator_model: "exact_asset_import",
          structured_output_mode: "strict_json_schema", source_prompt_sha256: "a".repeat(64)
        }]
      }
    };
    render(<SummaryPanel bundle={ViewerBundleSchema.parse(raw)} issues={null} summary={null} versions={[]} />);
    expect(screen.getByText(/0 composant\(s\) créé\(s\) · 1 composant\(s\) réutilisé\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/Géométrie source importée, placement contrôlé/)).toBeInTheDocument();
    expect(screen.queryByText(/Géométrie déterministe/)).not.toBeInTheDocument();
    expect(() => ViewerBundleSchema.parse({ ...raw, geometry_program_summary: {
      ...raw.geometry_program_summary, generated_component_count: 1, reused_component_count: 0
    } })).toThrow();
  });

  it("shows model, repair mode and prompt proof for generated geometry", () => {
    render(
      <SummaryPanel
        bundle={{
          ...bundle,
          geometry_program_summary: {
            program_count: 1,
            generated_component_count: 1,
            total_node_count: 5,
            repaired_program_count: 1,
            programs: [
              {
                program_id: "shelter_1.llm_v1",
                semantic_role: "technical_shelter",
                requested_quantity: 1,
                node_count: 5,
                authorship: "llm_generated",
                generator_provider: "groq",
                generator_model: "openai/gpt-oss-120b",
                structured_output_mode: "json_object_repaired",
                source_prompt_sha256: "a".repeat(64),
                source_description: "Créer un shelter technique extérieur.",
                source_description_origin: "user_requirement",
                placement_context: "À droite du pylône.",
                maximum_dimensions_m: { x: 3, y: 2.2, z: 2.5 },
                limitations: ["Sans certification structurelle."],
                deterministic_adjustments: [
                  "Uniform scale applied by the deterministic envelope adapter."
                ]
              }
            ]
          }
        }}
        issues={null}
        summary={null}
        versions={[]}
      />
    );

    expect(screen.getByText(/1 composant\(s\) créé\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/JSON réparé puis revalidé/)).toBeInTheDocument();
    expect(screen.getByText(/preuve aaaaaaaaaa/)).toBeInTheDocument();
    expect(screen.getByText(/Géométrie écrite par LLM/)).toBeInTheDocument();
    expect(
      screen.getByText("Intention source : Créer un shelter technique extérieur.")
    ).toBeInTheDocument();
    expect(screen.getByText("Implantation demandée : À droite du pylône.")).toBeInTheDocument();
    expect(screen.getByText(/Enveloppe contrôlée : 3 × 2.2 × 2.5 m max/)).toBeInTheDocument();
    expect(
      screen.getByText("Limite déclarée : Sans certification structurelle.")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Adaptation déterministe appliquée/)
    ).toBeInTheDocument();
  });

  it("does not offer a duplicate generation after the analysis launched a design", () => {
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={parsedRequirements}
        analysisSubmitted
        phase="completed"
        prompt="site 5G"
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent("déjà lancé le design affiché");
    expect(screen.queryByRole("button", { name: "Confirmer et générer" })).not.toBeInTheDocument();
  });

  it("blocks generation and explains unresolved requirement conflicts", () => {
    const onConfirm = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={{
          ...parsedRequirements,
          requirements: {
            ...parsedRequirements.requirements,
            requires_confirmation: true,
            confirmation_fields: ["tower_height_m"],
            conflicts: [
              {
                field: "tower_height_m",
                candidate_values: [30, 42],
                source_texts: ["pylône de 30 m", "pylône de 42 m"],
                reason: "Plusieurs valeurs explicites incompatibles ont été détectées.",
                resolved: false,
                resolution: null
              }
            ]
          }
        }}
        onConfirm={onConfirm}
        prompt="pylône 30 m puis 42 m"
      />
    );

    const confirm = screen.getByRole("button", { name: "Confirmer et générer" });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Confirmation impossible tant que les contradictions ne sont pas corrigées"
    );
    expect(screen.getByText(/Champs à préciser : hauteur du pylône/)).toBeInTheDocument();
  });

  it("translates extraction safeguards into product language", () => {
    expect(
      humanRequirementWarning({
        code: "LLM_SOURCE_FIELD_PROTECTED",
        message: "LLM values conflicting with explicit source requirements were ignored: ['azimuths_deg']."
      })
    ).toBe(
      "Une proposition du LLM contredisait une valeur explicite. Le cahier de charge utilisateur a été conservé."
    );
    expect(
      humanRequirementWarning({
        code: "DEFAULT_BEAMWIDTH_USED",
        message: "Beamwidth inferred as 65 degrees."
      })
    ).toBe("Ouverture d’antenne proposée: 65°.");
  });

  it("keeps a valid deterministic fallback confirmable and visibly explains it", () => {
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={{
          ...parsedRequirements,
          provider: "deterministic",
          extraction_provider: "fallback",
          fallback_used: true,
          llm_fallback_reason: "Groq timeout",
          errors: [{ code: "LLM_EXTRACTION_ERROR", message: "Groq timeout" }]
        }}
        prompt="site 5G"
      />
    );

    expect(
      screen.getByText(
        /L’analyse intelligente n’a pas répondu à temps; une extraction déterministe vérifiable a été utilisée/
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("Groq timeout")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmer et générer" })).toBeEnabled();
  });

  it("keeps the command field empty and requires an explicit user request", () => {
    render(
      <ChatCommandPanel
        {...commandDefaults}
      />
    );

    expect(screen.getByLabelText("Design prompt")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Analyser la demande" })).toBeDisabled();
  });

  it("shows an initial synchronization failure and runs its retry action", () => {
    const onRetryBootstrap = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        bootstrapError="La connexion au studio local n’a pas abouti."
        onRetryBootstrap={onRetryBootstrap}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "L’état initial du studio n’a pas pu être entièrement synchronisé."
    );
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetryBootstrap).toHaveBeenCalledOnce();
  });

  it("keeps a partial document review visible and retries without enabling generation", () => {
    const onReviewRetry = vi.fn();
    const summary = {
      pack_id: "pack_partial",
      status: "processed",
      document_count: 2,
      high_priority_count: 1,
      missing_blocking_count: 0,
      blocking_fields: [],
      conflict_count: 0,
      can_generate_design: true,
      qa_score: 1,
      processing_warning_count: 0,
      tool_status: {}
    };
    render(
      <ChatCommandPanel
        {...commandDefaults}
        documentPackReview={{
          packId: "pack_partial",
          summary,
          conflicts: [],
          missingFields: [],
          qa: null,
          documents: [],
          extractions: [],
          provenance: {},
          processing: null,
          consolidatedSpec: null,
          sectionErrors: {
            qa: { status: 503, retryable: true },
            processing: { status: 503, retryable: true },
            consolidatedSpec: { status: 503, retryable: true }
          }
        }}
        documentPackSummary={summary}
        onDocumentPackReviewRetry={onReviewRetry}
      />
    );

    expect(screen.getByText("Revue partielle")).toBeInTheDocument();
    expect(screen.getByText(/Sections indisponibles : QA documentaire/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Générer depuis le pack" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onReviewRetry).toHaveBeenCalledOnce();
  });

  it("keeps a retained document pack visible when its full review fails and retries it", () => {
    const onReviewRetry = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        documentPackReviewError="Les sections de revue n’ont pas répondu."
        documentPackSummary={{
          pack_id: "pack_retained",
          status: "processed",
          document_count: 2,
          high_priority_count: 1,
          missing_blocking_count: 0,
          blocking_fields: [],
          conflict_count: 0,
          can_generate_design: true,
          qa_score: 1,
          processing_warning_count: 0,
          tool_status: {}
        }}
        onDocumentPackReviewRetry={onReviewRetry}
      />
    );

    expect(screen.getByText("pack_retained")).toBeInTheDocument();
    expect(
      screen.getByText(/Le pack conservé n’est pas présenté comme vide/)
    ).toBeInTheDocument();
    expect(screen.getByText("Documents techniques").closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("button", { name: "Générer depuis le pack" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onReviewRetry).toHaveBeenCalledOnce();
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

  it("exposes the multi-file document composer and corrective review", () => {
    const onDocumentPackCorrection = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        documentPackReview={{
          summary: {
            pack_id: "pack_1",
            status: "processed",
            document_count: 2,
            high_priority_count: 1,
            missing_blocking_count: 1,
            blocking_fields: ["radio.hba_m"],
            conflict_count: 0,
            can_generate_design: false,
            qa_score: 0.7,
            processing_warning_count: 0,
            tool_status: {}
          },
          conflicts: [],
          missingFields: [
            {
              field: "radio.hba_m",
              value: null,
              status: "missing",
              confidence: 0,
              sources: [],
              values: [],
              severity: "blocking",
              resolution: null,
              reason: "HBA absente"
            }
          ],
          qa: {
            pack_id: "pack_1",
            status: "warning",
            score: 0.7,
            checks: [
              { name: "no_blocking_missing_fields", passed: false, reason: "La HBA doit être confirmée." }
            ],
            warnings: [],
            blocking_issues: ["radio.hba_m"],
            ready_to_generate: false,
            ready_confidence: 0.49,
            recommended_user_actions: ["Confirmer la HBA"],
            tool_failures: [],
            memory_writeback: {}
          },
          documents: [
            {
              document_id: "doc_1",
              path: "plans/elevation.pdf",
              filename: "elevation.pdf",
              extension: ".pdf",
              size_bytes: 1200,
              category: "elevation_plan",
              relevance_score: 0.98,
              confidence: 0.95,
              reason: "Contient les hauteurs radio",
              priority: "high",
              purpose: "needed_for_design",
              used_for_design: true,
              why_used_or_ignored: "Source principale HBA",
              extraction_status: "extracted",
              processing_tools: ["pdf_text"],
              processing_warnings: [],
              duplicate_of: null
            },
            {
              document_id: "doc_2",
              path: "admin/bail.pdf",
              filename: "bail.pdf",
              extension: ".pdf",
              size_bytes: 800,
              category: "administrative",
              relevance_score: 0.05,
              confidence: 0.9,
              reason: "Document administratif",
              priority: "ignore",
              purpose: "administrative_reference",
              used_for_design: false,
              why_used_or_ignored: "Sans données de conception telecom",
              extraction_status: "extracted",
              processing_tools: ["pdf_text"],
              processing_warnings: [],
              duplicate_of: null
            }
          ],
          extractions: [],
          provenance: {
            "radio.hba_m": [
              {
                document_id: "doc_1",
                file: "elevation.pdf",
                source_type: "text",
                page: 3,
                sheet: null,
                layer: null,
                confidence: 0.95,
                evidence: "HBA antennes: 24 m"
              }
            ]
          },
          processing: {
            pack_id: "pack_1",
            documents: [],
            warnings: [],
            tool_status: {},
            groq_rejected_fields: []
          },
          consolidatedSpec: {
            pack_id: "pack_1",
            source_mode: "mixed",
            llm_provider: "groq",
            llm_fallback_used: false,
            confidence_summary: { overall: 0.7 },
            processing_warnings: [],
            document_references: [],
            provenance_map: {}
          }
        }}
        documentPackSummary={{
          pack_id: "pack_1",
          status: "processed",
          document_count: 2,
          high_priority_count: 1,
          missing_blocking_count: 1,
          blocking_fields: ["radio.hba_m"],
          conflict_count: 0,
          can_generate_design: false,
          qa_score: 0.7,
          processing_warning_count: 0,
          tool_status: {}
        }}
        onDocumentPackCorrection={onDocumentPackCorrection}
      />
    );

    expect(screen.getByLabelText("Ajouter des pièces techniques")).toHaveAttribute(
      "multiple"
    );
    expect(screen.getByLabelText("Ajouter des pièces techniques")).toHaveAttribute(
      "accept",
      ".zip"
    );
    expect(screen.getByText("Hauteur des antennes (HBA): HBA absente")).toBeInTheDocument();
    expect(screen.getByText("HBA antennes: 24 m")).toBeInTheDocument();
    expect(screen.getByLabelText("Tri documentaire")).toHaveTextContent("1 utile(s)");
    expect(screen.getByLabelText("Tri documentaire")).toHaveTextContent("1 écarté(s)");
    fireEvent.change(screen.getByLabelText("Valeur documentaire confirmée"), {
      target: { value: "24,24,24" }
    });
    fireEvent.change(screen.getByLabelText("Justification de correction"), {
      target: { value: "Plan d’élévation vérifié" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer la correction" }));

    expect(onDocumentPackCorrection).toHaveBeenCalledWith(
      "radio.hba_m",
      "24,24,24",
      "Plan d’élévation vérifié"
    );
  });

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
    expect(screen.getByText("Construction dans Blender").closest("article")).toHaveTextContent("terminé");
  });

  it("does not invent RAG evidence when the artifact is absent", () => {
    render(<RagEvidencePanel bundle={bundle} evidence={null} />);

    expect(screen.getByText("Aucune preuve RAG chargée; le frontend n’en invente pas.")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA reranker unavailable")).not.toBeInTheDocument();
    expect(screen.getByText(/reranker NVIDIA est indisponible/)).toBeInTheDocument();
  });

  it("shows the real local lexical fallback when vector retrieval fails", () => {
    render(
      <RagEvidencePanel
        bundle={{
          ...bundle,
          rag_retrieval_status: "degraded_local_lexical",
          rag_retrieval_degraded_reason: "index_timeout"
        }}
        evidence={null}
      />
    );

    expect(screen.getByText("disponible avec limites")).toBeInTheDocument();
    expect(screen.getByText(/recherche vectorielle est indisponible/)).toBeInTheDocument();
    expect(screen.getByText(/corpus local réel par correspondance lexicale/)).toBeInTheDocument();
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

    expect(screen.getByText("Conception non produite")).toBeInTheDocument();
    expect(screen.getByText("Modèle 3D : non produit")).toBeInTheDocument();
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

    expect(screen.getByText("Hints candidats récupérés")).toBeInTheDocument();
    expect(screen.getByText("Aucun hint n’est prouvé comme appliqué au SceneSpec.")).toBeInTheDocument();
    expect(screen.getByText("include_labels")).toBeInTheDocument();
    expect(screen.getByText("scene_templates.md")).toBeInTheDocument();
    expect(screen.queryByText("Données RAG techniques")).not.toBeInTheDocument();
  });

  it("translates backend RAG limitations without hiding their meaning", () => {
    const limitations = [
      "RAG is evidence and controlled planning context, not a free-form planner.",
      "RAG does not participate in RequirementSpec extraction in v1.",
      "Only whitelisted payload.planning_hints are eligible for planner influence."
    ];

    const translated = limitations.map(humanRagLimitation);

    expect(translated).toHaveLength(3);
    expect(translated.join(" ")).not.toMatch(/free-form|does not participate|whitelisted/);
    expect(translated.join(" ")).toMatch(/contexte de planification contrôlé/);
    expect(translated.join(" ")).toMatch(/RequirementSpec/);
    expect(translated.join(" ")).toMatch(/explicitement autorisés/);
  });

  it("groups repeated per-sector adaptation parameters into one readable summary", () => {
    const capability = (id: string, path: string, label: string) => ({
      capability_id: id,
      asset_id: "ANT_PANEL_5G_001",
      profile_id: "sector_antenna_pose_v1",
      label,
      path,
      value_type: "number",
      execution_tool: "sector_layout",
      effect: "rf",
      description: label,
      unit: "deg",
      minimum: 0,
      maximum: 360,
      allowed_values: [],
      requires_regeneration: true
    });
    const summaries = summarizeAdaptationCapabilityGroups({
      scene_id: "scene_1",
      catalog_version: "1.0.0",
      catalog_hash: "hash",
      capabilities: [
        capability("sector_1:azimuth", "/sectors/0/azimuth_deg", "Azimut"),
        capability("sector_2:azimuth", "/sectors/1/azimuth_deg", "Azimut"),
        capability("sector_3:azimuth", "/sectors/2/azimuth_deg", "Azimut"),
        capability("sector_1:tilt", "/sectors/0/mechanical_tilt_deg", "Tilt mécanique"),
        capability("sector_2:tilt", "/sectors/1/mechanical_tilt_deg", "Tilt mécanique"),
        capability("sector_3:tilt", "/sectors/2/mechanical_tilt_deg", "Tilt mécanique")
      ],
      unsupported_operations: [],
      missing_profiles: []
    });

    expect(summaries).toHaveLength(1);
    expect(summaries[0]).toContain("2 paramètres sur 3 secteurs");
    expect(summaries[0]).toContain("Azimut");
    expect(summaries[0]).toContain("Tilt mécanique");
  });

  it("does not create a link for an unavailable artifact", () => {
    const toAbsoluteUrl = vi.fn((url: string | null | undefined) => url ?? null);
    render(
      <ArtifactsPanel
        bundle={{
          ...bundle,
          viewer_artifacts: [
            {
              name: "design.glb",
              url: "/designs/wf_1/artifacts/design.glb",
              content_type: "model/gltf-binary",
              available: false
            }
          ]
        }}
        toAbsoluteUrl={toAbsoluteUrl}
      />
    );

    const artifact = screen.getByText("Modèle 3D GLB").closest(".artifact-link");
    expect(artifact).toHaveAttribute("aria-disabled", "true");
    expect(artifact?.tagName).toBe("DIV");
    expect(toAbsoluteUrl).not.toHaveBeenCalled();
  });

  it("labels component assembly proofs as a verifiable deliverable", () => {
    render(
      <ArtifactsPanel
        bundle={{
          ...bundle,
          component_proofs_url: "/designs/wf_1/artifacts/component_proofs.json",
          viewer_artifacts: [
            {
              name: "component_proofs.json",
              url: "/designs/wf_1/artifacts/component_proofs.json",
              content_type: "application/json",
              available: true
            }
          ]
        }}
        toAbsoluteUrl={(url) => url ?? null}
      />
    );

    expect(
      screen.getByRole("link", { name: /Preuves des composants assemblés/ })
    ).toHaveAttribute("href", "/designs/wf_1/artifacts/component_proofs.json");
  });

  it("renders every real image artifact as a preview without inventing unavailable views", () => {
    render(
      <ArtifactsPanel
        bundle={{
          ...bundle,
          viewer_artifacts: [
            { name: "preview_front.png", url: "/front.png", content_type: "image/png", available: true },
            { name: "preview_top.png", url: "/top.png", content_type: "image/png", available: true },
            { name: "preview_missing.png", url: "/missing.png", content_type: "image/png", available: false }
          ]
        }}
        toAbsoluteUrl={(url) => url ? `http://127.0.0.1:8000${url}` : null}
      />
    );

    expect(screen.getByLabelText("Aperçus du design").querySelectorAll("img")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Vue de face" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vue de dessus" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /missing/i })).not.toBeInTheDocument();
  });

  it("explains selection scope and clears the inspection context", () => {
    const onSelect = vi.fn();
    render(<SceneCompositionPanel assemblyPlan={null} componentProofs={null}
      selectedSemanticRoot="antenna_S1_REAL_1" onSelect={onSelect} />);
    expect(screen.getByRole("status")).toHaveTextContent("limitée à ce composant");
    fireEvent.click(screen.getByRole("button", { name: "Désélectionner" }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("identifies exact imports as reused source geometry without a constructor qualification claim", () => {
    render(<SceneCompositionPanel assemblyPlan={null} componentProofs={{
      schema_version: "1.0", workflow_id: "wf_reuse", components: [],
      geometry_programs: [{
        component_id: "geometry_program:reuse.antenna", role_id: "antenna",
        origin: "catalog_asset", strategy: "reuse", generation_strategy: "imported_glb_exact",
        quantity: 1, exact_asset_sources: [{
          asset_id: "ANT_PANEL_4G_001", asset_file: "assets/processed/antenna.glb",
          asset_sha256: "a".repeat(64), manifest_file_name: "ANT_PANEL_4G_001.json",
          manifest_sha256: "b".repeat(64)
        }]
      }]
    }} />);
    expect(screen.getByText("Réutilisé · géométrie source importée")).toBeInTheDocument();
    expect(screen.getByText(/Source : ANT_PANEL_4G_001/)).toHaveTextContent("ne constitue pas une qualification constructeur");
    expect(screen.queryByText(/programme géométrique/)).not.toBeInTheDocument();
  });

  it("exposes the real assembly strategy and synchronizes a proof instance selection", () => {
    const onSelect = vi.fn();
    render(
      <SceneCompositionPanel
        assetDecisionSummary={{
          components: [{
            component_id: "antenna_component",
            role_id: "antenna",
            strategy: "reuse_component",
            strategy_evidence: "planned_not_execution_verified",
            asset_id: "ANT_REAL_1",
            considered_count: 2,
            rejected_count: 1,
            rationale: "Meilleur candidat compatible avec les connecteurs requis.",
            risks: ["Professional asset QA has not passed."]
          }],
          considered_asset_count: 2,
          selected_asset_count: 1,
          decision_authority: "llm_bounded",
          fallback_used: false,
          fallback_reason: null
        }}
        assemblyPlan={{
          schema_version: "1.0",
          workflow_id: "wf_1",
          selection_authority: "bounded_llm",
          selection_provider: "groq",
          selection_model: "openai/gpt-oss-120b",
          components: [{
            role_id: "antenna",
            asset_type: "antenna",
            required: true,
            candidate_scores: [],
            selected_asset_id: "ANT_REAL_1",
            generation_strategy: "reuse",
            selection_risks: ["Professional asset QA has not passed."],
            selection_reason: "Meilleur candidat compatible avec les connecteurs requis."
          }],
          connections: [{}],
          operations: []
        }}
        componentProofs={{
          schema_version: "1.0",
          workflow_id: "wf_1",
          components: [{
            component_id: "antenna_component",
            role_id: "antenna",
            origin: "catalog",
            strategy: "reuse",
            generation_strategy: "reuse",
            asset_id: "ANT_REAL_1",
            quantity: 1,
            instances: [{
              instance_id: "antenna_1",
              object_role: "antenna",
              semantic_root: "antenna_S1_REAL_1",
              geometry_source: "asset_glb",
              qa: null
            }],
            qa: null
          }],
          geometry_programs: [{
            component_id: "shelter_component",
            role_id: "technical_shelter",
            origin: "geometry_program",
            strategy: "procedural_generate",
            generation_strategy: "procedural_generate",
            quantity: 1,
            geometry_program: {},
            qa: null
          }]
        }}
        assetInventory={{
          status: "qualified",
          asset_count: 1,
          missing_file_count: 0,
          real_glb_asset_count: 1,
          import_qualified_glb_count: 1,
          generation_eligible_asset_count: 1,
          professional_evidence_asset_count: 0,
          reference_only_asset_count: 0,
          qualified_integrity_failure_count: 0,
          entries: [{
            asset_id: "ANT_REAL_1",
            type: "antenna",
            source: "Catalogue qualifié",
            generation_eligible: true,
            qualification_status: "qualified",
            milestone_evidence_eligible: false,
            milestone_evidence_failures: ["Professional QA report file is missing."],
            allowed_generation_modes: ["reuse"],
            qualification_limitations: [],
            qualified_file_hash_matches: true,
            preview_set: [{
              view: "front",
              url: "/assets/ANT_REAL_1/previews/front.png",
              sha256: "a".repeat(64),
              available: true,
              content_type: "image/png",
              width_px: 1024,
              height_px: 1024,
              qa_status: "passed"
            }],
            provenance_url: "/assets/ANT_REAL_1/provenance",
            visual_review_status: "passed_advisory",
            fidelity_status: "exact_import",
            qualification_version: "1.0"
          }],
          missing_files: []
        }}
        onSelect={onSelect}
        toAbsoluteUrl={(url) => url ?? null}
      />
    );

    expect(screen.getAllByText("Réutilisé").length).toBeGreaterThan(0);
    expect(screen.getByText("Généré")).toBeInTheDocument();
    expect(screen.getAllByText(/Meilleur candidat compatible/)).toHaveLength(2);
    expect(screen.queryByRole("img", { name: /Aperçu front/i })).not.toBeInTheDocument();
    expect(screen.getByText("Asset technique — preuve professionnelle incomplète")).toBeInTheDocument();
    expect(screen.getByText("Le rapport QA professionnel est absent.")).toBeInTheDocument();
    expect(screen.getByText("Stratégie planifiée, non certifiée par l’exécution")).toBeInTheDocument();
    expect(screen.getByText("La QA professionnelle de l’asset n’a pas réussi.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Consulter la provenance" })).toHaveAttribute(
      "href",
      "/assets/ANT_REAL_1/provenance"
    );
    expect(screen.queryByText("groq")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /choisir|sélectionner/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("treeitem", { name: /antenna/i }));
    expect(onSelect).toHaveBeenCalledWith("antenna_S1_REAL_1");
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

  it("presents the imported CAD library as quarantined product data", () => {
    const onSearch = vi.fn();
    render(
      <AssetLibraryPanel
        inventory={{
          status: "qualified_mixed_catalog",
          asset_count: 12,
          missing_file_count: 0,
          real_glb_asset_count: 12,
          import_qualified_glb_count: 4,
          generation_eligible_asset_count: 10,
          professional_evidence_asset_count: 0,
          reference_only_asset_count: 2,
          qualified_integrity_failure_count: 0,
          entries: [{
            asset_id: "ANT_PANEL_4G_001",
            type: "antenna",
            source: "internal_cleaned",
            generation_eligible: true,
            qualification_status: "qualified_for_generation",
            milestone_evidence_eligible: false,
            milestone_evidence_failures: ["Professional asset QA has not passed."],
            allowed_generation_modes: ["imported_glb_exact"],
            qualification_limitations: ["Géométrie interne générique."],
            qualified_file_hash_matches: true
          }, {
            asset_id: "ANT_SIERRA_6001124_REFERENCE",
            type: "antenna",
            family: "lte_mimo_panel",
            subtype: "2-in-1 omnidirectional panel antenna",
            manufacturer: "Sierra Wireless / Semtech",
            reference: "6001124",
            source: "vendor_supplied",
            original_url: "https://source.sierrawireless.com/6001124.step",
            source_format: "step",
            attribution_required: true,
            dimensions_m: { width: 0.15, depth: 0.045, height: 0.049 },
            generation_eligible: false,
            qualification_status: "reference_only",
            milestone_evidence_eligible: false,
            milestone_evidence_failures: ["Anchors are not qualified."],
            allowed_generation_modes: [],
            qualification_limitations: ["Stable anchors remain unverified."]
          }],
          missing_files: []
        }}
        onSearch={onSearch}
        summary={{
          status: "catalogued_quarantined",
          schema_version: "1.0.0",
          catalog_available: true,
          file_count: 11974,
          unique_content_count: 11531,
          duplicate_file_count: 443,
          generation_eligible_count: 0,
          cad_with_reference_preview_count: 7,
          reference_preview_link_count: 15,
          claimed_dimension_counts: { "2d": 8514, "3d": 2834 },
          limitations: ["Licence à vérifier."]
        }}
      />
    );

    expect(screen.getByText(/11[\s ]974 fichiers catalogués/)).toBeInTheDocument();
    expect(screen.getByText(/10 composants exploitables/)).toBeInTheDocument();
    expect(screen.getByText(/ant panel 4g 001/)).toBeInTheDocument();
    expect(screen.getByText("Sierra Wireless / Semtech")).toBeInTheDocument();
    expect(screen.getByText(/6001124 · 2-in-1 omnidirectional panel antenna/)).toBeInTheDocument();
    expect(screen.getByText("Référence uniquement")).toBeInTheDocument();
    expect(screen.getByText(/STEP · attribution requise/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ouvrir la source fabricant" })).toHaveAttribute(
      "href",
      "https://source.sierrawireless.com/6001124.step"
    );
    expect(screen.getByText(/mesh vérifié/)).toBeInTheDocument();
    expect(screen.getByText(/2\s834/)).toBeInTheDocument();
    expect(screen.getByText("Qualification requise")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Rechercher un pylône/), {
      target: { value: "pylône Orange 30 m" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));
    expect(onSearch).toHaveBeenCalledWith("pylône Orange 30 m");
  });

  it("shows real library results without offering unqualified Blender use", () => {
    render(
      <AssetLibraryPanel
        search={{
          query: "pylone 30m",
          filters: {},
          result_count: 1,
          results: [{
            file_id: "lib_tower",
            relative_path: "3D/Pylone/Orange/Orange_Pylone_30m_Galva.dwg",
            extension: "dwg",
            size_bytes: 4096,
            claimed_dimension: "3d",
            category: "Pylone",
            duplicate_of: null,
            license_status: "unknown_requires_review",
            qualification_status: "quarantined_unverified",
            conversion_status: "not_attempted",
            generation_eligible: false,
            reference_preview_file_ids: ["lib_preview_1", "lib_preview_2"],
            related_cad_file_ids: []
          }],
          selection_policy: "metadata_retrieval_only",
          generation_eligible: false,
          next_action: "Qualifier la licence, la géométrie et la conversion."
        }}
        summary={{
          status: "catalogued_quarantined",
          schema_version: "1.1.0",
          catalog_available: true,
          generation_eligible_count: 0,
          cad_with_reference_preview_count: 7,
          reference_preview_link_count: 15,
          limitations: []
        }}
      />
    );

    expect(screen.getByText("Orange_Pylone_30m_Galva.dwg")).toBeInTheDocument();
    expect(screen.getByText("En quarantaine")).toBeInTheDocument();
    expect(screen.getByText("2 aperçus")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Blender|utiliser/i })).not.toBeInTheDocument();
  });

  it("keeps inspector content behind contextual drawers", () => {
    render(
      <InspectorDock
        bundle={bundle}
        canRollback={false}
        events={[
          {
            event_id: "evt_1",
            event_type: "node_started",
            workflow_id: "wf_1",
            timestamp: "2026-06-16T10:00:00Z",
            phase: "planning",
            status: "running",
            node: "plan_scene",
            human_label: "Construction du plan",
            progress_message: "Planification en cours.",
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
        issues={null}
        summary={null}
        timeline={null}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    expect(screen.queryByLabelText("Résumé produit")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Vue" }));
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    expect(screen.getByLabelText("Résumé produit")).toHaveTextContent("Résumé du design");
    fireEvent.click(screen.getByRole("button", { name: /Progression/ }));
    expect(screen.getByLabelText("Timeline agents")).toHaveTextContent("Progression du design");
    expect(screen.queryByRole("button", { name: "Système" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bibliothèque" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("exposes contextual library and intelligence drawers when their real data exists", () => {
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
        events={[]}
        issues={null}
        summary={null}
        timeline={null}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    expect(screen.getByRole("button", { name: "Bibliothèque" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Intelligence" }));
    expect(screen.getByText("RAG et preuves")).toBeInTheDocument();
    expect(screen.getByText(/corpus local réel par correspondance lexicale/)).toBeInTheDocument();
  });

  it("keeps a repeated workflow failure out of the closed QA drawer and renders it once when opened", () => {
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
        events={[]}
        issues={{
          workflow_id: "wf_1",
          status: "failed",
          human_readable_issues: [{
            title: repeatedFailure,
            severity: "error",
            impact: repeatedFailure,
            recommended_action: repeatedFailure,
            technical_code: "GEOMETRY_PROGRAM_GENERATION_FAILED"
          }]
        }}
        summary={null}
        timeline={null}
        toAbsoluteUrl={(url) => url ?? null}
        onRollbackVersion={vi.fn()}
        rollbackBusyVersionId={null}
        versionMessage={null}
        versions={[]}
      />
    );

    expect(screen.queryByText(repeatedFailure)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Vérification/ }));
    expect(screen.getAllByText(repeatedFailure)).toHaveLength(1);
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

    expect(screen.getByRole("status")).toHaveTextContent("Assemblage Blender");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Positionnement des composants sélectionnés."
    );
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
