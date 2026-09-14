import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import WorkspaceShell from "./WorkspaceShell";

vi.mock("../App", () => ({
  default: ({
    initialPrompt,
    initialWorkflowId,
    onDraftChange,
    onBusyChange,
    onMutationBusyChange,
  }: {
    initialPrompt: string;
    initialWorkflowId: string | null;
    onDraftChange: (text: string) => void;
    onBusyChange: (busy: boolean) => void;
    onMutationBusyChange: (busy: boolean) => void;
  }) => {
    const [value, setValue] = useState(initialPrompt);
    return (
      <section>
        <button onClick={() => { onBusyChange(true); onMutationBusyChange(true); }}>Envoyer la demande</button>
        <button onClick={() => onMutationBusyChange(false)}>Demande acceptée</button>
        <span>{initialWorkflowId ?? "Conversation vide"}</span>
        <input
          aria-label="Brouillon du chat"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            onDraftChange(e.target.value);
          }}
        />
      </section>
    );
  },
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

it("isolates drafts and restores only the chosen chat, including after a reload", async () => {
  const common = {
    project_id: "project_one",
    created_at: "2026-09-13T12:00:00Z",
    updated_at: "2026-09-13T12:00:00Z",
  };
  const chats = [
    {
      ...common,
      chat_id: "chat_one",
      title: "Premier",
      draft_prompt: "Pylône nord",
      workflow_id: "wf_one",
      document_pack_id: null,
    },
    {
      ...common,
      chat_id: "chat_two",
      title: "Deuxième",
      draft_prompt: "Site sud",
      workflow_id: null,
      document_pack_id: null,
    },
  ];
  const draftPatches: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL, options?: RequestInit) => {
      const path = new URL(input).pathname;
      let result: unknown;
      if (path === "/workspace/projects")
        result = [{ ...common, title: "Projet réel" }];
      else if (path.endsWith("/chats")) result = chats;
      else {
        const chat = chats.find((c) => path.endsWith(c.chat_id));
        if (!chat) return new Response("", { status: 404 });
        if (options?.method === "PATCH") {
          const patch = JSON.parse(String(options.body));
          Object.assign(chat, patch);
          if (typeof patch.draft_prompt === "string")
            draftPatches.push(patch.draft_prompt);
        }
        result = chat;
      }
      return new Response(JSON.stringify(result), {
        headers: { "content-type": "application/json" },
      });
    }),
  );
  render(<WorkspaceShell />);
  fireEvent.click(await screen.findByRole("button", { name: "Projet réel" }));
  fireEvent.click(await screen.findByRole("button", { name: "Premier" }));
  expect(await screen.findByDisplayValue("Pylône nord")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Envoyer la demande" }));
  expect(screen.getByRole("button", { name: "Deuxième" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Nouveau projet" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Demande acceptée" }));
  expect(screen.getByRole("button", { name: "Deuxième" })).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Brouillon du chat"), {
    target: { value: "Pylône nord ré" },
  });
  fireEvent.change(screen.getByLabelText("Brouillon du chat"), {
    target: { value: "Pylône nord révis" },
  });
  fireEvent.change(screen.getByLabelText("Brouillon du chat"), {
    target: { value: "Pylône nord révisé" },
  });
  await waitFor(() => expect(chats[0].draft_prompt).toBe("Pylône nord révisé"));
  expect(draftPatches).toEqual(["Pylône nord révisé"]);
  fireEvent.click(screen.getByRole("button", { name: "Deuxième" }));
  expect(await screen.findByDisplayValue("Site sud")).toBeInTheDocument();
  expect(screen.queryByText("wf_one")).not.toBeInTheDocument();
  expect(screen.getByText("Conversation vide")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Premier" }));
  expect(
    await screen.findByDisplayValue("Pylône nord révisé"),
  ).toBeInTheDocument();
  cleanup();
  render(<WorkspaceShell />);
  expect(
    await screen.findByDisplayValue("Pylône nord révisé"),
  ).toBeInTheDocument();
  expect(screen.getByText("wf_one")).toBeInTheDocument();
});

