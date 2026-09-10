import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

export function PanelTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h3>{title}</h3>
    </div>
  );
}

export function ResourceRecovery({
  busy = false,
  label,
  message,
  onRetry
}: {
  busy?: boolean;
  label: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="resource-recovery" role="alert">
      <AlertTriangle size={17} aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <span>{message}</span>
      </div>
      {onRetry ? (
        <button disabled={busy} onClick={onRetry} type="button">
          {busy ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <RotateCcw size={14} aria-hidden="true" />}
          {busy ? "Chargement…" : "Réessayer"}
        </button>
      ) : null}
    </div>
  );
}

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

export function List({ title, items, empty }: { title: string; items: string[]; empty: string }) {
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

export function formatInteger(value: number): string {
  return new Intl.NumberFormat("fr-FR").format(value);
}
