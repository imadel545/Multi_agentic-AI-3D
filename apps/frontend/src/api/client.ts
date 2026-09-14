import {
  AdaptationCapabilityCatalogSchema,
  AssemblyPlanEvidenceSchema,
  AssetInventorySchema,
  AssetLibraryProbeSchema,
  AssetProvenanceSchema,
  AssetLibrarySearchSchema,
  AssetLibrarySummarySchema,
  CreateDesignResponseSchema,
  ComponentProofsSchema,
  ConversationSchema,
  CurrentOperationSchema,
  DocumentPackCapabilitiesSchema,
  DocumentPackSummarySchema,
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
  type AssetLibraryProbe,
  type AssetProvenance,
  type AssetLibrarySearch,
  type AssetLibrarySummary,
  type CreateDesignResponse,
  type ComponentProofs,
  type Conversation,
  type CurrentOperation,
  type DocumentPackCapabilities,
  type DocumentPackSummary,
  type EditDesignResponse,
  type Health,
  type LLMDecisionProvenance,
  type MultimodalConsent,
  type ParseRequirementsResponse,
  type RequirementAnalysisReceipt,
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
  chat_id?: string;
  document_pack_id?: string;
  document_context_hash?: string;
  requirements_text: string;
  confirmed_requirements?: RequirementSpec;
  confirmed_requirements_hash?: string;
  confirmed_analysis_receipt?: RequirementAnalysisReceipt;
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
  chat_id?: string;
  document_pack_id?: string;
  requirements_text: string;
  detail_level?: "low" | "medium" | "high";
  use_llm?: boolean | null;
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

  async probeAssetLibrary(fileId: string): Promise<AssetLibraryProbe> {
    return parseContract(
      "AssetLibraryProbe",
      AssetLibraryProbeSchema,
      await this.postJson(`/assets/library/${encodeURIComponent(fileId)}/probe`, {})
    );
  }

  async assetProvenance(assetId: string): Promise<AssetProvenance> {
    return parseContract(
      "AssetProvenance",
      AssetProvenanceSchema,
      await this.getJson(`/assets/${encodeURIComponent(assetId)}/provenance`)
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

  async createDocumentPack(files: File[], chatId?: string): Promise<DocumentPackSummary> {
    assertDocumentPackFiles(files);
    const chatHeaders: Record<string, string> = {};
    if (chatId) chatHeaders["x-chat-id"] = chatId;
    if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
      const file = files[0];
      return parseContract(
        "DocumentPackSummary",
        DocumentPackSummarySchema,
        await this.postBinary("/document-packs", file, {
          "content-type": "application/zip",
          "x-filename": file.name,
          ...chatHeaders
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
      await this.postBinary("/document-packs", form, chatHeaders)
    );
  }

  async documentPackSummary(packId: string): Promise<DocumentPackSummary> {
    return parseContract(
      "DocumentPackSummary",
      DocumentPackSummarySchema,
      await this.getJson(`/document-packs/${encodeURIComponent(packId)}`)
    );
  }

  async deleteDocumentPack(packId: string, chatId?: string): Promise<void> {
    const query = chatId
      ? `?${new URLSearchParams({ chat_id: chatId }).toString()}`
      : "";
    await this.deleteJson(`/document-packs/${encodeURIComponent(packId)}${query}`);
  }

  async listDesigns(limit?: number, offset = 0): Promise<WorkflowStatus[]> {
    const endpoint = limit === undefined
      ? "/designs"
      : `/designs?${new URLSearchParams({ limit: String(limit), offset: String(offset) })}`;
    const payload = await this.getJson(endpoint);
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

  async conversation(workflowId: string): Promise<Conversation> {
    return parseContract(
      "Conversation",
      ConversationSchema,
      await this.getJson(`/designs/${encodeURIComponent(workflowId)}/conversation`)
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
    const response = await this.fetcher(url, { credentials: "include" });
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
    const response = await this.fetcher(url, { ...options, credentials: "include" });
    return this.responseJson(response, endpoint);
  }

  private async postJson(endpoint: string, payload: unknown): Promise<unknown> {
    const response = await this.fetcher(new URL(endpoint, this.baseUrl), {
      method: "POST",
      credentials: "include",
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
      credentials: "include",
      headers,
      body
    });
    return this.responseJson(response, endpoint);
  }

  private async deleteJson(endpoint: string): Promise<unknown> {
    const response = await this.fetcher(new URL(endpoint, this.baseUrl), {
      method: "DELETE",
      credentials: "include"
    });
    return this.responseJson(response, endpoint);
  }

  private async responseJson(response: Response, endpoint: string): Promise<unknown> {
    if (!response.ok) {
      if (response.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new Event("telecom-auth-required"));
      }
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