it("does not let a delayed deep-link restore replace a newer project choice", async () => {
  const delayedChats = deferred<Response>();
  const projects = [
    {
      project_id: "project_one",
      title: "Projet mémorisé",
      created_at: "2026-09-13T12:00:00Z",
      updated_at: "2026-09-13T12:00:00Z",
    },
    {
      project_id: "project_two",
      title: "Projet choisi",
      created_at: "2026-09-13T13:00:00Z",
      updated_at: "2026-09-13T13:00:00Z",
    },
  ];
  window.history.replaceState(null, "", "/#project=project_one&chat=chat_one");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL) => {
      const path = new URL(input).pathname;
      if (path === "/workspace/projects")
        return new Response(JSON.stringify(projects), {
          headers: { "content-type": "application/json" },
        });
      if (path === "/workspace/projects/project_one/chats")
        return delayedChats.promise;
      if (path === "/workspace/projects/project_two/chats")
        return new Response("[]", {
          headers: { "content-type": "application/json" },
        });
      return new Response("", { status: 404 });
    }),
  );

  render(<WorkspaceShell />);
  fireEvent.click(await screen.findByRole("button", { name: "Projet choisi" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Projet choisi" }),
    ).toHaveAttribute("aria-current", "page"),
  );
  await waitFor(() =>
    expect(window.location.hash).toBe("#project=project_two"),
  );

  delayedChats.resolve(
    new Response(
      JSON.stringify([
        {
          ...projects[0],
          chat_id: "chat_one",
          title: "Conversation mémorisée",
          draft_prompt: "Ancien brouillon",
          workflow_id: null,
          document_pack_id: null,
        },
      ]),
      { headers: { "content-type": "application/json" } },
    ),
  );

  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Projet choisi" }),
    ).toHaveAttribute("aria-current", "page"),
  );
  expect(
    screen.getByRole("button", { name: "Projet mémorisé" }),
  ).not.toHaveAttribute("aria-current");
  expect(screen.queryByText("Conversation mémorisée")).not.toBeInTheDocument();
  expect(window.location.hash).toBe("#project=project_two");
});

it("keeps the latest draft visible and blocks navigation when saving fails", async () => {
  const project = {
    project_id: "project_one",
    title: "Projet réel",
    created_at: "2026-09-13T12:00:00Z",
    updated_at: "2026-09-13T12:00:00Z",
  };
  const chats = [
    {
      ...project,
      chat_id: "chat_one",
      title: "Premier",
      draft_prompt: "Demande initiale",
      workflow_id: null,
      document_pack_id: null,
    },
    {
      ...project,
      chat_id: "chat_two",
      title: "Deuxième",
      draft_prompt: "Autre demande",
      workflow_id: null,
      document_pack_id: null,
    },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL, options?: RequestInit) => {
      const path = new URL(input).pathname;
      if (path === "/workspace/projects")
        return new Response(JSON.stringify([project]));
      if (path.endsWith("/chats")) return new Response(JSON.stringify(chats));
      if (options?.method === "PATCH") return new Response("", { status: 503 });
      const value = chats.find((item) => path.endsWith(item.chat_id));
      return value
        ? new Response(JSON.stringify(value))
        : new Response("", { status: 404 });
    }),
  );

  render(<WorkspaceShell />);
  fireEvent.click(await screen.findByRole("button", { name: "Projet réel" }));
  fireEvent.click(await screen.findByRole("button", { name: "Premier" }));
  fireEvent.change(await screen.findByLabelText("Brouillon du chat"), {
    target: { value: "Dernière version non enregistrée" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Deuxième" }));

  expect(
    await screen.findByDisplayValue("Dernière version non enregistrée"),
  ).toBeInTheDocument();
  expect(screen.getByText("Conversation vide")).toBeInTheDocument();
  expect(
    await screen.findByText(/Votre texte reste affiché/),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Premier" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("keeps project and conversation deletion behind the matching three-dot menus", async () => {
  const project = {
    project_id: "project_one",
    title: "Projet radio",
    created_at: "2026-09-13T12:00:00Z",
    updated_at: "2026-09-13T12:00:00Z",
  };
  const chats = [
    {
      ...project,
      chat_id: "chat_one",
      title: "Secteur nord",
      draft_prompt: "",
      workflow_id: null,
      document_pack_id: null,
    },
  ];
  const requests: Array<{ path: string; method: string }> = [];
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL, options?: RequestInit) => {
      const path = new URL(input).pathname;
      const method = options?.method ?? "GET";
      requests.push({ path, method });
      if (path === "/workspace/projects")
        return new Response(JSON.stringify([project]));
      if (path.endsWith("/chats"))
        return new Response(JSON.stringify(chats));
      if (method === "DELETE") return new Response(null, { status: 204 });
      const value = chats.find((item) => path.endsWith(item.chat_id));
      return value
        ? new Response(JSON.stringify(value))
        : new Response("", { status: 404 });
    }),
  );

  render(<WorkspaceShell />);
  fireEvent.click(await screen.findByRole("button", { name: "Projet radio" }));
  expect(
    await screen.findByLabelText("Conversations du projet Projet radio"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Supprimer le projet" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Supprimer la conversation" }),
  ).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Options de la conversation Secteur nord" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Supprimer la conversation" }),
  );

  await waitFor(() =>
    expect(requests).toContainEqual({
      path: "/workspace/chats/chat_one",
      method: "DELETE",
    }),
  );
  expect(screen.queryByRole("button", { name: "Secteur nord" })).not.toBeInTheDocument();
});

