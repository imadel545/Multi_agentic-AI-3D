import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cpu,
  FileArchive,
  FileUp,
  Layers3,
  MessageSquareText,
  RadioTower,
  RotateCcw,
  Send,
  ShieldAlert,
  Sparkles,
  WifiOff,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import type {
  AssetInventory,
  CurrentOperation,
  DocumentPackCapabilities,
  DocumentPackField,
  DocumentPackReview,
  DocumentPackSummary,
  Health,
  ParseRequirementsResponse,
  PublicVersionInfo,
  StudioSummary,
  TimelineSummary,
  UserIssue,
  UserIssues,
  ViewerBundle
} from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import type { RuntimeMode, WorkflowPhase } from "../state/workflowMachine";
import { actionIsSupported } from "../state/workflowMachine";

export function BackendStatusBar({
  health,
  phase,
  bundle,
  issues
}: {
  health: Health | null;
  phase: WorkflowPhase;
  bundle: ViewerBundle | null;
  issues: UserIssues | null;
}) {
  const issueCount = issues?.human_readable_issues.length ?? bundle?.human_warnings_count ?? 0;
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <RadioTower size={22} aria-hidden="true" />
        <div>
          <strong>Agentic Telecom Studio</strong>
          <span>Studio IA 3D telecom local-first</span>
        </div>
      </div>
      <div className="topbar-status" aria-label="Studio runtime status">
        <span className={health?.status === "ok" ? "runtime-presence ok" : "runtime-presence warn"}>
          <span aria-hidden="true" />
          {health?.status === "ok" ? "Backend local connecté" : "Backend indisponible"}
        </span>
        {phase !== "idle" ? (
          <span className="workflow-truth">
            {phaseLabel(phase)} · {generationTruth(bundle)} · {qaTruth(bundle)}
          </span>
        ) : null}
        {issueCount ? (
          <span className="topbar-issue-count">
            <AlertTriangle size={14} aria-hidden="true" /> {issueCount} point(s) à vérifier
          </span>
        ) : null}
      </div>
    </header>
  );
}

