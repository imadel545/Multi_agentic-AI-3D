import { useEffect, useRef, useState } from "react";
import type { NormalizedWorkflowEvent } from "../api/sse";

const starts = new Set(["design_created", "edit_requested"]);
const finishes = new Set(["workflow_completed", "workflow_failed", "edit_outcome", "edit_patch_applied", "edit_patch_rejected"]);

/** Restore duration from recorded task events, never from a previous version's age. */
type TaskTiming = { task_started_at?: string | null; task_finished_at?: string | null };

export function recordedTaskInterval(events: NormalizedWorkflowEvent[], timing?: TaskTiming | null) {
  const serverStart = timing?.task_started_at ? Date.parse(timing.task_started_at) : NaN;
  const serverEnd = timing?.task_finished_at ? Date.parse(timing.task_finished_at) : null;
  const startIndex = events.map((event) => starts.has(event.event_type)).lastIndexOf(true);
  const eventStart = startIndex >= 0 ? Date.parse(events[startIndex].timestamp) : NaN;
  if (Number.isFinite(serverStart) && (!Number.isFinite(eventStart) || serverStart >= eventStart)) {
    return { start: serverStart, end: serverEnd !== null && Number.isFinite(serverEnd) ? serverEnd : null };
  }
  if (startIndex < 0) return null;
  const start = Date.parse(events[startIndex].timestamp);
  const terminal = events.slice(startIndex + 1).find((event) => finishes.has(event.event_type));
  const end = terminal ? Date.parse(terminal.timestamp) : null;
  if (!Number.isFinite(start) || (end !== null && !Number.isFinite(end))) return null;
  return { start, end };
}

export function TaskElapsedTime({ events, busy, timing }: { events: NormalizedWorkflowEvent[]; busy: boolean; timing?: TaskTiming | null }) {
  const [now, setNow] = useState(Date.now);
  const localStart = useRef<number | null>(null);
  const previousBusy = useRef(false);
  const previousStart = useRef<string | undefined>(undefined);
  const recorded = recordedTaskInterval(events, timing);
  const latestStart = recorded ? String(recorded.start) : undefined;
  const [pendingStart, setPendingStart] = useState(false);
  useEffect(() => {
    if (busy && !previousBusy.current) {
      localStart.current = Date.now();
      previousStart.current = latestStart;
      // An unfinished persisted task survives reload; a completed one is historical.
      setPendingStart(recorded?.end != null || latestStart === undefined);
      setNow(Date.now());
    }
    if (latestStart !== previousStart.current) setPendingStart(false);
    previousBusy.current = busy;
    if (!busy) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy, latestStart]);
  const start = busy && pendingStart ? localStart.current : recorded?.start;
  const end = busy && pendingStart ? null : recorded?.end;
  if (start == null || (!busy && end == null)) return null;
  const seconds = Math.max(0, Math.floor(((end ?? now) - start) / 1000));
  const text = seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, "0")} s`;
  return <span aria-live="off" aria-label={`Temps écoulé : ${text}`} style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}> · {text}</span>;
}
