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
  AdaptationCapabilityCatalog,
  AssetLibrarySearch,
  AssetLibrarySummary,
  AssetInventory,
  CurrentOperation,
  DocumentPackCapabilities,
  DocumentPackField,
  DocumentPackReview,
  DocumentPackSummary,
  Health,
  ParseRequirementsResponse,
  PublicVersionInfo,
  SceneAdaptationCapabilities,
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
          {health?.status === "ok" ? "Studio local connecté" : "Studio indisponible"}
        </span>
        {bundle?.generation_mode === "real_blender" ? (
          <span className="topbar-proof"><Boxes size={14} aria-hidden="true" /> Blender réel</span>
        ) : null}
        {bundle ? (
          <span className={bundle.mesh_qa_passed ? "topbar-proof ok" : "topbar-proof warn"}>
            <CheckCircle2 size={14} aria-hidden="true" /> {bundle.mesh_qa_passed ? "QA validée" : "QA à vérifier"}
          </span>
        ) : phase !== "idle" ? <span className="workflow-truth">{phaseLabel(phase)}</span> : null}
        {bundle?.completion_certificate_status === "issued" ? (
          <span className="topbar-proof"><ShieldAlert size={14} aria-hidden="true" /> Intégrité vérifiée</span>
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
  const [commandMode, setCommandMode] = useState<"new" | "revision">(
    canEdit ? "revision" : "new"
  );
  const previousCanEdit = useRef(canEdit);

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
  return (
    <section className="command-center" aria-label="Conversation de commande">
      <div className="conversation-heading">
        <span className="eyebrow">Conception assistée</span>
        <h1>Concevoir le site telecom</h1>
      </div>

      <div className="assistant-card conversation-message">
        <RadioTower size={18} aria-hidden="true" />
        <div>
          <strong>{phase === "completed" ? "Le résultat est prêt à inspecter" : "Décrivez le résultat attendu"}</strong>
          <p>
            {phase === "completed"
              ? "Inspectez le modèle, demandez une modification ou démarrez un nouveau site."
              : "Les contraintes sont extraites puis confirmées avant toute génération Blender."}
          </p>
        </div>
      </div>

      {canEdit ? (
        <div className="command-mode" role="group" aria-label="Type de commande">
          <button className={!revisionMode ? "active" : ""} onClick={() => setCommandMode("new")} type="button">Nouveau design</button>
          <button className={revisionMode ? "active" : ""} onClick={() => setCommandMode("revision")} type="button">Modifier le design</button>
        </div>
      ) : null}

      <div className="command-composer">
        <textarea
          aria-label={revisionMode ? "Revision prompt" : "Design prompt"}
          placeholder={revisionMode
            ? "Ex: augmente la hauteur à 35 m, ajoute une plateforme, corrige les labels…"
            : "Ex: pylône treillis 30 m, 3 secteurs à 24 m, azimuts 0/120/240, RRU, câbles, GPS…"}
          value={revisionMode ? revisionPrompt : prompt}
          onChange={(event) => revisionMode
            ? onRevisionPromptChange(event.target.value)
            : onPromptChange(event.target.value)}
          rows={4}
        />
        <button
          aria-label={revisionMode ? "Appliquer la révision" : "Analyser la demande"}
          className="composer-submit"
          disabled={disabled || (revisionMode ? revisionBusy || !revisionPrompt.trim() : analysisBusy || !prompt.trim())}
          onClick={revisionMode ? onRevisionSubmit : onAnalyze}
          title={revisionMode ? "Appliquer la modification" : "Analyser les contraintes"}
          type="button"
        >
          {revisionMode ? <Send size={18} aria-hidden="true" /> : <Sparkles size={18} aria-hidden="true" />}
        </button>
      </div>
      <p className="composer-hint">
        {revisionMode
          ? revisionBusy ? "Révision et validation en cours…" : "La modification passe par les outils bornés et la QA Blender."
          : analysisBusy ? "Analyse de la demande en cours…" : analysis ? "Modifiez le texte puis réanalysez si nécessaire." : "Vous confirmerez les paramètres extraits avant génération."}
      </p>

      {analysis ? (
        <RequirementsUnderstanding
          analysis={analysis}
          failedWorkflow={phase === "failed"}
          onConfirm={onConfirm}
          submitted={analysisSubmitted}
          submitting={disabled}
        />
      ) : null}
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

      {editMessage ? <p className="muted command-feedback">{editMessage}</p> : null}

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
        <p>La demande n’a pas pu être convertie en exigences exploitables.</p>
      </div>
    );
  }
  const warnings = uniqueRequirementWarnings([...analysis.warnings, ...requirements.warnings]);
  const confirmationLocked = submitted && !failedWorkflow;
  return (
    <div className="understanding-card" aria-label="Compréhension de la demande">
      <span className="eyebrow">
        {confirmationLocked
          ? "Compréhension utilisée pour le design"
          : failedWorkflow && submitted
            ? "Compréhension de la demande échouée"
            : "Paramètres compris à confirmer"}
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
        Source d’analyse : {analysisProviderLabel(analysis.provider, analysis.extraction_provider)}
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
            ? `Compréhension structurée${review.consolidatedSpec.llm_fallback_used ? " avec mode de secours signalé" : " validée"}.`
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
        <strong>{operation?.human_label ?? operation?.current_operation ?? (running ? "Conception en cours" : "Studio prêt")}</strong>
        <span>{operation?.progress_message ?? "Les étapes de conception apparaissent ici pendant la génération."}</span>
        {notice ? <small className="operation-notice" aria-live="polite">{notice}</small> : null}
      </div>
      <StatusPill label={pollingFallback ? "Mode de secours" : "Temps réel"} value={phaseLabel(phase)} tone={pollingFallback ? "warn" : "muted"} />
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
                <p>{humanTimelineMessage(row.message)}</p>
                <small>{humanPhase(row.phase)} · {stageStatusLabel(row.status)}</small>
              </div>
            </article>
          ))
        ) : (
          <p className="muted">Les spécialistes apparaîtront au démarrage de la conception.</p>
        )}
      </div>
    </section>
  );
}

