import {
  AdaptationCapabilityCatalogSchema,
  AssetInventorySchema,
  AssetLibrarySearchSchema,
  AssetLibrarySummarySchema,
  CreateDesignResponseSchema,
  CurrentOperationSchema,
  DocumentPackCapabilitiesSchema,
  DocumentExtractionSchema,
  DocumentPackConsolidatedSpecSchema,
  DocumentPackFieldSchema,
  DocumentPackGenerateDesignResponseSchema,
  DocumentPackProvenanceSchema,
  DocumentPackProcessingSchema,
  DocumentPackQASchema,
  DocumentPackSummarySchema,
  DocumentReferenceSchema,
  EditDesignResponseSchema,
  HealthSchema,
  ParseRequirementsResponseSchema,
  RollbackVersionResponseSchema,
  SceneAdaptationCapabilitiesSchema,
  StudioSummarySchema,
  TimelineSummarySchema,
  UserIssuesSchema,
  VersionsSchema,
  ViewerBundleSchema,
  WorkflowEventSchema,
  WorkflowStatusSchema,
  parseContract,
  type AdaptationCapabilityCatalog,
  type AssetInventory,
  type AssetLibrarySearch,
  type AssetLibrarySummary,
  type CreateDesignResponse,
  type CurrentOperation,
  type DocumentPackCapabilities,
  type DocumentPackReview,
  type DocumentPackGenerateDesignResponse,
  type DocumentPackSummary,
  type EditDesignResponse,
  type Health,
  type ParseRequirementsResponse,
  type PublicVersionInfo,
  type RequirementSpec,
  type RollbackVersionResponse,
  type SceneAdaptationCapabilities,
  type StudioSummary,
  type TimelineSummary,
  type UserIssues,
  type ViewerBundle,
  type WorkflowEvent,
  type WorkflowStatus
} from "./schemas";

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly endpoint: string,
    message: string
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export type CreateDesignPayload = {
  requirements_text: string;
  confirmed_requirements?: RequirementSpec;
  confirmed_requirements_hash?: string;
  options?: {
    detail_level?: "low" | "medium" | "high";
    use_llm?: boolean | null;
  };
};

export type EditDesignPayload = {
  edit_prompt: string;
};

export type ParseRequirementsPayload = {
  requirements_text: string;
  detail_level?: "low" | "medium" | "high";
  use_llm?: boolean | null;
};

