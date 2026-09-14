import { Clock3, Loader2, RadioTower, Sparkles } from "lucide-react";
import { useMemo } from "react";
import type { CurrentOperation, TimelineSummary } from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import type { RuntimeMode, WorkflowPhase } from "../state/workflowMachine";
import { PanelTitle } from "./StudioPrimitives";
import { StatusPill, humanPhase, humanTimelineMessage, phaseLabel, stageStatusLabel } from "./StudioProductDisplay";
import { macroStageMessage, summarizeStages, summarizeTimelineRows } from "./StudioWorkflowDisplay";

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
    humanOperationLabel(liveOperation?.current_node ?? liveOperation?.current_operation) ??
    (intent === "revision"
      ? "Modification du design"
      : intent === "rollback"
        ? "Restauration de la version"
        : phase === "submitting"
          ? "Préparation du design"
          : "Conception en cours");
  const message =
    (intent === "revision"
      ? "La modification est interprétée, appliquée au modèle 3D puis contrôlée avant de remplacer la version visible."
      : intent === "rollback"
        ? "La version sélectionnée est vérifiée avant de redevenir active."
        : "Le modèle est construit puis vérifié avant de devenir la version active.");
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
  if (normalized.includes("blender") || normalized.includes("build") || normalized.includes("geometry") || normalized.includes("assembl")) {
    return "Construction du modèle 3D";
  }
  if (normalized.includes("plan") || normalized.includes("blueprint") || normalized.includes("scene")) {
    return "Conception du plan 3D";
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

