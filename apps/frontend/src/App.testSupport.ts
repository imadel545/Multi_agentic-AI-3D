import { vi } from "vitest";
import type { TelecomStudioApi } from "./api/client";
import type { WorkflowStatus } from "./api/schemas";

export function workflow(
  workflowId: string,
  status: WorkflowStatus["status"],
  createdAt: string
): WorkflowStatus {
  return {
    workflow_id: workflowId,
    status,
    created_at: createdAt,
    artifacts: {},
    warnings: [],
    errors: [],
    available_actions: [],
    unsupported_actions: [],
    completion_certificate_status: status === "completed" ? "issued" : null
  };
}

export const confirmedAnalysisReceipt = {
  schema_version: "1.0.0" as const,
  receipt_id: `ira_${"a".repeat(32)}`,
  issued_at: "2026-09-11T10:00:00+00:00",
  confirmed_prompt_sha256: "b".repeat(64),
  confirmed_requirements_sha256: "c".repeat(64),
  detail_level: "high" as const,
  provider: "deterministic",
  model: null,
  extraction_provider: "fallback",
  fallback_used: true,
  fallback_reason: "provider_unavailable"
};

export function bootstrapApi(overrides: Record<string, unknown> = {}): TelecomStudioApi {
  return {
    health: vi.fn().mockResolvedValue({
      status: "ok",
      service: "agentic_telecom_3d_studio_api",
      version: "1.0.0",
      api_contract_version: "2026-07-29"
    }),
    studioSummary: vi.fn().mockResolvedValue({
      status: "ok",
      available_actions: [],
      unsupported_actions: []
    }),
    assetLibrarySummary: vi.fn().mockResolvedValue({
      status: "catalogued_quarantined",
      schema_version: "1.1.0",
      catalog_available: false,
      file_count: 0,
      generation_eligible_count: 0,
      limitations: []
    }),
    assetInventory: vi.fn().mockResolvedValue({
      status: "qualified_mixed_catalog",
      entries: [],
      generation_eligible_asset_count: 0,
      real_glb_asset_count: 0,
      import_qualified_glb_count: 0,
      reference_only_asset_count: 0
    }),
    adaptationCapabilityCatalog: vi.fn().mockResolvedValue({
      schema_version: "1.0.0",
      catalog_hash: "a".repeat(64),
      profiles: []
    }),
    documentPackCapabilities: vi.fn().mockResolvedValue({
      document_pack_status: "limited",
      supported_upload_format: "zip_or_multipart",
      supported_extensions: [".pdf"],
      limitations: [],
      truth: {},
      capabilities: {}
    }),
    conversation: vi.fn((workflowId: string) => Promise.resolve({
      workflow_id: workflowId,
      history_status: "legacy_partial",
      messages: []
    })),
    listDesigns: vi.fn().mockResolvedValue([]),
    artifactUrl: vi.fn((url: string | null | undefined) => url ?? null),
    ...overrides
  } as unknown as TelecomStudioApi;
}

export function deferredPromise<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}