export type DocumentPackCorrectionPayload = {
  field: string;
  value: string | number | boolean | number[] | string[];
  reason: string;
  confidence?: number;
  corrected_by?: string;
};

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class TelecomStudioApi {
  constructor(
    public readonly baseUrl: string = import.meta.env.VITE_API_BASE_URL ??
      "http://127.0.0.1:8000",
    private readonly fetcher: Fetcher = (input, init) => fetch(input, init)
  ) {}

  async health(): Promise<Health> {
    return parseContract("Health", HealthSchema, await this.getJson("/health"));
  }

  async studioSummary(): Promise<StudioSummary> {
    return parseContract("StudioSummary", StudioSummarySchema, await this.getJson("/studio/summary"));
  }

  async assetInventory(): Promise<AssetInventory> {
    return parseContract("AssetInventory", AssetInventorySchema, await this.getJson("/assets/inventory"));
  }

  async assetLibrarySummary(): Promise<AssetLibrarySummary> {
    return parseContract(
      "AssetLibrarySummary",
      AssetLibrarySummarySchema,
      await this.getJson("/assets/library/summary")
    );
  }

  async searchAssetLibrary(query: string, limit = 12): Promise<AssetLibrarySearch> {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    return parseContract(
      "AssetLibrarySearch",
      AssetLibrarySearchSchema,
      await this.getJson(`/assets/library/search?${params.toString()}`)
    );
  }

  async adaptationCapabilityCatalog(): Promise<AdaptationCapabilityCatalog> {
    return parseContract(
      "AdaptationCapabilityCatalog",
      AdaptationCapabilityCatalogSchema,
      await this.getJson("/assets/adaptation-capabilities")
    );
  }

  async designAdaptationCapabilities(workflowId: string): Promise<SceneAdaptationCapabilities> {
    return parseContract(
      "SceneAdaptationCapabilities",
      SceneAdaptationCapabilitiesSchema,
      await this.getJson(`/designs/${encodeURIComponent(workflowId)}/adaptation-capabilities`)
    );
  }

  async documentPackCapabilities(): Promise<DocumentPackCapabilities> {
    return parseContract(
      "DocumentPackCapabilities",
      DocumentPackCapabilitiesSchema,
      await this.getJson("/document-packs/capabilities")
    );
  }

  async parseRequirements(payload: ParseRequirementsPayload): Promise<ParseRequirementsResponse> {
    return parseContract(
      "ParseRequirementsResponse",
      ParseRequirementsResponseSchema,
      await this.postJson("/requirements/parse", payload)
    );
  }

  async createDocumentPack(file: File): Promise<DocumentPackSummary> {
    assertZipDocumentPack(file);
    return parseContract(
      "DocumentPackSummary",
      DocumentPackSummarySchema,
      await this.postBinary("/document-packs", file, {
        "content-type": "application/zip",
        "x-filename": file.name
      })
    );
  }

  async documentPackReview(packId: string): Promise<DocumentPackReview> {
    const [
      summary,
      conflicts,
      missingFields,
      qa,
      documents,
      extractions,
      provenance,
      processing,
      consolidatedSpec
    ] = await Promise.all([
      this.getJson(`/document-packs/${packId}`),
      this.getJson(`/document-packs/${packId}/conflicts`),
      this.getJson(`/document-packs/${packId}/missing-fields`),
      this.getJson(`/document-packs/${packId}/qa`),
      this.getJson(`/document-packs/${packId}/documents`),
      this.getJson(`/document-packs/${packId}/extractions`),
      this.getJson(`/document-packs/${packId}/provenance`),
      this.getJson(`/document-packs/${packId}/processing`),
      this.getJson(`/document-packs/${packId}/consolidated-spec`)
    ]);
    return {
      summary: parseContract("DocumentPackSummary", DocumentPackSummarySchema, summary),
      conflicts: parseContract(
        "DocumentPackConflicts",
        DocumentPackFieldSchema.array(),
        conflicts
      ),
      missingFields: parseContract(
        "DocumentPackMissingFields",
        DocumentPackFieldSchema.array(),
        missingFields
      ),
      qa: parseContract("DocumentPackQA", DocumentPackQASchema, qa),
      documents: parseContract("DocumentPackDocuments", DocumentReferenceSchema.array(), documents),
      extractions: parseContract("DocumentPackExtractions", DocumentExtractionSchema.array(), extractions),
      provenance: parseContract(
        "DocumentPackProvenance",
        DocumentPackProvenanceSchema,
        provenance
      ),
      processing: parseContract("DocumentPackProcessing", DocumentPackProcessingSchema, processing),
      consolidatedSpec: parseContract(
        "DocumentPackConsolidatedSpec",
        DocumentPackConsolidatedSpecSchema,
        consolidatedSpec
      )
    };
  }

  async applyDocumentPackCorrection(
    packId: string,
    correction: DocumentPackCorrectionPayload
  ): Promise<DocumentPackSummary> {
    return parseContract(
      "DocumentPackSummary",
      DocumentPackSummarySchema,
      await this.postJson(`/document-packs/${packId}/corrections`, correction)
    );
  }

  async generateDesignFromDocumentPack(packId: string): Promise<DocumentPackGenerateDesignResponse> {
    return parseContract(
      "DocumentPackGenerateDesignResponse",
      DocumentPackGenerateDesignResponseSchema,
      await this.postJson(`/document-packs/${packId}/generate-design`, {})
    );
  }

  async listDesigns(): Promise<WorkflowStatus[]> {
    const payload = await this.getJson("/designs");
    return parseContract("DesignList", WorkflowStatusSchema.array(), payload);
  }

  async createDesign(payload: CreateDesignPayload): Promise<CreateDesignResponse> {
    return parseContract(
      "CreateDesignResponse",
      CreateDesignResponseSchema,
      await this.postJson("/designs", payload)
    );
  }

  async workflowStatus(workflowId: string): Promise<WorkflowStatus> {
    return parseContract(
      "WorkflowStatus",
      WorkflowStatusSchema,
      await this.getJson(`/designs/${workflowId}`)
    );
  }

  async workflowEvents(workflowId: string): Promise<WorkflowEvent[]> {
    return parseContract(
      "WorkflowEvents",
      WorkflowEventSchema.array(),
      await this.getJson(`/designs/${workflowId}/events`)
    );
  }

  async viewerBundle(workflowId: string): Promise<ViewerBundle> {
    return parseContract(
      "ViewerBundle",
      ViewerBundleSchema,
      await this.getJson(`/designs/${workflowId}/viewer-bundle`)
    );
  }

  async timelineSummary(workflowId: string): Promise<TimelineSummary> {
    return parseContract(
      "TimelineSummary",
      TimelineSummarySchema,
      await this.getJson(`/designs/${workflowId}/timeline-summary`)
    );
  }

  async currentOperation(workflowId: string): Promise<CurrentOperation> {
    return parseContract(
      "CurrentOperation",
      CurrentOperationSchema,
      await this.getJson(`/designs/${workflowId}/current-operation`)
    );
  }

  async userIssues(workflowId: string): Promise<UserIssues> {
    return parseContract(
      "UserIssues",
      UserIssuesSchema,
      await this.getJson(`/designs/${workflowId}/user-issues`)
    );
  }

  async versions(workflowId: string): Promise<PublicVersionInfo[]> {
    return parseContract("Versions", VersionsSchema, await this.getJson(`/designs/${workflowId}/versions`));
  }

  async editDesign(workflowId: string, payload: EditDesignPayload): Promise<EditDesignResponse> {
    return parseContract(
      "EditDesignResponse",
      EditDesignResponseSchema,
      await this.postJson(`/designs/${workflowId}/edit`, payload)
    );
  }

  async rollbackVersion(workflowId: string, versionId: string): Promise<RollbackVersionResponse> {
    return parseContract(
      "RollbackVersionResponse",
      RollbackVersionResponseSchema,
      await this.postJson(`/designs/${workflowId}/versions/${versionId}/rollback`, {})
    );
  }

  artifactUrl(relativeUrl: string | null | undefined): string | null {
    if (!relativeUrl) {
      return null;
    }
    if (relativeUrl.includes("/Users/")) {
      throw new ApiClientError(0, relativeUrl, "Backend returned a local filesystem path.");
    }
    return new URL(relativeUrl, this.baseUrl).toString();
  }

  async artifactJson(relativeUrl: string | null | undefined): Promise<unknown | null> {
    if (!relativeUrl) {
      return null;
    }
    const url = this.artifactUrl(relativeUrl);
    if (!url) {
      return null;
    }
    const response = await this.fetcher(url);
    return this.responseJson(response, relativeUrl);
  }

  streamUrl(workflowId: string, afterEventId?: string | null): string {
    const url = new URL(`/designs/${workflowId}/events/stream`, this.baseUrl);
    if (afterEventId) {
      url.searchParams.set("after_event_id", afterEventId);
    }
    return url.toString();
  }

  private async getJson(endpoint: string): Promise<unknown> {
    const response = await this.fetcher(new URL(endpoint, this.baseUrl));
    return this.responseJson(response, endpoint);
  }

  private async postJson(endpoint: string, payload: unknown): Promise<unknown> {
    const response = await this.fetcher(new URL(endpoint, this.baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
    return this.responseJson(response, endpoint);
  }

  private async postBinary(
    endpoint: string,
    body: BodyInit,
    headers: Record<string, string>
  ): Promise<unknown> {
    const response = await this.fetcher(new URL(endpoint, this.baseUrl), {
      method: "POST",
      headers,
      body
    });
    return this.responseJson(response, endpoint);
  }

  private async responseJson(response: Response, endpoint: string): Promise<unknown> {
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const payload = await response.json();
        detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload);
      } catch {
        detail = await response.text();
      }
      throw new ApiClientError(response.status, endpoint, detail || "Backend request failed.");
    }
    return response.json();
  }
}

export const api = new TelecomStudioApi();

const ZipMimeTypes = new Set([
  "application/zip",
  "application/x-zip-compressed",
  "application/octet-stream"
]);

export function assertZipDocumentPack(file: File): void {
  const hasZipName = file.name.toLowerCase().endsWith(".zip");
  const hasSupportedMime = !file.type || ZipMimeTypes.has(file.type.toLowerCase());
  if (hasZipName && hasSupportedMime) {
    return;
  }
  throw new ApiClientError(
    0,
    "/document-packs",
    "Le backend accepte uniquement une archive ZIP. Regroupez les PDF, images, DXF ou autres fichiers dans un ZIP avant l’envoi."
  );
}
