import type { ReactNode } from "react";

import { statusTone } from "../lib/format";

type BadgeProps = {
  children: ReactNode;
  tone?: "good" | "warn" | "bad" | "idle";
};

export function Badge({ children, tone = "idle" }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status }: { status?: string | null }) {
  return <Badge tone={statusTone(status)}>{status ?? "unknown"}</Badge>;
}
