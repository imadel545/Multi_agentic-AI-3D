import { Clock3 } from "lucide-react";
import { useEffect, useState } from "react";

import { openEventStream } from "../../api/hooks";
import type { StudioEvent } from "../../api/types";
import { Badge } from "../../components/Badge";
import { groupPresentedEvents } from "../../lib/eventPresenter";

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
  const groups = groupPresentedEvents(merged);

  return (
    <section className="timeline-panel">
      <div className="panel-heading compact">
        <Clock3 size={16} />
        <h2>Agent Timeline</h2>
        <Badge tone={streamMode === "sse" ? "good" : "warn"}>{streamMode}</Badge>
      </div>
      <div className="timeline-list">
        {groups.length ? (
          groups.map(([phase, phaseEvents]) => (
            <section className="timeline-phase" key={phase}>
              <h3>{phase}</h3>
              {phaseEvents
                .slice()
                .reverse()
                .map((event, index) => (
                  <article className="timeline-event" key={`${event.title}-${index}`}>
                    <div className={`event-dot event-${event.status}`} />
                    <div>
                      <strong>{event.title}</strong>
                      <p>{event.summary}</p>
                      <span>
                        {event.actor} · {event.time}
                      </span>
                    </div>
                  </article>
                ))}
            </section>
          ))
        ) : (
          <div className="empty-state">No workflow events yet</div>
        )}
      </div>
    </section>
  );
}
