import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cpu,
  FileArchive,
  Layers3,
  LibraryBig,
  Loader2,
  MessageSquareText,
  RadioTower,
  RotateCcw,
  Send,
  ShieldAlert,
  Sparkles,
  WifiOff,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import type {
  AdaptationCapabilityCatalog,
  AssemblyPlanEvidence,
  AssetDecisionSummary,
  AssetLibrarySearch,
  AssetLibrarySummary,
  AssetInventory,
  ComponentProofs,
  CurrentOperation,
  DocumentPackCapabilities,
  DocumentPackField,
  DocumentPackReview,
  DocumentPackSummary,
  Health,
  LLMDecisionProvenance,
  MultimodalConsent,
  MultimodalIntelligence,
  ParseRequirementsResponse,
  PublicVersionInfo,
  RequirementSpec,
  SceneAdaptationCapabilities,
  StudioSummary,
  TimelineSummary,
  UserIssue,
  UserIssues,
  ViewerBundle
} from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import { geometryFidelityBadge } from "../features/three-viewer/viewerRules";
import type { RuntimeMode, WorkflowPhase } from "../state/workflowMachine";
import { actionIsSupported } from "../state/workflowMachine";
import { AssetLibraryPanel } from "./AssetLibraryPanel";
import { DocumentFileComposer } from "./DocumentFileComposer";
import { List, Metric, PanelTitle, ResourceRecovery, formatInteger } from "./StudioPrimitives";

import { SceneCompositionPanel, sceneInstanceCount } from "./SceneCompositionPanel";
import { compactFidelityLabel, humanSemanticRole, serviceStatusLabel, visualReviewStatusLabel } from "./StudioDisplayHelpers";

export function BackendStatusBar({
  health,
  healthError,
  healthLoading,
  onRetryHealth,
  phase,
  bundle,
  issues
}: {
  health: Health | null;
  healthError?: string | null;
  healthLoading?: boolean;
  onRetryHealth?: () => void;
  phase: WorkflowPhase;
  bundle: ViewerBundle | null;
  issues: UserIssues | null;
}) {
  const issueCount = displayIssueCount(issues, bundle);
  const fidelityBadge = geometryFidelityBadge(bundle);
  const workflowActive =
    phase === "submitting" || phase === "streaming" || phase === "running";
  const integrityVerified =
    !workflowActive &&
    bundle?.status === "completed" &&
    bundle.generation_mode === "real_blender" &&
    bundle.mesh_qa_passed === true &&
    bundle.completion_certificate_status === "issued";
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <RadioTower size={22} aria-hidden="true" />
        <div>
          <strong>Agentic Telecom Studio</strong>
          <span>Conception 3D telecom vérifiable</span>
        </div>
      </div>
      <div className="topbar-status" aria-label="Studio runtime status">
        <span className={health?.status === "ok" ? "runtime-presence ok" : "runtime-presence warn"}>
          <span aria-hidden="true" />
          {health?.status === "ok"
            ? "Studio local connecté"
            : healthLoading
              ? "Connexion au studio…"
              : "Studio indisponible"}
        </span>
        {healthError && onRetryHealth ? (
          <button className="topbar-retry" onClick={onRetryHealth} type="button">
            Réessayer la connexion
          </button>
        ) : null}
        {workflowActive ? (
          <span className="workflow-truth active">
            <Loader2 className="spin" size={14} aria-hidden="true" />
            {phase === "submitting"
              ? "Préparation en cours"
              : bundle
                ? "Modification en cours"
                : "Conception en cours"}
          </span>
        ) : bundle ? (
          <span className={integrityVerified ? "topbar-proof ok" : "topbar-proof warn"}>
            {integrityVerified ? <CheckCircle2 size={14} aria-hidden="true" /> : <AlertTriangle size={14} aria-hidden="true" />}
            {integrityVerified ? "Intégrité vérifiée" : workflowStatusLabel(bundle.status)}
          </span>
        ) : phase !== "idle" ? <span className="workflow-truth">{phaseLabel(phase)}</span> : null}
        {fidelityBadge ? (
          <span
            className={
              fidelityBadge.fidelity === "vendor_qualified"
                ? "topbar-proof ok"
                : "topbar-proof warn"
            }
            data-geometry-fidelity={fidelityBadge.fidelity}
            title={fidelityBadge.label}
          >
            <Boxes size={14} aria-hidden="true" /> {compactFidelityLabel(fidelityBadge.fidelity)}
          </span>
        ) : null}
        {issueCount ? (
          <span className="topbar-issue-count">
            <AlertTriangle size={14} aria-hidden="true" /> {issueCount} limite{issueCount > 1 ? "s" : ""} à examiner
          </span>
        ) : null}
      </div>
    </header>
  );
}

