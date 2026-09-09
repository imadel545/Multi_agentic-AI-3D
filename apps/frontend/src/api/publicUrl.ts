const PublicApiRoots = [
  "/assets",
  "/designs",
  "/document-packs",
  "/health",
  "/requirements",
  "/studio"
] as const;

function isPublicApiPath(value: string): boolean {
  return ["/rag/reindex", "/memory/vector/reindex"].includes(value) || PublicApiRoots.some(
    (root) =>
      value === root || value.startsWith(`${root}/`) || value.startsWith(`${root}?`)
  );
}

export function publicPathIssue(value: string, fieldName?: string): string | null {
  if (/^[A-Za-z]:[\\/]/.test(value)) {
    return "absolute Windows filesystem paths are not allowed";
  }
  if (value.startsWith("\\\\")) {
    return "UNC filesystem paths are not allowed";
  }
  if (/^file:/i.test(value)) {
    return "file URLs are not allowed";
  }
  const publicReferenceField =
    fieldName === "url" ||
    fieldName?.endsWith("_url") ||
    fieldName?.endsWith("_file") ||
    fieldName === "artifact_file";
  if (value.startsWith("/") && publicReferenceField && !isPublicApiPath(value)) {
    return "absolute filesystem paths are not allowed";
  }
  return null;
}

export function isPublicArtifactReference(value: string): boolean {
  if (!value || value !== value.trim()) {
    return false;
  }
  if (isPublicApiPath(value)) {
    return true;
  }
  try {
    const url = new URL(value);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}
