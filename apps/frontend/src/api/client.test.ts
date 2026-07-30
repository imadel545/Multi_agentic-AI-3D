import { describe, expect, it, vi } from "vitest";
import { ContractValidationError } from "./schemas";
import { ApiClientError, TelecomStudioApi } from "./client";

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json" },
    ...init
  });
}

describe("TelecomStudioApi", () => {
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
      options: { detail_level: "high" }
    });

    expect(fetcher).toHaveBeenCalledWith(new URL("/designs", "http://127.0.0.1:8000"), {
      body: JSON.stringify({
        requirements_text: "site 5G confirmé",
        confirmed_requirements: confirmedRequirements,
        confirmed_requirements_hash: "b".repeat(64),
        options: { detail_level: "high" }
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

  it("blocks artifact URLs that expose local paths", () => {
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetch);

    expect(() => client.artifactUrl("/Users/imad/output/design.glb")).toThrow(ApiClientError);
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
    expect(review.missingFields[0]?.field).toBe("radio.hba_m");
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

  it("starts document-pack generation through the existing workflow_id contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        pack_id: "pack_1",
        status: "started",
        workflow_id: "wf_from_pack"
      })
    );
    const client = new TelecomStudioApi("http://127.0.0.1:8000", fetcher);

    await expect(client.generateDesignFromDocumentPack("pack_1")).resolves.toMatchObject({
      workflow_id: "wf_from_pack"
    });
    expect(fetcher).toHaveBeenCalledWith(
      new URL("/document-packs/pack_1/generate-design", "http://127.0.0.1:8000"),
      {
        body: JSON.stringify({}),
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
