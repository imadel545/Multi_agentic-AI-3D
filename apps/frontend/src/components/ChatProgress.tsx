import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import type { NormalizedWorkflowEvent } from "../api/sse";

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
  editing
}: {
  events: NormalizedWorkflowEvent[];
  phase: string;
  editing: boolean;
}) {
  if (phase === "idle" && !editing) return null;
  const busy = editing || ["submitting", "streaming", "running"].includes(phase);
  const latest = events.at(-1);
  const label =
    editing
      ? "Modification du modèle en cours"
      : phase === "failed"
        ? "La demande nécessite une correction"
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
    </span>
  );
}
