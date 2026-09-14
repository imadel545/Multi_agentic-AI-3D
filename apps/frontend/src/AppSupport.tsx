import type { Dispatch } from "react";
import { ApiClientError, TelecomStudioApi } from "./api/client";
import type {
  DocumentPackCapabilities,
  EditDesignResponse,
  ViewerBundle,
  WorkflowEvent,
  WorkflowStatus
} from "./api/schemas";
import type { WorkflowMachineAction, WorkflowPhase } from "./state/workflowMachine";

export function selectViewerBundleForDisplay(
  phase: WorkflowPhase,
  current: ViewerBundle | null,
  lastCertified: ViewerBundle | null
): ViewerBundle | null {
  const preserveCertified =
    lastCertified &&
    (phase === "submitting" || phase === "streaming" || phase === "running" || phase === "failed") &&
    (!current || current.status === "failed");
  return preserveCertified ? lastCertified : current;
}

export function ViewerLoadingFallback() {
  return (
    <section className="viewer-shell viewer-loading" aria-label="Viewer 3D loading">
      <div className="viewer-toolbar">
        <div>
          <span className="eyebrow">Viewer 3D</span>
          <h2>Chargement du viewer</h2>
        </div>
      </div>
      <div className="viewer-fallback dark">
        <strong>Préparation WebGL</strong>
        <p>Le moteur 3D se charge séparément pour garder le studio réactif.</p>
      </div>
    </section>
  );
}

export function needsPolling(phase: WorkflowPhase, runtimeMode: string): boolean {
  return runtimeMode === "polling" && (phase === "running" || phase === "streaming");
}

export async function reconcileAfterAmbiguousMutation(
  reloadVerifiedState: () => Promise<void>
): Promise<boolean> {
  try {
    await reloadVerifiedState();
    return true;
  } catch {
    return false;
  }
}

export type UserActionContext =
  | "analysis"
  | "assets"
  | "bootstrap"
  | "connection"
  | "documents"
  | "edit"
  | "generation"
  | "resource"
  | "rollback";

export function userFacingError(error: unknown, context: UserActionContext): string {
  const action = {
    analysis: "L’analyse de la demande",
    assets: "La recherche de composants",
    bootstrap: "La synchronisation initiale du studio",
    connection: "La connexion au studio",
    documents: "L’analyse documentaire",
    edit: "La modification du design",
    generation: "La génération du design",
    resource: "Une information secondaire",
    rollback: "La restauration de version"
  }[context];
  if (error instanceof ApiClientError) {
    if (error.status === 0) return `${action} ne peut pas joindre le studio local.`;
    if (error.status === 404) return `${action} n’est plus disponible pour cet élément.`;
    if (error.status === 409) return `${action} doit être resynchronisée avant de continuer.`;
    if (error.status === 422) return `${action} nécessite des informations à corriger.`;
    if (error.status === 429) return "Le studio termine déjà une opération. Réessayez ensuite.";
    if (error.status === 507) {
      return "L’espace disque local est insuffisant. Libérez de la place avant de réessayer.";
    }
    if (error.status >= 500) return `${action} a rencontré un problème interne. Réessayez.`;
  }
  return `${action} n’a pas abouti. Réessayez ou rechargez l’état vérifié.`;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function documentPackBrowserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function selectWorkflowToRestore(designs: WorkflowStatus[]): WorkflowStatus | null {
  for (const statuses of [
    new Set(["pending", "running"]),
    new Set(["completed"]),
    new Set(["failed", "legacy_unverified", "integrity_failed"])
  ]) {
    const candidates = designs.filter(
      (design) =>
        statuses.has(design.status) &&
        (design.status !== "completed" ||
          design.completion_certificate_status === "issued")
    );
    if (candidates.length) {
      return [...candidates].sort(
        (left, right) => timestamp(right.created_at) - timestamp(left.created_at)
      )[0] ?? null;
    }
  }
  return null;
}

export function shouldForgetDocumentPackSession(error: unknown): boolean {
  return error instanceof ApiClientError && error.status === 404;
}

export function latestEventCursor(
  events: Array<Pick<WorkflowEvent, "event_id">>
): string | null {
  return events.at(-1)?.event_id ?? null;
}

export function latestEventSequence(
  events: Array<Pick<WorkflowEvent, "sequence">>
): number | null {
  let latest: number | null = null;
  for (const event of events) {
    if (event.sequence != null) {
      latest = Math.max(latest ?? 0, event.sequence);
    }
  }
  return latest;
}

export function documentPackSizeError(
  file: Pick<File, "size">,
  capabilities: DocumentPackCapabilities | null
): string | null {
  const maxZipSizeMb = capabilities?.limits?.max_zip_size_mb;
  if (!maxZipSizeMb || file.size <= maxZipSizeMb * 1024 * 1024) {
    return null;
  }
  return `Le ZIP dépasse la limite locale de ${maxZipSizeMb} Mo. Réduisez le pack avant de le joindre.`;
}

export function documentPackFilesSizeError(
  files: Array<Pick<File, "name" | "size">>,
  capabilities: DocumentPackCapabilities | null
): string | null {
  if (!files.length) {
    return "Ajoutez au moins une pièce technique.";
  }
  if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
    return documentPackSizeError(files[0], capabilities);
  }
  const maxCount = capabilities?.limits?.max_member_count;
  if (maxCount && files.length > maxCount) {
    return `Le cahier de charge dépasse la limite de ${maxCount} fichiers.`;
  }
  const maxMemberSizeMb = capabilities?.limits?.max_member_size_mb;
  const oversized = maxMemberSizeMb
    ? files.find((file) => file.size > maxMemberSizeMb * 1024 * 1024)
    : null;
  if (oversized) {
    return `${oversized.name} dépasse la limite de ${maxMemberSizeMb} Mo par fichier.`;
  }
  const maxTotalSizeMb = capabilities?.limits?.max_uncompressed_size_mb;
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (maxTotalSizeMb && total > maxTotalSizeMb * 1024 * 1024) {
    return `Les pièces dépassent la limite totale de ${maxTotalSizeMb} Mo.`;
  }
  return null;
}

