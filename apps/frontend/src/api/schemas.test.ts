import { describe, expect, it } from "vitest";
import {
  AssemblyPlanEvidenceSchema,
  AssetInventorySchema,
  ContractValidationError,
  AssetLibraryProbeSchema,
  AssetLibrarySearchSchema,
  ComponentProofsSchema,
  DocumentPackFieldSchema,
  DocumentPackQASchema,
  MultimodalIntelligenceSchema,
  ParseRequirementsResponseSchema,
  SceneAdaptationCapabilitiesSchema,
  StudioSummarySchema,
  ViewerBundleSchema,
  WorkflowEventSchema,
  parseContract
} from "./schemas";

it("accepts the studio's public reindex routes while rejecting local storage paths", () => {
  expect(StudioSummarySchema.safeParse({
    rag_reindex_url: "/rag/reindex",
    memory_vector_reindex_url: "/memory/vector/reindex"
  }).success).toBe(true);
  for (const path of ["/Users/imad/studio.db", "/memory/private/studio.db", "/rag/private.json"]) {
    expect(StudioSummarySchema.safeParse({ memory_vector_reindex_url: path }).success).toBe(false);
  }
});

const viewerBundlePayload = {
  workflow_id: "wf_123",
  status: "completed",
  generation_mode: "real_blender",
  mesh_qa_level: "mesh_level_transform_basic",
  mesh_qa_passed: true,
  qa_score: 0.91,
  requirement_coverage_passed: true,
  requirement_coverage_ratio: 1,
  completion_certificate_status: "issued",
  primary_glb_url: "/designs/wf_123/artifacts/design.glb",
  preview_url: "/designs/wf_123/artifacts/preview.png",
  component_proofs_url: "/designs/wf_123/artifacts/component_proofs.json",
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
  },
  rag_context_count: 3,
  qa_summary: {
    qa_status: "passed",
    qa_executed: true,
    blocked_before_qa: false,
    checks_passed: ["glb_structural"],
    checks_failed: [],
    warnings: [],
    errors: [],
    upstream_errors: [],
    limitations: [],
    preview_pixel_framing_qa: true
  },
  viewer_artifacts: [
    {
      name: "design.glb",
      url: "/designs/wf_123/artifacts/design.glb",
      content_type: "model/gltf-binary",
      available: true
    }
  ],
  limitations: [],
  unsupported_actions: []
};

