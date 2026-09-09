import {
  AdaptationCapabilityCatalogSchema,
  AssemblyPlanEvidenceSchema,
  AssetInventorySchema,
  AssetLibrarySearchSchema,
  AssetLibrarySummarySchema,
  CreateDesignResponseSchema,
  ComponentProofsSchema,
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
  LLMDecisionProvenanceSchema,
  ParseRequirementsResponseSchema,
  RequirementSpecSchema,
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
  type AssemblyPlanEvidence,
  type AssetInventory,
  type AssetLibrarySearch,
  type AssetLibrarySummary,
  type CreateDesignResponse,
  type ComponentProofs,
  type CurrentOperation,
  type DocumentPackCapabilities,
  type DocumentPackReview,
  type DocumentPackReviewSection,
  type DocumentPackReviewSectionError,
  type DocumentPackGenerateDesignResponse,
  type DocumentPackSummary,
  type EditDesignResponse,
  type Health,
  type LLMDecisionProvenance,
  type MultimodalConsent,
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
import { isPublicArtifactReference } from "./publicUrl";

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
    multimodal_consent?: MultimodalConsent;
  };
};

export type EditDesignPayload = {
  edit_prompt: string;
} & (
  | { target_semantic_root: string; expected_version_id: string }
  | { target_semantic_root?: never; expected_version_id?: never }
);

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
type RequestOptions = Pick<RequestInit, "signal">;

export class TelecomStudioApi {
  constructor(
    public readonly baseUrl: string = defaultApiBaseUrl(),
    private readonly fetcher: Fetcher = (input, init) => fetch(input, init)
  ) {}

  async health(): Promise<Health> {
    return parseContract("Health", HealthSchema, await this.getJson("/health"));
  }

  async studioSummary(options?: RequestOptions): Promise<StudioSummary> {
    return parseContract(
      "StudioSummary",
      StudioSummarySchema,
      await this.getJson("/studio/summary", options)
    );
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

  async createDocumentPack(files: File[]): Promise<DocumentPackSummary> {
    assertDocumentPackFiles(files);
    if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
      const file = files[0];
      return parseContract(
        "DocumentPackSummary",
        DocumentPackSummarySchema,
        await this.postBinary("/document-packs", file, {
          "content-type": "application/zip",
          "x-filename": file.name
        })
      );
    }
    const form = new FormData();
    for (const file of files) {
      form.append("files", file, file.name);
    }
    return parseContract(
      "DocumentPackSummary",
      DocumentPackSummarySchema,
      await this.postBinary("/document-packs", form)
    );
  }

