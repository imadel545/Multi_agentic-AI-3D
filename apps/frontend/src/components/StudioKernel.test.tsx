import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ViewerBundle } from "../api/schemas";
import {
  AgentStageRail,
  AgentTimeline,
  ArtifactsPanel,
  AssetLibraryPanel,
  BackendStatusBar,
  ChatCommandPanel,
  InspectorDock,
  IssuesPanel,
  QaPanel,
  RagEvidencePanel,
  RuntimeCapabilitiesPanel,
  SummaryPanel,
  VersionSummary,
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
  qa_summary: {},
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

    expect(
      screen.getByText("Équipements génériques techniques · 6 composants · antennes, radios")
    ).toHaveAttribute("data-geometry-fidelity", "technical_generic");
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
      }
    ]);

    expect(summarized.map((issue) => issue.title)).toEqual([
      "Inclinaison mécanique proposée",
      "Azimuts complétés",
      "Recherche documentaire temporairement dégradée",
      "Compréhension en mode de secours"
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

    expect(screen.getByText("Compréhension").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Plan SceneSpec").closest("article")).toHaveTextContent("terminé");
    expect(screen.getByText("Génération 3D").closest("article")).toHaveTextContent("terminé");
  });

  it("does not invent RAG evidence when the artifact is absent", () => {
    render(<RagEvidencePanel bundle={bundle} evidence={null} />);

    expect(screen.getByText("Aucune preuve RAG chargée; le frontend n’en invente pas.")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA reranker unavailable")).not.toBeInTheDocument();
    expect(screen.getByText(/reranker NVIDIA est indisponible/)).toBeInTheDocument();
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
          reference_only_asset_count: 2,
          qualified_integrity_failure_count: 0,
          entries: [{
            asset_id: "ANT_PANEL_4G_001",
            type: "antenna",
            source: "internal_cleaned",
            generation_eligible: true,
            qualification_status: "qualified_for_generation",
            allowed_generation_modes: ["imported_glb_exact"],
            qualification_limitations: ["Géométrie interne générique."],
            qualified_file_hash_matches: true
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
    fireEvent.click(screen.getByRole("button", { name: "Résumé" }));
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    expect(screen.getByLabelText("Résumé produit")).toHaveTextContent("Résumé du design");
    fireEvent.click(screen.getByRole("button", { name: /Agents/ }));
    expect(screen.getByLabelText("Timeline agents")).toHaveTextContent("Narration du workflow");
    fireEvent.click(screen.getByRole("button", { name: "RAG" }));
    expect(screen.getByLabelText("RAG evidence")).toHaveTextContent(
      "Aucune preuve RAG chargée"
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