export function ChatCommandPanel({
  conversation,
  creationPath = "telecom",
  onCreationPathChange,
  activeRequirements,
  analysis,
  analysisBusy,
  analysisError,
  analysisSubmitted,
  bootstrapError,
  bootstrapLoading,
  prompt,
  submissionPending,
  phase,
  error,
  failureIssue = null,
  canEdit,
  correctionBusy,
  revisionPrompt,
  revisionBusy,
  editMessage,
  versions,
  documentCapabilities = null,
  documentCapabilitiesError,
  documentCapabilitiesLoading,
  documentPackReview,
  documentPackReviewError,
  documentPackReviewLoading,
  documentPackSummary,
  documentPackMessage,
  documentPackBusy,
  multimodalConsent = "disabled",
  multimodalIntelligence = null,
  onAnalyze,
  onConfirm,
  onDocumentPackCorrection,
  onDocumentPackGenerate,
  onDocumentPackReviewRetry,
  onDocumentPackUpload,
  onDocumentCapabilitiesRetry,
  onMultimodalConsentChange,
  onPromptChange,
  onRevisionPromptChange,
  onRevisionSubmit,
  onRetryBootstrap
}: {
  conversation?: ReactNode;
  creationPath?: "telecom" | "free";
  onCreationPathChange?: (path: "telecom" | "free") => void;
  activeRequirements?: RequirementSpec | null;
  analysis: ParseRequirementsResponse | null;
  analysisBusy: boolean;
  analysisError: string | null;
  analysisSubmitted: boolean;
  bootstrapError?: string | null;
  bootstrapLoading?: boolean;
  prompt: string;
  submissionPending: boolean;
  phase: WorkflowPhase;
  error: string | null;
  failureIssue?: UserIssue | null;
  canEdit: boolean;
  correctionBusy: boolean;
  revisionPrompt: string;
  revisionBusy: boolean;
  editMessage: string | null;
  versions?: PublicVersionInfo[];
  documentCapabilities: DocumentPackCapabilities | null;
  documentCapabilitiesError?: string | null;
  documentCapabilitiesLoading?: boolean;
  documentPackReview: DocumentPackReview | null;
  documentPackReviewError?: string | null;
  documentPackReviewLoading?: boolean;
  documentPackSummary: DocumentPackSummary | null;
  documentPackMessage: string | null;
  documentPackBusy: boolean;
  multimodalConsent?: MultimodalConsent;
  multimodalIntelligence?: MultimodalIntelligence | null;
  onAnalyze: () => void;
  onConfirm: () => void;
  onDocumentPackCorrection: (field: string, value: string, reason: string) => void;
  onDocumentPackGenerate: () => void;
  onDocumentPackReviewRetry?: () => void;
  onDocumentPackUpload: (files: File[]) => Promise<boolean>;
  onDocumentCapabilitiesRetry?: () => void;
  onMultimodalConsentChange?: (value: MultimodalConsent) => void;
  onPromptChange: (value: string) => void;
  onRevisionPromptChange: (value: string) => void;
  onRevisionSubmit: () => void;
  onRetryBootstrap?: () => void;
}) {
  const disabled =
    submissionPending || phase === "submitting" || phase === "streaming" || phase === "running";
  const [commandMode, setCommandMode] = useState<"new" | "revision">(
    canEdit ? "revision" : "new"
  );
  const previousCanEdit = useRef(canEdit);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!canEdit && commandMode === "revision") {
      setCommandMode("new");
    }
    if (canEdit && !previousCanEdit.current) {
      setCommandMode("revision");
    }
    previousCanEdit.current = canEdit;
  }, [canEdit, commandMode]);

  const revisionMode = commandMode === "revision" && canEdit;
  const composerValue = revisionMode ? revisionPrompt : prompt;
  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(Math.max(composer.scrollHeight, 92), 210)}px`;
  }, [composerValue]);
  const assistantTitle = revisionBusy
    ? "Modification et contrôles en cours"
    : revisionMode
      ? "Décrivez la modification"
      : disabled
        ? "Conception et contrôles en cours"
      : phase === "completed"
        ? "Le résultat est prêt à inspecter"
        : phase === "failed"
          ? "Le résultat nécessite une correction"
          : "Décrivez le résultat attendu";
  const assistantMessage = revisionBusy
    ? "La version actuelle reste visible pendant la création et la validation de la nouvelle version."
    : revisionMode
      ? "Demandez un changement précis. La version actuelle reste disponible si les contrôles refusent la modification."
      : disabled
        ? "La demande confirmée est en cours d’assemblage. Le résultat ne sera annoncé qu’après Blender et la QA."
      : phase === "completed"
        ? "Inspectez le modèle, demandez une modification ou démarrez un nouveau site."
        : phase === "failed"
          ? "Les artefacts non vérifiés restent indisponibles. Corrigez la demande ou relancez une génération vérifiée."
          : creationPath === "free" ? "Décrivez l’objet et ses contraintes. Le moteur choisit le domaine et contrôle la construction avant de publier un résultat."
          : "Les contraintes sont extraites puis confirmées avant toute génération Blender.";
  const failedIssue = phase === "failed" && failureIssue
    ? humanizeUserIssue(failureIssue)
    : null;
  const submitCurrentCommand = () => {
    if (revisionMode) {
      if (!revisionBusy && revisionPrompt.trim()) onRevisionSubmit();
      return;
    }
    if (!analysisBusy && prompt.trim()) onAnalyze();
  };
  return (
    <section className="command-center" aria-label="Conversation de commande">
      <div className="conversation-header">
        <div className="conversation-heading">
          <span className="eyebrow">Assistant de conception</span>
          <h1>{revisionMode ? "Modifier le design" : "Créer un design 3D"}</h1>
        </div>
        {phase !== "failed" ? (
          <div className={`assistant-card conversation-message${revisionBusy ? " busy" : ""}`}>
            {revisionBusy ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <RadioTower size={18} aria-hidden="true" />}
            <div>
              <strong>{assistantTitle}</strong>
              <p>{assistantMessage}</p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="conversation-feed" aria-label="Conversation et cahier des charges">
        {conversation ?? <ConversationHistory
          activeRequirements={prompt.trim() ? null : activeRequirements ?? null}
          currentPrompt={analysis || analysisSubmitted ? prompt : ""}
          versions={versions ?? []}
        />}

        {phase === "failed" ? (
          <article className="workflow-recovery" role="alert">
            <div className="workflow-recovery-heading">
              <AlertTriangle size={18} aria-hidden="true" />
              <div>
                <strong>La construction 3D n’a pas abouti</strong>
                <p>
                  {failureRecoveryMessage(failedIssue)}
                </p>
              </div>
            </div>
            <div className="workflow-recovery-actions">
              <button
                className="secondary-action"
                onClick={() => composerRef.current?.focus()}
                type="button"
              >
                Corriger la demande
              </button>
            </div>
          </article>
        ) : null}

        {bootstrapError ? (
          <ResourceRecovery
            busy={bootstrapLoading}
            label="L’état initial du studio n’a pas pu être entièrement synchronisé."
            message={bootstrapError}
            onRetry={onRetryBootstrap}
          />
        ) : bootstrapLoading ? (
          <p className="resource-loading" aria-live="polite" role="status">
            <Loader2 className="spin" size={15} aria-hidden="true" /> Synchronisation du studio…
          </p>
        ) : null}

        {analysis && !revisionMode ? (
          <RequirementsUnderstanding
            analysis={analysis}
            failedWorkflow={phase === "failed"}
            onConfirm={onConfirm}
            submitted={analysisSubmitted}
            submitting={disabled}
          />
        ) : null}
        {analysisError ? <p className="inline-alert"><AlertTriangle size={16} aria-hidden="true" /> {analysisError}</p> : null}

        {!revisionMode ? (
          <>
            <DocumentPackIntake
              busy={documentPackBusy}
              capabilities={documentCapabilities}
              capabilitiesError={documentCapabilitiesError}
              capabilitiesLoading={documentCapabilitiesLoading}
              correctionBusy={correctionBusy}
              message={documentPackMessage}
              onCorrect={onDocumentPackCorrection}
              onGenerate={onDocumentPackGenerate}
              onCapabilitiesRetry={onDocumentCapabilitiesRetry}
              onReviewRetry={onDocumentPackReviewRetry}
              onUpload={onDocumentPackUpload}
              review={documentPackReview}
              reviewError={documentPackReviewError}
              reviewLoading={documentPackReviewLoading}
              summary={documentPackSummary}
            />
            <MultimodalConsentControl
              capability={multimodalIntelligence}
              consent={multimodalConsent}
              disabled={disabled || documentPackBusy}
              onChange={onMultimodalConsentChange}
            />
          </>
        ) : null}

        {editMessage ? (
          <p
            aria-live="polite"
            className={`command-feedback${editMessage.includes("non appliquée") || editMessage.includes("refusée") ? " warning" : " success"}`}
            role="status"
          >
            {editMessage}
          </p>
        ) : null}

        {error && phase !== "failed" ? (
          <p className="inline-alert">
            <AlertTriangle size={16} aria-hidden="true" /> {error}
          </p>
        ) : null}
      </div>

      <div className="command-dock">
        {!revisionMode && onCreationPathChange ? (
          <div className="command-mode" role="group" aria-label="Parcours de conception">
            <button type="button" aria-pressed={creationPath === "telecom"} disabled={disabled || analysisBusy} onClick={() => onCreationPathChange("telecom")}>Télécom avec validation</button>
            <button type="button" aria-pressed={creationPath === "free"} disabled={disabled || analysisBusy} onClick={() => onCreationPathChange("free")}>Intention libre</button>
          </div>
        ) : null}
        {!revisionMode && creationPath === "free" ? <p className="composer-hint">Décrivez un objet ou un aménagement. La demande sera envoyée directement au moteur de conception, qui choisit le domaine. Ce parcours expérimental dépend des capacités disponibles et lance la génération sans revue télécom préalable.</p> : null}
        {canEdit ? (
          <div className="command-mode" role="group" aria-label="Type de commande">
            <button className={!revisionMode ? "active" : ""} disabled={disabled || revisionBusy} onClick={() => setCommandMode("new")} type="button">Nouveau design</button>
            <button className={revisionMode ? "active" : ""} disabled={disabled || revisionBusy} onClick={() => setCommandMode("revision")} type="button">Modifier le design</button>
          </div>
        ) : null}

        <div className="command-composer">
          <textarea
            aria-label={revisionMode ? "Revision prompt" : "Design prompt"}
            placeholder={revisionMode
              ? "Décrivez la modification à appliquer au design…"
              : "Décrivez le site, ses contraintes et le résultat attendu…"}
            value={revisionMode ? revisionPrompt : prompt}
            disabled={disabled || revisionBusy}
            onChange={(event) => revisionMode
              ? onRevisionPromptChange(event.target.value)
              : onPromptChange(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                submitCurrentCommand();
              }
            }}
            ref={composerRef}
            rows={3}
          />
          <button
            aria-label={revisionMode ? "Appliquer la révision" : creationPath === "free" ? "Concevoir depuis cette intention" : "Analyser la demande"}
            className="composer-submit"
            disabled={disabled || (revisionMode ? revisionBusy || !revisionPrompt.trim() : analysisBusy || !prompt.trim())}
            onClick={revisionMode ? onRevisionSubmit : onAnalyze}
            title={revisionMode ? "Appliquer la modification" : creationPath === "free" ? "Concevoir depuis cette intention" : "Analyser les contraintes"}
            type="button"
          >
            {revisionMode ? (
              revisionBusy ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <Send size={18} aria-hidden="true" />
            ) : analysisBusy ? (
              <Loader2 className="spin" size={18} aria-hidden="true" />
            ) : (
              <Sparkles size={18} aria-hidden="true" />
            )}
          </button>
        </div>
        <p className="composer-hint">
          {revisionMode
            ? revisionBusy ? "Révision et validation en cours…" : "⌘ Entrée pour appliquer · la version actuelle reste protégée."
            : creationPath === "free" ? "⌘ Entrée pour lancer la conception · le moteur publiera les contrôles et limites."
            : analysisBusy ? "Analyse de la demande en cours…" : analysis ? "Modifiez le texte puis réanalysez si nécessaire." : "⌘ Entrée pour analyser · les paramètres seront confirmés avant génération."}
        </p>
      </div>
    </section>
  );
}

type ConversationEntry = {
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

function ConversationHistory({
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

function RequirementsUnderstanding({
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
        <p>La demande n’a pas pu être convertie en exigences exploitables.</p>
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
      {analysis.fallback_used ? (
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
          disabled={submitting || confirmationBlocked}
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

function DocumentPackIntake({
  busy,
  capabilities,
  capabilitiesError,
  capabilitiesLoading,
  correctionBusy,
  message,
  onCorrect,
  onCapabilitiesRetry,
  onGenerate,
  onReviewRetry,
  onUpload,
  review,
  reviewError,
  reviewLoading,
  summary
}: {
  busy: boolean;
  capabilities: DocumentPackCapabilities | null;
  capabilitiesError?: string | null;
  capabilitiesLoading?: boolean;
  correctionBusy: boolean;
  message: string | null;
  onCorrect: (field: string, value: string, reason: string) => void;
  onCapabilitiesRetry?: () => void;
  onGenerate: () => void;
  onReviewRetry?: () => void;
  onUpload: (files: File[]) => Promise<boolean>;
  review: DocumentPackReview | null;
  reviewError?: string | null;
  reviewLoading?: boolean;
  summary: DocumentPackSummary | null;
}) {
  const reviewComplete = review ? documentReviewComplete(review) : false;
  const canGenerate = summary?.can_generate_design === true && reviewComplete;
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (reviewError) {
      setExpanded(true);
    }
  }, [reviewError]);
  return (
    <details
      className="document-intake"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
      open={expanded}
    >
      <summary>
        <FileArchive size={17} aria-hidden="true" />
        <span>Documents techniques</span>
        {summary ? (
          <small>
            {summary.document_count} pièce(s) · {summary.can_generate_design ? "prêt" : "revue requise"}
          </small>
        ) : null}
      </summary>
      <div className="document-intake-body">
        <div className="document-intake-copy">
          <span className="eyebrow">Cahier de charge</span>
          <strong>Pièces techniques et cahier de charge</strong>
          <p>
            {capabilitiesError
              ? "Les limites d’import ne sont pas disponibles; aucun fichier n’est envoyé sans ce contrat."
              : capabilities?.document_pack_status === "limited"
              ? "Joignez directement plusieurs PDF, images, plans et tableaux, ou déposez un ZIP. Le backend local inventorie, déduplique et conserve la provenance avant de construire le design."
              : capabilitiesLoading
                ? "Capacités documentaires en cours de chargement."
                : "Capacités documentaires indisponibles."}
          </p>
        </div>
        {capabilitiesError ? (
          <ResourceRecovery
            busy={capabilitiesLoading}
            label="Le contrat d’import documentaire n’a pas été chargé."
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
        <div className="pack-summary">
          <strong>{summary.pack_id}</strong>
          <small>
            {summary.document_count} documents · {summary.missing_blocking_count} champs bloquants · QA {formatScore(summary.qa_score)}
          </small>
          <button className="secondary-action" disabled={!canGenerate || busy} onClick={onGenerate} type="button">
            Générer depuis le pack
          </button>
        </div>
        ) : null}
        {review ? (
        <DocumentPackReviewPanel
          busy={busy || correctionBusy}
          onCorrect={onCorrect}
          onRetry={onReviewRetry}
          review={review}
        />
        ) : null}
        {!review && reviewError ? (
          <ResourceRecovery
            busy={reviewLoading || busy}
            label="La revue documentaire n’a pas pu être synchronisée. Le pack conservé n’est pas présenté comme vide."
            message={reviewError}
            onRetry={onReviewRetry}
          />
        ) : !review && reviewLoading ? (
          <p className="resource-loading" aria-live="polite" role="status">
            <Loader2 className="spin" size={15} aria-hidden="true" /> Chargement de la revue documentaire…
          </p>
        ) : null}
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </details>
  );
}

export function multimodalConsentIsAvailable(
  capability: MultimodalIntelligence | null | undefined
): boolean {
  return capability?.enabled === true &&
    (capability.status === "operational" || capability.status === "configured_unverified");
}

function MultimodalConsentControl({
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
            Désactivée par défaut. Jusqu’à {capability.max_images_per_request} image(s),
            limitées à {Math.floor(capability.max_image_bytes / 1_000_000)} Mo chacune,
            peuvent être traitées à distance pour comprendre plans et croquis.
          </small>
        </span>
      </label>
      {capability.status === "configured_unverified" ? (
        <p role="status">Le service sera vérifié au moment de l’analyse; aucun succès n’est supposé.</p>
      ) : null}
      <p>
        Cocher cette autorisation n’envoie aucun fichier. Elle est enregistrée avec la prochaine
        commande de conception et ne peut être utilisée que par une étape d’analyse explicite.
        Le flux documentaire actuel ne déclenche pas encore la revue distante.
      </p>
      <p>La revue visuelle du design final reste désactivée dans ce milestone.</p>
    </section>
  );
}

function DocumentPackReviewPanel({
  busy,
  onCorrect,
  onRetry,
  review
}: {
  busy: boolean;
  onCorrect: (field: string, value: string, reason: string) => void;
  onRetry?: () => void;
  review: DocumentPackReview;
}) {
  const conflicts = review.conflicts ?? [];
  const missingFields = review.missingFields ?? [];
  const qa = review.qa;
  const documents = review.documents ?? [];
  const provenance = review.provenance;
  const processing = review.processing;
  const consolidatedSpec = review.consolidatedSpec;
  const correctionFields = [...conflicts, ...missingFields].filter(
    (field, index, items) => items.findIndex((candidate) => candidate.field === field.field) === index
  );
  const correctionFieldNames = Array.from(
    new Set([
      ...correctionFields.map((candidate) => candidate.field),
      ...(qa?.blocking_issues ?? [])
    ])
  );
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const selectedField = field || correctionFieldNames[0] || "";
  const failedChecks = (qa?.checks ?? []).filter((check) => !check.passed);
  const usedDocuments = documents.filter((document) => document.used_for_design);
  const ignoredDocuments = documents.filter((document) => !document.used_for_design);
  const failedDocuments = documents.filter((document) =>
    ["failed", "unavailable", "unsupported"].includes(document.extraction_status)
  );
  const criticalEvidence = Object.entries(provenance ?? {})
    .filter(([name]) => isCriticalDocumentField(name))
    .flatMap(([name, sources]) => sources.map((source) => ({ name, source })))
    .sort((left, right) => (right.source.confidence ?? 0) - (left.source.confidence ?? 0))
    .slice(0, 12);
  const processingWarnings = Array.from(
    new Set([
      ...(processing?.warnings ?? []),
      ...documents.flatMap((document) => document.processing_warnings)
    ])
  );

  const submitCorrection = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedField || !value.trim() || !reason.trim()) {
      return;
    }
    onCorrect(selectedField, value, reason);
    setValue("");
    setReason("");
  };

  return (
    <div className="pack-summary" aria-label="Revue du cahier de charge">
      <strong>{qa?.ready_to_generate ? "Cahier de charge prêt" : qa ? "Revue nécessaire" : "Revue partielle"}</strong>
      {qa ? (
        <small>Confiance {formatScore(qa.ready_confidence)} · {conflicts.length} conflit(s) · {missingFields.length} champ(s) manquant(s)</small>
      ) : (
        <small>Le statut QA documentaire n’est pas disponible.</small>
      )}
      {Object.keys(review.sectionErrors ?? {}).length ? (
        <ResourceRecovery
          busy={busy}
          label="Certaines parties de la revue n’ont pas été chargées. Les autres restent consultables."
          message={documentReviewFailureMessage(review)}
          onRetry={onRetry}
        />
      ) : null}
      <div className="document-triage-summary" aria-label="Tri documentaire">
        <span><strong>{usedDocuments.length}</strong> utile(s)</span>
        <span><strong>{ignoredDocuments.length}</strong> écarté(s)</span>
        <span><strong>{failedDocuments.length}</strong> non lu(s)</span>
      </div>
      <div className="document-intelligence-summary">
        <strong>Compréhension utilisée pour le design</strong>
        <small>
          {consolidatedSpec
            ? consolidatedSpec.source_mode === "groq" || consolidatedSpec.source_mode === "mixed"
              ? `Compréhension structurée${consolidatedSpec.llm_fallback_used ? " avec mode de secours signalé" : " validée"}.`
              : "Extraction déterministe; aucun raisonnement LLM n’est revendiqué."
            : "La synthèse consolidée n’a pas pu être chargée."}
        </small>
        {criticalEvidence.length ? (
          <ul className="evidence-list">
            {criticalEvidence.map(({ name, source }, index) => (
              <li key={`${name}-${source.document_id}-${index}`}>
                <strong>{humanDocumentField(name)}</strong>
                <span>{source.evidence}</span>
                <small>{formatEvidenceLocation(source.file, source.page, source.sheet, source.layer, source.confidence)}</small>
              </li>
            ))}
          </ul>
        ) : (
          <small>Aucune preuve critique exploitable n’a encore été consolidée.</small>
        )}
      </div>
      {correctionFields.length ? (
        <div className="mini-list">
          <strong>Points à corriger</strong>
          <ul>
            {correctionFields.slice(0, 8).map((item) => (
              <li key={item.field}>
                {humanDocumentField(item.field)}: {documentFieldReason(item)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {failedChecks.length ? (
        <List
          title="Contrôles documentaires à revoir"
          items={failedChecks.map((check) => check.reason)}
          empty="Tous les contrôles documentaires sont passés."
        />
      ) : null}
      {processingWarnings.length ? (
        <List
          title="Limites de lecture détectées"
          items={processingWarnings}
          empty="Aucune limite de traitement signalée."
        />
      ) : null}
      {ignoredDocuments.length || failedDocuments.length ? (
        <details className="document-details">
          <summary>Documents écartés ou non exploitables</summary>
          <ul>
            {[...ignoredDocuments, ...failedDocuments]
              .filter((document, index, items) => items.findIndex((item) => item.document_id === document.document_id) === index)
              .map((document) => (
                <li key={document.document_id}>
                  <strong>{document.filename}</strong>
                  <span>{document.why_used_or_ignored || document.reason}</span>
                  <small>{document.category} · {document.extraction_status}</small>
                </li>
              ))}
          </ul>
        </details>
      ) : null}
      {correctionFieldNames.length ? (
        <form className="revision-box" onSubmit={submitCorrection}>
          <label>
            Champ
            <select aria-label="Champ documentaire à corriger" onChange={(event) => setField(event.target.value)} value={selectedField}>
              {correctionFieldNames.map((name) => (
                <option key={name} value={name}>{humanDocumentField(name)}</option>
              ))}
            </select>
          </label>
          <label>
            Valeur confirmée
            <input aria-label="Valeur documentaire confirmée" onChange={(event) => setValue(event.target.value)} placeholder="Ex: 24,24,24 ou 30" value={value} />
          </label>
          <label>
            Justification
            <textarea aria-label="Justification de correction" onChange={(event) => setReason(event.target.value)} placeholder="Ex: valeur vérifiée sur le plan d’élévation, page 3" rows={2} value={reason} />
          </label>
          <button className="secondary-action" disabled={busy || !selectedField || !value.trim() || !reason.trim()} type="submit">
            {busy ? "Validation..." : "Enregistrer la correction"}
          </button>
        </form>
      ) : null}
      <List
        title="Actions recommandées"
        items={qa?.recommended_user_actions ?? []}
        empty={qa ? "Aucune action documentaire supplémentaire." : "Actions indisponibles tant que la QA documentaire n’est pas resynchronisée."}
      />
    </div>
  );
}

function documentReviewComplete(review: DocumentPackReview): boolean {
  return (
    review.summary !== null &&
    review.conflicts !== null &&
    review.missingFields !== null &&
    review.qa !== null &&
    review.documents !== null &&
    review.extractions !== null &&
    review.provenance !== null &&
    review.processing !== null &&
    review.consolidatedSpec !== null &&
    Object.keys(review.sectionErrors ?? {}).length === 0
  );
}

function documentReviewFailureMessage(review: DocumentPackReview): string {
  const labels: Record<string, string> = {
    summary: "résumé",
    conflicts: "conflits",
    missingFields: "champs manquants",
    qa: "QA documentaire",
    documents: "tri des documents",
    extractions: "extractions",
    provenance: "provenance",
    processing: "traitement",
    consolidatedSpec: "synthèse consolidée"
  };
  const sections = Object.keys(review.sectionErrors ?? {}).map(
    (section) => labels[section] ?? section
  );
  return `Sections indisponibles : ${sections.join(", ")}.`;
}

function isCriticalDocumentField(field: string): boolean {
  return /(tower|height|hba|azimuth|sector|foundation|cabinet|rru|cable|gps|antenna)/i.test(field);
}

function formatEvidenceLocation(
  file: string,
  page: number | null | undefined,
  sheet: string | null | undefined,
  layer: string | null | undefined,
  confidence: number | null | undefined
): string {
  const location = [
    file,
    page ? `page ${page}` : null,
    sheet ? `feuille ${sheet}` : null,
    layer ? `calque ${layer}` : null,
    typeof confidence === "number" ? `confiance ${formatScore(confidence)}` : null
  ].filter(Boolean);
  return location.join(" · ");
}

export function CurrentOperationStrip({
  notice,
  operation,
  phase,
  runtimeMode
}: {
  notice?: string | null;
  operation: CurrentOperation | null;
  phase: WorkflowPhase;
  runtimeMode: RuntimeMode;
}) {
  const running = phase === "running" || phase === "streaming" || phase === "submitting";
  const pollingFallback = runtimeMode === "polling" && running;
  const transportLabel =
    runtimeMode === "sse" && running
      ? "Temps réel"
      : pollingFallback
        ? "Mode de secours"
        : "Suivi inactif";
  return (
    <section className="operation-strip" aria-label="Opération courante">
      <Clock3 size={18} aria-hidden="true" />
      <div>
        <strong>{operation?.human_label ?? humanOperationLabel(operation?.current_operation) ?? (running ? "Conception en cours" : "Studio prêt")}</strong>
        <span>{operation?.progress_message ?? "Les étapes de conception apparaissent ici pendant la génération."}</span>
        {notice ? <small className="operation-notice" aria-live="polite">{notice}</small> : null}
      </div>
      <StatusPill
        label={transportLabel}
        value={phaseLabel(phase)}
        tone={pollingFallback || Boolean(notice) ? "warn" : "muted"}
      />
    </section>
  );
}

export function LiveGenerationOverlay({
  events,
  intent = "generation",
  operation,
  phase,
  runtimeMode,
  timeline
}: {
  events: NormalizedWorkflowEvent[];
  intent?: "generation" | "revision" | "rollback";
  operation: CurrentOperation | null;
  phase: WorkflowPhase;
  runtimeMode: RuntimeMode;
  timeline: TimelineSummary | null;
}) {
  const running = phase === "submitting" || phase === "streaming" || phase === "running";
  if (!running) {
    return null;
  }
  const liveOperation = operation?.is_terminal ? null : operation;
  const activity = summarizeStages(events, timeline, phase)
    .filter((stage) => stage.status !== "pending" && stage.status !== "waiting")
    .slice(-3)
    .map((stage) => ({
      id: stage.phase,
      label: stage.label,
      status: stage.status
    }));
  const label =
    liveOperation?.human_label ??
    humanOperationLabel(liveOperation?.current_operation) ??
    (intent === "revision"
      ? "Modification du design"
      : intent === "rollback"
        ? "Restauration de la version"
        : phase === "submitting"
          ? "Préparation du design"
          : "Conception en cours");
  const message =
    liveOperation?.progress_message ??
    (intent === "revision"
      ? "Le patch est interprété, exécuté dans Blender puis contrôlé avant de remplacer la version visible."
      : intent === "rollback"
        ? "La version sélectionnée est vérifiée avant de redevenir active."
        : "Les spécialistes coordonnent la conception et publient leurs preuves au fur et à mesure.");
  return (
    <section
      aria-atomic="true"
      aria-live="polite"
      aria-label="Progression de la conception"
      className="generation-overlay"
      role="status"
    >
      <div className="generation-loader" aria-hidden="true">
        <span />
        <span />
        <RadioTower size={25} />
      </div>
      <div className="generation-copy">
        <span className="eyebrow">
          {runtimeMode === "sse" ? "Mises à jour en temps réel" : "Synchronisation sécurisée"}
        </span>
        <strong>{label}</strong>
        <p>{message}</p>
        {activity.length ? (
          <div className="generation-activity">
            {activity.map((row) => (
              <span className={stageStatusTone(row.status)} key={row.id}>
                <i aria-hidden="true" />
                {row.label}
              </span>
            ))}
          </div>
        ) : (
          <div className="generation-awaiting">
            <Loader2 size={15} aria-hidden="true" />
            Préparation de la conception…
          </div>
        )}
      </div>
    </section>
  );
}

function stageStatusTone(status: string): string {
  if (status.includes("failed") || status === "error") {
    return "warning";
  }
  if (
    status.includes("completed") ||
    status === "passed" ||
    status === "generated"
  ) {
    return "completed";
  }
  return "running";
}

function humanOperationLabel(operation: string | null | undefined): string | null {
  if (!operation) return null;
  const normalized = operation.toLowerCase();
  if (normalized.includes("requirement") || normalized.includes("extract")) {
    return "Compréhension de la demande";
  }
  if (normalized.includes("plan") || normalized.includes("blueprint") || normalized.includes("scene")) {
    return "Conception du plan 3D";
  }
  if (normalized.includes("blender") || normalized.includes("build") || normalized.includes("geometry")) {
    return "Construction dans Blender";
  }
  if (normalized.includes("qa") || normalized.includes("quality") || normalized.includes("certif")) {
    return "Vérification du résultat";
  }
  return "Conception en cours";
}

export function AgentStageRail({
  events,
  timeline,
  phase
}: {
  events: NormalizedWorkflowEvent[];
  timeline: TimelineSummary | null;
  phase: WorkflowPhase;
}) {
  const rows = useMemo(() => summarizeStages(events, timeline, phase), [events, phase, timeline]);
  return (
    <section className="stage-rail" aria-label="Étapes agentiques">
      <div className="stage-heading">
        <Sparkles size={17} aria-hidden="true" />
        <strong>Progression intelligente</strong>
      </div>
      {rows.map((row) => (
        <article className={`stage-chip ${row.status}`} key={row.phase}>
          <span />
          <div>
            <strong>{row.label}</strong>
            <small>{stageStatusLabel(row.status)}</small>
          </div>
        </article>
      ))}
    </section>
  );
}

export function AgentTimeline({ events, timeline }: { events: NormalizedWorkflowEvent[]; timeline: TimelineSummary | null }) {
  const terminalEvent = [...events].reverse().find((event) =>
    event.event_type === "workflow_completed" || event.event_type === "workflow_failed"
  );
  const phase: WorkflowPhase =
    timeline?.status === "completed" || terminalEvent?.event_type === "workflow_completed"
      ? "completed"
      : timeline?.status === "failed" || terminalEvent?.event_type === "workflow_failed"
        ? "failed"
        : events.length || timeline?.timeline_steps.length
          ? "running"
          : "idle";
  const rows = summarizeStages(events, timeline, phase);

  return (
    <section className="drawer-section" aria-label="Timeline agents">
      <PanelTitle icon={<Sparkles size={17} />} title="Progression du design" />
      <p className="muted">Les détails techniques sont regroupés en étapes lisibles.</p>
      <div className="timeline-list macro-progress">
        {rows.map((row) => (
            <article className="timeline-item" key={row.phase}>
              <span className={`timeline-dot ${row.status}`} />
              <div>
                <strong>{row.label}</strong>
                <p>{macroStageMessage(row.label, row.status)}</p>
                <small>{stageStatusLabel(row.status)}</small>
              </div>
            </article>
          ))}
      </div>
    </section>
  );
}

type DrawerId =
  | "summary"
  | "agents"
  | "scene"
  | "quality"
  | "artifacts"
  | "library"
  | "system"
  | "versions";
type DrawerDefinition = { id: DrawerId; label: string; badge?: string; icon: ReactNode };

export function InspectorDock({
  assemblyPlan = null,
  adaptationCapabilities = null,
  adaptationCapabilitiesError = null,
  adaptationLoading = false,
  adaptationCatalog = null,
  adaptationCatalogError = null,
  assetInventory = null,
  assetInventoryError = null,
  assetLibrarySearch = null,
  assetLibrarySearchBusy = false,
  assetLibrarySearchError = null,
  assetLibrarySummary = null,
  assetLibrarySummaryError = null,
  assetLibraryLoading = false,
  bundle,
  canRollback,
  documentCapabilities,
  events,
  componentProofs = null,
  cognitiveEvidenceError = null,
  cognitiveEvidenceLoading = false,
  issues,
  ragEvidence = null,
  ragEvidenceError = null,
  ragEvidenceLoading = false,
  qaEvidence = null,
  qaEvidenceError = null,
  qaEvidenceLoading = false,
  llmProvenance = null,
  llmProvenanceError = null,
  llmProvenanceLoading = false,
  viewerBundleError = null,
  viewerBundleLoading = false,
  summary,
  timeline,
  toAbsoluteUrl,
  onRollbackVersion,
  onRetryAdaptation,
  onRetryAssets,
  onRetryAssetSearch,
  onRetryLlmProvenance,
  onRetryQaEvidence,
  onRetryRagEvidence,
  onRetryCognitiveEvidence,
  onRetryViewerBundle,
  onSearchAssetLibrary,
  onSelectSceneComponent,
  rollbackBusyVersionId,
  versionMessage,
  versions
  , selectedSemanticRoot = null
}: {
  assemblyPlan?: AssemblyPlanEvidence | null;
  adaptationCapabilities?: SceneAdaptationCapabilities | null;
  adaptationCapabilitiesError?: string | null;
  adaptationLoading?: boolean;
  adaptationCatalog?: AdaptationCapabilityCatalog | null;
  adaptationCatalogError?: string | null;
  assetInventory?: AssetInventory | null;
  assetInventoryError?: string | null;
  assetLibrarySearch?: AssetLibrarySearch | null;
  assetLibrarySearchBusy?: boolean;
  assetLibrarySearchError?: string | null;
  assetLibrarySummary?: AssetLibrarySummary | null;
  assetLibrarySummaryError?: string | null;
  assetLibraryLoading?: boolean;
  bundle: ViewerBundle | null;
  canRollback: boolean;
  documentCapabilities?: DocumentPackCapabilities | null;
  events: NormalizedWorkflowEvent[];
  componentProofs?: ComponentProofs | null;
  cognitiveEvidenceError?: string | null;
  cognitiveEvidenceLoading?: boolean;
  issues: UserIssues | null;
  ragEvidence?: unknown | null;
  ragEvidenceError?: string | null;
  ragEvidenceLoading?: boolean;
  qaEvidence?: unknown | null;
  qaEvidenceError?: string | null;
  qaEvidenceLoading?: boolean;
  llmProvenance?: LLMDecisionProvenance | null;
  llmProvenanceError?: string | null;
  llmProvenanceLoading?: boolean;
  viewerBundleError?: string | null;
  viewerBundleLoading?: boolean;
  summary: StudioSummary | null;
  timeline: TimelineSummary | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  onRollbackVersion: (versionId: string) => void;
  onRetryAdaptation?: () => void;
  onRetryAssets?: () => void;
  onRetryAssetSearch?: () => void;
  onRetryLlmProvenance?: () => void;
  onRetryQaEvidence?: () => void;
  onRetryRagEvidence?: () => void;
  onRetryCognitiveEvidence?: () => void;
  onRetryViewerBundle?: () => void;
  onSearchAssetLibrary?: (query: string) => void | Promise<void>;
  onSelectSceneComponent?: (semanticRoot: string | null) => void;
  rollbackBusyVersionId: string | null;
  versionMessage: string | null;
  versions: PublicVersionInfo[];
  selectedSemanticRoot?: string | null;
}) {
  const [activeDrawer, setActiveDrawer] = useState<DrawerId | null>(null);
  useEffect(() => {
    if (selectedSemanticRoot) setActiveDrawer("scene");
  }, [selectedSemanticRoot]);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const lastTriggerRef = useRef<HTMLButtonElement | null>(null);
  const issueCount = displayIssueCount(issues, bundle);
  const drawers: DrawerDefinition[] = [];
  if (bundle || viewerBundleError || viewerBundleLoading) drawers.push({ id: "summary", label: "Vue", icon: <CheckCircle2 size={16} /> });
  if (events.length || timeline) drawers.push({ id: "agents", label: "Progression", icon: <Sparkles size={16} /> });
  if (assemblyPlan || componentProofs || cognitiveEvidenceError || cognitiveEvidenceLoading) {
    drawers.push({
      id: "scene",
      label: "Composition",
      badge: componentProofs ? String(sceneInstanceCount(componentProofs)) : undefined,
      icon: <Layers3 size={16} />
    });
  }
  if (bundle || issueCount || viewerBundleError || qaEvidenceError || qaEvidenceLoading) {
    drawers.push({
      id: "quality",
      label: "Vérification",
      badge: issueCount ? String(issueCount) : undefined,
      icon: <ShieldAlert size={16} />
    });
  }
  if (bundle?.viewer_artifacts.length) drawers.push({ id: "artifacts", label: "Livrables", icon: <FileArchive size={16} /> });
  if (assetInventory || assetInventoryError || assetLibraryLoading) {
    drawers.push({ id: "library", label: "Bibliothèque", icon: <LibraryBig size={16} /> });
  }
  if (bundle?.rag_evidence_url || bundle?.llm_decision_provenance_url || summary) {
    drawers.push({ id: "system", label: "Intelligence", icon: <Cpu size={16} /> });
  }
  if (versions.length) drawers.push({ id: "versions", label: "Versions", badge: String(versions.length), icon: <Layers3 size={16} /> });
  useEffect(() => {
    if (!activeDrawer) {
      return;
    }
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveDrawer(null);
        lastTriggerRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !drawerRef.current) {
        return;
      }
      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [activeDrawer]);

  const closeDrawer = () => {
    setActiveDrawer(null);
    window.requestAnimationFrame(() => lastTriggerRef.current?.focus());
  };
  return (
    <aside className="context-dock" aria-label="Drawers contextuels">
      <div className="drawer-launcher">
        {drawers.map((drawer) => (
          <button
            aria-controls="studio-context-drawer"
            aria-expanded={activeDrawer === drawer.id}
            className={activeDrawer === drawer.id ? "drawer-action active" : "drawer-action"}
            key={drawer.id}
            onClick={(event) => {
              lastTriggerRef.current = event.currentTarget;
              if (activeDrawer === drawer.id) {
                closeDrawer();
              } else {
                setActiveDrawer(drawer.id);
              }
            }}
            type="button"
          >
            {drawer.icon}
            <span>{drawer.label}</span>
            {drawer.badge ? <small>{drawer.badge}</small> : null}
          </button>
        ))}
      </div>
      {activeDrawer ? (
        <div
          aria-label={`Détails ${activeDrawer}`}
          aria-modal="true"
          className="context-drawer"
          id="studio-context-drawer"
          ref={drawerRef}
          role="dialog"
        >
          <button aria-label="Fermer les détails" className="drawer-close" onClick={closeDrawer} ref={closeButtonRef} title="Fermer" type="button">
            <X size={16} aria-hidden="true" />
          </button>
          {activeDrawer === "summary" ? (
            <>
              {viewerBundleError ? <ResourceRecovery busy={viewerBundleLoading} label="Le résumé vérifié du design n’a pas été resynchronisé." message={viewerBundleError} onRetry={onRetryViewerBundle} /> : null}
              <SummaryPanel bundle={bundle} issues={issues} summary={summary} versions={versions} />
            </>
          ) : null}
          {activeDrawer === "agents" ? <AgentTimeline events={events} timeline={timeline} /> : null}
          {activeDrawer === "scene" ? (
            <SceneCompositionPanel
              assemblyPlan={assemblyPlan}
              assetDecisionSummary={bundle?.asset_decision_summary}
              assetInventory={assetInventory}
              componentProofs={componentProofs}
              error={cognitiveEvidenceError}
              loading={cognitiveEvidenceLoading}
              onRetry={onRetryCognitiveEvidence}
              onSelect={onSelectSceneComponent}
              selectedSemanticRoot={selectedSemanticRoot}
              toAbsoluteUrl={toAbsoluteUrl}
            />
          ) : null}
          {activeDrawer === "quality" ? (
            <>
              <QaPanel
                bundle={bundle}
                evidence={qaEvidence}
                error={qaEvidenceError ?? viewerBundleError}
                loading={qaEvidenceLoading || viewerBundleLoading}
                onRetry={qaEvidenceError ? onRetryQaEvidence : onRetryViewerBundle}
                toAbsoluteUrl={toAbsoluteUrl}
              />
              <IssuesPanel issues={issues} />
            </>
          ) : null}
          {activeDrawer === "artifacts" ? <ArtifactsPanel bundle={bundle} toAbsoluteUrl={toAbsoluteUrl} /> : null}
          {activeDrawer === "library" ? (
            <AssetLibraryPanel
              busy={assetLibrarySearchBusy}
              error={assetLibrarySearchError}
              inventory={assetInventory}
              inventoryError={assetInventoryError}
              loading={assetLibraryLoading}
              onRetry={onRetryAssets}
              onRetrySearch={onRetryAssetSearch}
              onSearch={onSearchAssetLibrary}
              search={assetLibrarySearch}
              summary={assetLibrarySummary}
              summaryError={assetLibrarySummaryError}
            />
          ) : null}
          {activeDrawer === "system" ? (
            <>
              <RuntimeCapabilitiesPanel
                adaptationCapabilities={adaptationCapabilities}
                adaptationCapabilitiesError={adaptationCapabilitiesError}
                adaptationLoading={adaptationLoading}
                adaptationCatalog={adaptationCatalog}
                adaptationCatalogError={adaptationCatalogError}
                bundle={bundle}
                documentCapabilities={documentCapabilities ?? null}
                inventory={assetInventory}
                onRetryAdaptation={onRetryAdaptation}
                summary={summary}
              />
              <RagEvidencePanel
                bundle={bundle}
                error={ragEvidenceError}
                evidence={ragEvidence}
                loading={ragEvidenceLoading}
                onRetry={onRetryRagEvidence}
              />
              <LlmProvenancePanel
                bundle={bundle}
                error={llmProvenanceError}
                loading={llmProvenanceLoading}
                onRetry={onRetryLlmProvenance}
                provenance={llmProvenance}
              />
            </>
          ) : null}
          {activeDrawer === "versions" ? (
            <VersionSummary
              busyVersionId={rollbackBusyVersionId}
              canRollback={canRollback}
              message={versionMessage}
              onRollback={onRollbackVersion}
              versions={versions}
            />
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

export function SummaryPanel({
  bundle,
  issues,
  summary,
  versions
}: {
  bundle: ViewerBundle | null;
  issues: UserIssues | null;
  summary: StudioSummary | null;
  versions: PublicVersionInfo[];
}) {
  const activeVersion = versions.find((version) => version.active)?.version_id ?? versions[0]?.version_id ?? "aucune";
  const issueCount = displayIssueCount(issues, bundle);
  return (
    <section className="drawer-section" aria-label="Résumé produit">
      <PanelTitle icon={<CheckCircle2 size={17} />} title="Résumé du design" />
      <div className="summary-card">
        <strong>{summaryHeadline(bundle)}</strong>
        <p>{nextUserAction(bundle, issueCount)}</p>
      </div>
      <div className="metric-grid">
        <Metric label="Conception" value={workflowStatusLabel(bundle?.status)} />
        <Metric label="Génération" value={generationTruth(bundle)} />
        <Metric label="QA" value={qaTruth(bundle)} />
        <Metric label="Version" value={activeVersion} />
      </div>
      {bundle?.geometry_program_summary?.program_count ? (
        <div className="summary-card">
          <strong>
            {bundle.geometry_program_summary.generated_component_count} composant(s) créé(s)
            {" · "}{bundle.geometry_program_summary.reused_component_count ?? 0} composant(s) réutilisé(s)
          </strong>
          <p>
            {bundle.geometry_program_summary.total_node_count} nœuds déclaratifs ·{" "}
            {bundle.geometry_program_summary.repaired_program_count} sortie(s) LLM réparée(s)
            et revalidée(s).
          </p>
          <ul className="compact-proof-list">
            {bundle.geometry_program_summary.programs.map((program) => (
              <li key={program.program_id}>
                <span>{humanSemanticRole(program.semantic_role)}</span>
                <small>
                  {program.origin === "catalog_asset" ? "Géométrie source importée, placement contrôlé" : <>
                    {program.authorship === "llm_generated" ? "Géométrie écrite par LLM" : "Géométrie déterministe"}
                    {" · "}
                    {program.generator_provider}:{program.generator_model}
                    {" · "}
                    {humanGeometryOutputMode(program.structured_output_mode)}
                  </>}
                  {" · preuve "}
                  {program.source_prompt_sha256.slice(0, 10)}
                </small>
                {program.source_description_origin === "legacy_unavailable" ? (
                  <small>Intention source indisponible pour ce composant historique.</small>
                ) : program.source_description ? (
                  <small>Intention source : {program.source_description}</small>
                ) : null}
                {program.placement_context ? (
                  <small>Implantation demandée : {program.placement_context}</small>
                ) : null}
                {program.maximum_dimensions_m ? (
                  <small>
                    Enveloppe contrôlée : {program.maximum_dimensions_m.x} ×{" "}
                    {program.maximum_dimensions_m.y} × {program.maximum_dimensions_m.z} m max.
                  </small>
                ) : null}
                {program.limitations.map((limitation) => (
                  <small key={limitation}>Limite déclarée : {limitation}</small>
                ))}
                {program.deterministic_adjustments.map((adjustment) => (
                  <small key={adjustment}>
                    Adaptation déterministe appliquée pour respecter les contraintes.
                  </small>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <List title="État des livrables" items={summarySignals(bundle, issueCount)} empty="Aucun livrable chargé." />
      <List
        title="Services de conception"
        items={[
          `Composants 3D : ${serviceStatusLabel(summary?.asset_inventory_status)}`,
          `Contexte documentaire : ${serviceStatusLabel(summary?.rag_status)}`,
          `Classement des références : ${serviceStatusLabel(summary?.rag_reranker_status)}`
        ]}
        empty="État des services indisponible."
      />
    </section>
  );
}

export function QaPanel({
  bundle,
  evidence,
  error = null,
  loading = false,
  onRetry,
  toAbsoluteUrl = (url) => url ?? null
}: {
  bundle: ViewerBundle | null;
  evidence?: unknown | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const qa = bundle?.qa_summary;
  const assembly = bundle?.assembly_constraint_summary;
  const assemblyEvidenceUrl = toAbsoluteUrl(bundle?.constraint_evidence_url);
  const passed = bundle?.mesh_qa_passed === true;
  const qaExecuted =
    qa?.qa_executed !== false &&
    bundle?.status === "completed" &&
    bundle.generation_mode === "real_blender" &&
    typeof bundle.mesh_qa_passed === "boolean";
  return (
    <section className="drawer-section" aria-label="Validation QA">
      <PanelTitle icon={<ShieldAlert size={17} />} title="Vérification du résultat" />
      {loading ? (
        <p className="muted" aria-live="polite">Synchronisation du rapport QA vérifié…</p>
      ) : error ? (
        <ResourceRecovery
          label="Le détail QA n’a pas pu être resynchronisé. Aucun contrôle manquant n’est supposé réussi."
          message={error}
          onRetry={onRetry}
        />
      ) : evidence ? (
        <p className="resource-proof" role="status">
          <CheckCircle2 size={15} aria-hidden="true" /> Rapport QA détaillé chargé depuis l’artefact backend.
        </p>
      ) : null}
      {qaExecuted && bundle ? (
        <>
          <div className="metric-grid">
            <Metric label="Score" value={formatScore(bundle.qa_score)} />
            <Metric label="Niveau mesh" value={meshQaLevelLabel(bundle.mesh_qa_level)} />
            <Metric
              label="Géométrie"
              value={
                passed && bundle.mesh_qa_level === "mesh_level_spatial_basic"
                  ? "interférences contrôlées"
                  : passed
                    ? "validée de base"
                    : "attention"
              }
            />
            <Metric label="Mode" value={generationTruth(bundle)} />
            <Metric
              label="Exigences"
              value={bundle.requirement_coverage_passed ? "couvertes" : "attention"}
            />
            <Metric
              label="Preuve d’intégrité"
              value={completionCertificateLabel(bundle.completion_certificate_status)}
            />
          </div>
          <List title="Échecs QA" items={stringArray(qa?.checks_failed)} empty="Aucun échec QA remonté." />
          <details className="drawer-disclosure">
            <summary>Portée et limites de cette validation</summary>
            <List title="Ce que la QA ne garantit pas" items={bundle.limitations} empty="Aucune limitation remontée." />
          </details>
        </>
      ) : bundle ? (
        <div className="qa-not-run" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>Validation 3D non exécutée</strong>
            <p>
              {bundle.status === "failed"
                ? qa?.blocked_before_qa === true
                  ? "La conception a été bloquée avant la QA; aucun contrôle 3D ne peut être annoncé."
                  : "La conception s’est arrêtée avant la construction Blender; aucun contrôle 3D ne peut être annoncé."
                : "Aucune preuve complète de construction Blender et de QA n’est disponible pour ce résultat."}
            </p>
          </div>
        </div>
      ) : (
        <p className="muted">La vérification apparaîtra après une construction Blender réelle.</p>
      )}
      {bundle ? (
        <div className="qa-evidence-split">
          {assembly ? (
            <section
              aria-label="Assemblage post-export"
              className={`qa-evidence-card${assembly.status === "passed" ? "" : " advisory"}`}
            >
              <div className="qa-evidence-heading">
                <strong>Assemblage post-export</strong>
                <span>{assemblyConstraintStatusLabel(assembly.status)}</span>
              </div>
              <p>
                Mesures déterministes réalisées sur {assemblyMeasurementScopeLabel(assembly.measurement_scope)}.
              </p>
              {assembly.status !== "not_available" ? (
                <div className="metric-grid">
                  <Metric label="Connexions requises (toutes)" value={formatInteger(assembly.required_connection_count)} />
                  <Metric label="Liaisons mécaniques mesurées" value={formatInteger(assembly.measured_instance_count)} />
                  {assembly.resolved_support_count > 0 ? (
                    <Metric label="Supports d’adaptation observés" value={formatInteger(assembly.resolved_support_count)} />
                  ) : null}
                  <Metric label="Erreur de position max." value={`${formatMeasurement(assembly.max_position_error_m)} m`} />
                  <Metric label="Erreur angulaire max." value={`${formatMeasurement(assembly.max_angular_error_deg)}°`} />
                </div>
              ) : null}
              {assembly.limitations.length ? (
                <List
                  title="Limites de la mesure"
                  items={assembly.limitations.map(assemblyLimitationLabel)}
                  empty="Aucune limitation publiée."
                />
              ) : null}
              <small>
                Ce contrôle décrit des écarts géométriques mesurés après export. Il ne constitue ni une validation d’ingénierie ni une preuve professionnelle.
              </small>
              {assemblyEvidenceUrl ? (
                <a href={assemblyEvidenceUrl} rel="noreferrer" target="_blank">
                  Consulter la preuve de mesure
                </a>
              ) : null}
            </section>
          ) : null}
          <section aria-label="Cadrage technique" className="qa-evidence-card">
            <div className="qa-evidence-heading">
              <strong>Cadrage technique</strong>
              <span>
                {qa?.preview_pixel_framing_qa
                  ? qa.preview_subject_framing_valid === true
                    ? "conforme"
                    : qa.preview_subject_framing_valid === false
                      ? "à corriger"
                      : "exécuté"
                  : "non exécuté"}
              </span>
            </div>
            <p>
              Contrôle déterministe de l’occupation, des marges et du centrage de la preview.
              Il ne valide ni la qualité esthétique ni la conformité métier.
            </p>
            {qa?.preview_pixel_framing_qa ? (
              <small>
                Occupation : {formatRatio(qa.preview_subject_bbox_width_ratio)} × {formatRatio(qa.preview_subject_bbox_height_ratio)} · marge minimale {formatRatio(qa.preview_subject_min_edge_margin_ratio)}
              </small>
            ) : null}
          </section>
          <section aria-label="Revue visuelle assistée" className="qa-evidence-card advisory">
            <div className="qa-evidence-heading">
              <strong>Revue visuelle assistée</strong>
              <span>{visualReviewStatusLabel(bundle.visual_review?.status ?? "not_requested")}</span>
            </div>
            <p>
              {bundle.visual_review?.summary ??
                "Aucune revue sémantique du rendu n’a été demandée pour ce résultat."}
            </p>
            {bundle.visual_review?.findings.length ? (
              <ul>
                {bundle.visual_review.findings.map((finding) => <li key={finding}>{finding}</li>)}
              </ul>
            ) : null}
            <small>Cette revue est consultative et ne peut jamais remplacer la QA déterministe.</small>
          </section>
        </div>
      ) : null}
    </section>
  );
}

export function IssuesPanel({ issues }: { issues: UserIssues | null }) {
  const summarizedIssues = summarizeUserIssues(issues?.human_readable_issues ?? []);
  const primaryIssues = summarizedIssues.slice(0, 4);
  const additionalIssues = summarizedIssues.slice(4);
  const renderIssue = (issue: UserIssue, index: number) => {
    const titleKey = normalizedIssueCopy(issue.title);
    const impactKey = normalizedIssueCopy(issue.impact);
    const actionKey = normalizedIssueCopy(issue.recommended_action);
    return (
      <article className={`issue-card ${issue.severity}`} key={`${issue.title}-${issue.technical_code ?? "issue"}-${index}`}>
        <strong>{issue.title}</strong>
        {impactKey && impactKey !== titleKey ? <p>{issue.impact}</p> : null}
        {actionKey && actionKey !== titleKey && actionKey !== impactKey ? (
          <small>{issue.recommended_action}</small>
        ) : null}
      </article>
    );
  };
  return (
    <section className="drawer-section" aria-label="Limites et actions">
      <PanelTitle icon={<AlertTriangle size={17} />} title="Limites et actions" />
      {summarizedIssues.length ? (
        <div className="issue-list">
          {primaryIssues.map(renderIssue)}
          {additionalIssues.length ? (
            <details className="issue-more">
              <summary>Afficher {additionalIssues.length} autre{additionalIssues.length > 1 ? "s" : ""} limite{additionalIssues.length > 1 ? "s" : ""}</summary>
              <div>{additionalIssues.map((issue, index) => renderIssue(issue, index + primaryIssues.length))}</div>
            </details>
          ) : null}
        </div>
      ) : issues ? (
        <p className="muted">Aucune alerte à examiner.</p>
      ) : (
        <p className="inline-alert">
          <AlertTriangle size={15} aria-hidden="true" />
          Le nombre d’alertes est connu, mais leur détail n’a pas pu être synchronisé.
        </p>
      )}
    </section>
  );
}

export function ArtifactsPanel({
  bundle,
  toAbsoluteUrl
}: {
  bundle: ViewerBundle | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
}) {
  const previews = availablePreviewArtifacts(bundle, toAbsoluteUrl);
  return (
    <section className="drawer-section" aria-label="Livrables">
      <PanelTitle icon={<FileArchive size={17} />} title="Livrables vérifiables" />
      {bundle ? (
        <>
        {previews.length ? (
          <div className="artifact-preview-grid" aria-label="Aperçus du design">
            {previews.map((preview) => (
              <a href={preview.url} key={preview.name} rel="noreferrer" target="_blank">
                <img alt={artifactLabel(preview.name)} loading="lazy" src={preview.url} />
                <span>{artifactLabel(preview.name)}</span>
              </a>
            ))}
          </div>
        ) : null}
        <div className="artifact-list">
          {bundle.viewer_artifacts.map((artifact) => {
            const url = artifact.available ? toAbsoluteUrl(artifact.url) : null;
            const content = (
              <>
                <span>{artifactLabel(artifact.name)}</span>
                <small>{url ? artifactKindLabel(artifact.content_type) : "Indisponible"}</small>
                <ChevronRight size={15} aria-hidden="true" />
              </>
            );
            return url ? (
              <a
                className="artifact-link"
                href={url}
                key={artifact.name}
                rel="noreferrer"
                target="_blank"
              >
                {content}
              </a>
            ) : (
              <div
                aria-disabled="true"
                className="artifact-link unavailable"
                key={artifact.name}
              >
                {content}
              </div>
            );
          })}
        </div>
        </>
      ) : (
        <p className="muted">Aucun artefact tant qu’un workflow n’est pas terminé.</p>
      )}
    </section>
  );
}

export function availablePreviewArtifacts(
  bundle: ViewerBundle | null,
  toAbsoluteUrl: (url: string | null | undefined) => string | null
): Array<{ name: string; url: string }> {
  if (!bundle) return [];
  return bundle.viewer_artifacts.flatMap((artifact) => {
    if (!artifact.available || !artifact.content_type.toLowerCase().startsWith("image/")) {
      return [];
    }
    const url = toAbsoluteUrl(artifact.url);
    return url ? [{ name: artifact.name, url }] : [];
  });
}

function humanGeometryOutputMode(mode: string): string {
  return {
    strict_json_schema: "schéma JSON strict",
    json_object_validated: "JSON validé localement",
    json_object_repaired: "JSON réparé puis revalidé"
  }[mode] ?? mode;
}

export function RagEvidencePanel({
  bundle,
  error = null,
  evidence,
  loading = false,
  onRetry
}: {
  bundle: ViewerBundle | null;
  error?: string | null;
  evidence: unknown | null;
  loading?: boolean;
  onRetry?: () => void;
}) {
  const summary = summarizeRagEvidence(evidence);
  return (
    <section className="drawer-section" aria-label="RAG evidence">
      <PanelTitle icon={<Cpu size={17} />} title="RAG et preuves" />
      <div className="metric-grid">
        <Metric label="Provider" value={bundle?.rag_reranker_provider ?? "unknown"} />
        <Metric label="Recherche" value={serviceStatusLabel(bundle?.rag_retrieval_status)} />
        <Metric label="Reranker" value={bundle?.rag_reranker_status ?? "unknown"} />
        <Metric label="Sources" value={String(bundle?.rag_context_count ?? 0)} />
        <Metric label="Extraction" value={summary.ragUsedForExtraction ? "oui" : "non"} />
        <Metric label="Planning" value={summary.ragUsedForPlanning ? "oui" : "non"} />
      </div>
      {bundle?.rag_retrieval_status === "degraded_local_lexical" ? (
        <p className="inline-alert">
          <WifiOff size={16} aria-hidden="true" /> La recherche vectorielle est indisponible;
          la recherche utilise temporairement le corpus local réel par correspondance lexicale.
        </p>
      ) : null}
      {bundle?.rag_reranker_degraded_reason ? (
        <p className="inline-alert">
          <WifiOff size={16} aria-hidden="true" />{" "}
          {humanRagLimitation(bundle.rag_reranker_degraded_reason)}
        </p>
      ) : null}
      {loading ? (
        <p className="muted" aria-live="polite">Chargement des preuves RAG vérifiées…</p>
      ) : error ? (
        <ResourceRecovery
          label="Les preuves RAG n’ont pas pu être chargées."
          message={error}
          onRetry={onRetry}
        />
      ) : evidence ? (
        <>
          <List
            title="Hints appliqués au plan"
            items={summary.appliedHints}
            empty="Aucun hint n’est prouvé comme appliqué au SceneSpec."
          />
          <List
            title="Hints candidats récupérés"
            items={summary.candidateHints}
            empty="Aucun hint candidat remonté."
          />
          <div className="source-list">
            {summary.sources.length ? (
              summary.sources.map((source, index) => (
                <article className="source-card" key={`${source.title}-${index}`}>
                  <strong>{source.title}</strong>
                  <p>{source.reason}</p>
                  <small>{source.score}</small>
                </article>
              ))
            ) : (
              <p className="muted">Aucune source RAG exploitable affichable.</p>
            )}
          </div>
          <List
            title="Limites RAG"
            items={summary.limitations.map(humanRagLimitation)}
            empty="Aucune limite RAG remontée."
          />
        </>
      ) : (
        <p className="muted">Aucune preuve RAG chargée; le frontend n’en invente pas.</p>
      )}
    </section>
  );
}

export function LlmProvenancePanel({
  bundle,
  error = null,
  loading = false,
  onRetry,
  provenance
}: {
  bundle: ViewerBundle | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  provenance: LLMDecisionProvenance | null;
}) {
  return (
    <section className="drawer-section" aria-label="Provenance de décision LLM">
      <PanelTitle icon={<Sparkles size={17} />} title="Provenance de décision" />
      {loading ? (
        <p className="muted" aria-live="polite">Chargement de la décision structurée…</p>
      ) : error ? (
        <ResourceRecovery
          label="La provenance LLM n’a pas pu être chargée; aucune décision n’est reconstruite côté navigateur."
          message={error}
          onRetry={onRetry}
        />
      ) : provenance ? (
        <>
          <div className="metric-grid">
            <Metric label="Provider" value={provenance.provider} />
            <Metric label="Modèle" value={provenance.model ?? "non déclaré"} />
            <Metric label="Capacité" value={humanSemanticRole(provenance.capability_called)} />
            <Metric label="Contrat" value={provenance.decision_contract_version} />
            <Metric label="Candidats" value={String(provenance.candidates_considered.length)} />
            <Metric label="Fallback" value={provenance.fallback_used ? "signalé" : "non"} />
          </div>
          <List
            title="Stratégies retenues"
            items={provenance.strategy_selected.map(humanSemanticRole)}
            empty="Aucune stratégie retenue n’est déclarée."
          />
          <List
            title="Justification enregistrée"
            items={provenance.rationale}
            empty="Aucune justification n’est déclarée."
          />
          <p className="resource-proof">
            <CheckCircle2 size={15} aria-hidden="true" /> Décision liée à la version active et conservée par le backend.
          </p>
        </>
      ) : bundle?.llm_decision_provenance_url ? (
        <p className="muted">La provenance est publiée mais n’a pas encore été chargée.</p>
      ) : (
        <p className="muted">Aucune provenance de décision versionnée n’est publiée pour ce résultat.</p>
      )}
    </section>
  );
}

export function RuntimeCapabilitiesPanel({
  adaptationCapabilities = null,
  adaptationCapabilitiesError = null,
  adaptationLoading = false,
  adaptationCatalog = null,
  adaptationCatalogError = null,
  summary,
  bundle,
  inventory,
  documentCapabilities,
  onRetryAdaptation
}: {
  adaptationCapabilities?: SceneAdaptationCapabilities | null;
  adaptationCapabilitiesError?: string | null;
  adaptationLoading?: boolean;
  adaptationCatalog?: AdaptationCapabilityCatalog | null;
  adaptationCatalogError?: string | null;
  summary: StudioSummary | null;
  bundle: ViewerBundle | null;
  inventory: AssetInventory | null;
  documentCapabilities: DocumentPackCapabilities | null;
  onRetryAdaptation?: () => void;
}) {
  const unsupported = bundle?.unsupported_actions ?? summary?.unsupported_actions ?? [];
  const runtime = bundle?.runtime_capabilities ?? summary?.runtime_capabilities;
  const showDownload =
    runtime?.can_download_artifacts === true &&
    actionIsSupported("download_artifacts", unsupported);
  return (
    <section className="drawer-section" aria-label="Capacités runtime">
      <PanelTitle icon={<Boxes size={17} />} title="Capacités réelles" />
      {adaptationCapabilitiesError || adaptationCatalogError ? (
        <ResourceRecovery
          busy={adaptationLoading}
          label="Les capacités d’adaptation ne sont pas disponibles; aucune capacité n’est supposée absente ou égale à zéro."
          message={[adaptationCapabilitiesError, adaptationCatalogError].filter(Boolean).join(" · ")}
          onRetry={onRetryAdaptation}
        />
      ) : null}
      <div className="metric-grid">
        <Metric label="Assets" value={inventory?.status ?? "unknown"} />
        <Metric
          label="Paramètres 3D actifs"
          value={adaptationLoading
            ? "chargement"
            : adaptationCapabilitiesError
              ? "indisponible"
              : adaptationCapabilities
                ? String(adaptationCapabilities.capabilities.length)
                : "non résolu"}
        />
        <Metric
          label="Profils d’adaptation"
          value={adaptationLoading
            ? "chargement"
            : adaptationCatalogError
              ? "indisponible"
              : adaptationCatalog
                ? String(adaptationCatalog.profiles.length)
                : "non résolu"}
        />
        <Metric label="Documents" value={documentCapabilities?.document_pack_status ?? "unknown"} />
        <Metric label="Download" value={showDownload ? "supporté" : "non supporté"} />
        <Metric label="WebSocket" value={truth(runtime?.websocket_runtime === true)} />
      </div>
      <List
        title="Modifications vérifiées du design actif"
        items={summarizeAdaptationCapabilityGroups(adaptationCapabilities)}
        empty={adaptationCapabilitiesError
          ? "Liste indisponible jusqu’à la prochaine synchronisation réussie."
          : bundle
            ? "Aucune capacité n’est déclarée pour ce design actif."
            : "Aucun design actif: les paramètres seront résolus après génération."}
      />
      <List
        title="Limites d’adaptation"
        items={adaptationCapabilities?.unsupported_operations ?? []}
        empty="Aucune limite supplémentaire déclarée."
      />
      <List
        title="Actions non supportées"
        items={unsupported.map((item) => `${item.action}: ${item.reason ?? item.future_requirement ?? ""}`)}
        empty="Aucune action non supportée remontée."
      />
    </section>
  );
}

export function VersionSummary({
  busyVersionId,
  canRollback,
  message,
  onRollback,
  versions
}: {
  busyVersionId: string | null;
  canRollback: boolean;
  message: string | null;
  onRollback: (versionId: string) => void;
  versions: PublicVersionInfo[];
}) {
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);
  const visibleVersions = useMemo(
    () => [...versions].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)).slice(0, 8),
    [versions]
  );
  const activeVersionId = versions.find((version) => version.active)?.version_id ?? null;
  useEffect(() => {
    setPendingVersionId(null);
  }, [activeVersionId]);
  return (
    <section className="drawer-section" aria-label="Versions">
      <PanelTitle icon={<RotateCcw size={17} />} title="Versions et rollback" />
      {visibleVersions.length ? (
        <div className="artifact-list">
          {visibleVersions.map((version) => (
            <div className="artifact-link" key={version.version_id}>
              <span>
                {version.version_id}
                {version.edit_description ? <small>{version.edit_description}</small> : null}
              </span>
              <small>{version.active ? "active" : version.status ?? version.generation_mode ?? "version"}</small>
              {!version.active && canRollback && version.status === "completed" ? (
                pendingVersionId === version.version_id ? (
                  <button
                    className="secondary-action"
                    disabled={busyVersionId !== null}
                    onClick={() => onRollback(version.version_id)}
                    type="button"
                  >
                    {busyVersionId === version.version_id ? "Restauration..." : "Confirmer"}
                  </button>
                ) : (
                  <button
                    className="ghost-action"
                    disabled={busyVersionId !== null}
                    onClick={() => setPendingVersionId(version.version_id)}
                    type="button"
                  >
                    Restaurer
                  </button>
                )
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Versions chargées après génération.</p>
      )}
      {versions.length > 8 ? <p className="muted">Les 8 versions les plus récentes sont affichées.</p> : null}
      {!canRollback && versions.length > 1 ? <p className="muted">Le rollback n’est pas annoncé comme disponible par le runtime.</p> : null}
      {message ? <p className="muted" aria-live="polite">{message}</p> : null}
    </section>
  );
}

type TimelineDisplayRow = {
  id: string;
  label: string;
  message: string;
  status: string;
  phase: string | null | undefined;
};

export function summarizeTimelineRows(rows: TimelineDisplayRow[]): TimelineDisplayRow[] {
  const grouped = {
    attribution: 0,
    nonVendorGrade: 0,
    otherAsset: 0
  };
  const visibleRows: TimelineDisplayRow[] = [];

  for (const row of rows) {
    if (isAssetIssueRow(row)) {
      const text = `${row.label} ${row.message}`;
      if (text.includes("ATTRIBUTION_REQUIRED")) {
        grouped.attribution += 1;
      } else if (text.includes("NOT_VENDOR_GRADE") || text.includes("INTERNAL_TEST_MINIMAL") || text.includes("INTERNAL_CLEANED") || text.includes("CC_BY")) {
        grouped.nonVendorGrade += 1;
      } else {
        grouped.otherAsset += 1;
      }
      continue;
    }
    visibleRows.push({
      ...row,
      label:
        row.label === "Certification des preuves"
          ? "Vérification des preuves"
          : row.label
    });
  }

  const groupedRows: TimelineDisplayRow[] = [];
  if (grouped.nonVendorGrade) {
    groupedRows.push({
      id: "grouped-non-vendor-grade-assets",
      label: `Modèles non constructeur : ${grouped.nonVendorGrade} éléments`,
      message: "Le design utilise des modèles réels ou importés, sans garantie constructeur. Consultez les alertes.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.attribution) {
    groupedRows.push({
      id: "grouped-attribution-assets",
      label: `Attributions requises : ${grouped.attribution} élément${grouped.attribution > 1 ? "s" : ""}`,
      message: "Certains modèles imposent une attribution de licence. Consultez les alertes.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.otherAsset) {
    groupedRows.push({
      id: "grouped-other-assets",
      label: `Autres alertes de modèles : ${grouped.otherAsset} élément${grouped.otherAsset > 1 ? "s" : ""}`,
      message: "D’autres avertissements sur les modèles sont disponibles dans les alertes.",
      phase: "issues",
      status: "completed"
    });
  }

  return [...visibleRows, ...groupedRows];
}

function isAssetIssueRow(row: TimelineDisplayRow): boolean {
  const text = `${row.label} ${row.message}`.toLowerCase();
  return text.includes("asset") || text.includes("not_vendor_grade") || text.includes("attribution_required");
}

export function summarizeStages(events: NormalizedWorkflowEvent[], timeline: TimelineSummary | null, phase: WorkflowPhase) {
  const stages = [
    {
      phase: "requirements",
      label: "Compréhension de la demande",
      phases: ["requirements", "extraction", "rag", "memory"],
      nodes: ["extract_requirements", "validate_requirements", "requirements", "retrieve_rag_context", "memory_recall"]
    },
    {
      phase: "planning",
      label: "Conception du plan 3D",
      phases: ["planning", "validation", "scene"],
      nodes: ["plan_scene", "validate_scene", "scene_repair_handler", "scene_planner"]
    },
    {
      phase: "generation",
      label: "Construction dans Blender",
      phases: ["generation", "blender", "viewer"],
      nodes: ["generate_blender", "blender_worker", "blender_failure_handler"]
    },
    {
      phase: "qa",
      label: "Vérification du résultat",
      phases: ["qa", "workflow", "completion"],
      nodes: ["qa_generation", "quality_gate", "workflow"]
    }
  ];
  const statusByPhase = new Map<string, string>();
  for (const event of events) {
    recordStageStatus(statusByPhase, stages, event.phase, event.node, event.status ?? event.event_type);
  }
  for (const step of timeline?.timeline_steps ?? []) {
    recordStageStatus(statusByPhase, stages, step.phase, step.node, step.status);
  }
  const terminalStatus = timeline?.status ?? (phase === "completed" || phase === "failed" ? phase : null);
  return stages.map((item) => {
    const observed =
      statusByPhase.get(item.phase) ?? terminalStageFallback(item.phase, terminalStatus, phase);
    const status =
      terminalStatus === "completed" && isFailureStageStatus(observed)
        ? "completed_with_warning"
        : observed;
    return { phase: item.phase, label: item.label, status };
  });
}

type StageDefinition = {
  phase: string;
  label: string;
  phases: string[];
  nodes: string[];
};

function recordStageStatus(statusByPhase: Map<string, string>, stages: StageDefinition[], phase: string | null | undefined, node: string | null | undefined, status: string) {
  const stage = stages.find((candidate) => {
    const normalizedPhase = (phase ?? "").toLowerCase();
    const normalizedNode = (node ?? "").toLowerCase();
    return candidate.phases.includes(normalizedPhase) || candidate.nodes.some((knownNode) => normalizedNode.includes(knownNode));
  });
  if (!stage) {
    return;
  }
  const current = statusByPhase.get(stage.phase);
  statusByPhase.set(stage.phase, strongestStageStatus(current, status));
}

function strongestStageStatus(current: string | undefined, next: string): string {
  if (!current) {
    return next;
  }
  const rank = (status: string) => {
    if (status.includes("failed") || status === "error") {
      return 5;
    }
    if (status.includes("completed") || status === "passed" || status === "generated") {
      return 4;
    }
    if (status.includes("running")) {
      return 3;
    }
    if (status === "pending") {
      return 2;
    }
    return 1;
  };
  return rank(next) >= rank(current) ? next : current;
}

function isFailureStageStatus(status: string): boolean {
  return status.includes("failed") || status === "error";
}

function terminalStageFallback(itemPhase: string, terminalStatus: string | null, phase: WorkflowPhase): string {
  if (phase === "idle" || phase === "drafting") {
    return "waiting";
  }
  if (terminalStatus === "completed") {
    return itemPhase === "qa" ? "completed" : "not_reported";
  }
  if (terminalStatus === "failed") {
    return itemPhase === "qa" ? "failed" : "not_reported";
  }
  return itemPhase === "qa" ? "waiting" : "pending";
}

function macroStageMessage(label: string, status: string): string {
  if (status.includes("failed") || status === "error") {
    return `${label} a rencontré un blocage. Consultez l’action proposée dans la conversation.`;
  }
  if (status.includes("completed") || status === "passed" || status === "generated") {
    return `${label} terminée avec une preuve backend enregistrée.`;
  }
  if (status.includes("running")) {
    return `${label} en cours.`;
  }
  if (status === "not_reported") {
    return "Cette étape n’a pas publié de preuve exploitable pour ce résultat.";
  }
  return "En attente de l’étape précédente.";
}

export function summarizeUserIssues(issues: UserIssue[]): UserIssue[] {
  const groups = {
    nonVendorGrade: 0,
    attribution: 0,
    otherAsset: 0
  };
  const visible: UserIssue[] = [];

  for (const issue of issues) {
    const text = `${issue.title} ${issue.impact} ${issue.recommended_action} ${issue.technical_code ?? ""}`;
    const normalized = text.toUpperCase();
    if (!isAssetIssueText(text)) {
      visible.push(humanizeUserIssue(issue));
      continue;
    }
    if (normalized.includes("ATTRIBUTION_REQUIRED")) {
      groups.attribution += 1;
    } else if (normalized.includes("NOT_VENDOR_GRADE") || normalized.includes("INTERNAL_TEST_MINIMAL") || normalized.includes("INTERNAL_CLEANED") || normalized.includes("CC_BY")) {
      groups.nonVendorGrade += 1;
    } else {
      groups.otherAsset += 1;
    }
  }

  const grouped: UserIssue[] = [];
  if (groups.nonVendorGrade) {
    grouped.push({
      title: `Modèles non constructeur: ${groups.nonVendorGrade} éléments`,
      severity: "warning",
      impact: "La scène peut être inspectée, mais certains modèles ne sont pas des assets constructeur.",
      recommended_action: "Ne promettez pas une fidélité exacte à un catalogue constructeur.",
      technical_code: "ASSET_NON_VENDOR_GRADE_GROUP"
    });
  }
  if (groups.attribution) {
    grouped.push({
      title: `Attributions de licence requises: ${groups.attribution}`,
      severity: "warning",
      impact: "Des assets utilisés dans la scène imposent une attribution.",
      recommended_action: "Conserver les attributions dans le rapport avant partage externe.",
      technical_code: "ASSET_ATTRIBUTION_REQUIRED_GROUP"
    });
  }
  if (groups.otherAsset) {
    grouped.push({
      title: `Autres alertes de modèles: ${groups.otherAsset}`,
      severity: "warning",
      impact: "Des limites assets sont remontées par le backend.",
      recommended_action: "Inspecter les détails dans les artefacts et rapports backend.",
      technical_code: "ASSET_WARNING_GROUP"
    });
  }
  return [...grouped, ...visible];
}

export function displayIssueCount(
  issues: UserIssues | null,
  bundle: ViewerBundle | null
): number {
  if (issues) {
    return summarizeUserIssues(issues.human_readable_issues).length;
  }
  return bundle?.human_warnings_count ?? 0;
}

function humanizeUserIssue(issue: UserIssue): UserIssue {
  const text = `${issue.title} ${issue.impact} ${issue.technical_code ?? ""}`;
  const normalized = text.toLowerCase();
  const inferredValue = text.match(/inferred as ([\d.]+) degrees?/i)?.[1];
  if (
    normalized.includes("mechanical tilt inferred") ||
    normalized.includes("mechanical tilt was not confirmed")
  ) {
    return {
      ...issue,
      title: "Inclinaison mécanique proposée",
      impact: `Une inclinaison mécanique de ${inferredValue ?? "3"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Confirmez cette valeur avec le cahier de charge radio."
    };
  }
  if (
    normalized.includes("electrical tilt inferred") ||
    normalized.includes("electrical tilt was not confirmed")
  ) {
    return {
      ...issue,
      title: "Inclinaison électrique proposée",
      impact: `Une inclinaison électrique de ${inferredValue ?? "0"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Confirmez cette valeur avec le cahier de charge radio."
    };
  }
  if (normalized.includes("beamwidth inferred")) {
    return {
      ...issue,
      title: "Ouverture d’antenne proposée",
      impact: `Une ouverture de ${inferredValue ?? "65"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Vérifiez cette ouverture pour chaque secteur radio."
    };
  }
  if (normalized.includes("no antenna model was confirmed")) {
    return {
      ...issue,
      title: "Famille d’antenne générique",
      impact: "Aucun modèle d’antenne précis n’a été confirmé; une famille générique a été utilisée.",
      recommended_action: "Sélectionnez un modèle qualifié avant de présenter le résultat comme fidèle à un constructeur."
    };
  }
  if (
    normalized.includes("sector beams and labels") &&
    normalized.includes("controlled product default")
  ) {
    return {
      ...issue,
      title: "Aides visuelles activées",
      impact: "Les faisceaux et labels sont affichés pour faciliter l’inspection; ils ne proviennent pas du cahier de charge.",
      recommended_action: "Conservez-les pour la revue ou désactivez-les dans une prochaine modification."
    };
  }
  if (normalized.includes("sector_count_azimuth_mismatch")) {
    return {
      ...issue,
      title: "Azimuts complétés",
      impact: "Le nombre d’azimuts fourni ne couvrait pas tous les secteurs; le backend a complété la répartition.",
      recommended_action: "Confirmez les azimuts affichés avant utilisation technique."
    };
  }
  if (
    normalized.includes("rag") &&
    (normalized.includes("degrad") || normalized.includes("dégrad"))
  ) {
    return {
      ...issue,
      title: "Recherche documentaire temporairement dégradée",
      impact: "Le classement secondaire des sources n’a pas répondu; l’ordre de recherche initial a été conservé.",
      recommended_action: "Le design reste inspectable; vérifiez les sources publiées dans les livrables."
    };
  }
  if (
    normalized.includes("extraction déterministe") ||
    normalized.includes("deterministic_extraction_requested")
  ) {
    return {
      ...issue,
      title: "Compréhension en mode de secours",
      impact: "La demande a été structurée avec des règles déterministes, sans décision du modèle Groq.",
      recommended_action: "Vérifiez les paramètres compris avant de modifier ou livrer le design."
    };
  }
  if (
    normalized.includes("qa spatiale") ||
    normalized.includes("mesh_level_spatial_basic")
  ) {
    return {
      ...issue,
      title: "Contrôle géométrique borné",
      impact: "Les positions et recouvrements généraux sont contrôlés, mais pas les collisions détaillées entre triangles.",
      recommended_action: "Effectuez une revue technique complémentaire avant validation d’ingénierie."
    };
  }
  return issue;
}

