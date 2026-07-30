import type { ViewerBundle } from "../../api/schemas";

export type ViewerSource =
  | { kind: "empty"; message: string }
  | { kind: "preview"; url: string; message: string }
  | { kind: "glb"; url: string; previewUrl: string | null }
  | { kind: "error"; message: string; previewUrl: string | null };

export type GeometryFidelityBadge = {
  fidelity: "schematic" | "technical_generic" | "vendor_qualified";
  label: string;
  count: number;
  roles: string[];
};

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
  if (bundle.status === "legacy_unverified") {
    return {
      kind: "error",
      message:
        "Ce résultat historique n'est pas certifié. Ses artefacts restent en quarantaine jusqu'à une nouvelle génération vérifiée.",
      previewUrl: null
    };
  }
  if (bundle.status === "integrity_failed") {
    return {
      kind: "error",
      message:
        "La preuve d'intégrité du résultat actif a échoué. Aucun artefact 3D n'est présenté comme valide.",
      previewUrl: null
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
    if (bundle.mesh_qa_level.includes("spatial")) {
      badges.push("QA spatiale contrôlée");
    } else if (bundle.mesh_qa_level.includes("transform")) {
      badges.push("QA transforms contrôlée");
    } else {
      badges.push(bundle.mesh_qa_level);
    }
  }
  badges.push(bundle.mesh_qa_passed ? "QA validée" : "QA attention");
  if (bundle.completion_certificate_status) {
    badges.push(
      bundle.completion_certificate_status === "issued"
        ? "Intégrité vérifiée"
        : "Preuve d’intégrité rejetée"
    );
  }
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
  const fidelityBadge = geometryFidelityBadge(bundle);
  if (fidelityBadge) {
    badges.push(fidelityBadge.label);
  }
  return badges;
}

export function geometryFidelityBadge(bundle: ViewerBundle | null): GeometryFidelityBadge | null {
  const summary = bundle?.geometry_fidelity_summary;
  if (!summary || summary.component_count === 0) {
    return null;
  }

  if (summary.counts.technical_generic > 0) {
    return buildGeometryFidelityBadge(
      "technical_generic",
      "Équipements génériques techniques",
      summary.counts.technical_generic,
      summary.roles.technical_generic
    );
  }
  if (summary.counts.schematic > 0) {
    return buildGeometryFidelityBadge(
      "schematic",
      "Équipements schématiques",
      summary.counts.schematic,
      summary.roles.schematic
    );
  }
  if (summary.counts.vendor_qualified === summary.component_count) {
    return buildGeometryFidelityBadge(
      "vendor_qualified",
      "Modèle fournisseur qualifié",
      summary.counts.vendor_qualified,
      summary.roles.vendor_qualified
    );
  }
  return null;
}

function buildGeometryFidelityBadge(
  fidelity: GeometryFidelityBadge["fidelity"],
  heading: string,
  count: number,
  roles: string[]
): GeometryFidelityBadge {
  const readableRoles = roles.map(humanAssetRole);
  const componentLabel = count === 1 ? "1 composant" : `${count} composants`;
  const roleLabel = readableRoles.length ? ` · ${readableRoles.join(", ")}` : "";
  return {
    fidelity,
    label: `${heading} · ${componentLabel}${roleLabel}`,
    count,
    roles: readableRoles
  };
}

function humanAssetRole(role: string): string {
  const labels: Record<string, string> = {
    antenna: "antennes",
    cabinet: "armoires",
    gps: "GPS",
    gps_antenna: "antennes GPS",
    power_cabinet: "armoires énergie",
    radio: "radios",
    tower: "pylône"
  };
  return labels[role] ?? role.replaceAll("_", " ");
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
