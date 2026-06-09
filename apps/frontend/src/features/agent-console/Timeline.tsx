import { Clock3 } from "lucide-react";
import { useEffect, useState } from "react";

import { openEventStream } from "../../api/hooks";
import type { StudioEvent } from "../../api/types";
import { Badge } from "../../components/Badge";
import { stringifyCompact } from "../../lib/format";

type TimelineProps = {
  workflowId?: string;
  events?: StudioEvent[];
};

export function Timeline({ workflowId, events = [] }: TimelineProps) {
  const [streamEvents, setStreamEvents] = useState<StudioEvent[]>([]);
  const [streamMode, setStreamMode] = useState<"sse" | "polling">("polling");

  useEffect(() => {
    if (!workflowId) return undefined;
    setStreamEvents([]);
    setStreamMode("sse");
    return openEventStream(
      workflowId,
      (event) => setStreamEvents((current) => [...current, event].slice(-80)),
      () => setStreamMode("polling"),
    );
  }, [workflowId]);

  const merged = streamMode === "sse" && streamEvents.length ? streamEvents : events;

  return (
    <section className="timeline-panel">
      <div className="panel-heading compact">
        <Clock3 size={16} />
        <h2>Agent Timeline</h2>
        <Badge tone={streamMode === "sse" ? "good" : "warn"}>{streamMode}</Badge>
      </div>
      <div className="timeline-list">
        {merged.length ? (
          merged
            .slice()
            .reverse()
            .map((event, index) => (
              <article className="timeline-event" key={`${event.event_id ?? index}-${index}`}>
                <div className="event-dot" />
                <div>
                  <strong>{event.event_type}</strong>
                  <p>{event.created_at ?? event.timestamp ?? "time pending"}</p>
                  {event.payload ? (
                    <span>{stringifyCompact(event.payload).slice(0, 180)}</span>
                  ) : null}
                </div>
              </article>
            ))
        ) : (
          <div className="empty-state">No workflow events yet</div>
        )}
      </div>
    </section>
  );
}