function failureRecoveryMessage(issue: UserIssue | null): string {
  if (!issue) {
    return "Votre demande est conservée. Corrigez-la avant de relancer la conception.";
  }
  const impact = issue.impact.trim();
  const title = issue.title.trim();
  if (impact) {
    return impact;
  }
  if (title) {
    return title;
  }
  return "Votre demande est conservée. Corrigez-la avant de relancer la conception.";
}

function normalizedIssueCopy(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function isAssetIssueText(text: string): boolean {
  const normalized = text.toUpperCase();
  return normalized.includes("ASSET") || normalized.includes("NOT_VENDOR_GRADE") || normalized.includes("ATTRIBUTION_REQUIRED") || normalized.includes("INTERNAL_TEST_MINIMAL") || normalized.includes("CC_BY");
}

function uniqueRequirementWarnings<T extends { code: string; message: string }>(warnings: T[]): T[] {
  const seen = new Set<string>();
  return warnings.filter((warning) => {
    const key = `${warning.code}:${warning.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function humanRequirementWarning(warning: { code: string; message: string }): string {
  const messages: Record<string, string> = {
    DEFAULT_NETWORK_USED: "Technologie proposée: 5G. Confirmez-la si le cahier de charge vise un autre réseau.",
    DEFAULT_TOWER_USED: "Structure proposée: pylône treillis. Confirmez-la si le support attendu est différent.",
    DEFAULT_TOWER_HEIGHT_USED: "Hauteur proposée: 30 m. Cette valeur doit être confirmée avant usage technique.",
    DEFAULT_SECTOR_COUNT_USED: "Configuration proposée: 3 secteurs.",
    DEFAULT_INSTALL_HEIGHT_USED: "La hauteur d’installation des antennes a été proposée faute de valeur explicite.",
    DEFAULT_AZIMUTHS_USED: "Les azimuts ont été répartis automatiquement selon le nombre de secteurs.",
    DEFAULT_MECHANICAL_TILT_USED: "Inclinaison mécanique proposée: 3°. Confirmez-la si une valeur radio est imposée.",
    DEFAULT_ELECTRICAL_TILT_USED: "Inclinaison électrique proposée: 0°. Confirmez-la si une valeur radio est imposée.",
    DEFAULT_BEAMWIDTH_USED: "Ouverture d’antenne proposée: 65°.",
    DEFAULT_CABLES_USED: "Les câbles ont été ajoutés à la scène faute d’instruction contraire.",
    DEFAULT_BEAMS_USED: "La visualisation des faisceaux a été activée.",
    DEFAULT_LABELS_USED: "Les labels techniques ont été activés.",
    LLM_FIELD_REPAIRED: "Des champs LLM manquants ou invalides ont été restaurés depuis l’analyse déterministe. Vérifiez les valeurs affichées.",
    LLM_SOURCE_FIELD_PROTECTED: "Une proposition du LLM contredisait une valeur explicite. Le cahier de charge utilisateur a été conservé."
  };
  if (messages[warning.code]) {
    return messages[warning.code];
  }
  if (warning.code.startsWith("DEFAULT_")) {
    return "Une valeur par défaut a été proposée par le backend. Vérifiez les paramètres affichés avant génération.";
  }
  if (warning.code.startsWith("LLM_")) {
    return "Le système a sécurisé une proposition du LLM. Vérifiez les paramètres affichés avant génération.";
  }
  return warning.message;
}

function humanExtractionFallback(reason: string | null | undefined): string {
  const normalized = (reason ?? "").toLowerCase();
  if (normalized.includes("requested")) {
    return "L’analyse déterministe a été demandée explicitement; vérifiez les hypothèses affichées.";
  }
  if (normalized.includes("timeout")) {
    return "L’analyse intelligente n’a pas répondu à temps; une extraction déterministe vérifiable a été utilisée.";
  }
  if (normalized.includes("unavailable") || normalized.includes("disabled")) {
    return "L’analyse intelligente n’est pas disponible; une extraction déterministe vérifiable a été utilisée.";
  }
  return "L’analyse intelligente n’a pas abouti; une extraction déterministe vérifiable a été utilisée.";
}

function humanExtractionError(error: { code: string; message: string }): string {
  const normalized = `${error.code} ${error.message}`.toLowerCase();
  if (normalized.includes("timeout")) {
    return "Le service d’analyse intelligente n’a pas répondu dans le délai prévu.";
  }
  return "Le service d’analyse intelligente n’a pas pu valider cette extraction.";
}

function humanRequirementField(field: string): string {
  return (
    {
      tower_height_m: "hauteur du pylône",
      sector_count: "nombre de secteurs",
      antenna_install_height_m: "hauteur d’installation des antennes",
      azimuths_deg: "azimuts",
      "sector_count/azimuths_deg": "nombre de secteurs et azimuts"
    }[field] ?? field.replaceAll("_", " ")
  );
}

function humanTowerType(towerType: string): string {
  return {
    lattice_tower: "pylône treillis",
    monopole: "monopôle",
    rooftop_mast: "mât toiture",
    small_cell_pole: "support small cell"
  }[towerType] ?? towerType.replaceAll("_", " ");
}

function humanAdaptationTool(tool: string): string {
  return {
    parametric_rebuild: "reconstruction paramétrique Blender",
    sector_layout: "placement radio contrôlé",
    asset_transform: "transformation d’asset",
    scene_visibility: "composition de scène",
    geometry_program_rebuild: "régénération géométrique LLM contrôlée"
  }[tool] ?? "outil backend déclaré";
}

export function summarizeAdaptationCapabilityGroups(
  capabilities: SceneAdaptationCapabilities | null
): string[] {
  const groups = new Map<
    string,
    { label: string; labels: Set<string>; sectors: Set<number>; tools: Set<string> }
  >();
  for (const capability of capabilities?.capabilities ?? []) {
    const sectorMatch = capability.path.match(/^\/sectors\/(\d+)\//);
    const key = sectorMatch
      ? "sectors"
      : capability.path.startsWith("/geometry_programs/")
        ? "generated"
      : capability.path.startsWith("/tower/")
        ? "tower"
        : capability.path.startsWith("/visual_elements/")
          ? "scene"
          : "other";
    const group =
      groups.get(key) ??
      {
        label:
          key === "sectors"
            ? "Secteurs radio"
            : key === "generated"
              ? "Composants générés"
            : key === "tower"
              ? "Pylône"
              : key === "scene"
                ? "Affichage de la scène"
                : "Autres composants",
        labels: new Set<string>(),
        sectors: new Set<number>(),
        tools: new Set<string>()
      };
    group.labels.add(capability.label);
    group.tools.add(humanAdaptationTool(capability.execution_tool));
    if (sectorMatch) group.sectors.add(Number(sectorMatch[1]) + 1);
    groups.set(key, group);
  }
  return ["scene", "tower", "sectors", "generated", "other"].flatMap((key) => {
    const group = groups.get(key);
    if (!group) return [];
    const sectorScope = group.sectors.size ? ` sur ${group.sectors.size} secteurs` : "";
    return [
      `${group.label} · ${group.labels.size} paramètres${sectorScope}: ${[
        ...group.labels
      ].join(", ")} · ${[...group.tools].join(" / ")}`
    ];
  });
}

function yesNo(value: boolean): string {
  return value ? "oui" : "non";
}

function humanDocumentField(field: string): string {
  const labels: Record<string, string> = {
    "radio.hba_m": "Hauteur des antennes (HBA)",
    "radio.azimuths_deg": "Azimuts des secteurs",
    "radio.sector_count": "Nombre de secteurs",
    "radio.network_type": "Technologie radio",
    "tower.tower_height_m": "Hauteur du pylône",
    "tower.tower_type": "Type de pylône",
    "tower.foundation_type": "Type de fondation"
  };
  return labels[field] ?? field.replaceAll(".", " › ").replaceAll("_", " ");
}

function documentFieldReason(field: DocumentPackField): string {
  if (field.status === "conflict" && field.values.length) {
    return `valeurs contradictoires ${field.values.map(displayDocumentValue).join(" / ")}`;
  }
  if (field.reason) {
    return field.reason;
  }
  return field.severity === "blocking" ? "valeur obligatoire absente" : "valeur à confirmer";
}

function displayDocumentValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(", ");
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "valeur non lisible";
}

function summaryHeadline(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "Aucun design chargé";
  }
  if (bundle.status === "failed") {
    return "Conception non produite";
  }
  if (bundle.generation_mode !== "real_blender") {
    return "Résultat dégradé";
  }
  if (bundle.mesh_qa_passed === false) {
    return "Design généré avec attention QA";
  }
  if (bundle.status === "completed") {
    return "Design prêt à inspecter";
  }
  return "Design en cours";
}

function nextUserAction(bundle: ViewerBundle | null, issueCount: number): string {
  if (!bundle) {
    return "Décrivez un site telecom ou chargez un ZIP documentaire.";
  }
  if (bundle.status === "failed") {
    return "Lire les alertes, corriger la demande, puis relancer.";
  }
  if (bundle.generation_mode !== "real_blender") {
    return "Utiliser la preview seulement comme fallback; corriger Blender avant validation.";
  }
  if (bundle.mesh_qa_passed === false) {
    return "Inspecter la QA et les alertes avant de considérer le GLB exploitable.";
  }
  if (issueCount > 0) {
    return "Inspecter le modèle 3D, puis lire les limites regroupées dans les alertes.";
  }
  return "Inspecter le GLB et télécharger les artefacts nécessaires.";
}

function summarySignals(bundle: ViewerBundle | null, issueCount: number): string[] {
  if (!bundle) {
    return [];
  }
  const failed = bundle.status === "failed";
  const signals = [
    `Modèle 3D : ${failed ? "non produit" : bundle.primary_glb_url ? "disponible" : "manquant"}`,
    `Aperçu : ${failed ? "non produit" : bundle.preview_url ? "disponible" : "manquant"}`,
    `Niveau de contrôle : ${meshQaLevelLabel(bundle.mesh_qa_level)}`,
    `Points à examiner : ${issueCount}`
  ];
  if (bundle.llm_fallback_used) {
    signals.push("La compréhension de la demande a utilisé un mode de secours contrôlé.");
  }
  if (bundle.rag_reranker_degraded_reason) {
    signals.push("Le classement secondaire des sources documentaires a fonctionné en mode de secours.");
  }
  return signals;
}

function analysisProviderLabel(provider?: string | null, extractionProvider?: string | null): string {
  const normalized = `${provider ?? ""} ${extractionProvider ?? ""}`.toLowerCase();
  if (normalized.includes("groq") || normalized.includes("gpt")) return "intelligence décisionnelle";
  if (normalized.includes("fallback") || normalized.includes("determin")) return "mode de secours contrôlé";
  return "analyse structurée";
}

function workflowStatusLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    completed: "terminée",
    failed: "échouée",
    running: "en cours",
    pending: "en attente"
  };
  return status ? labels[status] ?? "état disponible" : "pas lancée";
}

export function meshQaLevelLabel(level: string | null | undefined): string {
  const labels: Record<string, string> = {
    mesh_level_spatial_basic: "QA spatiale AABB",
    mesh_level_transform_basic: "Transforms 3D contrôlées",
    mesh_level_basic: "Géométrie de base",
    metadata_only: "Métadonnées seulement",
    not_available: "Non disponible"
  };
  return level ? (labels[level] ?? "Niveau non reconnu") : "Non disponible";
}

function completionCertificateLabel(status: string | null | undefined): string {
  if (status === "issued") {
    return "vérifiée localement";
  }
  if (status === "rejected") {
    return "rejeté";
  }
  return "absent";
}

function summarizeRagEvidence(evidence: unknown) {
  const record = asRecord(evidence);
  const contexts = Array.isArray(record?.["contexts"]) ? record["contexts"] : [];
  const sources = contexts.slice(0, 6).map((context) => {
    const source = asRecord(context);
    const title = readString(source?.["filename"]) ?? readString(source?.["source_path"]) ?? "source";
    const score = typeof source?.["score"] === "number" ? `score ${source["score"].toFixed(2)}` : "score n/a";
    return {
      title,
      reason: readString(source?.["reason"]) ?? "Contexte récupéré.",
      score
    };
  });
  return {
    ragUsedForExtraction: record?.["rag_used_for_extraction"] === true,
    ragUsedForPlanning: record?.["rag_used_for_planning"] === true,
    candidateHints: readStringArray(record?.["candidate_hint_fields"]),
    appliedHints: readStringArray(record?.["applied_hint_fields"]),
    limitations: readStringArray(record?.["limitations"]),
    sources
  };
}

export function humanRagLimitation(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (
    normalized.includes("evidence and controlled planning context") ||
    normalized.includes("not a free-form planner")
  ) {
    return "Le RAG fournit des preuves et un contexte de planification contrôlé; il ne planifie jamais librement la géométrie.";
  }
  if (
    normalized.includes("does not participate in requirementspec extraction") ||
    normalized.includes("not used for requirementspec extraction")
  ) {
    return "Le RAG ne participe pas à l’extraction du RequirementSpec dans cette version.";
  }
  if (
    normalized.includes("whitelisted") &&
    normalized.includes("planning_hints")
  ) {
    return "Seuls les indices de planification explicitement autorisés peuvent influencer le SceneSpec.";
  }
  if (normalized.includes("reranker") && normalized.includes("unavailable")) {
    return "Le reranker NVIDIA est indisponible; l’ordre vectoriel est conservé et le mode dégradé reste signalé.";
  }
  if (/^(le|la|les|un|une|seul|seuls|aucun|aucune)\b/i.test(value.trim())) {
    return value.trim();
  }
  return "Une limitation RAG supplémentaire est déclarée par le backend; son détail technique reste disponible dans les livrables.";
}

function StatusPill({
  label,
  tone = "muted",
  value
}: {
  label: string;
  tone?: "ok" | "warn" | "danger" | "muted";
  value: string;
}) {
  return (
    <span className={`status-pill ${tone}`}>
      <small>{label}</small>
      {value}
    </span>
  );
}

function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "unknown";
}

function formatRatio(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)} %` : "non publié";
}

function formatMeasurement(value: number): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 }).format(value);
}