export function ChatCommandPanel({
  analysis,
  analysisBusy,
  analysisError,
  analysisSubmitted,
  prompt,
  submissionPending,
  phase,
  error,
  canEdit,
  correctionBusy,
  revisionPrompt,
  revisionBusy,
  editMessage,
  documentCapabilities,
  documentPackReview,
  documentPackSummary,
  documentPackMessage,
  documentPackBusy,
  onAnalyze,
  onConfirm,
  onDocumentPackCorrection,
  onDocumentPackGenerate,
  onDocumentPackUpload,
  onPromptChange,
  onRevisionPromptChange,
  onRevisionSubmit
}: {
  analysis: ParseRequirementsResponse | null;
  analysisBusy: boolean;
  analysisError: string | null;
  analysisSubmitted: boolean;
  prompt: string;
  submissionPending: boolean;
  phase: WorkflowPhase;
  error: string | null;
  canEdit: boolean;
  correctionBusy: boolean;
  revisionPrompt: string;
  revisionBusy: boolean;
  editMessage: string | null;
  documentCapabilities: DocumentPackCapabilities | null;
  documentPackReview: DocumentPackReview | null;
  documentPackSummary: DocumentPackSummary | null;
  documentPackMessage: string | null;
  documentPackBusy: boolean;
  onAnalyze: () => void;
  onConfirm: () => void;
  onDocumentPackCorrection: (field: string, value: string, reason: string) => void;
  onDocumentPackGenerate: () => void;
  onDocumentPackUpload: (file: File) => void;
  onPromptChange: (value: string) => void;
  onRevisionPromptChange: (value: string) => void;
  onRevisionSubmit: () => void;
}) {
  const disabled =
    submissionPending || phase === "submitting" || phase === "streaming" || phase === "running";
  const examplePrompt =
    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, boîte alimentation, dalle béton, GPS, labels, couleurs professionnelles et export GLB.";
  return (
    <section className="command-center" aria-label="Conversation de commande">
      <div className="conversation-heading">
        <span className="eyebrow">Commande intelligente</span>
        <h1>Décris le site telecom</h1>
        <p>
          Le backend extrait le cahier de charge, construit un SceneSpec vérifiable,
          puis génère un GLB Blender réel.
        </p>
      </div>

      <textarea
        aria-label="Design prompt"
        placeholder="Ex: pylône treillis 30m, 3 secteurs à 24m, azimuts 0/120/240, RRU, câbles, GPS, dalle béton, labels..."
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        rows={4}
      />

      <div className="command-actions">
        <button className="ghost-action" disabled={disabled} onClick={() => onPromptChange(examplePrompt)} type="button">
          Exemple complet
        </button>
        <button className={analysis ? "secondary-action" : "primary-action"} disabled={disabled || analysisBusy || !prompt.trim()} onClick={onAnalyze} type="button">
          <Sparkles size={18} aria-hidden="true" />
          {analysisBusy ? "Analyse backend..." : analysis ? "Réanalyser" : "Analyser la demande"}
        </button>
      </div>

      {analysis ? (
        <RequirementsUnderstanding
          analysis={analysis}
          failedWorkflow={phase === "failed"}
          onConfirm={onConfirm}
          submitted={analysisSubmitted}
          submitting={disabled}
        />
      ) : (
        <div className="assistant-card">
          <MessageSquareText size={18} aria-hidden="true" />
          <div>
            <strong>Première étape: comprendre</strong>
            <p>L’assistant appelle le vrai extracteur backend avant toute génération Blender.</p>
          </div>
        </div>
      )}
      {analysisError ? <p className="inline-alert"><AlertTriangle size={16} aria-hidden="true" /> {analysisError}</p> : null}

      <DocumentPackIntake
        busy={documentPackBusy}
        capabilities={documentCapabilities}
        correctionBusy={correctionBusy}
        message={documentPackMessage}
        onCorrect={onDocumentPackCorrection}
        onGenerate={onDocumentPackGenerate}
        onUpload={onDocumentPackUpload}
        review={documentPackReview}
        summary={documentPackSummary}
      />

      {canEdit ? (
        <div className="revision-box">
          <span className="eyebrow">Modifier le design actif</span>
          <textarea
            aria-label="Revision prompt"
            onChange={(event) => onRevisionPromptChange(event.target.value)}
            placeholder="Ex: augmente la hauteur à 35m, ajoute une plateforme, corrige les labels..."
            rows={4}
            value={revisionPrompt}
          />
          <button className="secondary-action" disabled={disabled || revisionBusy || !revisionPrompt.trim()} onClick={onRevisionSubmit} type="button">
            {revisionBusy ? "Révision et validation..." : "Appliquer la révision"}
          </button>
          {editMessage ? <p className="muted">{editMessage}</p> : null}
        </div>
      ) : null}

      {error ? (
        <p className="inline-alert">
          <AlertTriangle size={16} aria-hidden="true" /> {error}
        </p>
      ) : null}
    </section>
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
        <p>L’extracteur backend n’a pas produit de RequirementSpec valide.</p>
      </div>
    );
  }
  const warnings = uniqueRequirementWarnings([...analysis.warnings, ...requirements.warnings]);
  const confirmationLocked = submitted && !failedWorkflow;
  return (
    <div className="understanding-card" aria-label="Compréhension backend">
      <span className="eyebrow">
        {confirmationLocked
          ? "Compréhension utilisée pour le design"
          : failedWorkflow && submitted
            ? "Compréhension du workflow échoué"
            : "Compréhension backend à confirmer"}
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
      <small>
        Extracteur: {analysis.provider ?? "inconnu"} · mode {analysis.extraction_provider ?? "inconnu"}
      </small>
      {analysis.fallback_used ? (
        <p className="inline-alert">
          <AlertTriangle size={15} aria-hidden="true" /> Fallback utilisé: {analysis.llm_fallback_reason ?? "raison non fournie"}
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
          items={analysis.errors.map((item) => item.message)}
          empty="Aucun incident."
        />
      ) : null}
      {confirmationLocked ? (
        <p className="confirmation-complete" role="status">
          <CheckCircle2 size={16} aria-hidden="true" /> Cette compréhension a déjà lancé le design affiché.
        </p>
      ) : (
        <button
          className="primary-action"
          disabled={submitting}
          onClick={onConfirm}
          type="button"
        >
          <Send size={18} aria-hidden="true" />
          {failedWorkflow && submitted ? "Relancer avec cette demande" : "Confirmer et générer"}
        </button>
      )}
    </div>
  );
}

