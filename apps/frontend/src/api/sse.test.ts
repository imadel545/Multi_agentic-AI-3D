import { describe, expect, it, vi } from "vitest";
import { openWorkflowEventStream } from "./sse";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  closed = false;
  listeners = new Map<string, EventListener>();

  constructor(public readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, payload: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(payload) });
    this.listeners.get(type)?.(event);
  }
}

describe("SSE adapter", () => {
  it("normalizes backend events and closes on terminal", () => {
    const onEvent = vi.fn();
    const onTerminal = vi.fn();
    const onError = vi.fn();

    openWorkflowEventStream(
      "http://127.0.0.1:8000/designs/wf_1/events/stream",
      { onError, onEvent, onTerminal },
      FakeEventSource as unknown as new (url: string) => EventSource
    );

    const source = FakeEventSource.instances.at(-1)!;
    source.emit("workflow_completed", {
      event_id: "evt_terminal",
      sequence: 9,
      event_type: "workflow_completed",
      workflow_id: "wf_1",
      timestamp: "2026-06-16T10:00:00Z",
      payload: {
        human_label: "Design prêt",
        progress_message: "Le GLB et les rapports sont disponibles.",
        status: "completed"
      }
    });

    expect(onError).not.toHaveBeenCalled();
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: "workflow_completed",
        sequence: 9,
        human_label: "Design prêt",
        progress_message: "Le GLB et les rapports sont disponibles."
      })
    );
    expect(onTerminal).toHaveBeenCalledOnce();
    expect(source.closed).toBe(true);
  });

  it("reports stream failure for polling fallback", () => {
    const onError = vi.fn();

    openWorkflowEventStream(
      "http://127.0.0.1:8000/designs/wf_1/events/stream",
      { onError, onEvent: vi.fn(), onTerminal: vi.fn() },
      FakeEventSource as unknown as new (url: string) => EventSource
    );

    const source = FakeEventSource.instances.at(-1)!;
    source.onerror?.();

    expect(onError).toHaveBeenCalledWith("connection_lost");
    expect(source.closed).toBe(false);
    source.onerror?.();
    source.onerror?.();
    expect(source.closed).toBe(true);
  });

  it("reports a typed sequence gap without exposing transport copy", () => {
    const onError = vi.fn();
    openWorkflowEventStream(
      "http://127.0.0.1:8000/designs/wf_1/events/stream",
      { onError, onEvent: vi.fn(), onTerminal: vi.fn() },
      FakeEventSource as unknown as new (url: string) => EventSource
    );
    const source = FakeEventSource.instances.at(-1)!;
    for (const sequence of [4, 6]) {
      source.emit("node_completed", {
        event_id: `evt_${sequence}`,
        sequence,
        event_type: "node_completed",
        workflow_id: "wf_1",
        timestamp: "2026-07-15T10:00:00Z",
        payload: {}
      });
    }
    expect(onError).toHaveBeenCalledWith("sequence_gap");
  });

  it("treats an applied edit as a terminal revision event", () => {
    const onTerminal = vi.fn();
    openWorkflowEventStream(
      "http://127.0.0.1:8000/designs/wf_1/events/stream",
      { onError: vi.fn(), onEvent: vi.fn(), onTerminal },
      FakeEventSource as unknown as new (url: string) => EventSource
    );
    const source = FakeEventSource.instances.at(-1)!;

    source.emit("edit_patch_applied", {
      event_id: "evt_edit",
      sequence: 12,
      event_type: "edit_patch_applied",
      workflow_id: "wf_1",
      timestamp: "2026-07-15T10:00:00Z",
      payload: { status: "completed", version_id: "v2" }
    });

    expect(onTerminal).toHaveBeenCalledOnce();
    expect(source.closed).toBe(true);
  });
});
