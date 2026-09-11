import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { TelecomStudioApi } from "../api/client";
import type { Conversation } from "../api/schemas";
import { DurableConversation } from "./DurableConversation";

afterEach(cleanup);
function history(workflowId: string, text: string): Conversation {
  return { workflow_id: workflowId, history_status: "recorded", messages: [{
    message_id: "request", role: "user", text, timestamp: "2026-09-11T10:00:00Z",
    operation_id: null, target_semantic_root: null, version_id: null
  }] };
}

it("restores recorded requests on remount without requiring version descriptions", async () => {
  const apiClient = { conversation: vi.fn().mockResolvedValue(history("wf_a", "Descendre cette radio de 40 cm.")) } as unknown as TelecomStudioApi;
  const first = render(<DurableConversation apiClient={apiClient} workflowId="wf_a" revision="one" busy={false} />);
  expect(await screen.findByText("Descendre cette radio de 40 cm.")).toBeInTheDocument();
  first.unmount();
  render(<DurableConversation apiClient={apiClient} workflowId="wf_a" revision="one" busy={false} />);
  expect(await screen.findByText("Descendre cette radio de 40 cm.")).toBeInTheDocument();
  expect(apiClient.conversation).toHaveBeenCalledTimes(2);
});

it("discards an older workflow response after switching designs", async () => {
  let resolveA!: (value: Conversation) => void;
  const pendingA = new Promise<Conversation>((resolve) => { resolveA = resolve; });
  const apiClient = { conversation: vi.fn((id: string) =>
    id === "wf_a" ? pendingA : Promise.resolve(history("wf_b", "Demande B"))
  ) } as unknown as TelecomStudioApi;
  const view = render(<DurableConversation apiClient={apiClient} workflowId="wf_a" revision="one" busy={false} />);
  view.rerender(<DurableConversation apiClient={apiClient} workflowId="wf_b" revision="one" busy={false} />);
  expect(await screen.findByText("Demande B")).toBeInTheDocument();
  resolveA(history("wf_a", "Demande A"));
  await waitFor(() => expect(screen.queryByText("Demande A")).not.toBeInTheDocument());
});

it("keeps loaded messages visible when synchronization fails", async () => {
  const conversation = vi.fn().mockResolvedValueOnce(history("wf_a", "Demande conservée"))
    .mockRejectedValueOnce(new Error("offline"));
  const apiClient = { conversation } as unknown as TelecomStudioApi;
  const view = render(<DurableConversation
    activeContext={<p>Contexte actif hors journal</p>}
    apiClient={apiClient}
    workflowId="wf_a"
    revision="one"
    busy={false}
  />);
  await screen.findByText("Demande conservée");
  view.rerender(<DurableConversation
    activeContext={<p>Contexte actif hors journal</p>}
    apiClient={apiClient}
    workflowId="wf_a"
    revision="two"
    busy={false}
  />);
  expect(await screen.findByRole("alert")).toHaveTextContent("n’a pas pu être synchronisée");
  expect(screen.getByText("Demande conservée")).toBeInTheDocument();
  expect(screen.getByText("Contexte actif hors journal")).toBeInTheDocument();
});

it("keeps real active context distinct from a partial legacy journal", async () => {
  const apiClient = {
    conversation: vi.fn().mockResolvedValue({ ...history("wf_a", "Ancienne modification"), history_status: "legacy_partial" })
  } as unknown as TelecomStudioApi;
  render(<DurableConversation
    activeContext={<p>Version active connue</p>}
    apiClient={apiClient}
    workflowId="wf_a"
    revision="one"
    busy={false}
  />);
  expect(await screen.findByText("Ancienne modification")).toBeInTheDocument();
  expect(screen.getByText("Version active connue")).toBeInTheDocument();
  expect(screen.getByText("Historique ancien partiel", { exact: false })).toBeInTheDocument();
});
