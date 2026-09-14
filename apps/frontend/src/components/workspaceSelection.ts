const LAST_SELECTION_KEY = "telecom-studio.workspace.selection";

export interface WorkspaceSelection {
  projectId: string | null;
  chatId: string | null;
}

/** Resolve the last valid workspace selection, with the URL taking precedence. */
export function readInitialWorkspaceSelection(): WorkspaceSelection {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const fromHash = {
    projectId: params.get("project"),
    chatId: params.get("chat"),
  };
  if (fromHash.projectId) return fromHash;
  return readLastWorkspaceSelection() ?? fromHash;
}

/** Remember where the user was so a plain reload reopens the same conversation. */
export function readLastWorkspaceSelection(
  storage: Storage | null = safeStorage(),
): WorkspaceSelection | null {
  try {
    const raw = storage?.getItem(LAST_SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { projectId?: unknown; chatId?: unknown };
    const projectId = typeof parsed.projectId === "string" ? parsed.projectId : null;
    const chatId = typeof parsed.chatId === "string" ? parsed.chatId : null;
    return projectId ? { projectId, chatId } : null;
  } catch {
    return null;
  }
}

export function writeLastWorkspaceSelection(
  projectId: string | null,
  chatId: string | null,
  storage: Storage | null = safeStorage(),
) {
  try {
    if (!projectId) storage?.removeItem(LAST_SELECTION_KEY);
    else storage?.setItem(LAST_SELECTION_KEY, JSON.stringify({ projectId, chatId }));
  } catch {
    // Browser storage is a convenience only; the URL hash remains authoritative.
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
