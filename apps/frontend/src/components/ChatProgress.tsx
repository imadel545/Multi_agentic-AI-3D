import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import type { CurrentOperation } from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import { TaskElapsedTime } from "./TaskElapsedTime";

const phaseLabels: Record<string, string> = {
  requirements: "Lecture de votre demande",
  extraction: "Lecture de votre demande",
  rag: "Recherche de références",
  memory: "Recherche de références",
  planning: "Préparation du design",
  scene: "Préparation du design",
  validation: "Contrôle du plan",
  generation: "Construction du modèle 3D",
  blender: "Construction du modèle 3D",
  qa: "Vérification du modèle",
  completion: "Préparation du résultat"
};

export function ChatProgress({
  events,
  phase,
  editing,
  analyzing = false,
  operation
}: {
  events: NormalizedWorkflowEvent[];
  phase: string;
  editing: boolean;
  analyzing?: boolean;
  operation?: CurrentOperation | null;
}) {
  if (phase === "idle" && !editing && !analyzing) return null;
  const busy = analyzing || editing || ["submitting", "streaming", "running"].includes(phase);
  const latest = events.at(-1);
  const interrupted = phase === "failed" && workflowWasInterrupted(events);
  const label =
    analyzing ? "Lecture de votre demande" : editing
      ? "Modification du modèle en cours"
      : phase === "failed"
        ? interrupted ? "La génération a été interrompue" : "La demande nécessite une correction"
        : phase === "completed"
          ? "Version actuelle disponible"
          : phaseLabels[latest?.phase ?? ""] ?? "Traitement de votre demande";
  return (
    <span className={`chat-progress${busy ? " busy" : ""}`} role="status" aria-live="polite">
      {busy ? (
        <Loader2 size={15} className="spin" aria-hidden="true" />
      ) : phase === "failed" ? (
        <AlertCircle size={15} aria-hidden="true" />
      ) : (
        <CheckCircle2 size={15} aria-hidden="true" />
      )}
      <span>{label}</span>
      <TaskElapsedTime key={analyzing ? "analysis" : "design"} events={analyzing ? [] : events} busy={busy} timing={analyzing ? null : operation} />
    </span>
  );
}

export function workflowWasInterrupted(events: NormalizedWorkflowEvent[]): boolean {
  return events.some((event) => {
    const error = event.raw.payload?.error;
    return error === "WORKFLOW_INTERRUPTED" || event.errors.some((item) =>
      typeof item === "string"
        ? item === "WORKFLOW_INTERRUPTED"
        : typeof item === "object" && item !== null && "code" in item &&
          item.code === "WORKFLOW_INTERRUPTED"
    );
  });
}
