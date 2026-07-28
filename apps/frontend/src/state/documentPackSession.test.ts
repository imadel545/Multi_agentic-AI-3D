import { beforeEach, describe, expect, it } from "vitest";
import {
  clearDocumentPackSession,
  readDocumentPackSession,
  writeDocumentPackSession
} from "./documentPackSession";

describe("document pack session pointer", () => {
  beforeEach(() => localStorage.clear());

  it("restores only a versioned bounded backend pack identifier", () => {
    writeDocumentPackSession(localStorage, "pack_abc123");
    expect(readDocumentPackSession(localStorage)).toBe("pack_abc123");
  });

  it("rejects malformed or obsolete local state without inventing pack data", () => {
    localStorage.setItem(
      "telecom-studio:document-pack-session:v1",
      JSON.stringify({ version: 0, packId: "pack_old" })
    );
    expect(readDocumentPackSession(localStorage)).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("clears the pointer without touching backend-owned document data", () => {
    writeDocumentPackSession(localStorage, "pack_abc123");
    clearDocumentPackSession(localStorage);
    expect(readDocumentPackSession(localStorage)).toBeNull();
  });

  it("keeps the studio usable when browser storage is unavailable", () => {
    const unavailableStorage = {
      getItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
      removeItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("blocked", "SecurityError");
      }
    };

    expect(() => writeDocumentPackSession(unavailableStorage, "pack_abc123")).not.toThrow();
    expect(readDocumentPackSession(unavailableStorage)).toBeNull();
    expect(() => clearDocumentPackSession(unavailableStorage)).not.toThrow();
  });
});