function assemblyConstraintStatusLabel(status: "passed" | "failed" | "not_available"): string {
  return {
    passed: "contrôle passé",
    failed: "écart détecté",
    not_available: "mesure indisponible"
  }[status];
}

function assemblyMeasurementScopeLabel(scope: string): string {
  if (scope === "exported_glb_anchor_frames") {
    return "les repères d’ancrage du GLB exporté";
  }
  return scope.replaceAll("_", " ");
}

function assemblyLimitationLabel(limitation: string): string {
  return {
    "Required non-mechanical connections are reported but are not geometrically evaluated by AssemblyConstraintEvidence v1.":
      "Les connexions requises non mécaniques sont signalées, mais ne sont pas encore mesurées géométriquement.",
    "Anchor frames are semantic coordinate frames reconstructed from exported glTF component roots or dedicated constraint-marker nodes; they are not contact mesh.":
      "Les repères sont reconstruits depuis le GLB exporté ; ils ne prouvent pas à eux seuls le contact physique des surfaces.",
    "Collision, physical contact, fastener engagement, deformation, load capacity and electrical or routing continuity are not evaluated.":
      "Les collisions fines, le contact, la visserie, la déformation, la tenue aux charges et la continuité électrique ou de routage ne sont pas évalués."
  }[limitation] ?? limitation;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function truth(value: boolean): string {
  return value ? "oui" : "non";
}

function qaTruth(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "en attente";
  }
  return bundle.mesh_qa_passed ? "validée" : "à examiner";
}

