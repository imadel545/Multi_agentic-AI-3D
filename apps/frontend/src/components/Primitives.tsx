import type { ReactNode } from "react";

import type { PresentedIssue } from "../lib/issuePresenter";
import { Badge } from "./Badge";

type PanelShellProps = {
  title: string;
  eyebrow?: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function PanelShell({ title, eyebrow, icon, action, children, className }: PanelShellProps) {
  return (
    <section className={["panel-shell", className].filter(Boolean).join(" ")}>
      <header className="panel-shell-header">
        <div className="panel-shell-title">
          {icon}
          <div>
            {eyebrow ? <span>{eyebrow}</span> : null}
            <h2>{title}</h2>
          </div>
        </div>
        {action ? <div className="panel-shell-action">{action}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  tone = "idle",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "good" | "warn" | "bad" | "idle";
}) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <p>{detail}</p> : null}
    </article>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="product-empty-state">
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ActionButton({
  children,
  variant = "secondary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button className={`action-button action-${variant}`} type="button" {...props}>
      {children}
    </button>
  );
}

export function WarningCard({ issue }: { issue: PresentedIssue }) {
  return (
    <article className={`warning-card warning-${issue.severity}`}>
      <header>
        <div>
          <strong>{issue.title}</strong>
          <span>{issue.code}</span>
        </div>
        <Badge tone={issue.severity === "error" ? "bad" : "warn"}>
          {issue.count > 1 ? `${issue.severity} x${issue.count}` : issue.severity}
        </Badge>
      </header>
      <p>{issue.impact}</p>
      <div className="recommended-action">{issue.action}</div>
      <details>
        <summary>Détail technique</summary>
        <code>{issue.detail}</code>
      </details>
    </article>
  );
}

export function CommandMessage({
  role,
  title,
  body,
  meta,
  status,
}: {
  role: "user" | "assistant" | "system";
  title: string;
  body: ReactNode;
  meta?: ReactNode;
  status?: "running" | "passed" | "warning" | "failed" | "info";
}) {
  return (
    <article className={`command-message message-${role} message-${status ?? "info"}`}>
      <header>
        <strong>{title}</strong>
        {meta ? <span>{meta}</span> : null}
      </header>
      <div>{body}</div>
    </article>
  );
}