type DrawerId = "summary" | "agents" | "qa" | "issues" | "artifacts" | "library" | "rag" | "runtime" | "versions";
type DrawerDefinition = { id: DrawerId; label: string; badge?: string; icon: ReactNode };

export function InspectorDock({
  assetLibrarySearch = null,
  assetLibrarySearchBusy = false,
  assetLibrarySearchError = null,
  assetLibrarySummary = null,
  bundle,
  canRollback,
  events,
  issues,
  summary,
  timeline,
  toAbsoluteUrl,
  onRollbackVersion,
  onSearchAssetLibrary,
  rollbackBusyVersionId,
  versionMessage,
  versions
}: {
  assetLibrarySearch?: AssetLibrarySearch | null;
  assetLibrarySearchBusy?: boolean;
  assetLibrarySearchError?: string | null;
  assetLibrarySummary?: AssetLibrarySummary | null;
  bundle: ViewerBundle | null;
  canRollback: boolean;
  events: NormalizedWorkflowEvent[];
  issues: UserIssues | null;
  summary: StudioSummary | null;
  timeline: TimelineSummary | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  onRollbackVersion: (versionId: string) => void;
  onSearchAssetLibrary?: (query: string) => void | Promise<void>;
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
  if (events.length || timeline) drawers.push({ id: "agents", label: "Agents", icon: <Sparkles size={16} /> });
  if (bundle) drawers.push({ id: "qa", label: "QA", badge: bundle.mesh_qa_passed ? "validée" : "à revoir", icon: <ShieldAlert size={16} /> });
  if (issueCount) drawers.push({ id: "issues", label: "Alertes", badge: String(issueCount), icon: <AlertTriangle size={16} /> });
  if (bundle?.viewer_artifacts.length) drawers.push({ id: "artifacts", label: "Livrables", icon: <FileArchive size={16} /> });
  if (assetLibrarySummary?.catalog_available) drawers.push({ id: "library", label: "Bibliothèque", icon: <Boxes size={16} /> });
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
          {activeDrawer === "library" ? (
            <AssetLibraryPanel
              busy={assetLibrarySearchBusy}
              error={assetLibrarySearchError}
              onSearch={onSearchAssetLibrary}
              search={assetLibrarySearch}
              summary={assetLibrarySummary}
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
        <Metric label="Conception" value={workflowStatusLabel(bundle?.status)} />
        <Metric label="Génération" value={generationTruth(bundle)} />
        <Metric label="QA" value={qaTruth(bundle)} />
        <Metric label="Version" value={activeVersion} />
      </div>
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
          <List title="Échecs QA" items={stringArray(qa["checks_failed"])} empty="Aucun échec QA remonté." />
          <List title="Ce que la QA ne garantit pas" items={bundle.limitations} empty="Aucune limitation remontée." />
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
    <section className="drawer-section" aria-label="Alertes utilisateur">
      <PanelTitle icon={<AlertTriangle size={17} />} title="Alertes à examiner" />
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
        <p className="muted">Aucune alerte à examiner.</p>
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
    <section className="drawer-section" aria-label="Livrables">
      <PanelTitle icon={<FileArchive size={17} />} title="Livrables vérifiables" />
      {bundle ? (
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
      ) : (
        <p className="muted">Aucun artefact tant qu’un workflow n’est pas terminé.</p>
      )}
    </section>
  );
}

export function AssetLibraryPanel({
  busy = false,
  error = null,
  onSearch,
  search = null,
  summary
}: {
  busy?: boolean;
  error?: string | null;
  onSearch?: (query: string) => void | Promise<void>;
  search?: AssetLibrarySearch | null;
  summary: AssetLibrarySummary | null;
}) {
  const [query, setQuery] = useState("");
  const dimensions = summary?.claimed_dimension_counts ?? {};
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim() && onSearch) void onSearch(query.trim());
  };
  return (
    <section className="drawer-section" aria-label="Bibliothèque de designs">
      <PanelTitle icon={<Boxes size={17} />} title="Bibliothèque CAD telecom" />
      {summary ? (
        <>
          <div className="summary-card">
            <strong>{formatInteger(summary.file_count ?? 0)} fichiers catalogués</strong>
            <p>
              Chaque fichier est recherché par contenu et provenance. Aucun brut n'est utilisé
              dans Blender avant qualification et conversion contrôlée.
            </p>
          </div>
          <div className="metric-grid">
            <Metric label="Contenus uniques" value={formatInteger(summary.unique_content_count ?? 0)} />
            <Metric label="Classés 3D" value={formatInteger(dimensions["3d"] ?? 0)} />
            <Metric label="Classés 2D" value={formatInteger(dimensions["2d"] ?? 0)} />
            <Metric label="Prêts pour Blender" value={formatInteger(summary.generation_eligible_count)} />
            <Metric label="CAD avec aperçu" value={formatInteger(summary.cad_with_reference_preview_count)} />
          </div>
          <form className="library-search" onSubmit={submitSearch}>
            <label htmlFor="asset-library-query">Rechercher un pylône, équipement ou dimension</label>
            <div className="library-search-row">
              <input
                id="asset-library-query"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex. pylône Orange 30 m"
                type="search"
                value={query}
              />
              <button disabled={busy || !query.trim() || !onSearch} type="submit">
                {busy ? "Recherche…" : "Rechercher"}
              </button>
            </div>
          </form>
          {error ? <p className="inline-alert"><AlertTriangle size={16} aria-hidden="true" /> Recherche indisponible : {error}</p> : null}
          {search ? (
            <div className="library-results" aria-live="polite">
              <div className="library-results-heading">
                <strong>{formatInteger(search.result_count)} résultat{search.result_count > 1 ? "s" : ""}</strong>
                <small>Aucun résultat n'est sélectionné automatiquement.</small>
              </div>
              {search.results.length ? search.results.map((entry) => (
                <article className="library-result-card" key={entry.file_id}>
                  <div>
                    <strong>{libraryFileName(entry.relative_path)}</strong>
                    <small>{entry.category} · {entry.claimed_dimension.toUpperCase()} · {entry.extension.toUpperCase()}</small>
                  </div>
                  <p>{entry.relative_path}</p>
                  <div className="library-result-meta">
                    <span>{entry.generation_eligible ? "Qualifié pour génération" : "En quarantaine"}</span>
                    <span>{entry.reference_preview_file_ids.length} aperçu{entry.reference_preview_file_ids.length > 1 ? "s" : ""}</span>
                  </div>
                </article>
              )) : <p className="muted">Aucun fichier du catalogue ne correspond à cette recherche.</p>}
              <p className="library-next-action">{search.next_action}</p>
            </div>
          ) : null}
          <div className="summary-card warning-card">
            <strong>Qualification requise</strong>
            <p>
              Les licences sont à vérifier et les solides DWG ACIS exigent une passerelle CAD
              avant maillage. Cette quarantaine protège les designs produits.
            </p>
          </div>
          <List title="Limites actuelles" items={summary.limitations} empty="Aucune limitation remontée." />
        </>
      ) : <p className="muted">La bibliothèque locale n'est pas cataloguée.</p>}
    </section>
  );
}

function libraryFileName(relativePath: string): string {
  return relativePath.split("/").pop() ?? relativePath;
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
        </>
      ) : (
        <p className="muted">Aucune preuve RAG chargée; le frontend n’en invente pas.</p>
      )}
    </section>
  );
}

