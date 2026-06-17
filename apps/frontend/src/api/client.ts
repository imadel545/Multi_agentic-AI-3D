import {
  AssetInventorySchema,
  CreateDesignResponseSchema,
  CurrentOperationSchema,
  DocumentPackCapabilitiesSchema,
  DocumentPackGenerateDesignResponseSchema,
  DocumentPackSummarySchema,
  EditDesignResponseSchema,
  HealthSchema,
  RollbackVersionResponseSchema,
  StudioSummarySchema,
  TimelineSummarySchema,
  UserIssuesSchema,
  VersionsSchema,
  ViewerBundleSchema,
  WorkflowEventSchema,
  WorkflowStatusSchema,
  parseContract,
  type AssetInventory,
  type CreateDesignResponse,
  type CurrentOperation,
  type DocumentPackCapabilities,
  type DocumentPackGenerateDesignResponse,
  type DocumentPackSummary,
  type EditDesignResponse,
  type Health,
  type PublicVersionInfo,
  type RollbackVersionResponse,
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
  options?: {
    detail_level?: "low" | "medium" | "high";
    use_llm?: boolean | null;
  };
};

export type EditDesignPayload = {
  edit_prompt: string;
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

  async documentPackCapabilities(): Promise<DocumentPackCapabilities> {
    return parseContract(
      "DocumentPackCapabilities",
      DocumentPackCapabilitiesSchema,
      await this.getJson("/document-packs/capabilities")
    );
  }

  async createDocumentPack(file: File): Promise<DocumentPackSummary> {
    return parseContract(
      "DocumentPackSummary",
      DocumentPackSummarySchema,
      await this.postBinary("/document-packs", file, {
        "content-type": "application/zip",
        "x-filename": file.name
      })
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

  streamUrl(workflowId: string): string {
    return new URL(`/designs/${workflowId}/events/stream`, this.baseUrl).toString();
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
