import { AlertTriangle, FileArchive, Loader2, Paperclip, RadioTower, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  DocumentPackCapabilities,
  DocumentPackSummary,
  MultimodalConsent,
  MultimodalIntelligence,
  ParseRequirementsResponse,
  PublicVersionInfo,
  RequirementSpec,
  UserIssue
} from "../api/schemas";
import type { WorkflowPhase } from "../state/workflowMachine";
import { ConversationTray } from "./ConversationTray";
import { ConversationHistory, RequirementsUnderstanding } from "./StudioConversationContext";
import { DocumentPackIntake, MultimodalConsentControl } from "./StudioDocumentIntake";
import { ResourceRecovery } from "./StudioPrimitives";
import { failureRecoveryMessage, humanizeUserIssue } from "./StudioWorkflowDisplay";

export function ChatCommandPanel({
  conversation,
  activity,
  onFreeDesign,
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
  revisionPrompt,
  revisionBusy,
  editMessage,
  versions,
  documentCapabilities = null,
  documentCapabilitiesError,
  documentCapabilitiesLoading,
  documentPackSummary,
  documentPackMessage,
  documentPackBusy,
  multimodalConsent = "disabled",
  multimodalIntelligence = null,
  onAnalyze,
  onConfirm,
  onDocumentPackDetach,
  onDocumentPackRetry,
  onDocumentPackUpload,
  onDocumentCapabilitiesRetry,
  onMultimodalConsentChange,
  onPromptChange,
  onRevisionPromptChange,
  onRevisionSubmit,
  onRetryBootstrap,
  onNewChat
}: {
  onNewChat?: (draft?: string) => void;
  conversation?: ReactNode;
  activity?: ReactNode;
  onFreeDesign?: () => void;
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
  revisionPrompt: string;
  revisionBusy: boolean;
  editMessage: string | null;
  versions?: PublicVersionInfo[];
  documentCapabilities: DocumentPackCapabilities | null;
  documentCapabilitiesError?: string | null;
  documentCapabilitiesLoading?: boolean;
  documentPackSummary: DocumentPackSummary | null;
  documentPackMessage: string | null;
  documentPackBusy: boolean;
  multimodalConsent?: MultimodalConsent;
  multimodalIntelligence?: MultimodalIntelligence | null;
  onAnalyze: () => void;
  onConfirm: () => void;
  onDocumentPackDetach?: () => Promise<void>;
  onDocumentPackRetry?: () => void;
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
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [conversationOpen, setConversationOpen] = useState(false);
  const previousCanEdit = useRef(canEdit);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const attachmentButtonRef = useRef<HTMLButtonElement | null>(null);
  const attachmentCloseRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!canEdit && commandMode === "revision") {
      setCommandMode("new");
    }
    if (canEdit && !previousCanEdit.current) {
      setCommandMode("revision");
    }
    previousCanEdit.current = canEdit;
  }, [canEdit, commandMode]);
  useEffect(() => {
    if (!attachmentsOpen) return;
    attachmentCloseRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setAttachmentsOpen(false);
      window.requestAnimationFrame(() => attachmentButtonRef.current?.focus());
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [attachmentsOpen]);

  const revisionMode = commandMode === "revision" && canEdit;
  useEffect(() => {
    if (revisionMode) {
      setAttachmentsOpen(false);
      setConversationOpen(false);
    }
  }, [revisionMode]);
  const composerValue = revisionMode ? revisionPrompt : prompt;
  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(Math.max(composer.scrollHeight, 58), 150)}px`;
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
        ? "La demande confirmée est en cours d’assemblage. Le résultat ne sera annoncé qu’après construction et vérification du modèle 3D."
      : phase === "completed"
        ? "Inspectez le modèle, demandez une modification ou démarrez un nouveau site."
        : phase === "failed"
          ? "Les artefacts non vérifiés restent indisponibles. Corrigez la demande ou relancez une génération vérifiée."
          : "Décrivez le site ou l’objet à concevoir. Les contraintes comprises sont confirmées avant toute construction du modèle 3D.";
  const failedIssue = phase === "failed" && failureIssue
    ? humanizeUserIssue(failureIssue)
    : null;
  const submitCurrentCommand = () => {
    if (phase === "failed" && onNewChat) {
      onNewChat(prompt);
      return;
    }
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

      <ConversationTray
        activity={activity}
        attention={analysisError || error || bootstrapError || editMessage || (phase === "failed" ? phase : null) || (analysis && !analysisSubmitted && !revisionMode ? analysis : null)}
        onOpenChange={(next) => {
          setConversationOpen(next);
          if (next) setAttachmentsOpen(false);
        }}
        open={conversationOpen}
      >

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
            {!onNewChat ? (
              <div className="workflow-recovery-actions">
                <button
                  className="secondary-action"
                  onClick={() => composerRef.current?.focus()}
                  type="button"
                >
                  Corriger la demande
                </button>
              </div>
            ) : null}
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
        {analysisError ? (
          <p className="inline-alert">
            <AlertTriangle size={16} aria-hidden="true" /> {analysisError}
            {onFreeDesign && !revisionMode ? (
              <button className="inline-alert-action" disabled={disabled || analysisBusy} onClick={onFreeDesign} type="button">
                Concevoir sans confirmation télécom
              </button>
            ) : null}
          </p>
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
      </ConversationTray>

      <div className="command-dock">
        {canEdit && !onNewChat ? (
          <div className="command-mode" role="group" aria-label="Type de commande">
            <button className={!revisionMode ? "active" : ""} disabled={disabled || revisionBusy} onClick={() => setCommandMode("new")} type="button">Nouveau design</button>
            <button className={revisionMode ? "active" : ""} disabled={disabled || revisionBusy} onClick={() => setCommandMode("revision")} type="button">Modifier le design</button>
          </div>
        ) : null}

        {!revisionMode ? (
          <section
            aria-label="Pièces jointes et cahier de charge"
            className="attachment-popover"
            hidden={!attachmentsOpen}
            id="studio-attachment-popover"
          >
            <div className="attachment-popover-header">
              <strong>Pièces jointes</strong>
              <button
                aria-label="Fermer les pièces jointes"
                onClick={() => {
                  setAttachmentsOpen(false);
                  attachmentButtonRef.current?.focus();
                }}
                ref={attachmentCloseRef}
                type="button"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <DocumentPackIntake
              busy={documentPackBusy}
              capabilities={documentCapabilities}
              capabilitiesError={documentCapabilitiesError}
              capabilitiesLoading={documentCapabilitiesLoading}
              message={documentPackMessage}
              onCapabilitiesRetry={onDocumentCapabilitiesRetry}
              onRetry={onDocumentPackRetry}
              onUpload={onDocumentPackUpload}
              summary={documentPackSummary}
            />
            <MultimodalConsentControl
              capability={multimodalIntelligence}
              consent={multimodalConsent}
              disabled={disabled || documentPackBusy}
              onChange={onMultimodalConsentChange}
            />
          </section>
        ) : null}
        {!revisionMode && documentPackSummary ? (
          <div className="composer-attachment-strip" aria-label="Pièces jointes à la conversation">
            <div className="composer-attachment-chip">
              <FileArchive size={16} aria-hidden="true" />
              <span>
                <strong>
                  {documentPackSummary.document_count} {documentPackSummary.document_count === 1 ? "pièce jointe" : "pièces jointes"}
                </strong>
                <small>Contexte de la prochaine demande</small>
              </span>
              {onDocumentPackDetach ? (
                <button
                  aria-label="Retirer les pièces jointes de cette conversation"
                  disabled={documentPackBusy}
                  onClick={() => void onDocumentPackDetach()}
                  title="Retirer les pièces jointes"
                  type="button"
                >
                  <X size={14} aria-hidden="true" />
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
        <div className="command-composer">
          {!revisionMode ? (
            <button
              aria-controls="studio-attachment-popover"
              aria-expanded={attachmentsOpen}
              aria-label="Ajouter des pièces jointes"
              className="composer-attachment"
              disabled={disabled || documentPackBusy}
              onClick={() => {
                setConversationOpen(false);
                setAttachmentsOpen((value) => !value);
              }}
              ref={attachmentButtonRef}
              title="Ajouter des PDF, images, plans, tableaux ou ZIP"
              type="button"
            >
              <Paperclip size={18} aria-hidden="true" />
            </button>
          ) : null}
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
            aria-label={
              phase === "failed" && onNewChat
                ? "Reprendre dans une nouvelle conversation"
                : revisionMode
                  ? "Appliquer la révision"
                  : "Analyser la demande"
            }
            className="composer-submit"
            disabled={disabled || (revisionMode ? revisionBusy || !revisionPrompt.trim() : analysisBusy || !prompt.trim())}
            onClick={submitCurrentCommand}
            title={
              phase === "failed" && onNewChat
                ? "Conserver cette demande dans une nouvelle conversation"
                : revisionMode
                  ? "Appliquer la modification"
                  : "Analyser les contraintes"
            }
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
            : analysisBusy ? "Analyse de la demande en cours…" : analysis ? "Modifiez le texte puis réanalysez si nécessaire." : "⌘ Entrée pour analyser · les paramètres seront confirmés avant génération."}
        </p>
      </div>
    </section>
  );
}