function DocumentPackIntake({
  busy,
  capabilities,
  correctionBusy,
  message,
  onCorrect,
  onGenerate,
  onUpload,
  review,
  summary
}: {
  busy: boolean;
  capabilities: DocumentPackCapabilities | null;
  correctionBusy: boolean;
  message: string | null;
  onCorrect: (field: string, value: string, reason: string) => void;
  onGenerate: () => void;
  onUpload: (file: File) => void;
  review: DocumentPackReview | null;
  summary: DocumentPackSummary | null;
}) {
  const accept = ".zip,application/zip,application/x-zip-compressed";
  const canGenerate = summary?.can_generate_design === true;
  const [expanded, setExpanded] = useState(Boolean(summary || review || message));
  useEffect(() => {
    if (summary || review || message) {
      setExpanded(true);
    }
  }, [message, review, summary]);
  return (
    <details
      className="document-intake"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
      open={expanded}
    >
      <summary>
        <FileArchive size={17} aria-hidden="true" />
        <span>Cahier de charge documentaire</span>
        {summary ? <small>{summary.document_count} pièce(s)</small> : null}
      </summary>
      <div className="document-intake-body">
        <div>
        <span className="eyebrow">Cahier de charge</span>
        <strong>ZIP documentaire</strong>
        <p>
          {capabilities?.document_pack_status === "limited"
            ? "Regroupez PDF, images, DXF et autres pièces dans un seul ZIP. Le backend local trie les pièces utiles avant de construire le design."
            : "Capacités documentaires en cours de chargement."}
        </p>
        </div>
        <label className="file-drop">
        <FileUp size={17} aria-hidden="true" />
        <span>{busy ? "Traitement..." : "Charger un ZIP"}</span>
        <input
          accept={accept}
          aria-label="Cahier de charge"
          disabled={busy}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) {
              onUpload(file);
            }
          }}
          type="file"
        />
        </label>
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
          busy={correctionBusy}
          onCorrect={onCorrect}
          review={review}
        />
        ) : null}
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </details>
  );
}