it("keeps the new conversation action beside the selected project menu", async () => {
  const project = {
    project_id: "project_circet",
    title: "circet",
    created_at: "2026-09-13T12:00:00Z",
    updated_at: "2026-09-13T12:00:00Z",
  };
  const requests: Array<{ method: string; path: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL, options?: RequestInit) => {
      const path = new URL(input).pathname;
      const method = options?.method ?? "GET";
      requests.push({ method, path });
      if (path === "/workspace/projects") {
        return new Response(JSON.stringify([project]), {
          headers: { "content-type": "application/json" },
        });
      }
      if (path === "/workspace/projects/project_circet/chats") {
        if (method === "POST") {
          return new Response(
            JSON.stringify({
              ...project,
              chat_id: "chat_created",
              title: "Nouvelle conversation",
              draft_prompt: "",
              workflow_id: null,
              document_pack_id: null,
            }),
            { headers: { "content-type": "application/json" } },
          );
        }
        return new Response("[]", {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("", { status: 404 });
    }),
  );

  render(<WorkspaceShell />);
  const projectButton = await screen.findByRole("button", { name: "circet" });
  fireEvent.click(projectButton);
  const newChatButton = await screen.findByRole("button", { name: "Nouvelle conversation" });
  expect(newChatButton.parentElement).toHaveClass("workspace-project-actions");
  expect(
    screen.getByRole("img", { name: "Circet — Créateur de réseaux" }),
  ).toHaveAttribute("src", "/brand/circet-logo.jpg");
  const sectionTitle = screen.getByText("Conversations");
  expect(sectionTitle.parentElement).not.toContainElement(newChatButton);
  fireEvent.click(newChatButton);
  await waitFor(() =>
    expect(requests).toContainEqual({
      method: "POST",
      path: "/workspace/projects/project_circet/chats",
    }),
  );
  expect(await screen.findByText("Conversation vide")).toBeInTheDocument();
});

describe("workspace selection memory", () => {
  it("reopens the last project and conversation after a reload without a hash", async () => {
    const { readLastWorkspaceSelection, writeLastWorkspaceSelection } = await import("./workspaceSelection");
    const store = new Map<string, string>();
    const storage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
    } as unknown as Storage;
    writeLastWorkspaceSelection("project_a", "chat_b", storage);
    expect(readLastWorkspaceSelection(storage)).toEqual({ projectId: "project_a", chatId: "chat_b" });
    writeLastWorkspaceSelection(null, null, storage);
    expect(readLastWorkspaceSelection(storage)).toBeNull();
    expect(readLastWorkspaceSelection({ getItem: () => "{broken" } as unknown as Storage)).toBeNull();
  });
});
