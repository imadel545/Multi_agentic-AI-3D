import { Database, FileSearch, Network, ScrollText } from "lucide-react";

import { useDocumentPack } from "../api/hooks";
import type { StudioEvent } from "../api/types";
import { Badge, StatusBadge } from "../components/Badge";
import { JsonBlock } from "../components/JsonBlock";
import { EmptyState } from "../components/Primitives";
import { DocumentPackPanel } from "../features/document-pack/DocumentPackPanel";
import { groupPresentedEvents } from "../lib/eventPresenter";
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
    <footer className="bottom-dock intelligence-dock">
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
          {pack.data?.spec ? (
            <JsonBlock value={pack.data.spec} />
          ) : (
            <EmptyState
              title="No ProjectDesignSpec loaded"
              description="Select a document pack to inspect extracted fields, source pages and corrections."
            />
          )}
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
  if (!events.length) {
    return (
      <EmptyState
        title="No agent event loaded"
        description="Start a generation or select a workflow to see the agentic timeline."
      />
    );
  }
  const groups = groupPresentedEvents(events);
  return (
    <div className="event-phase-board">
      {groups.map(([phase, items]) => (
        <section className="event-phase" key={phase}>
          <header>
            <strong>{phase}</strong>
            <Badge tone="idle">{items.length}</Badge>
          </header>
          {items
            .slice()
            .reverse()
            .slice(0, 5)
            .map((event, index) => (
              <article className={`narrative-event event-${event.status}`} key={`${event.title}-${index}`}>
                <div>
                  <strong>{event.title}</strong>
                  <p>{event.summary}</p>
                  <span>
                    {event.actor} · {event.time}
                  </span>
                </div>
                <StatusBadge status={event.status} />
                {event.detail ? (
                  <details>
                    <summary>Détail</summary>
                    <code>{event.detail}</code>
                  </details>
                ) : null}
              </article>
            ))}
        </section>
      ))}
    </div>
  );
}
