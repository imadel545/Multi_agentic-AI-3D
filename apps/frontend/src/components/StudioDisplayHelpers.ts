export function humanSemanticRole(role: string): string {
  if (role === "tower_access") return "accès et maintenance du pylône";
  return role.replaceAll("_", " ").replaceAll(".", " ");
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
