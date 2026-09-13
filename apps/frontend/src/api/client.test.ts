import { describe, expect, it, vi } from "vitest";
import {
  ContractValidationError,
  ViewerBundleSchema,
  parseContract
} from "./schemas";
import { ApiClientError, TelecomStudioApi } from "./client";

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
    ...init
  });
}

describe("TelecomStudioApi", () => {
  it("forwards an AbortSignal to terminal workflow reads", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      workflow_id: "wf_1",
      status: "completed",
      created_at: "2026-07-15T10:00:00Z",
      artifacts: {},
      warnings: [],
      errors: [],
      available_actions: [],
      unsupported_actions: [],
      completion_certificate_status: "issued"
    }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);
    const controller = new AbortController();

    await client.workflowStatus("wf_1", { signal: controller.signal });

    expect(fetcher).toHaveBeenCalledWith(
      new URL("/designs/wf_1", "http://127.0.0.1:8000"),
      { signal: controller.signal }
    );
  });

  it("loads and validates composition evidence from backend artifact URLs", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "1.0",
        workflow_id: "wf_1",
        components: [{
          component_id: "tower_component",
          role_id: "tower",
          origin: "catalog",
          strategy: "reuse",
          generation_strategy: "reuse",
          asset_id: "TOWER_REAL_1",
          quantity: 1,
          instances: [{
            instance_id: "tower_1",
            object_role: "tower",
            semantic_root: "tower_REAL_1",
            geometry_source: "asset_glb"
          }]
        }],
        geometry_programs: []
      }))
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "1.0",
        workflow_id: "wf_1",
        selection_authority: "bounded_llm",
        selection_provider: "groq",
        selection_model: "openai/gpt-oss-120b",
        components: [],
        connections: [],
        operations: []
      }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const proofs = await client.componentProofs("/designs/wf_1/artifacts/component_proofs.json");
    const plan = await client.assemblyPlan("/designs/wf_1/artifacts/assembly_plan.json");

    expect(proofs?.components[0]?.instances[0]?.semantic_root).toBe("tower_REAL_1");
    expect(plan?.selection_authority).toBe("bounded_llm");
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/designs/wf_1/artifacts/component_proofs.json"
    );
  });
  it("rejects inconsistent geometry-program aggregate counts", () => {
    expect(() =>
      parseContract("ViewerBundle", ViewerBundleSchema, {
        workflow_id: "wf_1",
        status: "completed",
        available_actions: [],
        unsupported_actions: [],
        geometry_program_summary: {
          program_count: 2,
          generated_component_count: 1,
          total_node_count: 3,
          repaired_program_count: 0,
          programs: [
            {
              program_id: "shelter.llm_v1",
              semantic_role: "shelter",
              requested_quantity: 1,
              node_count: 3,
              authorship: "llm_generated",
              generator_provider: "groq",
              generator_model: "openai/gpt-oss-120b",
              structured_output_mode: "strict_json_schema",
              source_prompt_sha256: "a".repeat(64),
              limitations: [],
              deterministic_adjustments: []
            }
          ]
        }
      })
    ).toThrow(ContractValidationError);
  });

  it("loads the real quarantined asset-library summary", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        status: "catalogued_quarantined",
        schema_version: "1.0.0",
        catalog_available: true,
        file_count: 11974,
        generation_eligible_count: 0,
        limitations: ["Licence à vérifier."]
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.assetLibrarySummary();

    expect(result.catalog_available).toBe(true);
    expect(result.generation_eligible_count).toBe(0);
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/assets/library/summary", "http://127.0.0.1:8000")
    );
  });

  it("loads a documented professional candidate without enabling it", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      asset_id: "ANT_SIERRA_6001124_REFERENCE",
      family: "lte_mimo_panel",
      subtype: "2-in-1 omnidirectional panel antenna",
      manufacturer: "Sierra Wireless / Semtech",
      reference: "6001124",
      source: "vendor_supplied",
      source_provenance: "Official manufacturer STEP assembly.",
      original_url: "https://source.sierrawireless.com/6001124.step",
      source_format: "step",
      source_file_sha256: "a".repeat(64),
      license: "Internal review only.",
      attribution_required: true,
      geometry_status: "reference_only",
      geometry_fidelity: "technical_generic",
      conversion_method: "Controlled STEP inspection and Blender roundtrip.",
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
        limitations: ["Anchor coordinates are unverified."]
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
        evidence: "Internal evidence review only."
      },
      local_evidence_status: "unavailable",
      representations: [],
      previews: [],
      review: {
        status: "reference_only",
        summary: "La source peut être examinée, mais elle reste exclue des designs.",
        checks: [],
        blockers: [{ code: "admission", message: "Ce composant ne peut pas entrer dans un design." }],
        available_actions: [{
          action_id: "open_vendor_source",
          kind: "external_source",
          label: "Ouvrir la source constructeur",
          url: "https://source.sierrawireless.com/6001124.step"
        }]
      }
    }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.assetProvenance("ANT_SIERRA_6001124_REFERENCE");

    expect(result.generation_eligible).toBe(false);
    expect(result.qualification.mesh_integrity_verified).toBe(true);
    expect(result.review.status).toBe("reference_only");
    expect(fetcher).toHaveBeenCalledWith(
      new URL(
        "/assets/ANT_SIERRA_6001124_REFERENCE/provenance",
        "http://127.0.0.1:8000"
      )
    );
  });

  it("searches the real asset-library catalog with an encoded query", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        query: "pylône Orange 30 m",
        filters: {},
        result_count: 1,
        results: [{
          file_id: "lib_tower",
          relative_path: "3D/Pylone/Orange/Orange_Pylone_30m_Galva.dwg",
          extension: "dwg",
          size_bytes: 1024,
          claimed_dimension: "3d",
          category: "Pylone",
          duplicate_of: null,
          license_status: "unknown_requires_review",
          qualification_status: "quarantined_unverified",
          conversion_status: "not_attempted",
          generation_eligible: false,
          reference_preview_file_ids: ["lib_preview"]
        }],
        selection_policy: "metadata_retrieval_only",
        generation_eligible: false,
        next_action: "Qualifier la licence et la géométrie."
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.searchAssetLibrary("pylône Orange 30 m");

    expect(result.results[0]?.reference_preview_file_ids).toEqual(["lib_preview"]);
    expect(fetcher).toHaveBeenCalledWith(
      new URL(
        "/assets/library/search?q=pyl%C3%B4ne+Orange+30+m&limit=12",
        "http://127.0.0.1:8000"
      )
    );
  });

  it("requests a local geometry probe through the existing asset-library endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
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
        declared_unit: "millimeters",
        unit_metadata_conflict: true,
        entity_counts: { "3DSOLID": 4 },
        contains_acis_3d_solids: true,
        contains_mesh_convertible_geometry: false,
        conversion_route: "requires_acis_brep_bridge",
        blender_ready: false,
        generation_eligible: false,
        limitations: ["Une conversion et une QA géométrique restent obligatoires."]
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.probeAssetLibrary("lib_rfs_mount");

    expect(result.contains_acis_3d_solids).toBe(true);
    expect(result.conversion_route).toBe("requires_acis_brep_bridge");
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/assets/library/lib_rfs_mount/probe", "http://127.0.0.1:8000"),
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}"
      }
    );
  });

  it("posts designs to the existing /designs contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ workflow_id: "wf_1", status: "pending" }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.createDesign({ requirements_text: "site 5G" });

    expect(result.workflow_id).toBe("wf_1");
    expect(fetcher).toHaveBeenCalledWith(new URL("/designs", "http://127.0.0.1:8000"), {
      body: JSON.stringify({ requirements_text: "site 5G" }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
  });

  it("uses the real requirements parser before design creation", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        requirements: {
          network_type: "5G",
          site_type: "telecom_site",
          tower_type: "lattice_tower",
          tower_height_m: 30,
          tower_characteristics: { structure: "lattice" },
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
          repair_events: []
        },
        requirements_hash: "a".repeat(64),
        warnings: [],
        errors: [],
        provider: "groq:openai/gpt-oss-120b",
        extraction_provider: "llm",
        fallback_used: false,
        llm_fallback_reason: null
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const result = await client.parseRequirements({ requirements_text: "site 5G" });

    expect(result.requirements?.azimuths_deg).toEqual([0, 120, 240]);
    expect(result.requirements_hash).toBe("a".repeat(64));
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/requirements/parse", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({ requirements_text: "site 5G" }),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });

  it("posts the exact confirmed RequirementSpec and its backend hash", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ workflow_id: "wf_2", status: "pending" }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);
    const confirmedAnalysisReceipt = {
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
    const confirmedRequirements = {
      network_type: "5G",
      site_type: "telecom_site",
      tower_type: "lattice_tower",
      tower_height_m: 30,
      tower_characteristics: { structure: "lattice" },
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
    };

    await client.createDesign({
      requirements_text: "site 5G confirmé",
      confirmed_requirements: confirmedRequirements,
      confirmed_requirements_hash: "b".repeat(64),
      confirmed_analysis_receipt: confirmedAnalysisReceipt,
      options: { detail_level: "high", multimodal_consent: "allow_input_analysis" }
    });

    expect(fetcher).toHaveBeenCalledWith(new URL("/designs", "http://127.0.0.1:8000"), {
      body: JSON.stringify({
        requirements_text: "site 5G confirmé",
        confirmed_requirements: confirmedRequirements,
        confirmed_requirements_hash: "b".repeat(64),
        confirmed_analysis_receipt: confirmedAnalysisReceipt,
        options: { detail_level: "high", multimodal_consent: "allow_input_analysis" }
      }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
  });

  it("turns HTTP errors into readable client errors", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ detail: "Backend unavailable" }, { status: 503 }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.health()).rejects.toMatchObject({
      endpoint: "/health",
      message: "Backend unavailable",
      name: "ApiClientError",
      status: 503
    });
  });

  it("rejects invalid backend payloads before UI consumption", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ workflow_id: "wf_1" }));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.createDesign({ requirements_text: "site 5G" })).rejects.toBeInstanceOf(
      ContractValidationError
    );
  });

  it("accepts only public API or HTTP artifact references", () => {
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetch);

    expect(client.artifactUrl("/designs/wf_1/artifacts/glb")).toBe(
      "http://127.0.0.1:8000/designs/wf_1/artifacts/glb"
    );
    expect(client.artifactUrl("https://cdn.example.test/design.glb")).toBe(
      "https://cdn.example.test/design.glb"
    );
    for (const invalid of [
      "/tmp/design.glb",
      "/Volumes/project/design.glb",
      "file:///tmp/design.glb",
      "C:\\temp\\design.glb",
      "design.glb"
    ]) {
      expect(() => client.artifactUrl(invalid)).toThrow(ApiClientError);
    }
  });

  it("prepares edit and rollback calls on the existing /designs contract", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          workflow_id: "wf_1",
          edit_id: "edit_1",
          status: "applied",
          edit_status: "applied",
          message: "Version créée",
          version_id: "v2",
          artifacts: { glb: "/designs/wf_1/artifacts/glb?version_id=v2" },
          available_actions: ["open_viewer"]
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          workflow_id: "wf_1",
          version_id: "v1",
          active_version_id: "v1",
          rolled_back: true,
          status: "rolled_back",
          message: "Version restaurée",
          viewer_bundle_url: "/designs/wf_1/viewer-bundle",
          timeline_url: "/designs/wf_1/timeline-summary",
          user_issues_url: "/designs/wf_1/user-issues",
          current_operation_url: "/designs/wf_1/current-operation",
          available_actions: ["open_viewer"]
        })
      );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.editDesign("wf_1", { edit_prompt: "monte les antennes à 26m" })).resolves.toMatchObject({
      edit_status: "applied",
      version_id: "v2"
    });
    await expect(client.rollbackVersion("wf_1", "v1")).resolves.toMatchObject({
      active_version_id: "v1",
      rolled_back: true
    });
    expect(fetcher).toHaveBeenNthCalledWith(1, new URL("/designs/wf_1/edit", "http://127.0.0.1:8000"), {
      body: JSON.stringify({ edit_prompt: "monte les antennes à 26m" }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      new URL("/designs/wf_1/versions/v1/rollback", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({}),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });

  it("uploads document-pack ZIPs without creating a new product entity", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_1",
        status: "ready",
        document_count: 3,
        can_generate_design: true
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);
    const file = new File(["zip-bytes"], "cahier-charge.zip", { type: "application/zip" });

    const result = await client.createDocumentPack([file]);

    expect(result.pack_id).toBe("pack_1");
    expect(result.can_generate_design).toBe(true);
    expect(fetcher).toHaveBeenCalledWith(new URL("/document-packs", "http://127.0.0.1:8000"), {
      body: file,
      headers: {
        "content-type": "application/zip",
        "x-filename": "cahier-charge.zip"
      },
      method: "POST"
    });
  });

  it("uploads multiple direct documents as multipart without inventing a project entity", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_direct",
        status: "processed",
        document_count: 2,
        can_generate_design: false
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);
    const files = [
      new File(["pdf"], "cahier.pdf", { type: "application/pdf" }),
      new File(["image"], "site.jpg", { type: "image/jpeg" })
    ];

    const result = await client.createDocumentPack(files);

    expect(result.pack_id).toBe("pack_direct");
    const request = fetcher.mock.calls[0][1];
    expect(request.method).toBe("POST");
    expect(request.headers).toEqual({});
    expect(request.body).toBeInstanceOf(FormData);
    expect(Array.from((request.body as FormData).getAll("files"))).toHaveLength(2);
  });

  it("loads the real document-pack review and submits a bounded correction", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          pack_id: "pack_1",
          status: "processed",
          document_count: 2,
          missing_blocking_count: 1,
          conflict_count: 0,
          can_generate_design: false,
          qa_score: 0.6
        })
      )
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            field: "radio.hba_m",
            value: null,
            status: "missing",
            confidence: 0,
            severity: "blocking"
          }
        ])
      )
      .mockResolvedValueOnce(
        jsonResponse({
          pack_id: "pack_1",
          status: "warning",
          score: 0.6,
          checks: [],
          blocking_issues: ["radio.hba_m"],
          ready_to_generate: false,
          ready_confidence: 0.49
        })
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            document_id: "doc_1",
            path: "plans/elevation.pdf",
            filename: "elevation.pdf",
            extension: ".pdf",
            size_bytes: 1200,
            sha256: "a".repeat(64),
            category: "elevation_plan",
            relevance_score: 0.98,
            confidence: 0.95,
            reason: "Contient les hauteurs radio",
            extractability: "text",
            priority: "high",
            purpose: "needed_for_design",
            used_for_design: true,
            why_used_or_ignored: "Source principale HBA",
            cad_status: "not_cad",
            extraction_status: "extracted",
            processing_tools: ["pdf_text"],
            processing_warnings: [],
            duplicate_of: null
          }
        ])
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            field: "radio.hba_m",
            value: 24,
            confidence: 0.95,
            source: {
              document_id: "doc_1",
              file: "elevation.pdf",
              source_type: "text",
              page: 3,
              evidence: "HBA antennes: 24 m"
            }
          }
        ])
      )
      .mockResolvedValueOnce(
        jsonResponse({
          "radio.hba_m": [
            {
              document_id: "doc_1",
              file: "elevation.pdf",
              source_type: "text",
              page: 3,
              evidence: "HBA antennes: 24 m"
            }
          ]
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          pack_id: "pack_1",
          documents: [
            {
              document_id: "doc_1",
              path: "plans/elevation.pdf",
              extension: ".pdf",
              category: "elevation_plan",
              extractability: "text",
              extraction_status: "extracted",
              cad_status: "not_cad",
              processing_tools: ["pdf_text"],
              processing_warnings: []
            }
          ],
          warnings: [],
          tool_status: { pdf: "available" },
          groq_rejected_fields: []
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          pack_id: "pack_1",
          source_mode: "mixed",
          llm_provider: "groq",
          llm_fallback_used: false,
          confidence_summary: { overall: 0.8 },
          processing_warnings: [],
          document_references: [],
          provenance_map: {}
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          pack_id: "pack_1",
          status: "processed",
          document_count: 2,
          missing_blocking_count: 0,
          conflict_count: 0,
          can_generate_design: true,
          qa_score: 1
        })
      );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const review = await client.documentPackReview("pack_1");
    expect(review.missingFields?.[0]?.field).toBe("radio.hba_m");
    await client.applyDocumentPackCorrection("pack_1", {
      field: "radio.hba_m",
      value: [24, 24, 24],
      reason: "Plan d’élévation vérifié"
    });

    expect(fetcher).toHaveBeenNthCalledWith(
      10,
      new URL("/document-packs/pack_1/corrections", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({
          field: "radio.hba_m",
          value: [24, 24, 24],
          reason: "Plan d’élévation vérifié"
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });

  it("keeps successful document-review sections and recovers the failed section on retry", async () => {
    let qaAvailable = false;
    const fetcher = vi.fn(async (request: RequestInfo | URL) => {
      const requestUrl =
        request instanceof URL
          ? request
          : new URL(typeof request === "string" ? request : request.url);
      const path = requestUrl.pathname;
      if (path.endsWith("/qa")) {
        if (!qaAvailable) {
          return jsonResponse({ detail: "temporary QA outage" }, { status: 503 });
        }
        return jsonResponse({
          pack_id: "pack_retry",
          status: "passed",
          score: 1,
          checks: [],
          warnings: [],
          blocking_issues: [],
          ready_to_generate: true,
          ready_confidence: 1,
          recommended_user_actions: [],
          tool_failures: [],
          memory_writeback: {}
        });
      }
      if (path.endsWith("/conflicts") || path.endsWith("/missing-fields")) {
        return jsonResponse([]);
      }
      if (path.endsWith("/documents") || path.endsWith("/extractions")) {
        return jsonResponse([]);
      }
      if (path.endsWith("/provenance")) {
        return jsonResponse({});
      }
      if (path.endsWith("/processing")) {
        return jsonResponse({
          pack_id: "pack_retry",
          documents: [],
          warnings: [],
          tool_status: {},
          groq_rejected_fields: []
        });
      }
      if (path.endsWith("/consolidated-spec")) {
        return jsonResponse({
          pack_id: "pack_retry",
          source_mode: "deterministic",
          llm_provider: null,
          llm_fallback_used: true,
          confidence_summary: {},
          processing_warnings: [],
          document_references: [],
          provenance_map: {}
        });
      }
      return jsonResponse({
        pack_id: "pack_retry",
        status: "processed",
        document_count: 1,
        missing_blocking_count: 0,
        conflict_count: 0,
        can_generate_design: true,
        qa_score: 1
      });
    });
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    const partial = await client.documentPackReview("pack_retry");
    expect(partial.summary?.pack_id).toBe("pack_retry");
    expect(partial.documents).toEqual([]);
    expect(partial.qa).toBeNull();
    expect(partial.sectionErrors?.qa).toEqual({ status: 503, retryable: true });

    qaAvailable = true;
    const recovered = await client.documentPackReview("pack_retry");
    expect(recovered.qa?.ready_to_generate).toBe(true);
    expect(recovered.sectionErrors).toEqual({});
    expect(
      fetcher.mock.calls.filter(([request]) => (request as URL).pathname.endsWith("/qa"))
    ).toHaveLength(2);
  });

  it("starts document-pack generation through the existing workflow_id contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_1",
        status: "started",
        workflow_id: "wf_from_pack"
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(
      client.generateDesignFromDocumentPack("pack_1", "allow_input_analysis")
    ).resolves.toMatchObject({
      workflow_id: "wf_from_pack"
    });
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/document-packs/pack_1/generate-design", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({ multimodal_consent: "allow_input_analysis" }),
        headers: { "content-type": "application/json" },
        method: "POST"
      }
    );
  });

  it("requests bounded workflow-event deltas only when a sequence cursor is provided", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([]));
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await client.workflowEvents("wf_1");
    await client.workflowEvents("wf_1", 42);

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      new URL("/designs/wf_1/events", "http://127.0.0.1:8000")
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      new URL("/designs/wf_1/events?after_sequence=42", "http://127.0.0.1:8000")
    );
  });

  it("adds an encoded after_event_id cursor to the existing SSE route", () => {
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetch);

    expect(client.streamUrl("wf_1", "evt/terminal 1")).toBe(
      "http://127.0.0.1:8000/designs/wf_1/events/stream?after_event_id=evt%2Fterminal+1"
    );
  });
});
