import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SceneCompositionPanel } from "./SceneCompositionPanel";
import {
  ArtifactsPanel,
  RagEvidencePanel,
  SummaryPanel,
  humanRagLimitation,
  summarizeAdaptationCapabilityGroups
} from "./StudioKernel";
import { bundle } from "./StudioKernel.testFixtures";

afterEach(() => cleanup());

describe("studio kernel evidence and composition", () => {
  it("does not invent RAG evidence when the artifact is absent", () => {
    render(<RagEvidencePanel bundle={bundle} evidence={null} />);

    expect(screen.getByText("Aucune source de conception chargée; le studio n’en invente pas.")).toBeInTheDocument();
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

    expect(screen.getAllByText("disponible avec limites").length).toBeGreaterThan(0);
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

    expect(screen.getByText("Indices candidats récupérés")).toBeInTheDocument();
    expect(screen.getByText("Aucun indice récupéré n’est prouvé comme appliqué au plan 3D.")).toBeInTheDocument();
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
    expect(translated.join(" ")).toMatch(/contexte contrôlé/);
    expect(translated.join(" ")).toMatch(/extraction initiale des exigences/);
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
    render(<SceneCompositionPanel componentProofs={null}
      selectedSemanticRoot="antenna_S1_REAL_1" onSelect={onSelect} />);
    expect(screen.getByRole("status")).toHaveTextContent("changements demandés dans le chat viseront cet élément");
    fireEvent.click(screen.getByRole("button", { name: "Revenir au design complet" }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("shows a product label from component evidence instead of the backend identity", () => {
    render(
      <SceneCompositionPanel
        componentProofs={{
          schema_version: "1.0",
          workflow_id: "wf_labels",
          components: [{
            component_id: "sector_antennas",
            role_id: "sector_antenna",
            origin: "catalog",
            strategy: "reuse",
            generation_strategy: "imported_glb_exact",
            asset_id: "ANT_PANEL_5G_001",
            quantity: 1,
            instances: [{
              instance_id: "S2",
              object_role: "antenna",
              semantic_root: "antenna_S2_ANT_PANEL_5G_001",
              geometry_source: "imported_glb_exact",
              qa: null
            }],
            qa: null
          }],
          geometry_programs: []
        }}
        selectedSemanticRoot="antenna_S2_ANT_PANEL_5G_001"
      />
    );

    const selectionStatus = screen.getByRole("status");
    expect(selectionStatus).toHaveTextContent("antenne du secteur S2");
    expect(selectionStatus).not.toHaveTextContent("ANT_PANEL_5G_001");
  });

  it("shows a version-bound Blender sector inspection only for the selected exported component", () => {
    render(
      <SceneCompositionPanel
        componentProofs={null}
        selectedSemanticRoot="antenna_S1_ANT_PANEL_5G_001"
        sectorPreviews={[{
          sector_id: "S1",
          preview_url: "/designs/wf_1/sector-previews/3696ad59777e09d5?version_id=v12345678",
          semantic_roots: ["antenna_S1_ANT_PANEL_5G_001", "radio_S1_RRU_SMALL_001"],
          expected_roles: ["antenna", "rru", "cable"],
          exported_roles: ["antenna", "cable", "radio"],
          framed_roles: ["antenna", "mount_bracket", "radio"],
          post_blender_identity_verified: true,
          visual_framing_verified: true,
          subject_bbox_height_ratio: 0.82,
          subject_contrast_mean: 144,
          limitations: ["Le rendu ne certifie pas la géométrie constructeur."]
        }]}
        toAbsoluteUrl={(url) => url ? `http://127.0.0.1:8000${url}` : null}
      />
    );

    expect(screen.getByRole("img", { name: "Vue rapprochée du secteur S1" }))
      .toHaveAttribute(
        "src",
        "http://127.0.0.1:8000/designs/wf_1/sector-previews/3696ad59777e09d5?version_id=v12345678"
      );
    expect(screen.getByText("Vue issue du modèle 3D de la version active")).toBeInTheDocument();
    expect(screen.getByText(/ne valide pas la pose ni les caractéristiques du constructeur/)).toBeInTheDocument();
  });

  it("identifies exact imports as reused source geometry without a constructor qualification claim", () => {
    render(<SceneCompositionPanel componentProofs={{
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
    expect(screen.getByText("Modèle source conservé")).toBeInTheDocument();
    expect(screen.getByText("Source : Source du catalogue du projet")).toBeInTheDocument();
    expect(screen.queryByText("ANT_PANEL_4G_001")).not.toBeInTheDocument();
    expect(screen.queryByText(/manifest|sha|programme géométrique/i)).not.toBeInTheDocument();
  });

  it("exposes the real assembly strategy and synchronizes a proof instance selection", () => {
    const onSelect = vi.fn();
    render(
      <SceneCompositionPanel
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
            manufacturer: "Radio Systems",
            reference: "Panel 800",
            source: "Catalogue qualifié",
            dimensions_m: { width: 0.3, depth: 0.12, height: 1.4 },
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

    expect(screen.getByText("Modèle source conservé")).toBeInTheDocument();
    expect(screen.getByText("Créé pour ce projet")).toBeInTheDocument();
    expect(screen.getByText("Source : Radio Systems · Panel 800")).toBeInTheDocument();
    expect(screen.getByText("L × P × H : 0,3 × 0,12 × 1,4 m")).toBeInTheDocument();
    expect(screen.queryByText(/qualification professionnelle/i)).not.toBeInTheDocument();
    expect(screen.queryByText("groq")).not.toBeInTheDocument();
    expect(screen.queryByText("ANT_REAL_1")).not.toBeInTheDocument();
    expect(screen.queryByText(/QA|manifest|hash|agent/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("treeitem", { name: /antenne/i }));
    expect(onSelect).toHaveBeenCalledWith("antenna_S1_REAL_1");
  });

});
