import { describe, expect, it } from "vitest";
import {
  ContractValidationError,
  AssetLibrarySearchSchema,
  DocumentPackFieldSchema,
  DocumentPackQASchema,
  ParseRequirementsResponseSchema,
  SceneAdaptationCapabilitiesSchema,
  ViewerBundleSchema,
  WorkflowEventSchema,
  parseContract
} from "./schemas";

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
  rag_context_count: 3,
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
        reference_preview_file_ids: ["lib_image"]
      }],
      selection_policy: "metadata_retrieval_only",
      generation_eligible: false,
      next_action: "Qualifier avant usage."
    });

    expect(parsed.results[0]?.generation_eligible).toBe(false);
    expect(parsed.results[0]?.reference_preview_file_ids).toEqual(["lib_image"]);
  });

  it("accepts real backend style viewer payloads", () => {
    const parsed = parseContract("ViewerBundle", ViewerBundleSchema, viewerBundlePayload);

    expect(parsed.primary_glb_url).toBe("/designs/wf_123/artifacts/design.glb");
    expect(parsed.viewer_artifacts).toHaveLength(1);
  });

  it("rejects local filesystem paths in public payloads", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        ...viewerBundlePayload,
        primary_glb_url: "/Users/imad/Desktop/output.glb"
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
    for (const forbidden of ["file:///tmp/design.glb", "/home/user/design.glb", "C:\\temp\\design.glb"]) {
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