export function RuntimeCapabilitiesPanel({
  adaptationCapabilities = null,
  adaptationCatalog = null,
  summary,
  bundle,
  inventory,
  documentCapabilities
}: {
  adaptationCapabilities?: SceneAdaptationCapabilities | null;
  adaptationCatalog?: AdaptationCapabilityCatalog | null;
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
        <Metric
          label="Paramètres 3D actifs"
          value={String(adaptationCapabilities?.capabilities.length ?? 0)}
        />
        <Metric
          label="Profils d’adaptation"
          value={String(adaptationCatalog?.profiles.length ?? 0)}
        />
        <Metric label="Documents" value={documentCapabilities?.document_pack_status ?? "unknown"} />
        <Metric label="Download" value={showDownload ? "supporté" : "non supporté"} />
        <Metric label="WebSocket" value={truth(!unsupported.some((item) => item.action === "websocket_runtime"))} />
      </div>
      <List
        title="Modifications vérifiées du design actif"
        items={(adaptationCapabilities?.capabilities ?? []).map(
          (capability) =>
            `${capability.label} · ${humanAdaptationTool(capability.execution_tool)}`
        )}
        empty="Aucun design actif: les paramètres seront résolus après génération."
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

function humanizeUserIssue(issue: UserIssue): UserIssue {
  const text = `${issue.title} ${issue.impact} ${issue.technical_code ?? ""}`;
  const normalized = text.toLowerCase();
  const inferredValue = text.match(/inferred as ([\d.]+) degrees?/i)?.[1];
  if (normalized.includes("mechanical tilt inferred")) {
    return {
      ...issue,
      title: "Inclinaison mécanique proposée",
      impact: `Une inclinaison mécanique de ${inferredValue ?? "3"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Confirmez cette valeur avec le cahier de charge radio."
    };
  }
  if (normalized.includes("electrical tilt inferred")) {
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
      recommended_action: "Le design reste inspectable, mais vérifiez les sources dans le panneau RAG."
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

function humanAdaptationTool(tool: string): string {
  return {
    parametric_rebuild: "reconstruction paramétrique Blender",
    sector_layout: "placement radio contrôlé",
    asset_transform: "transformation d’asset",
    scene_visibility: "composition de scène"
  }[tool] ?? "outil backend déclaré";
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
    `GLB: ${failed ? "absent car workflow échoué" : bundle.primary_glb_url ? "disponible" : "manquant"}`,
    `Preview: ${failed ? "absente car workflow échoué" : bundle.preview_url ? "disponible" : "manquante"}`,
    `Mesh QA: ${meshQaLevelLabel(bundle.mesh_qa_level)}`,
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

function serviceStatusLabel(status?: string | null): string {
  const normalized = status?.toLowerCase() ?? "";
  if (["ok", "ready", "available", "enabled", "ready_for_import"].some((value) => normalized.includes(value))) {
    return "disponible";
  }
  if (["degraded", "limited", "fallback", "passthrough"].some((value) => normalized.includes(value))) {
    return "disponible avec limites";
  }
  if (["unavailable", "disabled", "error", "missing"].some((value) => normalized.includes(value))) {
    return "indisponible";
  }
  return "état non confirmé";
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

function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "unknown";
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("fr-FR").format(value);
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
    "preview.png": "Aperçu de contrôle",
    "scene_metadata.json": "Métadonnées de la scène",
    "requirements_spec.json": "Exigences consolidées",
    "extraction_report.json": "Rapport de compréhension",
    "scene_spec.json": "Plan de scène vérifiable",
    "qa_report.json": "Rapport QA",
    "generation_report.json": "Rapport génération",
    "rag_evidence.json": "Preuves du contexte IA",
    "planning_decision.json": "Décisions de planification",
    "geometry_validation.json": "Validation géométrie",
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
