import { lazy, Suspense, useEffect } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import {
  useDesign,
  useDesignEvents,
  useDesigns,
  useHealth,
  useStudioMutations,
} from "../api/hooks";
import { AgentConsole } from "../features/agent-console/AgentConsole";
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
    if (!activeWorkflowId && designs.data?.length) {
      const preferredWorkflow =
        designs.data.find((design) => design.status === "completed" && design.generation_mode)
          ?.workflow_id ?? designs.data[0].workflow_id;
      setActiveWorkflowId(preferredWorkflow);
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
      <main className="studio-product-shell">
        <Group orientation="vertical">
          <Panel defaultSize="73%" minSize="520px">
            <Group orientation="horizontal" className="studio-workspace">
              <Panel defaultSize="26%" minSize="320px" maxSize="440px">
                <AgentConsole workflow={workflow.data} events={events.data} />
              </Panel>
              <Separator className="resize-handle resize-handle-vertical" />
              <Panel defaultSize="50%" minSize="560px">
                <Suspense
                  fallback={<div className="viewer-shell viewer-empty">Loading 3D viewer...</div>}
                >
                  <ThreeViewer workflow={workflow.data} />
                </Suspense>
              </Panel>
              <Separator className="resize-handle resize-handle-vertical" />
              <Panel defaultSize="24%" minSize="320px" maxSize="440px">
                <InspectorPanel workflow={workflow.data} />
              </Panel>
            </Group>
          </Panel>
          <Separator className="resize-handle resize-handle-horizontal" />
          <Panel defaultSize="27%" minSize="150px" maxSize="360px">
            <BottomDock events={events.data} />
          </Panel>
        </Group>
      </main>
    </div>
  );
}
