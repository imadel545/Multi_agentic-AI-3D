import { Database, FileSearch, Network, ScrollText } from "lucide-react";

import { useDocumentPack } from "../api/hooks";
import type { StudioEvent } from "../api/types";
import { Badge, StatusBadge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { stringifyCompact } from "../lib/format";
import { DocumentPackPanel } from "../features/document-pack/DocumentPackPanel";
import { useStudioStore, type BottomTab } from "../stores/studioStore";

type BottomDockProps = {
  events?: StudioEvent[];
};

const tabs: Array<{ id: BottomTab; label: string; icon: typeof FileSearch }> = [
  { id: "documents", label: "Documents", icon: FileSearch },
  { id: "provenance", label: "Provenance", icon: Network },
  { id: "events", label: "Events", icon: ScrollText },
  { id: "memory", label: "Memory", icon: Database },
];

export function BottomDock({ events }: BottomDockProps) {
  const bottomTab = useStudioStore((state) => state.bottomTab);
  const setBottomTab = useStudioStore((state) => state.setBottomTab);
  const activePackId = useStudioStore((state) => state.activePackId);
  const pack = useDocumentPack(activePackId);

  return (
    <footer className="bottom-dock">
      <div className="dock-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              className={bottomTab === tab.id ? "active" : ""}
              key={tab.id}
              type="button"
              onClick={() => setBottomTab(tab.id)}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>
      {bottomTab === "documents" ? <DocumentPackPanel /> : null}
      {bottomTab === "provenance" ? (
        <section className="dock-panel">
          <h2>Provenance and consolidated specification</h2>
          <JsonBlock value={pack.data?.spec} empty="No ProjectDesignSpec loaded." />
        </section>
      ) : null}
      {bottomTab === "events" ? (
        <section className="dock-panel">
          <div className="panel-heading compact">
            <ScrollText size={16} />
            <h2>Agent events</h2>
            <Badge tone={(events ?? pack.data?.events)?.length ? "good" : "idle"}>
              {(events ?? pack.data?.events)?.length ?? 0}
            </Badge>
          </div>
          <EventDock events={events ?? pack.data?.events ?? []} />
        </section>
      ) : null}
      {bottomTab === "memory" ? (
        <section className="dock-panel">
          <h2>Document-pack memory summary</h2>
          <JsonBlock value={pack.data?.memory} empty="No memory summary loaded." />
        </section>
      ) : null}
    </footer>
  );
}

function EventDock({ events }: { events: StudioEvent[] }) {
  if (!events.length) return <div className="empty-state">No events loaded.</div>;
  return (
    <div className="event-table">
      {events
        .slice()
        .reverse()
        .slice(0, 18)
        .map((event, index) => (
          <article key={`${event.event_id ?? event.event_type}-${index}`}>
            <div>
              <strong>{event.event_type}</strong>
              <p>{event.created_at ?? event.timestamp ?? "time pending"}</p>
            </div>
            <p>{event.payload ? stringifyCompact(event.payload).slice(0, 140) : "no payload"}</p>
            <StatusBadge status={event.event_type.includes("failed") ? "failed" : "completed"} />
          </article>
        ))}
    </div>
  );
}
