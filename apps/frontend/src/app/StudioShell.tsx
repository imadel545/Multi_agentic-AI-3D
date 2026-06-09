import { lazy, Suspense, useEffect } from "react";

import {
  useDesign,
  useDesignEvents,
  useDesigns,
  useHealth,
  useStudioMutations,
} from "../api/hooks";
import { AgentConsole } from "../features/agent-console/AgentConsole";
import { Timeline } from "../features/agent-console/Timeline";
import { InspectorPanel } from "../features/qa-panel/InspectorPanel";
import { useStudioStore } from "../stores/studioStore";
import { BottomDock } from "./BottomDock";
import { TopBar } from "./TopBar";

const ThreeViewer = lazy(() =>
  import("../features/three-viewer/ThreeViewer").then((module) => ({
    default: module.ThreeViewer,
  })),
);

export function StudioShell() {
  const activeWorkflowId = useStudioStore((state) => state.activeWorkflowId);
  const setActiveWorkflowId = useStudioStore((state) => state.setActiveWorkflowId);
  const health = useHealth();
  const designs = useDesigns();
  const workflow = useDesign(activeWorkflowId);
  const events = useDesignEvents(activeWorkflowId);
  useStudioMutations(activeWorkflowId);

  useEffect(() => {
    if (!activeWorkflowId && designs.data?.[0]?.workflow_id) {
      setActiveWorkflowId(designs.data[0].workflow_id);
    }
  }, [activeWorkflowId, designs.data, setActiveWorkflowId]);

  return (
    <div className="studio-root">
      <TopBar backendStatus={health.data?.status} workflow={workflow.data} />
      {health.isError ? (
        <div className="backend-warning">
          Backend offline or unreachable at the configured API URL. Controls stay visible, but
          generation, uploads and artifacts require FastAPI.
        </div>
      ) : null}
      <div className="studio-grid">
        <div className="left-rail">
          <AgentConsole />
          <Timeline workflowId={activeWorkflowId} events={events.data} />
        </div>
        <Suspense fallback={<div className="viewer-shell viewer-empty">Loading 3D viewer...</div>}>
          <ThreeViewer workflow={workflow.data} />
        </Suspense>
        <InspectorPanel workflow={workflow.data} />
      </div>
      <BottomDock events={events.data} />
    </div>
  );
}
