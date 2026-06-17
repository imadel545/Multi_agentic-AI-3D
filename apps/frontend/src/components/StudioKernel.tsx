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
import { useMemo, useState, type ChangeEvent, type ReactNode } from "react";
import type {
  AssetInventory,
  CurrentOperation,
  DocumentPackCapabilities,
  DocumentPackSummary,
  Health,
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
        <StatusPill label="Backend" value={health?.status ?? "offline"} tone={health?.status === "ok" ? "ok" : "warn"} />
        <StatusPill label="Workflow" value={phaseLabel(phase)} tone={phaseTone(phase)} />
        <StatusPill label="3D" value={generationTruth(bundle)} tone={bundle?.generation_mode === "real_blender" ? "ok" : "muted"} />
        <StatusPill label="QA" value={qaTruth(bundle)} tone={bundle?.mesh_qa_passed ? "ok" : "warn"} />
        <StatusPill label="Issues" value={String(issueCount)} tone={issueCount ? "warn" : "ok"} />
      </div>
    </header>
  );
}

export function ChatCommandPanel({
  prompt,
  phase,
  error,
  canEdit,
  revisionPrompt,
  editMessage,
  documentCapabilities,
  documentPackSummary,
  documentPackMessage,
  documentPackBusy,
  onDocumentPackGenerate,
  onDocumentPackUpload,
  onPromptChange,
  onRevisionPromptChange,
  onRevisionSubmit,
  onSubmit
}: {
  prompt: string;
  phase: WorkflowPhase;
  error: string | null;
  canEdit: boolean;
  revisionPrompt: string;
  editMessage: string | null;
  documentCapabilities: DocumentPackCapabilities | null;
  documentPackSummary: DocumentPackSummary | null;
  documentPackMessage: string | null;
  documentPackBusy: boolean;
  onDocumentPackGenerate: () => void;
  onDocumentPackUpload: (file: File) => void;
  onPromptChange: (value: string) => void;
  onRevisionPromptChange: (value: string) => void;
  onRevisionSubmit: () => void;
  onSubmit: () => void;
}) {
  const disabled = phase === "submitting" || phase === "streaming" || phase === "running";
  const examplePrompt =
    "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, boîte alimentation, dalle béton, GPS, labels, couleurs professionnelles et export GLB.";
  const understanding = previewPromptUnderstanding(prompt);
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
        <button className="primary-action" disabled={disabled || !prompt.trim()} onClick={onSubmit}>
          <Send size={18} aria-hidden="true" />
          Générer le design
        </button>
      </div>

      <div className="assistant-card">
        <MessageSquareText size={18} aria-hidden="true" />
        <div>
          <strong>Assistant studio</strong>
          <p>
            Le backend montrera les étapes réelles et les limites au lieu
            d’inventer une capacité non supportée.
          </p>
        </div>
      </div>

      <div className="understanding-card">
        <span className="eyebrow">Prélecture locale</span>
        <strong>{understanding.title}</strong>
        <ul>
          {understanding.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <small>La vérité finale vient du backend: RequirementSpec, SceneSpec, QA et artefacts.</small>
      </div>

      <DocumentPackIntake
        busy={documentPackBusy}
        capabilities={documentCapabilities}
        message={documentPackMessage}
        onGenerate={onDocumentPackGenerate}
        onUpload={onDocumentPackUpload}
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
          <button className="secondary-action" disabled={disabled || !revisionPrompt.trim()} onClick={onRevisionSubmit} type="button">
            Appliquer la révision
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

function DocumentPackIntake({
  busy,
  capabilities,
  message,
  onGenerate,
  onUpload,
  summary
}: {
  busy: boolean;
  capabilities: DocumentPackCapabilities | null;
  message: string | null;
  onGenerate: () => void;
  onUpload: (file: File) => void;
  summary: DocumentPackSummary | null;
}) {
  const accept = capabilities?.supported_extensions?.join(",") || ".zip";
  const canGenerate = summary?.can_generate_design === true;
  return (
    <div className="document-intake">
      <div>
        <span className="eyebrow">Cahier de charge</span>
        <strong>ZIP documentaire</strong>
        <p>
          {capabilities?.document_pack_status === "limited"
            ? "Ingestion limitée et synchrone; le backend expose les champs manquants."
            : "Capacités documentaires en cours de chargement."}
        </p>
      </div>
      <label className="file-drop">
        <FileUp size={17} aria-hidden="true" />
        <span>{busy ? "Traitement..." : "Charger un ZIP"}</span>
        <input
          accept={accept}
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
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}

export function CurrentOperationStrip({
  operation,
  phase,
  runtimeMode
}: {
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

export function InspectorDock({
  bundle,
  documentCapabilities,
  events,
  evidence,
  inventory,
  issues,
  summary,
  timeline,
  toAbsoluteUrl,
  versions
}: {
  bundle: ViewerBundle | null;
  documentCapabilities: DocumentPackCapabilities | null;
  events: NormalizedWorkflowEvent[];
  evidence: unknown | null;
  inventory: AssetInventory | null;
  issues: UserIssues | null;
  summary: StudioSummary | null;
  timeline: TimelineSummary | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
  versions: PublicVersionInfo[];
}) {
  const [activeDrawer, setActiveDrawer] = useState<DrawerId | null>(null);
  const issueCount = issues?.human_readable_issues.length ?? bundle?.human_warnings_count ?? 0;
  const drawers: Array<{ id: DrawerId; label: string; badge?: string; icon: ReactNode }> = [
    { id: "summary", label: "Résumé", icon: <CheckCircle2 size={16} /> },
    { id: "agents", label: "Agents", icon: <Sparkles size={16} /> },
    { id: "qa", label: "QA", badge: qaTruth(bundle), icon: <ShieldAlert size={16} /> },
    { id: "issues", label: "Warnings", badge: issueCount ? String(issueCount) : undefined, icon: <AlertTriangle size={16} /> },
    { id: "artifacts", label: "Artefacts", badge: bundle ? String(bundle.viewer_artifacts.length) : undefined, icon: <FileArchive size={16} /> },
    { id: "rag", label: "RAG", badge: bundle?.rag_reranker_degraded_reason ? "dégradé" : undefined, icon: <Cpu size={16} /> },
    { id: "runtime", label: "Runtime", icon: <Boxes size={16} /> },
    { id: "versions", label: "Versions", badge: versions.length ? String(versions.length) : undefined, icon: <Layers3 size={16} /> }
  ];
  return (
    <aside className="context-dock" aria-label="Drawers contextuels">
      <div className="drawer-launcher">
        {drawers.map((drawer) => (
          <button
            className={activeDrawer === drawer.id ? "drawer-action active" : "drawer-action"}
            key={drawer.id}
            onClick={() => setActiveDrawer(activeDrawer === drawer.id ? null : drawer.id)}
            type="button"
          >
            {drawer.icon}
            <span>{drawer.label}</span>
            {drawer.badge ? <small>{drawer.badge}</small> : null}
          </button>
        ))}
      </div>
      {activeDrawer ? (
        <div className="context-drawer">
          <button className="drawer-close" onClick={() => setActiveDrawer(null)} title="Fermer le drawer" type="button">
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
          {activeDrawer === "versions" ? <VersionSummary versions={versions} /> : null}
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
          {bundle.viewer_artifacts.map((artifact) => (
            <a className={artifact.available ? "artifact-link" : "artifact-link unavailable"} href={toAbsoluteUrl(artifact.url) ?? undefined} key={artifact.name} rel="noreferrer" target="_blank">
              <span>{artifactLabel(artifact.name)}</span>
              <small>{artifact.available ? artifact.content_type : "absent"}</small>
              <ChevronRight size={15} aria-hidden="true" />
            </a>
          ))}
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
          <List title="Hints contrôlés autorisés" items={summary.hints} empty="Aucun hint contrôlé remonté." />
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

export function VersionSummary({ versions }: { versions: PublicVersionInfo[] }) {
  return (
    <section className="drawer-section" aria-label="Versions">
      <PanelTitle icon={<RotateCcw size={17} />} title="Versions et rollback" />
      {versions.length ? (
        <div className="artifact-list">
          {versions.map((version) => (
            <div className="artifact-link" key={version.version_id}>
              <span>{version.version_id}</span>
              <small>{version.active ? "active" : version.generation_mode ?? "version"}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Versions chargées après génération.</p>
      )}
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
  return stages.map((item) => ({
    phase: item.phase,
    label: item.label,
    status: statusByPhase.get(item.phase) ?? terminalStageFallback(item.phase, terminalStatus, phase)
  }));
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

function previewPromptUnderstanding(prompt: string) {
  const normalized = prompt.toLowerCase();
  const items: string[] = [];
  const towerHeight = prompt.match(/(\d+(?:[.,]\d+)?)\s*m/i)?.[1];
  const hba = prompt.match(/(?:hba|secteurs?\s+à)\s*(\d+(?:[.,]\d+)?)\s*m/i)?.[1];
  const azimuths = prompt.match(/azimuts?\s*:?\s*([0-9°,\s/;.-]+)/i)?.[1];
  if (towerHeight) {
    items.push(`Hauteur pylône détectée: ${towerHeight.replace(",", ".")} m`);
  }
  if (hba) {
    items.push(`Hauteur antennes détectée: ${hba.replace(",", ".")} m`);
  }
  if (azimuths) {
    items.push(`Azimuts mentionnés: ${azimuths.trim()}`);
  }
  for (const [token, label] of [
    ["rru", "RRU/radios demandés"],
    ["câble", "Câbles demandés"],
    ["cable", "Câbles demandés"],
    ["gps", "GPS demandé"],
    ["boîte", "Boîte alimentation demandée"],
    ["cabinet", "Cabinet demandé"],
    ["dalle", "Dalle/fondation demandée"],
    ["label", "Labels demandés"]
  ]) {
    if (normalized.includes(token) && !items.includes(label)) {
      items.push(label);
    }
  }
  return {
    title: prompt.trim() ? "Contraintes visibles avant extraction backend" : "En attente de cahier de charge",
    items: items.length ? items.slice(0, 7) : ["Aucune contrainte locale détectée pour l’instant."]
  };
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
    hints: readStringArray(record?.["candidate_hint_fields"]),
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

function phaseTone(phase: WorkflowPhase): "ok" | "warn" | "danger" | "muted" {
  if (phase === "completed") {
    return "ok";
  }
  if (phase === "failed") {
    return "danger";
  }
  if (phase === "degraded") {
    return "warn";
  }
  return "muted";
}

function stageStatusLabel(status: string): string {
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
