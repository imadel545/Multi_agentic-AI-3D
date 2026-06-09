import { Database, FileSearch, Network, ScrollText } from "lucide-react";

import { useDocumentPack } from "../api/hooks";
import type { StudioEvent } from "../api/types";
import { JsonBlock } from "../components/JsonBlock";
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
          <h2>Raw workflow events</h2>
          <JsonBlock value={events ?? pack.data?.events} empty="No events loaded." />
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
