import { Activity, Download, Server, TriangleAlert } from "lucide-react";

import type { WorkflowStatus } from "../api/types";
import { Badge, StatusBadge } from "../components/Badge";
import { asPercent, shortId } from "../lib/format";

type TopBarProps = {
  backendStatus?: string;
  workflow?: WorkflowStatus;
};

export function TopBar({ backendStatus, workflow }: TopBarProps) {
  const warningCount = workflow?.warnings?.length ?? 0;
  const errorCount = workflow?.errors?.length ?? 0;

  return (
    <header className="top-bar">
      <div className="brand-block">
        <div className="brand-mark">3D</div>
        <div>
          <h1>Agentic Telecom Studio</h1>
          <p>Document intelligence to SceneSpec to Blender QA</p>
        </div>
      </div>
      <div className="top-status-grid">
        <div className="status-cell">
          <Server size={15} />
          <span>Backend</span>
          <StatusBadge status={backendStatus ?? "offline"} />
        </div>
        <div className="status-cell">
          <Activity size={15} />
          <span>Workflow</span>
          <strong>{shortId(workflow?.workflow_id)}</strong>
        </div>
        <div className="status-cell">
          <span>QA</span>
          <Badge tone={workflow?.qa_score === 1 ? "good" : workflow?.qa_score ? "warn" : "idle"}>
            {asPercent(workflow?.qa_score)}
          </Badge>
        </div>
        <div className="status-cell">
          <span>Mode</span>
          <StatusBadge status={workflow?.generation_mode ?? "not_generated"} />
        </div>
        <div className="status-cell">
          <TriangleAlert size={15} />
          <span>Issues</span>
          <Badge tone={errorCount ? "bad" : warningCount ? "warn" : "good"}>
            {errorCount} err / {warningCount} warn
          </Badge>
        </div>
        {workflow?.download_url ? (
          <a className="download-link" href={workflow.download_url} target="_blank" rel="noreferrer">
            <Download size={15} />
            Archive
          </a>
        ) : null}
      </div>
    </header>
  );
}
