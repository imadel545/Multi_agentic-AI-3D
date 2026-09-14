import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetLibraryPanel } from "./AssetLibraryPanel";
import {
  RuntimeCapabilitiesPanel
} from "./StudioKernel";
import { bundle } from "./StudioKernel.testFixtures";

afterEach(() => cleanup());

describe("studio kernel asset library", () => {
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
    expect(screen.getByRole("link", { name: /Ouvrir la source de Sierra Wireless/ })).toHaveAttribute(
      "href",
      "https://source.sierrawireless.com/6001124.step"
    );
    expect(screen.getByText(/mesh vérifié/)).toBeInTheDocument();
    expect(screen.getByText(/2\s834/)).toBeInTheDocument();
    expect(screen.getByText("Qualification requise")).toBeInTheDocument();
    expect(screen.getByText("Géométries exploitables").parentElement).toHaveTextContent("0");

    fireEvent.change(screen.getByLabelText(/Rechercher un pylône/), {
      target: { value: "pylône Orange 30 m" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));
    expect(onSearch).toHaveBeenCalledWith("pylône Orange 30 m");
  });

  it("opens a professional candidate dossier without offering design use", async () => {
    const onReview = vi.fn().mockResolvedValue({
      asset_id: "ANT_SIERRA_6001124_REFERENCE",
      family: "lte_mimo_panel",
      subtype: "2-in-1 omnidirectional panel antenna",
      manufacturer: "Sierra Wireless / Semtech",
      reference: "6001124",
      source: "vendor_supplied",
      source_provenance: "Source STEP officielle du fabricant et fiche technique associée.",
      original_url: "https://source.sierrawireless.com/6001124.step",
      source_format: "step",
      source_file_sha256: "a".repeat(64),
      license: "Revue interne locale uniquement; redistribution non autorisée.",
      attribution_required: true,
      attribution: "Sierra Wireless / Semtech 6001124",
      geometry_status: "reference_only",
      geometry_fidelity: "technical_generic",
      conversion_method: "Hiérarchie STEP inspectée et aller-retour 3D réel mesuré.",
      generation_eligible: false,
      dimensions_m: { width: 0.15, depth: 0.045, height: 0.049 },
      bounding_box_m: null,
      qualification: {
        status: "reference_only",
        allowed_generation_modes: [],
        units: "meters",
        mesh_integrity_verified: true,
        dimensions_verified: false,
        pivot_verified: false,
        orientation_verified: false,
        limitations: ["Connector identities and anchor coordinates are unverified."]
      },
      qualification_version: null,
      qa: { status: "not_run", checks: [], limitations: [] },
      milestone_evidence_eligible: false,
      milestone_evidence_failures: ["Asset is not qualified for generation."],
      usage_rights: {
        status: "review_only",
        project_use_authorized: false,
        derivative_use_authorized: false,
        redistribution_authorized: false,
        evidence: "Revue interne locale uniquement."
      },
      local_evidence_status: "unavailable",
      representations: [],
      previews: [],
      review: {
        status: "reference_only",
        summary: "La source peut être examinée, mais elle reste exclue des designs.",
        checks: [{
          check_id: "geometry_scale",
          status: "incomplete",
          title: "Géométrie et échelle",
          detail: "Les dimensions complètes restent à qualifier."
        }, {
          check_id: "pivot_orientation",
          status: "incomplete",
          title: "Repère d’installation",
          detail: "Le pivot et l’orientation d’installation restent à mesurer."
        }],
        blockers: [{
          code: "pivot_orientation",
          message: "Le pivot et l’orientation d’installation restent à mesurer."
        }],
        available_actions: [{
          action_id: "open_vendor_source",
          kind: "external_source",
          label: "Ouvrir la source constructeur",
          url: "https://source.sierrawireless.com/6001124.step"
        }, {
          action_id: "view_verified_preview:front",
          kind: "internal_preview",
          label: "Voir la vue vérifiée front",
          url: "/assets/ANT_SIERRA_6001124_REFERENCE/previews/front"
        }]
      }
    });
    render(
      <AssetLibraryPanel
        inventory={{
          status: "qualified_mixed_catalog",
          asset_count: 3,
          missing_file_count: 0,
          real_glb_asset_count: 0,
          import_qualified_glb_count: 0,
          generation_eligible_asset_count: 1,
          professional_evidence_asset_count: 0,
          professional_evidence_rejected_count: 1,
          reference_only_asset_count: 1,
          qualified_integrity_failure_count: 0,
          entries: [{
            asset_id: "ANT_SIERRA_6001124_REFERENCE",
            type: "antenna",
            family: "lte_mimo_panel",
            subtype: "2-in-1 omnidirectional panel antenna",
            manufacturer: "Sierra Wireless / Semtech",
            reference: "6001124",
            source: "vendor_supplied",
            source_format: "step",
            dimensions_m: { width: 0.15, depth: 0.045, height: 0.049 },
            generation_eligible: false,
            qualification_status: "reference_only",
            allowed_generation_modes: [],
            qualification_limitations: ["Stable anchors remain unverified."],
            milestone_evidence_eligible: false,
            milestone_evidence_failures: ["Anchors are not qualified."]
          }, {
            asset_id: "UNPROVED_VENDOR_PANEL",
            type: "antenna",
            family: "vendor_panel",
            subtype: "declared panel",
            manufacturer: "Evidence pending vendor",
            reference: "PANEL-PENDING",
            source: "vendor_supplied",
            source_format: "glb",
            asset_import_mode: "professional_evidence_rejected",
            generation_eligible: false,
            qualification_status: "qualified_for_generation",
            allowed_generation_modes: [],
            qualification_limitations: [],
            milestone_evidence_eligible: false,
            milestone_evidence_failures: ["Viewer representation hash mismatch."]
          }, {
            asset_id: "ANT_GENERIC_PANEL",
            type: "antenna",
            family: "generic_panel",
            subtype: "generic panel",
            manufacturer: null,
            reference: null,
            source: "internal_parametric",
            source_format: "parametric_profile",
            generation_eligible: true,
            qualification_status: "qualified",
            allowed_generation_modes: ["parametric_generated"],
            qualification_limitations: [],
            milestone_evidence_eligible: false,
            milestone_evidence_failures: []
          }],
          missing_files: []
        }}
        onReview={onReview}
        toAbsoluteUrl={(url) => url ? new URL(url, "http://127.0.0.1:8012").toString() : null}
        summary={{
          status: "catalogued_quarantined",
          schema_version: "1.1.0",
          catalog_available: true,
          generation_eligible_count: 0,
          cad_with_reference_preview_count: 0,
          reference_preview_link_count: 0,
          limitations: []
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Examiner Sierra Wireless.*6001124/ }));

    await waitFor(() => expect(onReview).toHaveBeenCalledWith("ANT_SIERRA_6001124_REFERENCE"));
    expect(await screen.findByLabelText("Dossier du candidat professionnel")).toHaveTextContent(
      "Non utilisable dans un design"
    );
    expect(screen.getByText("Maillage contrôlé").parentElement).toHaveTextContent("oui");
    expect(screen.getAllByText(/pivot et l’orientation d’installation/i)).toHaveLength(2);
    expect(screen.getByText("Géométrie et échelle")).toBeInTheDocument();
    expect(screen.getByText("Evidence pending vendor")).toBeInTheDocument();
    expect(screen.getByText("Preuves incohérentes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir la vue vérifiée front" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8012/assets/ANT_SIERRA_6001124_REFERENCE/previews/front"
    );
    expect(screen.queryByRole("button", { name: /utiliser|ajouter/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Rechercher un pylône/), {
      target: { value: "Sierra 6001124" }
    });
    expect(screen.queryByText("ant generic panel")).not.toBeInTheDocument();
    expect(screen.getByText("Sierra Wireless / Semtech", { selector: "strong" })).toBeInTheDocument();
  });

  it("keeps an admitted professional asset inspectable", () => {
    const onReview = vi.fn();
    render(
      <AssetLibraryPanel
        inventory={{
          status: "qualified_mixed_catalog",
          asset_count: 1,
          missing_file_count: 0,
          real_glb_asset_count: 1,
          import_qualified_glb_count: 1,
          generation_eligible_asset_count: 1,
          professional_evidence_asset_count: 1,
          reference_only_asset_count: 0,
          qualified_integrity_failure_count: 0,
          entries: [{
            asset_id: "AUTHORIZED_VENDOR_PANEL",
            type: "antenna",
            family: "sector_panel",
            manufacturer: "Authorized manufacturer",
            reference: "PANEL-001",
            source: "vendor_supplied",
            source_format: "glb",
            asset_import_mode: "imported_glb_exact",
            generation_eligible: true,
            qualification_status: "qualified_for_generation",
            allowed_generation_modes: ["imported_glb_exact"],
            qualification_limitations: [],
            milestone_evidence_eligible: true,
            milestone_evidence_failures: []
          }],
          missing_files: []
        }}
        onReview={onReview}
        summary={null}
      />
    );

    expect(screen.getByText("Authorized manufacturer")).toBeInTheDocument();
    expect(screen.getByText("Admis pour import exact")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Examiner Authorized manufacturer PANEL-001/ }));
    expect(onReview).toHaveBeenCalledWith("AUTHORIZED_VENDOR_PANEL");
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
            related_cad_file_ids: [],
            retrieval_evidence: {
              method: "corpus_idf_metadata",
              matched_terms: { pylone: ["pylone"], "30m": ["30m"] },
              query_coverage: 1,
              geometry_verified: false
            }
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
    expect(screen.getByLabelText("Preuve de recherche catalogue")).toHaveTextContent(
      "Recherche lexicale dans le catalogue"
    );
    expect(screen.getByLabelText("Preuve de recherche catalogue")).toHaveTextContent(
      "Géométrie non vérifiée"
    );
    expect(screen.queryByRole("button", { name: /Blender|utiliser/i })).not.toBeInTheDocument();
  });

  it("shows a real CAD probe without promoting the raw source to Blender", () => {
    const onProbe = vi.fn();
    render(
      <AssetLibraryPanel
        onProbe={onProbe}
        probe={{
          file: {
            file_id: "lib_rfs_mount",
            relative_path: "3D/Antenne/RFS/Fixation/APM40/APM40_Fixation.dwg",
            extension: "dwg",
            size_bytes: 8192,
            claimed_dimension: "3d",
            category: "Antenne",
            license_status: "unknown_requires_review",
            qualification_status: "quarantined_unverified",
            conversion_status: "not_attempted",
            generation_eligible: false,
            reference_preview_file_ids: [],
            related_cad_file_ids: []
          },
          probe_status: "completed",
          tool: "dwgread",
          declared_unit: "millimeters",
          unit_metadata_conflict: true,
          entity_counts: { "3DSOLID": 4 },
          contains_acis_3d_solids: true,
          contains_mesh_convertible_geometry: false,
          conversion_route: "requires_acis_brep_bridge",
          blender_ready: false,
          generation_eligible: false,
          limitations: ["La licence et les unités doivent être confirmées avant validation."]
        }}
        search={{
          query: "APM40 fixation",
          filters: {},
          result_count: 1,
          results: [{
            file_id: "lib_rfs_mount",
            relative_path: "3D/Antenne/RFS/Fixation/APM40/APM40_Fixation.dwg",
            extension: "dwg",
            size_bytes: 8192,
            claimed_dimension: "3d",
            category: "Antenne",
            duplicate_of: null,
            license_status: "unknown_requires_review",
            qualification_status: "quarantined_unverified",
            conversion_status: "not_attempted",
            generation_eligible: false,
            reference_preview_file_ids: [],
            related_cad_file_ids: []
          }],
          selection_policy: "metadata_retrieval_only",
          generation_eligible: false,
          next_action: "Qualifier avant usage."
        }}
        summary={{
          status: "catalogued_quarantined",
          schema_version: "1.1.0",
          catalog_available: true,
          generation_eligible_count: 0,
          cad_with_reference_preview_count: 0,
          reference_preview_link_count: 0,
          dwg_probe_available: true,
          limitations: []
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Examiner le contenu 3D" }));

    expect(onProbe).toHaveBeenCalledWith("lib_rfs_mount");
    expect(screen.getByLabelText("Résultat de l’analyse géométrique")).toHaveTextContent(
      "de vrais solides 3D"
    );
    expect(screen.getByLabelText("Résultat de l’analyse géométrique")).toHaveTextContent(/Géométrie exploitable\s*non/);
    expect(screen.queryByRole("button", { name: /utiliser.*blender|générer/i })).not.toBeInTheDocument();
  });

});