function generationTruth(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "aucun";
  }
  if (bundle.generation_mode === "real_blender") {
    return "Blender réel";
  }
  return bundle.generation_mode ?? "unknown";
}

function phaseLabel(phase: WorkflowPhase): string {
  return {
    idle: "prêt",
    drafting: "rédaction",
    submitting: "envoi",
    streaming: "streaming",
    running: "en cours",
    completed: "terminé",
    failed: "échec",
    degraded: "dégradé"
  }[phase];
}

function stageStatusLabel(status: string): string {
  if (status === "completed_with_warning") {
    return "terminé avec alerte";
  }
  if (status.includes("completed") || status === "passed" || status === "generated") {
    return "terminé";
  }
  if (status.includes("running")) {
    return "en cours";
  }
  if (status.includes("failed") || status === "error") {
    return "échec";
  }
  if (status === "not_reported") {
    return "non reporté";
  }
  if (status === "waiting" || status === "pending") {
    return "en attente";
  }
  return status;
}

function humanPhase(phase: string | null | undefined): string {
  if (!phase) {
    return "orchestration";
  }
  return {
    workflow: "orchestration",
    quality_gate: "contrôle final",
    memory: "mémoire",
    viewer: "visualisation 3D",
    issues: "alertes",
    qa: "qualité"
  }[phase] ?? phase.replaceAll("_", " ");
}

