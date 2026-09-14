import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { normalizeWorkflowEvent } from "../api/sse";
import { TaskElapsedTime } from "./TaskElapsedTime";

const event = (type: string, timestamp: string) => normalizeWorkflowEvent({
  event_id: `${type}-${timestamp}`, workflow_id: "wf-timer", timestamp, event_type: type, payload: { warnings: [], errors: [], artifact_refs: [] }
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("restores a running task from server events and freezes at its recorded finish", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-09-14T12:01:00Z"));
  const events = [event("design_created", "2026-09-14T12:00:00Z")];
  const { rerender } = render(<TaskElapsedTime events={events} busy />);
  expect(screen.getByLabelText("Temps écoulé : 1 min 00 s")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(5000));
  expect(screen.getByLabelText("Temps écoulé : 1 min 05 s")).toBeInTheDocument();
  rerender(<TaskElapsedTime events={[...events, event("workflow_completed", "2026-09-14T12:01:03Z")]} busy={false} />);
  act(() => vi.advanceTimersByTime(60000));
  expect(screen.getByLabelText("Temps écoulé : 1 min 03 s")).toBeInTheDocument();
});

it("starts edits at submission then uses their own persisted events, not original design age", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-09-14T13:00:00Z"));
  const history = [event("design_created", "2026-09-14T12:00:00Z"), event("workflow_completed", "2026-09-14T12:02:00Z")];
  const { rerender } = render(<TaskElapsedTime events={history} busy={false} />);
  rerender(<TaskElapsedTime events={history} busy />);
  act(() => vi.advanceTimersByTime(4000));
  expect(screen.getByLabelText("Temps écoulé : 4 s")).toBeInTheDocument();
  const edited = [...history, event("edit_requested", "2026-09-14T13:00:01Z")];
  rerender(<TaskElapsedTime events={edited} busy />);
  expect(screen.getByLabelText("Temps écoulé : 3 s")).toBeInTheDocument();
  rerender(<TaskElapsedTime events={[...edited, event("edit_outcome", "2026-09-14T13:00:03Z")]} busy={false} />);
  expect(screen.getByLabelText("Temps écoulé : 2 s")).toBeInTheDocument();
});

it("does not invent a historical duration when timestamps are unavailable", () => {
  render(<TaskElapsedTime events={[]} busy={false} />);
  expect(screen.queryByLabelText(/Temps écoulé/)).not.toBeInTheDocument();
});

it("restores a completed duration even when the frontend event window omits its start", () => {
  render(<TaskElapsedTime events={[]} busy={false} timing={{
    task_started_at: "2026-09-14T12:00:00Z", task_finished_at: "2026-09-14T12:08:12Z"
  }} />);
  expect(screen.getByLabelText("Temps écoulé : 8 min 12 s")).toBeInTheDocument();
});
