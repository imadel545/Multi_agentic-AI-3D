const DocumentPackSessionKey = "telecom-studio:document-pack-session:v1";
const DocumentPackSessionVersion = 1;

type StorageReader = Pick<Storage, "getItem" | "removeItem" | "setItem">;

type DocumentPackSession = {
  version: 1;
  packId: string;
};

export function readDocumentPackSession(storage: StorageReader): string | null {
  try {
    const raw = storage.getItem(DocumentPackSessionKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DocumentPackSession>;
    if (
      parsed.version !== DocumentPackSessionVersion ||
      typeof parsed.packId !== "string" ||
      !/^pack_[a-zA-Z0-9_-]{1,120}$/.test(parsed.packId)
    ) {
      safeRemove(storage);
      return null;
    }
    return parsed.packId;
  } catch {
    safeRemove(storage);
    return null;
  }
}

export function writeDocumentPackSession(storage: StorageReader, packId: string): void {
  if (!/^pack_[a-zA-Z0-9_-]{1,120}$/.test(packId)) return;
  try {
    storage.setItem(
      DocumentPackSessionKey,
      JSON.stringify({ version: DocumentPackSessionVersion, packId })
    );
  } catch {
    // The backend remains authoritative when browser storage is unavailable.
  }
}

export function clearDocumentPackSession(storage: StorageReader): void {
  safeRemove(storage);
}

function safeRemove(storage: Pick<Storage, "removeItem">): void {
  try {
    storage.removeItem(DocumentPackSessionKey);
  } catch {
    // Storage failures must not break the active backend-backed session.
  }
}