describe("frontend contract schemas", () => {
  it("accepts optional governed multimodal, visual review and asset evidence fields", () => {
    const bundle = parseContract("ViewerBundle", ViewerBundleSchema, {
      ...viewerBundlePayload,
      multimodal_consent: "allow_input_analysis",
      multimodal_intelligence: {
        status: "operational",
        enabled: true,
        requires_project_consent: true,
        max_images_per_request: 3,
        max_image_bytes: 20_000_000,
        remote_processing: true,
        capabilities: ["multimodal_interpretation"],
        visual_design_critic: "disabled_until_m5"
      },
      visual_review: {
        status: "review_required",
        advisory_only: true,
        summary: "Un détail mérite une vérification humaine.",
        findings: ["Support partiellement masqué"],
        limitations: ["Avis non certifiant"]
      }
    });
    const inventory = parseContract("AssetInventory", AssetInventorySchema, {
      status: "qualified",
      asset_count: 1,
      missing_file_count: 0,
      real_glb_asset_count: 1,
      professional_evidence_asset_count: 0,
      entries: [{
        asset_id: "ANT_5011006",
        type: "antenna",
        source: "Catalogue qualifié",
        qualification_status: "qualified",
        milestone_evidence_eligible: false,
        milestone_evidence_failures: ["Professional QA report file is missing."],
        preview_set: [{
          view: "front",
          url: "/assets/ANT_5011006/previews/front.png",
          sha256: "a".repeat(64),
          width_px: 1024,
          height_px: 1024,
          qa_status: "passed"
        }],
        provenance_url: "/assets/ANT_5011006/provenance",
        fidelity_status: "exact_import",
        visual_review_status: "passed_advisory"
      }]
    });

    expect(bundle.multimodal_consent).toBe("allow_input_analysis");
    expect(bundle.visual_review?.advisory_only).toBe(true);
    expect(inventory.entries[0]?.preview_set?.[0]?.view).toBe("front");
    expect(inventory.entries[0]?.milestone_evidence_eligible).toBe(false);
    expect(inventory.professional_evidence_asset_count).toBe(0);
  });

  it("accepts optional post-export assembly constraint evidence", () => {
    const bundle = parseContract("ViewerBundle", ViewerBundleSchema, {
      ...viewerBundlePayload,
      assembly_constraint_summary: {
        status: "passed",
        measurement_scope: "exported_glb_anchor_frames",
        required_connection_count: 8,
        measured_instance_count: 14,
        resolved_support_count: 3,
        max_position_error_m: 0.012,
        max_angular_error_deg: 0.45,
        limitations: ["Mesure bornée aux connexions déclarées."]
      },
      constraint_evidence_url: "/designs/wf_123/artifacts/constraint_evidence"
    });

    expect(bundle.assembly_constraint_summary?.status).toBe("passed");
    expect(bundle.assembly_constraint_summary?.max_position_error_m).toBe(0.012);
    expect(bundle.assembly_constraint_summary?.resolved_support_count).toBe(3);
    expect(bundle.constraint_evidence_url).toBe(
      "/designs/wf_123/artifacts/constraint_evidence"
    );
  });

  it("rejects invalid post-export assembly constraint measurements", () => {
    expect(() => ViewerBundleSchema.parse({
      ...viewerBundlePayload,
      assembly_constraint_summary: {
        status: "passed",
        measurement_scope: "exported_glb_anchor_frames",
        required_connection_count: -1,
        measured_instance_count: 2,
        max_position_error_m: -0.1,
        max_angular_error_deg: 0.5,
        limitations: []
      }
    })).toThrow();
    expect(() => ViewerBundleSchema.parse({
      ...viewerBundlePayload,
      assembly_constraint_summary: {
        status: "claimed_professional",
        measurement_scope: "exported_glb_anchor_frames",
        required_connection_count: 1,
        measured_instance_count: 2,
        max_position_error_m: 0.1,
        max_angular_error_deg: 0.5,
        limitations: []
      }
    })).toThrow();
  });

  it("keeps legacy viewer and inventory payloads valid without M1 optional fields", () => {
    expect(() => ViewerBundleSchema.parse(viewerBundlePayload)).not.toThrow();
    expect(() => AssetInventorySchema.parse({
      status: "qualified",
      asset_count: 0,
      missing_file_count: 0,
      real_glb_asset_count: 0,
      entries: []
    })).not.toThrow();
  });

  it("enforces the public 20,000,000-byte vision image ceiling", () => {
    const capability = {
      status: "operational",
      enabled: true,
      requires_project_consent: true,
      max_images_per_request: 3,
      max_image_bytes: 20_000_000,
      remote_processing: true,
      capabilities: ["multimodal_interpretation"],
      visual_design_critic: "disabled_until_m5"
    };
    expect(() => MultimodalIntelligenceSchema.parse(capability)).not.toThrow();
    expect(() => MultimodalIntelligenceSchema.parse({
      ...capability,
      max_image_bytes: 20 * 1024 * 1024
    })).toThrow();
  });

  it("validates real component proofs and bounded assembly decisions", () => {
    const proofs = parseContract("ComponentProofs", ComponentProofsSchema, {
      schema_version: "1.0",
      workflow_id: "wf_1",
      components: [{
        component_id: "antenna_component",
        role_id: "antenna",
        origin: "catalog",
        strategy: "adapt",
        generation_strategy: "asset_adaptation",
        asset_id: "ANT_REAL_1",
        quantity: 1,
        instances: [{
          instance_id: "antenna_1",
          object_role: "antenna",
          semantic_root: "antenna_S1_REAL_1",
          geometry_source: "asset_glb"
        }]
      }],
      geometry_programs: []
    });
    const plan = parseContract("AssemblyPlan", AssemblyPlanEvidenceSchema, {
      schema_version: "1.0",
      workflow_id: "wf_1",
      selection_authority: "bounded_llm",
      selection_provider: "groq",
      selection_model: "openai/gpt-oss-120b",
      components: [{
        role_id: "antenna",
        asset_type: "antenna",
        required: true,
        candidate_scores: [{ asset_id: "ANT_REAL_1", total_score: 0.95, reasons: ["compatible"] }],
        selected_asset_id: "ANT_REAL_1",
        generation_strategy: "asset_adaptation",
        selection_reason: "Candidate compatible le mieux classé."
      }]
    });

    expect(proofs.components[0]?.instances[0]?.semantic_root).toBe("antenna_S1_REAL_1");
    expect(plan.components[0]?.candidate_scores[0]?.total_score).toBe(0.95);
    expect(() => ComponentProofsSchema.parse({
      schema_version: "1.0",
      workflow_id: "wf_bad",
      components: [{
        component_id: "bad",
        role_id: "bad",
        origin: "catalog",
        strategy: "free_code",
        generation_strategy: "free_code",
        asset_id: null,
        quantity: 1,
        instances: []
      }]
    })).toThrow();
  });
  it("accepts pinned exact imports and rejects contradictory geometry provenance", () => {
    const program = {
      component_id: "geometry_program:reuse.antenna",
      role_id: "antenna",
      origin: "catalog_asset",
      strategy: "reuse",
      generation_strategy: "imported_glb_exact",
      quantity: 1,
      exact_asset_sources: [{
        asset_id: "ANT_PANEL_4G_001",
        asset_file: "assets/processed/antenna.glb",
        asset_sha256: "a".repeat(64),
        manifest_file_name: "ANT_PANEL_4G_001.json",
        manifest_sha256: "b".repeat(64)
      }]
    };
    const proof = (overrides = {}) => ({
      schema_version: "1.0",
      workflow_id: "wf_1",
      geometry_programs: [{ ...program, ...overrides }]
    });
    expect(ComponentProofsSchema.parse(proof()).geometry_programs[0]?.exact_asset_sources?.[0]?.asset_id)
      .toBe("ANT_PANEL_4G_001");
    for (const overrides of [
      { origin: "geometry_program" },
      { strategy: "procedural_generate" },
      { generation_strategy: "geometry_program_v2" },
      { exact_asset_sources: [] },
      { quantity: 2 },
      { exact_asset_sources: [{ ...program.exact_asset_sources[0], asset_sha256: "missing" }] }
    ]) {
      expect(() => ComponentProofsSchema.parse(proof(overrides))).toThrow();
    }
    expect(() => ComponentProofsSchema.parse(proof({
      origin: "geometry_program", strategy: "procedural_generate",
      generation_strategy: "geometry_program_v2", exact_asset_sources: undefined
    }))).not.toThrow();
  });

  it("validates quarantined library search results and preview links", () => {
    const parsed = parseContract("AssetLibrarySearch", AssetLibrarySearchSchema, {
      query: "pylone 30m",
      result_count: 1,
      results: [{
        file_id: "lib_tower",
        relative_path: "3D/Pylone/Orange_Pylone_30m.dwg",
        extension: "dwg",
        size_bytes: 2048,
        claimed_dimension: "3d",
        category: "Pylone",
        license_status: "unknown_requires_review",
        qualification_status: "quarantined_unverified",
        conversion_status: "not_attempted",
        generation_eligible: false,
        reference_preview_file_ids: ["lib_image"],
        retrieval_evidence: {
          method: "corpus_idf_metadata",
          matched_terms: { pylone: ["pylone"], "30m": ["30m"] },
          query_coverage: 1,
          geometry_verified: false
        }
      }],
      selection_policy: "metadata_retrieval_only",
      generation_eligible: false,
      next_action: "Qualifier avant usage."
    });

    expect(parsed.results[0]?.generation_eligible).toBe(false);
    expect(parsed.results[0]?.reference_preview_file_ids).toEqual(["lib_image"]);
    expect(parsed.results[0]?.retrieval_evidence?.geometry_verified).toBe(false);
  });

  it("preserves a real DWG probe as quarantined evidence", () => {
    const parsed = parseContract("AssetLibraryProbe", AssetLibraryProbeSchema, {
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
        reference_preview_file_ids: []
      },
      probe_status: "completed",
      tool: "dwgread",
      parser_mode: "latin1_non_finite_normalized",
      sanitized_non_finite_values: 2,
      declared_unit: "millimeters",
      unit_metadata_conflict: true,
      entity_counts: { "3DSOLID": 4 },
      contains_acis_3d_solids: true,
      contains_mesh_convertible_geometry: false,
      conversion_route: "requires_acis_brep_bridge",
      blender_ready: false,
      generation_eligible: false,
      limitations: ["Les solides ACIS exigent une passerelle CAD B-Rep avant Blender."]
    });

    expect(parsed.file.generation_eligible).toBe(false);
    expect(parsed.blender_ready).toBe(false);
    expect(parsed.unit_metadata_conflict).toBe(true);
  });

  it("accepts real backend style viewer payloads", () => {
    const parsed = parseContract("ViewerBundle", ViewerBundleSchema, viewerBundlePayload);

    expect(parsed.primary_glb_url).toBe("/designs/wf_123/artifacts/design.glb");
    expect(parsed.component_proofs_url).toBe(
      "/designs/wf_123/artifacts/component_proofs.json"
    );
    expect(parsed.viewer_artifacts).toHaveLength(1);
    expect(parsed.geometry_fidelity_summary?.counts.technical_generic).toBe(6);
    expect(parsed.geometry_fidelity_summary?.roles.technical_generic).toEqual([
      "antenna",
      "radio"
    ]);
    expect(parsed.qa_summary?.qa_status).toBe("passed");
    expect(parsed.qa_summary?.qa_executed).toBe(true);
  });

  it("rejects inconsistent geometry fidelity component counts", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        geometry_fidelity_summary: {
          ...viewerBundlePayload.geometry_fidelity_summary,
          component_count: 99
        }
      })
    ).toThrow(ContractValidationError);
  });

  it("accepts explicit quarantine states and rejects unknown lifecycle states", () => {
    expect(
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        status: "integrity_failed",
        completion_certificate_status: "rejected",
        primary_glb_url: null,
        preview_url: null,
        viewer_artifacts: []
      }).status
    ).toBe("integrity_failed");
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        status: "completed_without_proof"
      })
    ).toThrow(ContractValidationError);
  });

  it("rejects local filesystem paths in public payloads", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        primary_glb_url: "/srv/private-output/design.glb"
      })
    ).toThrow(ContractValidationError);
  });

  it("rejects internal path fields even when nested", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        viewer_artifacts: [
          {
            name: "design.glb",
            url: "/designs/wf_123/artifacts/design.glb",
            content_type: "model/gltf-binary",
            available: true,
            local_path: "/tmp/design.glb"
          }
        ]
      })
    ).toThrow(ContractValidationError);
  });

  it("rejects cross-platform local paths and raw stack traces", () => {
    for (const forbidden of [
      "file:///tmp/design.glb",
      "/home/user/design.glb",
      "/tmp/design.glb",
      "/Volumes/project/design.glb",
      "C:\\temp\\design.glb"
    ]) {
      expect(() =>
        parseContract("ViewerBundle", ViewerBundleSchema, {
          ...viewerBundlePayload,
          primary_glb_url: forbidden
        })
      ).toThrow(ContractValidationError);
    }
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        traceback: "Traceback (most recent call last)"
      })
    ).toThrow(ContractValidationError);
  });

  it("accepts normalized event fields from the backend", () => {
    const parsed = parseContract("WorkflowEvent", WorkflowEventSchema, {
      event_id: "evt_1",
      event_type: "node_started",
      workflow_id: "wf_123",
      timestamp: "2026-06-16T10:00:00Z",
      event_source: "langgraph",
      payload: {
        phase: "planning",
        node: "scene_planner",
        human_label: "Construction SceneSpec",
        progress_message: "Le planner structure la scène.",
        status: "running",
        warnings: [],
        errors: [],
        artifact_refs: []
      }
    });

    expect(parsed.payload.human_label).toBe("Construction SceneSpec");
  });

  it("validates the backend RequirementSpec understanding contract", () => {
    const parsed = parseContract("ParseRequirements", ParseRequirementsResponseSchema, {
      requirements: {
        network_type: "5G",
        site_type: "telecom_site",
        tower_type: "lattice_tower",
        tower_height_m: 30,
        tower_characteristics: {
          structure: "lattice",
          foundation_type: "concrete_pad"
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
        warnings: [{ code: "DEFAULT_BEAMWIDTH_USED", message: "Beamwidth assumed." }]
      },
      requirements_hash: "a".repeat(64),
      warnings: [],
      errors: [],
      provider: "groq:openai/gpt-oss-120b",
      extraction_provider: "llm",
      fallback_used: false
    });

    expect(parsed.requirements?.include_gps_antenna).toBe(true);
    expect(parsed.requirements_hash).toBe("a".repeat(64));
    expect(parsed.requirements?.warnings[0]?.code).toBe("DEFAULT_BEAMWIDTH_USED");
  });

  it("validates document-pack review fields and QA without requiring raw specs", () => {
    const field = parseContract("DocumentPackField", DocumentPackFieldSchema, {
      field: "radio.hba_m",
      value: null,
      status: "missing",
      confidence: 0,
      severity: "blocking"
    });
    const qa = parseContract("DocumentPackQA", DocumentPackQASchema, {
      pack_id: "pack_1",
      status: "warning",
      score: 0.75,
      checks: [
        { name: "no_blocking_missing_fields", passed: false, reason: "HBA is required." }
      ],
      blocking_issues: ["radio.hba_m"],
      ready_to_generate: false,
      ready_confidence: 0.49,
      recommended_user_actions: ["Confirm HBA"]
    });

    expect(field.severity).toBe("blocking");
    expect(qa.ready_to_generate).toBe(false);
    expect(qa.checks[0]?.passed).toBe(false);
  });

  it("validates resolved adaptation capabilities from the active SceneSpec", () => {
    const parsed = parseContract(
      "SceneAdaptationCapabilities",
      SceneAdaptationCapabilitiesSchema,
      {
        scene_id: "wf_123",
        catalog_version: "1.0.0",
        catalog_hash: "a".repeat(64),
        capabilities: [
          {
            capability_id: "accessory_1:accessory_scale",
            asset_id: "GPS_ANTENNA_001",
            profile_id: "accessory_transform_v1",
            label: "Échelle de l'accessoire",
            path: "/accessory_assets/0/scale",
            value_type: "vector3",
            execution_tool: "asset_transform",
            effect: "geometry",
            description: "Échelle XYZ vérifiée.",
            minimum: 0.05,
            maximum: 20,
            allowed_values: [],
            requires_regeneration: true
          }
        ],
        unsupported_operations: ["Pas de retopologie libre"],
        missing_profiles: []
      }
    );

    expect(parsed.capabilities[0]?.execution_tool).toBe("asset_transform");
    expect(parsed.missing_profiles).toHaveLength(0);
  });
});
