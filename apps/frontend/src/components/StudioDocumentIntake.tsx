import type { DocumentPackCapabilities, DocumentPackSummary, MultimodalConsent, MultimodalIntelligence } from "../api/schemas";
import { DocumentFileComposer } from "./DocumentFileComposer";
import { ResourceRecovery } from "./StudioPrimitives";

export function DocumentPackIntake({
  busy,
  capabilities,
  capabilitiesError,
  capabilitiesLoading,
  message,
  onCapabilitiesRetry,
  onRetry,
  onUpload,
  summary
}: {
  busy: boolean;
  capabilities: DocumentPackCapabilities | null;
  capabilitiesError?: string | null;
  capabilitiesLoading?: boolean;
  message: string | null;
  onCapabilitiesRetry?: () => void;
  onRetry?: () => void;
  onUpload: (files: File[]) => Promise<boolean>;
  summary: DocumentPackSummary | null;
}) {
  return (
    <section className="document-intake">
      <div className="document-intake-body">
        <div className="document-intake-copy">
          <span className="eyebrow">Cahier de charge</span>
          <strong>Ajouter des pièces au brief</strong>
          <p>
            {capabilitiesError
              ? "Les limites d’import ne sont pas disponibles; aucun fichier n’est envoyé sans ce contrat."
              : capabilities?.document_pack_status === "limited"
              ? "Ajoutez des PDF, images, plans, tableaux ou un ZIP à cette conversation."
              : capabilitiesLoading
                ? "Capacités documentaires en cours de chargement."
                : "Capacités documentaires indisponibles."}
          </p>
        </div>
        {capabilitiesError ? (
          <ResourceRecovery
            busy={capabilitiesLoading}
            label="Les options d’import n’ont pas pu être chargées."
            message={capabilitiesError}
            onRetry={onCapabilitiesRetry}
          />
        ) : null}
        <DocumentFileComposer
          busy={busy}
          capabilities={capabilities}
          disabledReason={
            capabilities
              ? null
              : capabilitiesLoading
                ? "Le contrat d’import documentaire est en cours de chargement."
                : capabilitiesError ??
                  "Le contrat d’import documentaire est indisponible. Réessayez avant de joindre des fichiers."
          }
          onSubmit={onUpload}
        />
        {summary ? (
          <p className="document-intake-next-step">
            Ajoutez votre demande dans le champ principal. Les pièces jointes servent de contexte et ne lancent jamais un design seules.
          </p>
        ) : null}
        {!summary && message ? (
          <ResourceRecovery
            busy={busy}
            label="Les pièces jointes n’ont pas pu être synchronisées."
            message={message}
            onRetry={onRetry}
          />
        ) : null}
        {summary && message ? <p className="muted">{message}</p> : null}
      </div>
    </section>
  );
}

export function multimodalConsentIsAvailable(
  capability: MultimodalIntelligence | null | undefined
): boolean {
  return capability?.enabled === true &&
    (capability.status === "operational" || capability.status === "configured_unverified");
}

export function MultimodalConsentControl({
  capability,
  consent,
  disabled,
  onChange
}: {
  capability: MultimodalIntelligence | null;
  consent: MultimodalConsent;
  disabled: boolean;
  onChange?: (value: MultimodalConsent) => void;
}) {
  if (!capability || !multimodalConsentIsAvailable(capability) || !onChange) {
    return null;
  }
  const consentGranted = consent === "allow_input_analysis";
  return (
    <section className="multimodal-consent" aria-label="Analyse assistée des images">
      <label>
        <input
          checked={consentGranted}
          disabled={disabled}
          onChange={(event) =>
            onChange(event.currentTarget.checked ? "allow_input_analysis" : "disabled")
          }
          type="checkbox"
        />
        <span>
          <strong>Autoriser l’analyse assistée des images jointes</strong>
          <small>
            Optionnel · jusqu’à {capability.max_images_per_request} image(s) de {Math.floor(capability.max_image_bytes / 1_000_000)} Mo,
            analysées à distance pour comprendre plans et croquis. Cocher cette autorisation n’envoie aucun fichier.
            {capability.status === "configured_unverified" ? " La disponibilité sera vérifiée à l’analyse." : ""}
          </small>
        </span>
      </label>
    </section>
  );
}

