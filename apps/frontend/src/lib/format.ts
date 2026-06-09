export function asPercent(value: number | null | undefined): string {
  if (typeof value !== "number") return "n/a";
  return `${Math.round(value * 100)}%`;
}

export function shortId(value: string | null | undefined): string {
  if (!value) return "none";
  return value.length > 14 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
}

export function statusTone(status: string | null | undefined): "good" | "warn" | "bad" | "idle" {
  if (!status) return "idle";
  if (["completed", "passed", "ok", "ready_for_import", "imported_glb", "good"].includes(status)) {
    return "good";
  }
  if (["failed", "error", "missing_file", "blocked"].includes(status)) return "bad";
  if (
    [
      "warning",
      "partial_import_ready",
      "procedural_fallback",
      "fallback",
      "pending",
      "running",
      "check",
    ].includes(status)
  ) {
    return "warn";
  }
  return "idle";
}

export function stringifyCompact(value: unknown): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
