import { AlertTriangle, Boxes, CheckCircle2, Loader2, RadioTower } from "lucide-react";
import type { Health, UserIssues, ViewerBundle } from "../api/schemas";
import type { WorkflowPhase } from "../state/workflowMachine";
import { geometryFidelityBadge } from "../features/three-viewer/viewerRules";
import { compactFidelityLabel } from "./StudioDisplayHelpers";
import { workflowStatusLabel, phaseLabel } from "./StudioProductDisplay";
import { displayIssueCount } from "./StudioWorkflowDisplay";

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
  const showRuntimeProblem =
    healthLoading || Boolean(healthError) || health?.status !== "ok";
  if (
    !showRuntimeProblem &&
    !workflowActive &&
    !bundle &&
    phase === "idle" &&
    !issueCount
  ) {
    return null;
  }
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
        {showRuntimeProblem ? (
          <span className="runtime-presence warn">
            <span aria-hidden="true" />
            {healthLoading ? "Connexion au studio…" : "Studio indisponible"}
          </span>
        ) : null}
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
            {integrityVerified ? "Modèle vérifié" : workflowStatusLabel(bundle.status)}
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


