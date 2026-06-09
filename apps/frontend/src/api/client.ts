import type {
  AssetInventory,
  CreateDesignResponse,
  DesignListItem,
  DocumentPackBundle,
  DocumentPackSummary,
  EditDesignResponse,
  StudioEvent,
  VersionInfo,
  WorkflowStatus,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export const apiBaseUrl = API_BASE.replace(/\/$/, "");

type JsonBody = Record<string, unknown> | Array<unknown>;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body instanceof ArrayBuffer ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string; error?: string };
      detail = payload.detail ?? payload.error ?? detail;
    } catch {
      // Keep HTTP status detail when the response is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body?: JsonBody): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const studioApi = {
  health: () => request<{ status: string; version: string }>("/health"),
  listDesigns: () => request<DesignListItem[]>("/designs"),
  createDesign: (requirementsText: string, useLlm = true) =>
    postJson<CreateDesignResponse>("/designs", {
      requirements_text: requirementsText,
      options: { detail_level: "high", generate_variants: false, use_llm: useLlm },
    }),
  getDesign: (workflowId: string) => request<WorkflowStatus>(`/designs/${workflowId}`),
  getEvents: (workflowId: string) => request<StudioEvent[]>(`/designs/${workflowId}/events`),
  editDesign: (workflowId: string, editPrompt: string) =>
    postJson<EditDesignResponse>(`/designs/${workflowId}/edit`, { edit_prompt: editPrompt }),
  listVersions: (workflowId: string) =>
    request<VersionInfo[]>(`/designs/${workflowId}/versions`),
  rollbackVersion: (workflowId: string, versionId: string) =>
    postJson<{ workflow_id: string; version_id: string; rolled_back: boolean }>(
      `/designs/${workflowId}/versions/${versionId}/rollback`,
    ),
  assetInventory: () => request<AssetInventory>("/assets/inventory"),
  listDocumentPacks: () => request<DocumentPackSummary[]>("/document-packs"),
  capabilities: () => request<Record<string, unknown>>("/document-packs/capabilities"),
  uploadDocumentPack: async (file: File) => {
    const body = await file.arrayBuffer();
    return request<DocumentPackSummary>("/document-packs", {
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/zip",
        "x-filename": file.name,
      },
    });
  },
  documentPackBundle: async (packId: string): Promise<DocumentPackBundle> => {
    const [
      summary,
      documents,
      extractions,
      spec,
      conflicts,
      missing,
      qa,
      processing,
      trace,
      events,
      memory,
    ] = await Promise.all([
      request<DocumentPackSummary>(`/document-packs/${packId}`),
      request<DocumentPackBundle["documents"]>(`/document-packs/${packId}/documents`),
      request<DocumentPackBundle["extractions"]>(`/document-packs/${packId}/extractions`),
      request<Record<string, unknown>>(`/document-packs/${packId}/consolidated-spec`),
      request<DocumentPackBundle["conflicts"]>(`/document-packs/${packId}/conflicts`),
      request<DocumentPackBundle["missing"]>(`/document-packs/${packId}/missing-fields`),
      request<Record<string, unknown>>(`/document-packs/${packId}/qa`),
      request<Record<string, unknown>>(`/document-packs/${packId}/processing`),
      request<StudioEvent[]>(`/document-packs/${packId}/trace`),
      request<StudioEvent[]>(`/document-packs/${packId}/events`),
      request<Record<string, unknown>>(`/document-packs/${packId}/memory-summary`),
    ]);
    return { summary, documents, extractions, spec, conflicts, missing, qa, processing, trace, events, memory };
  },
  applyCorrection: (packId: string, field: string, value: string, reason: string) =>
    postJson<DocumentPackSummary>(`/document-packs/${packId}/corrections`, {
      field,
      value,
      reason,
      confidence: 1,
      corrected_by: "frontend_user",
    }),
  generateDesignFromPack: (packId: string) =>
    postJson<CreateDesignResponse & { pack_id: string; mapping?: Record<string, unknown> }>(
      `/document-packs/${packId}/generate-design`,
    ),
};

export function artifactUrl(
  workflowId: string | undefined,
  artifactName: string,
  versionId?: string | null,
): string | undefined {
  if (!workflowId) return undefined;
  const params = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return `${apiBaseUrl}/designs/${workflowId}/artifacts/${artifactName}${params}`;
}
