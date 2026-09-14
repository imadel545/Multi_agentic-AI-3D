import { AlertTriangle, CheckCircle2, Send } from "lucide-react";
import type { ParseRequirementsResponse, PublicVersionInfo, RequirementSpec } from "../api/schemas";
import { List, Metric } from "./StudioPrimitives";
import { humanSemanticRole } from "./StudioDisplayHelpers";
import { analysisProviderLabel } from "./StudioProductDisplay";
import { humanExtractionError, humanExtractionFallback, humanRequirementField, humanRequirementWarning, humanTowerType, uniqueRequirementWarnings, yesNo } from "./StudioWorkflowDisplay";

export type ConversationEntry = {
  id: string;
  label: string;
  message: string;
  role: "user" | "assistant" | "system";
};

export function conversationHistoryEntries({
  activeRequirements,
  currentPrompt,
  versions
}: {
  activeRequirements: RequirementSpec | null;
  currentPrompt: string;
  versions: PublicVersionInfo[];
}): ConversationEntry[] {
  const entries: ConversationEntry[] = [];
  const prompt = currentPrompt.trim();
  if (prompt) {
    entries.push({ id: "current-prompt", label: "Vous", message: prompt, role: "user" });
  } else if (activeRequirements) {
    entries.push({
      id: "restored-requirements",
      label: "Contexte actif restauré",
      message: `${activeRequirements.network_type} · ${humanTowerType(activeRequirements.tower_type)} · ${activeRequirements.tower_height_m} m · ${activeRequirements.sector_count} secteur(s)`,
      role: "system"
    });
  }
  [...versions]
    .filter((version) => {
      const description = version.edit_description?.trim() ?? "";
      return Boolean(description) && !/^initial from [a-z0-9._-]+$/i.test(description);
    })
    .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at))
    .slice(-3)
    .forEach((version) => {
      entries.push({
        id: version.version_id,
        label: version.active ? "Vous · modification active" : "Vous · modification enregistrée",
        message: version.edit_description!.trim(),
        role: "user"
      });
    });
  return entries;
}