  async documentPackReview(packId: string): Promise<DocumentPackReview> {
    const [
      summaryResult,
      conflictsResult,
      missingFieldsResult,
      qaResult,
      documentsResult,
      extractionsResult,
      provenanceResult,
      processingResult,
      consolidatedSpecResult
    ] = await Promise.allSettled([
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
    const sectionErrors: Partial<
      Record<DocumentPackReviewSection, DocumentPackReviewSectionError>
    > = {};
    const failures: unknown[] = [];
    const section = <T,>(
      name: DocumentPackReviewSection,
      result: PromiseSettledResult<unknown>,
      parse: (payload: unknown) => T
    ): T | null => {
      if (result.status === "rejected") {
        failures.push(result.reason);
        sectionErrors[name] = documentPackSectionError(result.reason);
        return null;
      }
      try {
        return parse(result.value);
      } catch (error) {
        failures.push(error);
        sectionErrors[name] = documentPackSectionError(error);
        return null;
      }
    };
    const review: DocumentPackReview = {
      packId,
      summary: section("summary", summaryResult, (payload) =>
        parseContract("DocumentPackSummary", DocumentPackSummarySchema, payload)
      ),
      conflicts: section("conflicts", conflictsResult, (payload) =>
        parseContract("DocumentPackConflicts", DocumentPackFieldSchema.array(), payload)
      ),
      missingFields: section("missingFields", missingFieldsResult, (payload) =>
        parseContract("DocumentPackMissingFields", DocumentPackFieldSchema.array(), payload)
      ),
      qa: section("qa", qaResult, (payload) =>
        parseContract("DocumentPackQA", DocumentPackQASchema, payload)
      ),
      documents: section("documents", documentsResult, (payload) =>
        parseContract("DocumentPackDocuments", DocumentReferenceSchema.array(), payload)
      ),
      extractions: section("extractions", extractionsResult, (payload) =>
        parseContract("DocumentPackExtractions", DocumentExtractionSchema.array(), payload)
      ),
      provenance: section("provenance", provenanceResult, (payload) =>
        parseContract("DocumentPackProvenance", DocumentPackProvenanceSchema, payload)
      ),
      processing: section("processing", processingResult, (payload) =>
        parseContract("DocumentPackProcessing", DocumentPackProcessingSchema, payload)
      ),
      consolidatedSpec: section("consolidatedSpec", consolidatedSpecResult, (payload) =>
        parseContract("DocumentPackConsolidatedSpec", DocumentPackConsolidatedSpecSchema, payload)
      ),
      sectionErrors
    };
    const loadedSectionCount = Object.entries(review).filter(
      ([name, value]) => !["packId", "sectionErrors"].includes(name) && value !== null
    ).length;
    if (loadedSectionCount === 0) {
      throw failures[0] ?? new ApiClientError(0, `/document-packs/${packId}`, "Review unavailable.");
    }
    return review;
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

  async generateDesignFromDocumentPack(
    packId: string,
    multimodalConsent: MultimodalConsent = "disabled"
  ): Promise<DocumentPackGenerateDesignResponse> {
    return parseContract(
      "DocumentPackGenerateDesignResponse",
      DocumentPackGenerateDesignResponseSchema,
      await this.postJson(`/document-packs/${packId}/generate-design`, {
        multimodal_consent: multimodalConsent
      })
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

  async workflowStatus(workflowId: string, options?: RequestOptions): Promise<WorkflowStatus> {
    return parseContract(
      "WorkflowStatus",
      WorkflowStatusSchema,
      await this.getJson(`/designs/${workflowId}`, options)
    );
  }

  async workflowEvents(
    workflowId: string,
    afterSequence?: number | null
  ): Promise<WorkflowEvent[]> {
    const params = new URLSearchParams();
    if (afterSequence != null) {
      params.set("after_sequence", String(afterSequence));
    }
    const query = params.size ? `?${params.toString()}` : "";
    return parseContract(
      "WorkflowEvents",
      WorkflowEventSchema.array(),
      await this.getJson(`/designs/${workflowId}/events${query}`)
    );
  }

  async viewerBundle(workflowId: string, options?: RequestOptions): Promise<ViewerBundle> {
    return parseContract(
      "ViewerBundle",
      ViewerBundleSchema,
      await this.getJson(`/designs/${workflowId}/viewer-bundle`, options)
    );
  }

  async componentProofs(relativeUrl: string | null | undefined): Promise<ComponentProofs | null> {
    const payload = await this.artifactJson(relativeUrl);
    return payload === null
      ? null
      : parseContract("ComponentProofs", ComponentProofsSchema, payload);
  }

  async assemblyPlan(
    relativeUrl: string | null | undefined
  ): Promise<AssemblyPlanEvidence | null> {
    const payload = await this.artifactJson(relativeUrl);
    return payload === null
      ? null
      : parseContract("AssemblyPlanEvidence", AssemblyPlanEvidenceSchema, payload);
  }

  async requirementsSpec(
    relativeUrl: string | null | undefined
  ): Promise<RequirementSpec | null> {
    const payload = await this.artifactJson(relativeUrl);
    return payload === null
      ? null
      : parseContract("RequirementSpec", RequirementSpecSchema, payload);
  }

  async timelineSummary(workflowId: string, options?: RequestOptions): Promise<TimelineSummary> {
    return parseContract(
      "TimelineSummary",
      TimelineSummarySchema,
      await this.getJson(`/designs/${workflowId}/timeline-summary`, options)
    );
  }

  async currentOperation(workflowId: string, options?: RequestOptions): Promise<CurrentOperation> {
    return parseContract(
      "CurrentOperation",
      CurrentOperationSchema,
      await this.getJson(`/designs/${workflowId}/current-operation`, options)
    );
  }

  async userIssues(workflowId: string, options?: RequestOptions): Promise<UserIssues> {
    return parseContract(
      "UserIssues",
      UserIssuesSchema,
      await this.getJson(`/designs/${workflowId}/user-issues`, options)
    );
  }

  async versions(workflowId: string, options?: RequestOptions): Promise<PublicVersionInfo[]> {
    return parseContract(
      "Versions",
      VersionsSchema,
      await this.getJson(`/designs/${workflowId}/versions`, options)
    );
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
    if (!isPublicArtifactReference(relativeUrl)) {
      throw new ApiClientError(0, relativeUrl, "Backend returned an invalid public artifact URL.");
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

  async llmDecisionProvenance(
    relativeUrl: string | null | undefined
  ): Promise<LLMDecisionProvenance | null> {
    const payload = await this.artifactJson(relativeUrl);
    if (payload === null) {
      return null;
    }
    return parseContract(
      "LLMDecisionProvenance",
      LLMDecisionProvenanceSchema,
      payload
    );
  }

  streamUrl(workflowId: string, afterEventId?: string | null): string {
    const url = new URL(`/designs/${workflowId}/events/stream`, this.baseUrl);
    if (afterEventId) {
      url.searchParams.set("after_event_id", afterEventId);
    }
    return url.toString();
  }

  private async getJson(endpoint: string, options?: RequestOptions): Promise<unknown> {
    const url = new URL(endpoint, this.baseUrl);
    const response = options ? await this.fetcher(url, options) : await this.fetcher(url);
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
    headers: Record<string, string> = {}
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

function documentPackSectionError(error: unknown): DocumentPackReviewSectionError {
  const status = error instanceof ApiClientError ? error.status : 0;
  return {
    status,
    retryable: status === 0 || status === 408 || status === 429 || status >= 500
  };
}

export function defaultApiBaseUrl(): string {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "http://127.0.0.1:8000";
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

export function assertDocumentPackFiles(files: File[]): void {
  if (!files.length) {
    throw new ApiClientError(0, "/document-packs", "Ajoutez au moins une pièce technique.");
  }
  const zipCount = files.filter((file) => file.name.toLowerCase().endsWith(".zip")).length;
  if (zipCount && files.length !== 1) {
    throw new ApiClientError(
      0,
      "/document-packs",
      "Un ZIP doit être envoyé seul; ne mélangez pas une archive et des fichiers directs."
    );
  }
  if (zipCount === 1) {
    assertZipDocumentPack(files[0]);
  }
}
