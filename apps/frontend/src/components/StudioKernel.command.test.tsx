import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewerBundleSchema } from "../api/schemas";
import {
  ChatCommandPanel,
  SummaryPanel,
  humanRequirementWarning
} from "./StudioKernel";
import { bundle, commandDefaults, parsedRequirements } from "./StudioKernel.testFixtures";

afterEach(() => cleanup());

describe("studio kernel conversation command", () => {
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
    expect(screen.getByText(/Source d’analyse : analyse assistée de votre demande/)).toBeInTheDocument();
    expect(screen.queryByText(/groq:openai\/gpt-oss-120b/)).not.toBeInTheDocument();
    expect(screen.queryByText("Prélecture locale")).not.toBeInTheDocument();
  });

  it("does not confirm an analysis whose server receipt is missing", () => {
    const onConfirm = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        analysis={{ ...parsedRequirements, analysis_receipt: null }}
        onConfirm={onConfirm}
        prompt="site 5G"
      />
    );

    const confirm = screen.getByRole("button", { name: "Confirmer et générer" });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "La provenance vérifiée de cette analyse n’est pas disponible"
    );
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("explains missing site evidence without offering confirmation of a default design", () => {
    render(<ChatCommandPanel {...commandDefaults} analysis={{
      requirements: null, requirements_hash: null, analysis_receipt: null,
      warnings: [], errors: [{ code: "TELECOM_BRIEF_REQUIRED", message: "Site absent" }],
      provider: "groq", extraction_provider: "groq", fallback_used: false
    }} />);
    expect(screen.getByText(/Précisez le site à concevoir/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirmer/ })).not.toBeInTheDocument();
  });

  it("offers unconfirmed free design only when the request cannot be structured", () => {
    const freeDesign = vi.fn();
    const { rerender } = render(<ChatCommandPanel {...commandDefaults} onFreeDesign={freeDesign}
      analysisError="La demande n’a pas pu être structurée pour confirmation." analysis={null} />);
    expect(screen.queryByRole("button", { name: /Télécom avec validation|Intention libre/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Concevoir sans confirmation télécom" }));
    expect(freeDesign).toHaveBeenCalledTimes(1);
    rerender(<ChatCommandPanel {...commandDefaults} analysisError="Erreur réseau" analysis={null} />);
    expect(screen.queryByRole("button", { name: "Concevoir sans confirmation télécom" })).not.toBeInTheDocument();
  });

  it("preserves queued attachments when closing the panel", () => {
    const upload = vi.fn().mockResolvedValue(true);
    render(<ChatCommandPanel {...commandDefaults}
      onNewChat={vi.fn()}
      onDocumentPackUpload={upload}
      documentCapabilities={{
        document_pack_status: "limited", supported_upload_format: "zip_or_multiple_files",
        supported_extensions: [".pdf"], limitations: [], limits: {}, truth: {}, capabilities: {}
      }} />);
    const trigger = screen.getByRole("button", { name: "Ajouter des pièces jointes" });
    fireEvent.click(trigger);
    const files = [new File(["document"], "plan.pdf", { type: "application/pdf" })];
    fireEvent.change(screen.getByLabelText("Ajouter des pièces techniques"), { target: { files } });
    fireEvent.click(screen.getByRole("button", { name: "Fermer les pièces jointes" }));
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Joindre 1 pièce(s)" })).not.toBeInTheDocument();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Joindre 1 pièce(s)" }));
    expect(upload).toHaveBeenCalledWith(files);
  });

  it("keeps the conversation and attachment surfaces mutually exclusive", () => {
    render(
      <ChatCommandPanel
        {...commandDefaults}
        documentCapabilities={{
          document_pack_status: "limited",
          supported_upload_format: "zip_or_multiple_files",
          supported_extensions: [".pdf"],
          limitations: [],
          limits: {},
          truth: {},
          capabilities: {}
        }}
      />
    );

    const conversationButton = screen.getByRole("button", { name: "Conversation" });
    const attachmentButton = screen.getByRole("button", { name: "Ajouter des pièces jointes" });
    fireEvent.click(conversationButton);
    expect(conversationButton).toHaveAttribute("aria-expanded", "true");
    expect(attachmentButton).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(attachmentButton);
    expect(attachmentButton).toHaveAttribute("aria-expanded", "true");
    expect(conversationButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Conversation et cahier des charges" })).not.toBeInTheDocument();

    fireEvent.click(conversationButton);
    expect(conversationButton).toHaveAttribute("aria-expanded", "true");
    expect(attachmentButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Pièces jointes et cahier de charge" })).not.toBeInTheDocument();
  });

  it("exposes a real action to detach an imported pack from the conversation", () => {
    const onDocumentPackDetach = vi.fn().mockResolvedValue(undefined);
    render(
      <ChatCommandPanel
        {...commandDefaults}
        documentPackSummary={{
          pack_id: "pack_attached",
          status: "processed",
          document_count: 1,
          high_priority_count: 1,
          missing_blocking_count: 2,
          blocking_fields: ["tower.tower_height_m"],
          conflict_count: 0,
          can_generate_design: false,
          qa_score: 0.7,
          processing_warning_count: 0,
          tool_status: {}
        }}
        onDocumentPackDetach={onDocumentPackDetach}
      />
    );

    const removeButton = screen.getByRole("button", {
      name: "Retirer les pièces jointes de cette conversation"
    });
    expect(removeButton).toBeEnabled();
    fireEvent.click(removeButton);
    expect(onDocumentPackDetach).toHaveBeenCalledOnce();
    expect(screen.getByText("1 pièce jointe")).toBeInTheDocument();
    expect(screen.queryByText(/informations extraites/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Générer le design" })).not.toBeInTheDocument();
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

    const attachmentButton = screen.getByRole("button", { name: "Ajouter des pièces jointes" });
    expect(attachmentButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(attachmentButton);
    const consent = screen.getByRole("checkbox", {
      name: /Autoriser l’analyse assistée des images jointes/i
    });
    expect(consent).not.toBeChecked();
    expect(screen.getByText(/Cocher cette autorisation n’envoie aucun fichier/)).toBeInTheDocument();
    expect(screen.queryByText(/milestone|flux documentaire/i)).not.toBeInTheDocument();
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

  it("starts a new conversation after a workspace design fails", () => {
    const onNewChat = vi.fn();
    render(
      <ChatCommandPanel
        {...commandDefaults}
        failureIssue={{
          title: "La construction a échoué",
          severity: "error",
          impact: "Aucun modèle vérifié n’est disponible.",
          recommended_action: "Précisez la demande.",
          technical_code: "GENERATION_FAILED"
        }}
        onNewChat={onNewChat}
        phase="failed"
        prompt="Corriger la hauteur et relancer"
      />
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Reprendre dans une nouvelle conversation"
      })
    );

    expect(onNewChat).toHaveBeenCalledWith("Corriger la hauteur et relancer");
    expect(
      screen.queryByRole("button", { name: "Corriger la demande" })
    ).not.toBeInTheDocument();
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
    expect(screen.getByText("abri technique")).toBeInTheDocument();
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

  it("shows persisted initial analysis without exposing receipt internals", () => {
    const receipt = {
      schema_version: "1.0.0" as const,
      receipt_id: `ira_${"d".repeat(32)}`,
      issued_at: "2026-09-11T10:00:00+00:00",
      confirmed_prompt_sha256: "e".repeat(64),
      confirmed_requirements_sha256: "f".repeat(64),
      detail_level: "high" as const,
      provider: "groq:openai/gpt-oss-120b",
      model: "openai/gpt-oss-120b",
      extraction_provider: "llm",
      fallback_used: false,
      fallback_reason: null
    };
    render(
      <SummaryPanel
        bundle={{
          ...bundle,
          input_analysis: receipt,
          input_analysis_status: "verified"
        }}
        issues={null}
        summary={null}
        versions={[]}
      />
    );

    const context = screen.getByLabelText("Compréhension initiale");
    expect(context).toHaveTextContent("Compréhension initiale vérifiée");
    expect(context).toHaveTextContent("groq:openai/gpt-oss-120b");
    expect(context).toHaveTextContent("openai/gpt-oss-120b");
    expect(context).toHaveTextContent("Mode de secours");
    expect(context).toHaveTextContent("non utilisé");
    expect(context).not.toHaveTextContent(receipt.receipt_id);
    expect(context).not.toHaveTextContent(receipt.confirmed_prompt_sha256);
    expect(context).not.toHaveTextContent(receipt.confirmed_requirements_sha256);
  });

  it("labels legacy analysis truthfully when a persisted version has no receipt", () => {
    render(
      <SummaryPanel
        bundle={{ ...bundle, input_analysis: null, input_analysis_status: "legacy_unattested" }}
        issues={null}
        summary={null}
        versions={[]}
      />
    );

    expect(screen.getByLabelText("Compréhension initiale")).toHaveTextContent(
      "Compréhension initiale non attestée"
    );
    expect(screen.getByLabelText("Compréhension initiale")).toHaveTextContent(
      "Aucun fournisseur ni modèle n’est revendiqué"
    );
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

    fireEvent.click(screen.getByRole("button", { name: "Conversation" }));
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
      "Une valeur proposée automatiquement contredisait votre demande ; votre valeur a été conservée."
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
          errors: [{ code: "LLM_EXTRACTION_ERROR", message: "Groq timeout" }],
          analysis_receipt: {
            ...parsedRequirements.analysis_receipt,
            provider: "deterministic",
            model: null,
            extraction_provider: "fallback",
            fallback_used: true,
            fallback_reason: "Groq timeout"
          }
        }}
        prompt="site 5G"
      />
    );

    expect(
      screen.getByText(
        /L’analyse assistée n’a pas répondu à temps ; les paramètres ont été extraits directement de votre demande/
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

});