function DocumentPackReviewPanel({
  busy,
  onCorrect,
  review
}: {
  busy: boolean;
  onCorrect: (field: string, value: string, reason: string) => void;
  review: DocumentPackReview;
}) {
  const correctionFields = [...review.conflicts, ...review.missingFields].filter(
    (field, index, items) => items.findIndex((candidate) => candidate.field === field.field) === index
  );
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const selectedField = field || correctionFields[0]?.field || "";
  const failedChecks = review.qa.checks.filter((check) => !check.passed);
  const usedDocuments = review.documents.filter((document) => document.used_for_design);
  const ignoredDocuments = review.documents.filter((document) => !document.used_for_design);
  const failedDocuments = review.documents.filter((document) =>
    ["failed", "unavailable", "unsupported"].includes(document.extraction_status)
  );
  const criticalEvidence = Object.entries(review.provenance)
    .filter(([name]) => isCriticalDocumentField(name))
    .flatMap(([name, sources]) => sources.map((source) => ({ name, source })))
    .sort((left, right) => (right.source.confidence ?? 0) - (left.source.confidence ?? 0))
    .slice(0, 12);
  const processingWarnings = Array.from(
    new Set([
      ...review.processing.warnings,
      ...review.documents.flatMap((document) => document.processing_warnings)
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
      <strong>{review.qa.ready_to_generate ? "Cahier de charge prêt" : "Revue nécessaire"}</strong>
      <small>Confiance {formatScore(review.qa.ready_confidence)} · {review.conflicts.length} conflit(s) · {review.missingFields.length} champ(s) manquant(s)</small>
      <div className="document-triage-summary" aria-label="Tri documentaire">
        <span><strong>{usedDocuments.length}</strong> utile(s)</span>
        <span><strong>{ignoredDocuments.length}</strong> écarté(s)</span>
        <span><strong>{failedDocuments.length}</strong> non lu(s)</span>
      </div>
      <div className="document-intelligence-summary">
        <strong>Compréhension utilisée pour le design</strong>
        <small>
          {review.consolidatedSpec.source_mode === "groq" || review.consolidatedSpec.source_mode === "mixed"
            ? `Extraction structurée ${review.consolidatedSpec.llm_provider ?? "LLM"}${review.consolidatedSpec.llm_fallback_used ? " avec repli signalé" : " validée"}.`
            : "Extraction déterministe; aucun raisonnement LLM n’est revendiqué."}
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
      {correctionFields.length ? (
        <form className="revision-box" onSubmit={submitCorrection}>
          <label>
            Champ
            <select aria-label="Champ documentaire à corriger" onChange={(event) => setField(event.target.value)} value={selectedField}>
              {correctionFields.map((item) => (
                <option key={item.field} value={item.field}>{humanDocumentField(item.field)}</option>
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
        items={review.qa.recommended_user_actions}
        empty="Aucune action documentaire supplémentaire."
      />
    </div>
  );
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
  return (
    <section className="operation-strip" aria-label="Opération courante">
      <Clock3 size={18} aria-hidden="true" />
      <div>
        <strong>{operation?.human_label ?? operation?.current_operation ?? (running ? "Workflow en cours" : "Studio prêt")}</strong>
        <span>{operation?.progress_message ?? "Les étapes backend apparaissent ici pendant la génération."}</span>
        {notice ? <small className="operation-notice" aria-live="polite">{notice}</small> : null}
      </div>
      <StatusPill label={pollingFallback ? "Fallback polling" : "Runtime"} value={phaseLabel(phase)} tone={pollingFallback ? "warn" : "muted"} />
    </section>
  );
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
  const rawRows =
    timeline?.timeline_steps.map((step, index) => ({
      id: `${step.step}-${step.timestamp ?? step.duration_ms ?? index}-${index}`,
      label: step.human_label ?? step.label ?? step.human_readable,
      message: step.progress_message ?? step.human_readable,
      status: step.status,
      phase: step.phase
    })) ??
    events.map((event) => ({
      id: event.event_id,
      label: event.human_label,
      message: event.progress_message,
      status: event.status ?? event.event_type,
      phase: event.phase
    }));
  const rows = summarizeTimelineRows(rawRows);

  return (
    <section className="drawer-section" aria-label="Timeline agents">
      <PanelTitle icon={<Sparkles size={17} />} title="Narration du workflow" />
      <div className="timeline-list">
        {rows.length ? (
          rows.slice(-14).map((row) => (
            <article className="timeline-item" key={row.id}>
              <span className={`timeline-dot ${row.status}`} />
              <div>
                <strong>{row.label}</strong>
                <p>{row.message}</p>
                <small>{humanPhase(row.phase)} · {stageStatusLabel(row.status)}</small>
              </div>
            </article>
          ))
        ) : (
          <p className="muted">Les agents apparaîtront au démarrage du workflow backend.</p>
        )}
      </div>
    </section>
  );
}

type DrawerId = "summary" | "agents" | "qa" | "issues" | "artifacts" | "rag" | "runtime" | "versions";
type DrawerDefinition = { id: DrawerId; label: string; badge?: string; icon: ReactNode };

export function InspectorDock({
  bundle,
  canRollback,
  documentCapabilities,
  events,
  evidence,
  inventory,
  issues,
  summary,
  timeline,
  toAbsoluteUrl,
  onRollbackVersion,
  rollbackBusyVersionId,
  versionMessage,
  versions
}: {
  bundle: ViewerBundle | null;
  canRollback: boolean;
  documentCapabilities: DocumentPackCapabilities | null;
  events: NormalizedWorkflowEvent[];
  evidence: unknown | null;
  inventory: AssetInventory | null;
  issues: UserIssues | null;
  summary: StudioSummary | null;
  timeline: TimelineSummary | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  onRollbackVersion: (versionId: string) => void;
  rollbackBusyVersionId: string | null;
  versionMessage: string | null;
  versions: PublicVersionInfo[];
}) {
  const [activeDrawer, setActiveDrawer] = useState<DrawerId | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const lastTriggerRef = useRef<HTMLButtonElement | null>(null);
  const issueCount = issues?.human_readable_issues.length ?? bundle?.human_warnings_count ?? 0;
  const drawers: DrawerDefinition[] = [];
  if (bundle) drawers.push({ id: "summary", label: "Résumé", icon: <CheckCircle2 size={16} /> });
  if (events.length || timeline) drawers.push({ id: "agents", label: "Progression", icon: <Sparkles size={16} /> });
  if (bundle) drawers.push({ id: "qa", label: "QA", badge: qaTruth(bundle), icon: <ShieldAlert size={16} /> });
  if (issueCount) drawers.push({ id: "issues", label: "Warnings", badge: String(issueCount), icon: <AlertTriangle size={16} /> });
  if (bundle?.viewer_artifacts.length) drawers.push({ id: "artifacts", label: "Artefacts", badge: String(bundle.viewer_artifacts.length), icon: <FileArchive size={16} /> });
  if (evidence || bundle?.rag_context_count) drawers.push({ id: "rag", label: "Contexte IA", badge: bundle?.rag_reranker_degraded_reason ? "dégradé" : undefined, icon: <Cpu size={16} /> });
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
        <div className="context-drawer" id="studio-context-drawer" role="region" aria-label={`Détails ${activeDrawer}`}>
          <button aria-label="Fermer les détails" className="drawer-close" onClick={closeDrawer} ref={closeButtonRef} title="Fermer" type="button">
            <X size={16} aria-hidden="true" />
          </button>
          {activeDrawer === "summary" ? <SummaryPanel bundle={bundle} issues={issues} summary={summary} versions={versions} /> : null}
          {activeDrawer === "agents" ? <AgentTimeline events={events} timeline={timeline} /> : null}
          {activeDrawer === "qa" ? <QaPanel bundle={bundle} /> : null}
          {activeDrawer === "issues" ? <IssuesPanel issues={issues} /> : null}
          {activeDrawer === "artifacts" ? <ArtifactsPanel bundle={bundle} toAbsoluteUrl={toAbsoluteUrl} /> : null}
          {activeDrawer === "rag" ? <RagEvidencePanel bundle={bundle} evidence={evidence} /> : null}
          {activeDrawer === "runtime" ? (
            <RuntimeCapabilitiesPanel
              bundle={bundle}
              documentCapabilities={documentCapabilities}
              inventory={inventory}
              summary={summary}
            />
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
  const issueCount = issues?.human_readable_issues.length ?? bundle?.human_warnings_count ?? 0;
  return (
    <section className="drawer-section" aria-label="Résumé produit">
      <PanelTitle icon={<CheckCircle2 size={17} />} title="Résumé du design" />
      <div className="summary-card">
        <strong>{summaryHeadline(bundle)}</strong>
        <p>{nextUserAction(bundle, issueCount)}</p>
      </div>
      <div className="metric-grid">
        <Metric label="Workflow" value={bundle?.status ?? "pas lancé"} />
        <Metric label="Génération" value={generationTruth(bundle)} />
        <Metric label="QA" value={qaTruth(bundle)} />
        <Metric label="Version" value={activeVersion} />
      </div>
      <List title="Signaux produit" items={summarySignals(bundle, issueCount)} empty="Aucun signal produit chargé." />
      <List
        title="Capacités backend"
        items={[
          `Assets: ${summary?.asset_inventory_status ?? "unknown"}`,
          `RAG: ${summary?.rag_status ?? "unknown"}`,
          `Reranker: ${summary?.rag_reranker_status ?? "unknown"}`
        ]}
        empty="Résumé backend indisponible."
      />
    </section>
  );
}

export function QaPanel({ bundle }: { bundle: ViewerBundle | null }) {
  const qa = bundle?.qa_summary ?? {};
  const passed = bundle?.mesh_qa_passed === true;
  return (
    <section className="drawer-section" aria-label="Validation QA">
      <PanelTitle icon={<ShieldAlert size={17} />} title="Validation honnête" />
      {bundle ? (
        <>
          <div className="metric-grid">
            <Metric label="Score" value={formatScore(bundle.qa_score)} />
            <Metric label="Niveau mesh" value={bundle.mesh_qa_level ?? "unknown"} />
            <Metric label="Géométrie" value={passed ? "validée de base" : "attention"} />
            <Metric label="Mode" value={generationTruth(bundle)} />
          </div>
          <List title="Échecs QA" items={stringArray(qa["checks_failed"])} empty="Aucun échec QA remonté." />
          <List title="Ce que la QA ne garantit pas" items={bundle.limitations} empty="Aucune limitation remontée." />
          <DeveloperDetails payload={qa} label="Données QA techniques" />
        </>
      ) : (
        <p className="muted">La QA apparaîtra après un viewer bundle réel.</p>
      )}
    </section>
  );
}

export function IssuesPanel({ issues }: { issues: UserIssues | null }) {
  const summarizedIssues = summarizeUserIssues(issues?.human_readable_issues ?? []);
  return (
    <section className="drawer-section" aria-label="Warnings utilisateur">
      <PanelTitle icon={<AlertTriangle size={17} />} title="Warnings compréhensibles" />
      {summarizedIssues.length ? (
        <div className="issue-list">
          {summarizedIssues.map((issue, index) => (
            <article className={`issue-card ${issue.severity}`} key={`${issue.title}-${issue.technical_code ?? "issue"}-${index}`}>
              <strong>{issue.title}</strong>
              <p>{issue.impact}</p>
              <small>{issue.recommended_action}</small>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted">Aucun warning utilisateur chargé.</p>
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
  return (
    <section className="drawer-section" aria-label="Artefacts">
      <PanelTitle icon={<FileArchive size={17} />} title="Artefacts vérifiables" />
      {bundle ? (
        <div className="artifact-list">
          {bundle.viewer_artifacts.map((artifact) => {
            const url = artifact.available ? toAbsoluteUrl(artifact.url) : null;
            const content = (
              <>
                <span>{artifactLabel(artifact.name)}</span>
                <small>{url ? artifact.content_type : "absent"}</small>
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
      ) : (
        <p className="muted">Aucun artefact tant qu’un workflow n’est pas terminé.</p>
      )}
    </section>
  );
}

export function RagEvidencePanel({ bundle, evidence }: { bundle: ViewerBundle | null; evidence: unknown | null }) {
  const summary = summarizeRagEvidence(evidence);
  return (
    <section className="drawer-section" aria-label="RAG evidence">
      <PanelTitle icon={<Cpu size={17} />} title="RAG et preuves" />
      <div className="metric-grid">
        <Metric label="Provider" value={bundle?.rag_reranker_provider ?? "unknown"} />
        <Metric label="Reranker" value={bundle?.rag_reranker_status ?? "unknown"} />
        <Metric label="Sources" value={String(bundle?.rag_context_count ?? 0)} />
        <Metric label="Extraction" value={summary.ragUsedForExtraction ? "oui" : "non"} />
        <Metric label="Planning" value={summary.ragUsedForPlanning ? "oui" : "non"} />
      </div>
      {bundle?.rag_reranker_degraded_reason ? (
        <p className="inline-alert">
          <WifiOff size={16} aria-hidden="true" /> {bundle.rag_reranker_degraded_reason}
        </p>
      ) : null}
      {evidence ? (
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
          <List title="Limites RAG" items={summary.limitations} empty="Aucune limite RAG remontée." />
          <DeveloperDetails payload={evidence} label="Données RAG techniques" />
        </>
      ) : (
        <p className="muted">Aucune preuve RAG chargée; le frontend n’en invente pas.</p>
      )}
    </section>
  );
}

export function RuntimeCapabilitiesPanel({
  summary,
  bundle,
  inventory,
  documentCapabilities
}: {
  summary: StudioSummary | null;
  bundle: ViewerBundle | null;
  inventory: AssetInventory | null;
  documentCapabilities: DocumentPackCapabilities | null;
}) {
  const unsupported = bundle?.unsupported_actions ?? summary?.unsupported_actions ?? [];
  const showDownload = actionIsSupported("download_artifacts", unsupported);
  return (
    <section className="drawer-section" aria-label="Capacités runtime">
      <PanelTitle icon={<Boxes size={17} />} title="Capacités réelles" />
      <div className="metric-grid">
        <Metric label="Assets" value={inventory?.status ?? "unknown"} />
        <Metric label="Documents" value={documentCapabilities?.document_pack_status ?? "unknown"} />
        <Metric label="Download" value={showDownload ? "supporté" : "non supporté"} />
        <Metric label="WebSocket" value={truth(!unsupported.some((item) => item.action === "websocket_runtime"))} />
      </div>
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
              {!version.active && canRollback && version.status !== "failed" ? (
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
    visibleRows.push(row);
  }

  const groupedRows: TimelineDisplayRow[] = [];
  if (grouped.nonVendorGrade) {
    groupedRows.push({
      id: "grouped-non-vendor-grade-assets",
      label: `Assets non vendor-grade: ${grouped.nonVendorGrade} éléments`,
      message: "Le design utilise des assets réels/importés mais pas constructeur. Détails dans Warnings.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.attribution) {
    groupedRows.push({
      id: "grouped-attribution-assets",
      label: `Attributions requises: ${grouped.attribution} élément${grouped.attribution > 1 ? "s" : ""}`,
      message: "Des assets imposent une attribution de licence. Détails dans Warnings.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.otherAsset) {
    groupedRows.push({
      id: "grouped-other-assets",
      label: `Warnings assets: ${grouped.otherAsset} élément${grouped.otherAsset > 1 ? "s" : ""}`,
      message: "Des avertissements assets sont disponibles dans Warnings.",
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
      label: "Compréhension",
      phases: ["requirements", "extraction"],
      nodes: ["extract_requirements", "validate_requirements", "requirements"]
    },
    {
      phase: "rag",
      label: "Contexte RAG",
      phases: ["rag", "memory"],
      nodes: ["retrieve_rag_context", "memory_recall", "rag", "memory"]
    },
    {
      phase: "planning",
      label: "Plan SceneSpec",
      phases: ["planning", "validation", "scene"],
      nodes: ["plan_scene", "validate_scene", "scene_repair_handler", "scene_planner"]
    },
    {
      phase: "generation",
      label: "Génération 3D",
      phases: ["generation", "blender", "viewer"],
      nodes: ["generate_blender", "blender_worker", "blender_failure_handler"]
    },
    {
      phase: "qa",
      label: "Validation",
      phases: ["qa"],
      nodes: ["qa_generation", "quality_gate"]
    },
    {
      phase: "workflow",
      label: "Résultat",
      phases: ["workflow", "completion"],
      nodes: ["workflow"]
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
    return itemPhase === "workflow" ? "completed" : "not_reported";
  }
  if (terminalStatus === "failed") {
    return itemPhase === "workflow" ? "failed" : "not_reported";
  }
  return itemPhase === "workflow" ? "waiting" : "pending";
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
      visible.push(issue);
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
      title: `Assets non vendor-grade: ${groups.nonVendorGrade} éléments`,
      severity: "warning",
      impact: "La scène peut être inspectée, mais certains modèles ne sont pas des assets constructeur.",
      recommended_action: "Afficher cette limite à l’utilisateur et ne pas promettre une fidélité vendor-grade.",
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
      title: `Autres warnings assets: ${groups.otherAsset}`,
      severity: "warning",
      impact: "Des limites assets sont remontées par le backend.",
      recommended_action: "Inspecter les détails dans les artefacts et rapports backend.",
      technical_code: "ASSET_WARNING_GROUP"
    });
  }
  return [...grouped, ...visible];
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

function humanTowerType(towerType: string): string {
  return {
    lattice_tower: "pylône treillis",
    monopole: "monopôle",
    rooftop_mast: "mât toiture",
    small_cell_pole: "support small cell"
  }[towerType] ?? towerType.replaceAll("_", " ");
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
    return "Workflow échoué";
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
    return "Lire les warnings, corriger la demande, puis relancer.";
  }
  if (bundle.generation_mode !== "real_blender") {
    return "Utiliser la preview seulement comme fallback; corriger Blender avant validation.";
  }
  if (bundle.mesh_qa_passed === false) {
    return "Inspecter la QA et les warnings avant de considérer le GLB exploitable.";
  }
  if (issueCount > 0) {
    return "Inspecter le modèle 3D, puis lire les limites regroupées dans Warnings.";
  }
  return "Inspecter le GLB et télécharger les artefacts nécessaires.";
}

function summarySignals(bundle: ViewerBundle | null, issueCount: number): string[] {
  if (!bundle) {
    return [];
  }
  const failed = bundle.status === "failed";
  const signals = [
    `GLB: ${failed ? "absent car workflow échoué" : bundle.primary_glb_url ? "disponible" : "manquant"}`,
    `Preview: ${failed ? "absente car workflow échoué" : bundle.preview_url ? "disponible" : "manquante"}`,
    `Mesh QA: ${bundle.mesh_qa_level ?? "unknown"}`,
    `Warnings utilisateur: ${issueCount}`
  ];
  if (bundle.llm_fallback_used) {
    signals.push(`Fallback LLM: ${bundle.llm_fallback_reason ?? "raison indisponible"}`);
  }
  if (bundle.rag_reranker_degraded_reason) {
    signals.push(`Reranker RAG dégradé: ${bundle.rag_reranker_degraded_reason}`);
  }
  return signals;
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

function PanelTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h3>{title}</h3>
    </div>
  );
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function List({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="mini-list">
      <strong>{title}</strong>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}

function DeveloperDetails({ payload, label }: { payload: unknown; label: string }) {
  return (
    <details className="developer-details">
      <summary>{label}</summary>
      <pre>{JSON.stringify(payload, null, 2)}</pre>
    </details>
  );
}

function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "unknown";
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
  return bundle.mesh_qa_passed ? "passed" : "attention";
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
    return "workflow";
  }
  return phase.replaceAll("_", " ");
}

function artifactLabel(name: string): string {
  const labels: Record<string, string> = {
    "design.glb": "Modèle 3D GLB",
    "preview.png": "Preview backend",
    "scene_spec.json": "SceneSpec",
    "qa_report.json": "Rapport QA",
    "generation_report.json": "Rapport génération",
    "rag_evidence.json": "Preuves RAG",
    "geometry_validation.json": "Validation géométrie",
    "technical_report.md": "Rapport technique"
  };
  return labels[name] ?? name;
}