function humanTimelineMessage(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("certification des preuves")) {
    return message.replace("Certification des preuves", "Vérification des preuves");
  }
  const mechanicalTilt = message.match(/mechanical tilt inferred as ([\d.]+) degrees?/i);
  if (mechanicalTilt) {
    return `Inclinaison mécanique proposée à ${mechanicalTilt[1]}°. Vérifiez-la dans les alertes.`;
  }
  const electricalTilt = message.match(/electrical tilt inferred as ([\d.]+) degrees?/i);
  if (electricalTilt) {
    return `Inclinaison électrique proposée à ${electricalTilt[1]}°. Vérifiez-la dans les alertes.`;
  }
  const beamwidth = message.match(/beamwidth inferred as ([\d.]+) degrees?/i);
  if (beamwidth) {
    return `Ouverture d’antenne proposée à ${beamwidth[1]}°. Vérifiez-la dans les alertes.`;
  }
  if (normalized.includes("sector_count_azimuth_mismatch")) {
    return "Les azimuts ont été complétés pour correspondre au nombre de secteurs demandé.";
  }
  if (normalized.includes("platforms recommended")) {
    return "Une plateforme est recommandée pour la sécurité sur ce pylône.";
  }
  return message.replaceAll("Warnings", "les alertes");
}

function artifactLabel(name: string): string {
  const labels: Record<string, string> = {
    "design.glb": "Modèle 3D GLB",
    "preview.png": "Vue d’ensemble",
    "preview_front.png": "Vue de face",
    "preview_side.png": "Vue latérale",
    "preview_top.png": "Vue de dessus",
    "preview_closeup.png": "Gros plan principal",
    "scene_metadata.json": "Métadonnées de la scène",
    "requirements_spec.json": "Exigences consolidées",
    "extraction_report.json": "Rapport de compréhension",
    "scene_spec.json": "Plan de scène vérifiable",
    "qa_report.json": "Rapport QA",
    "generation_report.json": "Rapport génération",
    "rag_evidence.json": "Preuves du contexte IA",
    "planning_decision.json": "Décisions de planification",
    "geometry_validation.json": "Validation géométrie",
    "component_proofs.json": "Preuves des composants assemblés",
    "requirement_coverage.json": "Couverture des exigences",
    "completion_certificate.json": "Preuve locale de complétion",
    "technical_report.md": "Rapport technique"
  };
  return labels[name] ?? name;
}

function artifactKindLabel(contentType: string): string {
  if (contentType === "model/gltf-binary") return "Modèle 3D";
  if (contentType.startsWith("image/")) return "Image de contrôle";
  if (contentType === "text/markdown") return "Rapport lisible";
  if (contentType === "application/json") return "Données vérifiables";
  return "Livrable";
}