export function ConversationHistory({
  activeRequirements,
  currentPrompt,
  versions
}: {
  activeRequirements: RequirementSpec | null;
  currentPrompt: string;
  versions: PublicVersionInfo[];
}) {
  const entries = conversationHistoryEntries({
    activeRequirements,
    currentPrompt,
    versions
  });
  if (!entries.length) return null;
  return (
    <div className="conversation-history" aria-label="Conversation">
      <span className="conversation-history-label">Conversation</span>
      <div className="conversation-history-list">
        {entries.map((entry) => {
          const compact = entry.message.length > 280;
          return (
            <article className={`conversation-entry ${entry.role}`} key={entry.id}>
              <strong>{entry.label}</strong>
              <p className={compact ? "message-clamp" : undefined}>{entry.message}</p>
              {compact ? (
                <details>
                  <summary>Voir la demande complète</summary>
                  <p>{entry.message}</p>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}

export function ActiveWorkflowContext({
  activeRequirements,
  currentPrompt,
  versions
}: {
  activeRequirements: RequirementSpec | null;
  currentPrompt: string;
  versions: PublicVersionInfo[];
}) {
  const entries = conversationHistoryEntries({ activeRequirements, currentPrompt, versions });
  if (!entries.length) return null;
  return (
    <section className="conversation-history" aria-label="Contexte actif non archivé">
      <span className="conversation-history-label">Contexte actif non archivé</span>
      <p className="muted">
        Ces informations sont le contexte courant du design, pas des messages retrouvés dans le journal.
      </p>
      <div className="conversation-history-list">
        {entries.map((entry) => (
          <article className="conversation-entry system" key={entry.id}>
            <strong>{activeContextLabel(entry)}</strong>
            <p>{entry.message}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function activeContextLabel(entry: ConversationEntry): string {
  if (entry.id === "current-prompt") return "Demande active";
  if (entry.id === "restored-requirements") return "Exigences actives";
  return entry.label.includes("active") ? "Version active" : "Version enregistrée";
}

export function RequirementsUnderstanding({
  analysis,
  failedWorkflow,
  onConfirm,
  submitted,
  submitting
}: {
  analysis: ParseRequirementsResponse;
  failedWorkflow: boolean;
  onConfirm: () => void;
  submitted: boolean;
  submitting: boolean;
}) {
  const requirements = analysis.requirements;
  if (!requirements) {
    return (
      <div className="understanding-card">
        <strong>Demande non confirmable</strong>
        {analysis.errors.length ? (
          <ul>{analysis.errors.map((error, index) => <li key={index}>{humanExtractionError(error)}</li>)}</ul>
        ) : <p>La demande n’a pas pu être convertie en exigences exploitables.</p>}
      </div>
    );
  }
  const warnings = uniqueRequirementWarnings([...analysis.warnings, ...requirements.warnings]);
  const confirmationLocked = submitted;
  const unresolvedConflicts = (requirements.conflicts ?? []).filter(
    (conflict) => !conflict.resolved
  );
  const confirmationBlocked =
    Boolean(requirements.requires_confirmation) || unresolvedConflicts.length > 0;
  const receiptMissing = !analysis.analysis_receipt;
  return (
    <div className="understanding-card" aria-label="Compréhension de la demande">
      <span className="eyebrow">
        {confirmationLocked ? "Cahier des charges utilisé" : "Paramètres compris à confirmer"}
      </span>
      <strong>{requirements.network_type} · {humanTowerType(requirements.tower_type)}</strong>
      <div className="metric-grid">
        <Metric label="Hauteur" value={`${requirements.tower_height_m} m`} />
        <Metric label="Secteurs" value={String(requirements.sector_count)} />
        <Metric label="HBA" value={`${requirements.antenna_install_height_m} m`} />
        <Metric label="Azimuts" value={requirements.azimuths_deg.map((value) => `${value}°`).join(" / ")} />
      </div>
      <p>
        RRU {yesNo(requirements.include_rru)} · câbles {yesNo(requirements.include_cables)} · cabinet {yesNo(requirements.include_power_cabinet)} · GPS {yesNo(requirements.include_gps_antenna)} · labels {yesNo(requirements.include_labels)}
      </p>
      {requirements.geometry_requests.length ? (
        <div className="generated-intent-summary">
          <strong>
            {analysis.fallback_used
              ? "Composants hors catalogue détectés"
              : "Composants nouveaux compris par l’IA"}
          </strong>
          <ul>
            {requirements.geometry_requests.map((request) => (
              <li key={request.request_id}>
                <span>
                  {request.quantity > 1 ? `${request.quantity} × ` : ""}
                  {humanSemanticRole(request.semantic_role)}
                </span>
                <small>{request.description}</small>
                {request.placement_context ? (
                  <small>Placement demandé : {request.placement_context}</small>
                ) : null}
                {request.maximum_dimensions_m ? (
                  <small>
                    Enveloppe maximale : {request.maximum_dimensions_m.x} ×{" "}
                    {request.maximum_dimensions_m.y} × {request.maximum_dimensions_m.z} m
                  </small>
                ) : null}
              </li>
            ))}
          </ul>
          <small>
            Ils seront conçus par le spécialiste 3D, puis contrôlés avant la construction.
          </small>
        </div>
      ) : null}
      <small>
        Source d’analyse : {analysisProviderLabel(analysis.provider, analysis.extraction_provider)}
      </small>
      {analysis.fallback_used && !/groq|gpt/i.test(`${analysis.provider ?? ""} ${analysis.extraction_provider ?? ""}`) ? (
        <p className="inline-alert">
          <AlertTriangle size={15} aria-hidden="true" /> {humanExtractionFallback(
            analysis.llm_fallback_reason
          )}
        </p>
      ) : null}
      {warnings.length ? (
        <List
          title="Hypothèses prises en compte"
          items={warnings.map(humanRequirementWarning)}
          empty="Aucun avertissement d’extraction."
        />
      ) : null}
      {analysis.errors.length ? (
        <List
          title="Incidents d’extraction signalés"
          items={analysis.errors.map(humanExtractionError)}
          empty="Aucun incident."
        />
      ) : null}
      {receiptMissing ? (
        <p className="inline-alert" role="alert">
          <AlertTriangle size={15} aria-hidden="true" /> La provenance vérifiée de cette analyse
          n’est pas disponible. Réanalysez la demande avant de générer le design.
        </p>
      ) : null}
      {confirmationBlocked ? (
        <div className="inline-alert" role="alert">
          <AlertTriangle size={15} aria-hidden="true" />
          <div>
            <strong>Confirmation impossible tant que les contradictions ne sont pas corrigées.</strong>
            <ul>
              {unresolvedConflicts.map((conflict, index) => (
                <li key={`${conflict.field}-${index}`}>
                  {humanRequirementField(conflict.field)} : {conflict.reason}
                </li>
              ))}
            </ul>
            {(requirements.confirmation_fields ?? []).length ? (
              <small>
                Champs à préciser :{" "}
                {(requirements.confirmation_fields ?? []).map(humanRequirementField).join(", ")}
              </small>
            ) : null}
          </div>
        </div>
      ) : null}
      {confirmationLocked ? (
        <p className="confirmation-complete" role="status">
          {failedWorkflow ? <AlertTriangle size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
          {failedWorkflow
            ? "Cette demande est conservée et peut être corrigée ou relancée depuis le message ci-dessus."
            : "Cette compréhension a déjà lancé le design affiché."}
        </p>
      ) : (
        <button
          className="primary-action"
          disabled={submitting || confirmationBlocked || receiptMissing}
          onClick={onConfirm}
          type="button"
        >
          <Send size={18} aria-hidden="true" />
          Confirmer et générer
        </button>
      )}
    </div>
  );
}


