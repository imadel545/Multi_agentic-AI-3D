import type { ViewerBundle } from "../../api/schemas";

export type ViewerSource =
  | { kind: "empty"; message: string }
  | { kind: "preview"; url: string; message: string }
  | { kind: "glb"; url: string; previewUrl: string | null }
  | { kind: "error"; message: string; previewUrl: string | null };

export function resolveViewerSource(
  bundle: ViewerBundle | null,
  toAbsoluteUrl: (url: string | null | undefined) => string | null
): ViewerSource {
  if (!bundle) {
    return { kind: "empty", message: "Aucun design généré pour le moment." };
  }
  const previewUrl = artifactUrlIfAvailable(bundle, ["preview.png"], bundle.preview_url, toAbsoluteUrl);
  if (bundle.status === "failed") {
    return {
      kind: "error",
      message: "Le workflow a échoué. Le viewer final n'est pas disponible.",
      previewUrl
    };
  }
  const glbUrl = artifactUrlIfAvailable(bundle, ["design.glb", "telecom_design.glb"], bundle.primary_glb_url, toAbsoluteUrl);
  if (!glbUrl) {
    if (previewUrl) {
      return {
        kind: "preview",
        url: previewUrl,
        message: "GLB indisponible; affichage de la preview backend."
      };
    }
    return { kind: "error", message: "Aucun GLB ni preview disponible.", previewUrl: null };
  }
  return { kind: "glb", url: glbUrl, previewUrl };
}

function artifactUrlIfAvailable(
  bundle: ViewerBundle,
  names: string[],
  fallbackUrl: string | null | undefined,
  toAbsoluteUrl: (url: string | null | undefined) => string | null
): string | null {
  const artifact = bundle.viewer_artifacts.find((item) => names.includes(item.name));
  if (artifact) {
    return artifact.available ? toAbsoluteUrl(artifact.url) : null;
  }
  return toAbsoluteUrl(fallbackUrl);
}

export function viewerBadges(bundle: ViewerBundle | null): string[] {
  if (!bundle) {
    return [];
  }
  const badges = [];
  if (bundle.generation_mode) {
    badges.push(bundle.generation_mode === "real_blender" ? "Blender réel" : `Mode ${bundle.generation_mode}`);
  }
  if (bundle.mesh_qa_level) {
    badges.push(bundle.mesh_qa_level.includes("transform") ? "QA mesh de base" : bundle.mesh_qa_level);
  }
  badges.push(bundle.mesh_qa_passed ? "QA validée" : "QA attention");
  if (bundle.llm_fallback_used) {
    badges.push("Fallback LLM");
  }
  if (bundle.rag_reranker_degraded_reason) {
    badges.push("RAG dégradé");
  }
  const assetSummary = bundle.asset_import_summary ?? {};
  const fallbackCount = Number(assetSummary["procedural_fallback_count"] ?? 0);
  if (fallbackCount > 0) {
    badges.push("Fallback asset");
  }
  return badges;
}

type WebGLCapableWindow = Window & { WebGLRenderingContext?: unknown };

export function hasUsableWebGL(
  ownerDocument: Document = document,
  ownerWindow: WebGLCapableWindow = window as WebGLCapableWindow
): boolean {
  if (!ownerWindow.WebGLRenderingContext) {
    return false;
  }
  const canvas = ownerDocument.createElement("canvas");
  try {
    return Boolean(
      canvas.getContext("webgl2") ||
        canvas.getContext("webgl") ||
        canvas.getContext("experimental-webgl")
    );
  } catch {
    return false;
  }
}
