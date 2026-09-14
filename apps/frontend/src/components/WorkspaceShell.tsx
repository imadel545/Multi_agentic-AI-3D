import { useEffect, useMemo, useRef, useState } from "react";
import {
  Folder,
  Plus,
  MessageSquare,
  ArrowUpRight,
  MoreHorizontal,
  RadioTower,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import App from "../App";
import { api } from "../api/client";
import { WorkspaceApi, type Chat, type Project } from "../api/workspace";
import type { WorkflowStatus } from "../api/schemas";
import "../workspace.css";

const DRAFT_SAVE_ERROR =
  "Le brouillon n’a pas pu être enregistré. Votre texte reste affiché; réessayez avant de changer de conversation.";

export default function WorkspaceShell() {
  const client = useMemo(() => new WorkspaceApi(api.baseUrl), []);
  const [initialSelection] = useState(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    return {
      projectId: params.get("project"),
      chatId: params.get("chat"),
    };
  });
  const [projects, setProjects] = useState<Project[]>([]),
    [chats, setChats] = useState<Chat[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null),
    [chat, setChat] = useState<Chat | null>(null);
  const [busy, setBusy] = useState(false),
    [working, setWorking] = useState(false),
    [mutationBusy, setMutationBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [projectTitle, setProjectTitle] = useState(""),
    [newProject, setNewProject] = useState(false);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const sidebarControl = useRef<HTMLButtonElement>(null);
  const toggleSidebar = () => {
    setOpenMenu(null);
    setSidebarOpen((open) => !open);
    requestAnimationFrame(() => sidebarControl.current?.focus());
  };
  const menuTriggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [history, setHistory] = useState<WorkflowStatus[] | null>(null);
  const [restored, setRestored] = useState(false);
  const draft = useRef("");
  const activeChatId = useRef(chat?.chat_id);
  activeChatId.current = chat?.chat_id;
  const pendingDraft = useRef<{ chatId: string; value: string } | null>(null);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeDraftSave = useRef<Promise<boolean> | null>(null);
  function persistDraft(chatId: string, value: string) {
    draft.current = value;
    pendingDraft.current = { chatId, value };
    if (draftTimer.current) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      draftTimer.current = null;
      void flushDraft(false);
    }, 350);
  }
  async function flushDraft(raiseOnFailure = true): Promise<boolean> {
    if (draftTimer.current) {
      clearTimeout(draftTimer.current);
      draftTimer.current = null;
    }
    while (activeDraftSave.current || pendingDraft.current) {
      if (activeDraftSave.current) {
        const saved = await activeDraftSave.current;
        if (!saved) {
          if (raiseOnFailure) throw new Error(DRAFT_SAVE_ERROR);
          return false;
        }
        continue;
      }
      const next = pendingDraft.current;
      if (!next) break;
      pendingDraft.current = null;
      activeDraftSave.current = (async () => {
        try {
          const saved = await client.updateChat(next.chatId, {
            draft_prompt: next.value,
          });
          setChats((items) =>
            items.map((item) =>
              item.chat_id === saved.chat_id ? saved : item,
            ),
          );
          setChat((current) =>
            current?.chat_id === saved.chat_id ? saved : current,
          );
          setError((current) =>
            current === DRAFT_SAVE_ERROR ? null : current,
          );
          return true;
        } catch {
          if (!pendingDraft.current) pendingDraft.current = next;
          setError(DRAFT_SAVE_ERROR);
          return false;
        }
      })();
      const saved = await activeDraftSave.current;
      activeDraftSave.current = null;
      if (!saved) {
        if (raiseOnFailure) throw new Error(DRAFT_SAVE_ERROR);
        return false;
      }
    }
    return true;
  }
  const epoch = useRef(0);
  const operationInProgress = useRef(false);
  const locked = busy || working;
  const navigationLocked = busy || mutationBusy;
  useEffect(() => {
    if (!openMenu) return;
    const closeOnPointer = (event: PointerEvent) => {
      if (
        event.target instanceof Element &&
        event.target.closest(".workspace-item-menu")
      ) return;
      setOpenMenu(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const trigger = menuTriggerRefs.current[openMenu];
      setOpenMenu(null);
      window.requestAnimationFrame(() => trigger?.focus());
    };
    document.addEventListener("pointerdown", closeOnPointer);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnPointer);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [openMenu]);
  useEffect(() => {
    if (!restored) return;
    const params = new URLSearchParams();
    if (projectId) params.set("project", projectId);
    if (chat) params.set("chat", chat.chat_id);
    const suffix = params.size > 0 ? `#${params.toString()}` : "";
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${suffix}`,
    );
  }, [projectId, chat?.chat_id, restored]);
  async function perform(task: () => Promise<void>) {
    if (operationInProgress.current) return;
    setOpenMenu(null);
    operationInProgress.current = true;
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Impossible de charger cet espace.",
      );
    } finally {
      operationInProgress.current = false;
      setBusy(false);
    }
  }
  async function saveDraft() {
    await flushDraft(true);
  }
  async function selectProject(id: string) {
    const token = ++epoch.current;
    await saveDraft();
    const items = await client.chats(id);
    if (token !== epoch.current) return;
    setProjectId(id);
    setChats(items);
    setChat(null);
    setHistory(null);
    draft.current = "";
    setRestored(true);
  }
  useEffect(() => {
    let live = true;
    const token = ++epoch.current;
    const selected = initialSelection.projectId;
    const selectedChat = initialSelection.chatId;
    void client
      .projects()
      .then((items) => {
        if (live && token === epoch.current) {
          setProjects(items);
          if (selected && items.some((p) => p.project_id === selected)) {
            void client
              .chats(selected)
              .then((rows) => {
                if (!live || token !== epoch.current) return;
                setProjectId(selected);
                setChats(rows);
                const found = rows.find((c) => c.chat_id === selectedChat);
                if (found) {
                  setChat(found);
                  draft.current = found.draft_prompt;
                }
                setRestored(true);
              })
              .catch(() => {
                if (live && token === epoch.current) {
                  setError("Impossible de restaurer la conversation.");
                  setRestored(true);
                }
              });
          } else {
            setRestored(true);
          }
        }
      })
      .catch(() => {
        if (live && token === epoch.current) {
          setError(
            "Le studio ne peut pas charger vos projets. Vérifiez la connexion et réessayez.",
          );
          setRestored(true);
        }
      });
    return () => {
      live = false;
    };
  }, [client]);
  async function chooseChat(value: Chat) {
    const token = ++epoch.current;
    await saveDraft();
    const fresh = await client.chat(value.chat_id);
    if (token !== epoch.current) return;
    setChat(fresh);
    draft.current = fresh.draft_prompt;
    setHistory(null);
    setRestored(true);
  }
  async function createChat(initialDraft = "") {
    if (!projectId) return;
    await saveDraft();
    ++epoch.current;
    const value = await client.createChat(
      projectId,
      "Nouvelle conversation",
      undefined,
      initialDraft,
    );
    setChats((items) => [value, ...items]);
    setChat(value);
    draft.current = initialDraft;
    setHistory(null);
    setRestored(true);
  }
  async function loadUnlinkedDesigns() {
    const designs: WorkflowStatus[] = [];
    for (let offset = 0; ; offset += 200) {
      const page = await api.listDesigns(200, offset);
      designs.push(...page);
      if (page.length < 200) break;
    }
    const linked = new Set(await client.linkedWorkflowIds());
    setHistory(designs.filter((design) => !linked.has(design.workflow_id)));
  }
  async function retryWorkspaceLoad() {
    const items = await client.projects();
    setProjects(items);
    const targetProject = projectId ?? initialSelection.projectId;
    if (
      !targetProject ||
      !items.some((item) => item.project_id === targetProject)
    )
      return;
    const rows = await client.chats(targetProject);
    setProjectId(targetProject);
    setChats(rows);
    const targetChat = chat?.chat_id ?? initialSelection.chatId;
    if (!targetChat) return;
    const restoredChat = rows.find((item) => item.chat_id === targetChat);
    if (restoredChat) {
      setChat(restoredChat);
      draft.current = restoredChat.draft_prompt;
    }
  }
  async function updateActive(
    patch: Partial<
      Pick<Chat, "workflow_id" | "document_pack_id" | "title" | "draft_prompt">
    >,
  ) {
    if (!chat) return;
    const value = await client.updateChat(chat.chat_id, patch);
    setChats((items) =>
      items.map((c) => (c.chat_id === value.chat_id ? value : c)),
    );
    setChat((current) =>
      current?.chat_id === value.chat_id ? value : current,
    );
  }
  return (
    <div className={`product-shell${sidebarOpen ? "" : " sidebar-collapsed"}`} aria-busy={navigationLocked || !restored}>
      <aside className="project-sidebar" id="workspace-sidebar" hidden={!sidebarOpen} aria-label="Projets et conversations">
        <div className="workspace-brand">
          <RadioTower size={22} />
          <strong>
            Telecom Studio<span>Conception assistée par IA</span>
          </strong>
          <button ref={sidebarControl} className="sidebar-toggle" type="button" aria-label="Replier les projets"
            aria-controls="workspace-sidebar" aria-expanded={sidebarOpen}
            onClick={toggleSidebar}>
            <PanelLeftClose size={18} />
          </button>
        </div>
        <button
          type="button"
          className="workspace-new"
          disabled={navigationLocked}
          aria-expanded={newProject}
          aria-controls="workspace-new-project-form"
          onClick={() => setNewProject(!newProject)}
        >
          <Plus size={17} />
          Nouveau projet
        </button>
        {newProject && (
          <form
            id="workspace-new-project-form"
            className="workspace-project-form"
            onSubmit={(e) => {
              e.preventDefault();
              void perform(async () => {
                await saveDraft();
                ++epoch.current;
                const value = await client.createProject(projectTitle);
                setProjects((items) => [value, ...items]);
                setProjectId(value.project_id);
                setChats([]);
                setChat(null);
                setNewProject(false);
                setProjectTitle("");
                setRestored(true);
              });
            }}
          >
            <input
              autoFocus
              aria-label="Nom du projet"
              placeholder="Nom du projet"
              value={projectTitle}
              maxLength={120}
              onChange={(e) => setProjectTitle(e.target.value)}
            />
            <div className="workspace-project-form-actions">
              <button disabled={navigationLocked || !projectTitle.trim()}>
                Créer
              </button>
              <button
                type="button"
                disabled={navigationLocked}
                onClick={() => {
                  setNewProject(false);
                  setProjectTitle("");
                }}
              >
                Annuler
              </button>
            </div>
          </form>
        )}
        <nav aria-label="Vos projets" className="workspace-projects">
          {projects.map((project) => (
            <div className="workspace-project-node" key={project.project_id}>
              <div className="workspace-project-row">
                <button
                  aria-expanded={projectId === project.project_id}
                  className={
                    projectId === project.project_id
                      ? "workspace-project selected"
                      : "workspace-project"
                  }
                  disabled={navigationLocked}
                  type="button"
                  aria-current={
                    projectId === project.project_id ? "page" : undefined
                  }
                  onClick={() =>
                    void perform(() => selectProject(project.project_id))
                  }
                >
                  <Folder size={16} />
                  <span>{project.title}</span>
                </button>
                <div className="workspace-item-menu">
                  <button
                    aria-controls={`workspace-project-actions-${project.project_id}`}
                    aria-expanded={openMenu === `project:${project.project_id}`}
                    aria-label={`Options du projet ${project.title}`}
                    className="workspace-more"
                    disabled={navigationLocked}
                    onClick={() =>
                      setOpenMenu((current) =>
                        current === `project:${project.project_id}`
                          ? null
                          : `project:${project.project_id}`,
                      )
                    }
                    ref={(element) => {
                      menuTriggerRefs.current[`project:${project.project_id}`] = element;
                    }}
                    type="button"
                  >
                    <MoreHorizontal size={17} />
                  </button>
                  {openMenu === `project:${project.project_id}` ? (
                    <div
                      aria-label={`Actions du projet ${project.title}`}
                      className="workspace-menu-popover"
                      id={`workspace-project-actions-${project.project_id}`}
                      role="group"
                    >
                      {projectId === project.project_id ? (
                        <button
                          disabled={navigationLocked}
                          onClick={() => {
                            setOpenMenu(null);
                            void perform(loadUnlinkedDesigns);
                          }}
                          type="button"
                        >
                          <ArrowUpRight size={15} />
                          Retrouver un design
                        </button>
                      ) : null}
                      <button
                        className="danger"
                        disabled={locked}
                        onClick={() => {
                          setOpenMenu(null);
                          if (
                            window.confirm(
                              "Supprimer ce projet et ses conversations ? Les designs vérifiés resteront disponibles dans l’historique des designs.",
                            )
                          )
                            void perform(async () => {
                              ++epoch.current;
                              if (projectId === project.project_id)
                                await saveDraft();
                              await client.deleteProject(project.project_id);
                              setProjects((items) =>
                                items.filter(
                                  (item) =>
                                    item.project_id !== project.project_id,
                                ),
                              );
                              if (projectId === project.project_id) {
                                setProjectId(null);
                                setChats([]);
                                setChat(null);
                                setHistory(null);
                                draft.current = "";
                              }
                              setRestored(true);
                            });
                        }}
                        type="button"
                      >
                        Supprimer le projet
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
              {projectId === project.project_id ? (
                <section
                  aria-label={`Conversations du projet ${project.title}`}
                  className="workspace-chats"
                >
                  <div className="workspace-section-title">
                    <span>Conversations</span>
                    <button
                      aria-label="Nouvelle conversation"
                      disabled={navigationLocked}
                      onClick={() => void perform(createChat)}
                      title="Nouvelle conversation"
                      type="button"
                    >
                      <Plus size={17} />
                    </button>
                  </div>
                  {chats.map((item) => (
                    <div className="workspace-chat-row" key={item.chat_id}>
                      <button
                        aria-current={
                          chat?.chat_id === item.chat_id ? "page" : undefined
                        }
                        className={
                          chat?.chat_id === item.chat_id ? "selected" : ""
                        }
                        disabled={navigationLocked}
                        onClick={() => void perform(() => chooseChat(item))}
                        type="button"
                      >
                        <MessageSquare size={15} />
                        <span>{item.title}</span>
                      </button>
                      <div className="workspace-item-menu">
                        <button
                          aria-controls={`workspace-chat-actions-${item.chat_id}`}
                          aria-expanded={openMenu === `chat:${item.chat_id}`}
                          aria-label={`Options de la conversation ${item.title}`}
                          className="workspace-more"
                          disabled={locked}
                          onClick={() =>
                            setOpenMenu((current) =>
                              current === `chat:${item.chat_id}`
                                ? null
                                : `chat:${item.chat_id}`,
                            )
                          }
                          ref={(element) => {
                            menuTriggerRefs.current[`chat:${item.chat_id}`] = element;
                          }}
                          type="button"
                        >
                          <MoreHorizontal size={17} />
                        </button>
                        {openMenu === `chat:${item.chat_id}` ? (
                          <div
                            aria-label={`Actions de la conversation ${item.title}`}
                            className="workspace-menu-popover"
                            id={`workspace-chat-actions-${item.chat_id}`}
                            role="group"
                          >
                            <button
                              className="danger"
                              onClick={() => {
                                setOpenMenu(null);
                                if (
                                  window.confirm(
                                    "Supprimer cette conversation ? Son design vérifié restera disponible dans l’historique des designs.",
                                  )
                                )
                                  void perform(async () => {
                                    ++epoch.current;
                                    if (chat?.chat_id === item.chat_id)
                                      await saveDraft();
                                    await client.deleteChat(item.chat_id);
                                    setChats((items) =>
                                      items.filter(
                                        (current) =>
                                          current.chat_id !== item.chat_id,
                                      ),
                                    );
                                    if (chat?.chat_id === item.chat_id) {
                                      setChat(null);
                                      setHistory(null);
                                      draft.current = "";
                                    }
                                    setRestored(true);
                                  });
                              }}
                              type="button"
                            >
                              Supprimer la conversation
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </section>
              ) : null}
            </div>
          ))}
        </nav>
      </aside>
      <div className="product-workspace">
        {!sidebarOpen ? <button ref={sidebarControl} className="sidebar-toggle sidebar-restore" type="button"
          aria-label="Afficher les projets" aria-controls="workspace-sidebar" aria-expanded={false}
          onClick={toggleSidebar}><PanelLeftOpen size={18} /></button> : null}
        {!restored && (
          <p className="workspace-loading" role="status" aria-live="polite">
            Chargement de votre espace…
          </p>
        )}
        {error && (
          <div role="alert" className="workspace-error">
            {error}
            <button
              type="button"
              onClick={() => void perform(retryWorkspaceLoad)}
            >
              Réessayer
            </button>
          </div>
        )}
        {history ? (
          <section className="workspace-history">
            <h1>Retrouver un design</h1>
            <p>
              Rattachez un résultat existant à une conversation de ce projet.
              Ses versions et messages sont conservés.
            </p>
            <button type="button" onClick={() => setHistory(null)}>
              Fermer
            </button>
            {history.map((design) => (
              <button
                type="button"
                disabled={navigationLocked}
                key={design.workflow_id}
                onClick={() =>
                  void perform(async () => {
                    if (!projectId) return;
                    await saveDraft();
                    const value = await client.createChat(
                      projectId,
                      `Design du ${new Date(design.created_at ?? "").toLocaleDateString("fr-FR")}`,
                      design.workflow_id,
                    );
                    setChats((items) => [value, ...items]);
                    setChat(value);
                    draft.current = "";
                    setHistory(null);
                    setRestored(true);
                  })
                }
              >
                <span>
                  {new Date(design.created_at ?? "").toLocaleString("fr-FR")}
                </span>
                <span>
                  {design.status === "completed"
                    ? "Résultat disponible"
                    : design.status === "running"
                      ? "En cours"
                      : "À examiner"}
                </span>
              </button>
            ))}
            {history.length === 0 ? (
              <p>Aucun design non classé n’est disponible.</p>
            ) : null}
          </section>
        ) : chat ? (
          <App
            key={chat.chat_id}
            chatId={chat.chat_id}
            initialWorkflowId={chat.workflow_id}
            initialPrompt={chat.draft_prompt}
            initialDocumentPackId={chat.document_pack_id}
            onDraftChange={(value) => persistDraft(chat.chat_id, value)}
            onWorkflowCreated={async (id, submittedPrompt) => {
              try {
                await flushDraft(false);
                await updateActive({
                  workflow_id: id,
                  title: submittedPrompt.trim().slice(0, 90) || chat.title,
                  draft_prompt: "",
                });
                if (pendingDraft.current?.chatId === chat.chat_id)
                  pendingDraft.current = null;
                if (activeChatId.current === chat.chat_id && draftTimer.current) {
                  clearTimeout(draftTimer.current);
                  draftTimer.current = null;
                }
                if (activeChatId.current === chat.chat_id) draft.current = "";
              } catch {
                setError(
                  "Le design a été créé, mais les informations de cette conversation n’ont pas toutes été actualisées. Rechargez-la pour retrouver l’état enregistré.",
                );
              }
            }}
            onDocumentPackLinked={async (id) => {
              setChats((items) =>
                items.map((item) =>
                  item.chat_id === chat.chat_id
                    ? { ...item, document_pack_id: id }
                    : item,
                ),
              );
              setChat((current) =>
                current?.chat_id === chat.chat_id
                  ? { ...current, document_pack_id: id }
                  : current,
              );
            }}
            onBusyChange={setWorking}
            onMutationBusyChange={setMutationBusy}
            onNewChat={(failedPrompt = "") =>
              void perform(() => createChat(failedPrompt))
            }
          />
        ) : (
          <section className="workspace-welcome">
            <RadioTower size={42} />
            <p>Votre espace de conception</p>
            <h1>
              {projectId
                ? "Une conversation, un design."
                : "Du projet au modèle 3D."}
            </h1>
            <p>
              {projectId
                ? "Décrivez votre intention, ajoutez vos documents et faites évoluer le modèle au fil de la conversation."
                : "Organisez vos sites et vos échanges, puis concevez et modifiez vos modèles dans un même espace."}
            </p>
            <button
              type="button"
              disabled={navigationLocked}
              onClick={() =>
                projectId ? void perform(createChat) : setNewProject(true)
              }
            >
              <Plus size={18} />
              {projectId
                ? "Commencer une conversation"
                : "Créer mon premier projet"}
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
