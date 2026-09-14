import type { ComponentProofs } from "../api/schemas";

const semanticRoleLabels: Record<string, string> = {
  antenna: "antenne",
  antenna_mount: "support d’antenne",
  cable: "chemin de câble",
  mount_bracket: "support d’antenne",
  radio: "unité radio",
  remote_radio: "unité radio",
  rru: "unité radio",
  safety_feature: "élément de sécurité",
  sector_antenna: "antenne sectorielle",
  sector_cable_route: "chemin de câble du secteur",
  support_structure: "structure porteuse",
  technical_shelter: "abri technique",
  tower: "pylône",
  tower_access: "accès et maintenance du pylône"
};

export function humanSemanticRole(role: string): string {
  const normalized = role.trim().toLowerCase();
  return semanticRoleLabels[normalized] ?? normalized.replaceAll("_", " ").replaceAll(".", " ");
}

/** Resolve a backend identity to a stable product label without parsing its name. */
export function humanComponentInstanceLabel(
  proofs: ComponentProofs | null,
  semanticRoot: string | null
): string | null {
  if (!semanticRoot) return null;
  for (const component of proofs?.components ?? []) {
    const instance = component.instances.find((candidate) => candidate.semantic_root === semanticRoot);
    if (instance) {
      const role = humanSemanticRole(instance.object_role || component.role_id);
      return /^S\d+$/i.test(instance.instance_id)
        ? `${role} du secteur ${instance.instance_id.toUpperCase()}`
        : role;
    }
  }
  return "composant 3D sélectionné";
}

export function visualReviewStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    not_requested: "non demandée",
    passed_advisory: "aucune anomalie signalée",
    review_required: "vérification humaine recommandée",
    failed: "indisponible"
  };
  return labels[status] ?? "statut non reconnu";
}

export function compactFidelityLabel(fidelity: string): string {
  return {
    vendor_qualified: "Fidélité constructeur",
    technical_generic: "Fidélité technique générique",
    schematic: "Fidélité schématique"
  }[fidelity] ?? "Fidélité à vérifier";
}

export function serviceStatusLabel(status?: string | null): string {
  const normalized = status?.toLowerCase() ?? "";
  if (["unavailable", "disabled", "error", "missing"].some((value) => normalized.includes(value))) {
    return "indisponible";
  }
  if (
    [
      "qualified_mixed_catalog",
      "primary_nvidia_embedding",
      "primary_nvidia_reranker",
      "primary_vector",
      "primary_vector_cache"
    ].includes(normalized)
  ) {
    return "opérationnel";
  }
  if (["degraded", "limited", "fallback", "passthrough"].some((value) => normalized.includes(value))) {
    return "disponible avec limites";
  }
  if (["ok", "ready", "available", "enabled", "ready_for_import"].some((value) => normalized.includes(value))) {
    return "disponible";
  }
  return "état non confirmé";
}