export function timestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function isTerminalStatus(status: string): boolean {
  return (
    status === "completed" ||
    status === "failed" ||
    status === "legacy_unverified" ||
    status === "integrity_failed"
  );
}

export function createTestApi(baseUrl = "http://127.0.0.1:8000", fetcher = fetch) {
  return new TelecomStudioApi(baseUrl, fetcher);
}

export function applyResourceResult<T>(
  result: PromiseSettledResult<T>,
  resource: string,
  onValue: (value: T) => void,
  send: Dispatch<WorkflowMachineAction>
) {
  if (result.status === "fulfilled") {
    onValue(result.value);
    send({ type: "RESOURCE_RECOVERED", resource });
    return;
  }
  send({
    type: "RESOURCE_FAILED",
    resource,
    message: userFacingError(result.reason, "resource")
  });
}

export function revisionOutcomeMessage(
  result: EditDesignResponse,
  submittedPrompt?: string
): string {
  const patch = result.patch as Record<string, unknown> | null | undefined;
  const unsupported = Array.isArray(patch?.unsupported_requests)
    ? patch.unsupported_requests.filter(
        (item): item is string => typeof item === "string" && Boolean(item.trim())
      ).map(humanUnsupportedEditRequest)
    : [];
  const description = submittedPrompt?.trim()
    || (typeof patch?.edit_description === "string" && patch.edit_description.trim()
      ? patch.edit_description.trim()
      : null);
  if (result.status === "applied") {
    const applied = description
      ? `Modification appliquée : ${description}`
      : "Modification appliquée et revalidée.";
    return unsupported.length
      ? `${applied} Non réalisé : ${unsupported.join(" ")}`
      : applied;
  }
  const errorCodes = (result.errors ?? [])
    .map((error) => String(error.code ?? "").toUpperCase())
    .join(" ");
  if (errorCodes.includes("GEOMETRY_VALIDATION")) {
    return "La nouvelle version a été refusée par le contrôle géométrique. La version vérifiée précédente reste active.";
  }
  if (unsupported.length) {
    return `Modification non appliquée. Capacité indisponible : ${unsupported.join(" ")}`;
  }
  return "Modification non appliquée. La version vérifiée précédente reste active.";
}

export function humanUnsupportedEditRequest(message: string): string {
  const normalized = message.toLowerCase();
  if (
    (normalized.includes("door") || normalized.includes("porte")) &&
    (normalized.includes("green space") || normalized.includes("espace vert"))
  ) {
    return "L’ajout d’une porte ou barrière au sol pour délimiter un espace vert n’est pas encore disponible.";
  }
  if (normalized.includes("not supported") || normalized.includes("is not supported")) {
    return "Une partie de la demande n’est pas disponible dans les capacités d’édition actuelles.";
  }
  return message;
}
