import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { normalizeWorkflowEvent } from "../api/sse";
import { ChatProgress } from "./ChatProgress";
import { ConversationTray } from "./ConversationTray";

afterEach(cleanup);
it("keeps messages mounted when folded and reveals a new actionable error", () => {
  const { rerender } = render(
    <ConversationTray attention={null}>
      <input aria-label="Draft" defaultValue="Keep this" />
    </ConversationTray>
  );
  fireEvent.click(screen.getByRole("button", { name: "Conversation" }));
  const draft = screen.getByRole("textbox");
  draft.focus();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("button", { name: "Conversation" })).toHaveFocus();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  rerender(
    <ConversationTray attention="Upload failed">
      <input aria-label="Draft" defaultValue="Keep this" />
    </ConversationTray>
  );
  expect(screen.getByRole("textbox")).toBe(draft);
  expect(draft).toHaveValue("Keep this");
});
it("updates chat activity from observed events without claiming completion while running", () => {
  const { rerender } = render(
    <ChatProgress events={[]} phase="idle" editing={false} />
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  const event = normalizeWorkflowEvent({
    event_id: "evt_one",
    workflow_id: "wf_one",
    timestamp: "2026-09-14T01:00:00Z",
    event_type: "node_started",
    payload: {
      phase: "generation",
      status: "running",
      node: "generate_blender",
      warnings: [],
      errors: [],
      artifact_refs: []
    }
  });
  rerender(<ChatProgress events={[event]} phase="running" editing={false} />);
  expect(screen.getByRole("status")).toHaveTextContent("Construction du modèle 3D");
  expect(screen.getByRole("status")).not.toHaveTextContent("disponible");
  rerender(<ChatProgress events={[event]} phase="failed" editing={false} />);
  expect(screen.getByRole("status")).toHaveTextContent("correction");
  rerender(<ChatProgress events={[event]} phase="completed" editing />);
  expect(screen.getByRole("status")).toHaveTextContent("Modification du modèle en cours");
});
