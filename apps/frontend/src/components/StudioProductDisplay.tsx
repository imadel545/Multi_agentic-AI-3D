import type { ViewerBundle } from "../api/schemas";
import type { WorkflowPhase } from "../state/workflowMachine";

export function summaryHeadline(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "Aucun design chargé";
  }
  if (bundle.status === "failed") {
    return "Conception non produite";
  }
  if (bundle.generation_mode !== "real_blender") {
    return "Résultat dégradé";
  }
  if (bundle.mesh_qa_passed === false) {
    return "Design généré avec attention QA";
  }
  if (bundle.status === "completed") {
    return "Design prêt à inspecter";
  }
  return "Design en cours";
}

export function nextUserAction(bundle: ViewerBundle | null, issueCount: number): string {
  if (!bundle) {
    return "Décrivez un site telecom ou chargez un ZIP documentaire.";
  }
  if (bundle.status === "failed") {
    return "Lire les alertes, corriger la demande, puis relancer.";
  }
  if (bundle.generation_mode !== "real_blender") {
    return "Utiliser l’aperçu seulement comme secours; corriger la construction 3D avant validation.";
  }
  if (bundle.mesh_qa_passed === false) {
    return "Inspecter la QA et les alertes avant de considérer le GLB exploitable.";
  }
  if (issueCount > 0) {
    return "Inspecter le modèle 3D, puis lire les limites regroupées dans les alertes.";
  }
  return "Inspecter le GLB et télécharger les artefacts nécessaires.";
}

export function summarySignals(bundle: ViewerBundle | null, issueCount: number): string[] {
  if (!bundle) {
    return [];
  }
  const failed = bundle.status === "failed";
  const signals = [
    `Modèle 3D : ${failed ? "non produit" : bundle.primary_glb_url ? "disponible" : "manquant"}`,
    `Aperçu : ${failed ? "non produit" : bundle.preview_url ? "disponible" : "manquant"}`,
    `Niveau de contrôle : ${meshQaLevelLabel(bundle.mesh_qa_level)}`,
    `Points à examiner : ${issueCount}`
  ];
  if (bundle.llm_fallback_used) {
    signals.push("La compréhension de la demande a utilisé un mode de secours contrôlé.");
  }
  if (bundle.rag_reranker_degraded_reason) {
    signals.push("Le classement secondaire des sources documentaires a fonctionné en mode de secours.");
  }
  return signals;
}

export function analysisProviderLabel(provider?: string | null, extractionProvider?: string | null): string {
  const normalized = `${provider ?? ""} ${extractionProvider ?? ""}`.toLowerCase();
  if (normalized.includes("groq") || normalized.includes("gpt")) return "intelligence décisionnelle";
  if (normalized.includes("fallback") || normalized.includes("determin")) return "mode de secours contrôlé";
  return "analyse structurée";
}

export function workflowStatusLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    completed: "terminée",
    failed: "échouée",
    running: "en cours",
    pending: "en attente"
  };
  return status ? labels[status] ?? "état disponible" : "pas lancée";
}

export function meshQaLevelLabel(level: string | null | undefined): string {
  const labels: Record<string, string> = {
    mesh_level_spatial_basic: "QA spatiale AABB",
    mesh_level_transform_basic: "Transforms 3D contrôlées",
    mesh_level_basic: "Géométrie de base",
    metadata_only: "Métadonnées seulement",
    not_available: "Non disponible"
  };
  return level ? (labels[level] ?? "Niveau non reconnu") : "Non disponible";
}

export function completionCertificateLabel(status: string | null | undefined): string {
  if (status === "issued") {
    return "vérifiée localement";
  }
  if (status === "rejected") {
    return "rejeté";
  }
  return "absent";
}

export function summarizeRagEvidence(evidence: unknown) {
  const record = asRecord(evidence);
  const contexts = Array.isArray(record?.["contexts"]) ? record["contexts"] : [];
  const sources = contexts.slice(0, 6).map((context) => {
    const source = asRecord(context);
    const title = readString(source?.["filename"]) ?? readString(source?.["source_path"]) ?? "source";
    const score = typeof source?.["score"] === "number" ? `score ${source["score"].toFixed(2)}` : "score n/a";
    return {
      title,
      reason: readString(source?.["reason"]) ?? "Contexte récupéré.",
      score
    };
  });
  return {
    ragUsedForExtraction: record?.["rag_used_for_extraction"] === true,
    ragUsedForPlanning: record?.["rag_used_for_planning"] === true,
    candidateHints: readStringArray(record?.["candidate_hint_fields"]),
    appliedHints: readStringArray(record?.["applied_hint_fields"]),
    limitations: readStringArray(record?.["limitations"]),
    sources
  };
}

export function humanRagLimitation(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (
    normalized.includes("evidence and controlled planning context") ||
    normalized.includes("not a free-form planner")
  ) {
    return "La recherche documentaire fournit des preuves et un contexte contrôlé; elle ne décide pas librement de la géométrie.";
  }
  if (
    normalized.includes("does not participate in requirementspec extraction") ||
    normalized.includes("not used for requirementspec extraction")
  ) {
    return "La recherche documentaire ne participe pas à l’extraction initiale des exigences dans cette version.";
  }
  if (
    normalized.includes("whitelisted") &&
    normalized.includes("planning_hints")
  ) {
    return "Seuls les indices de planification explicitement autorisés peuvent influencer le plan 3D.";
  }
  if (normalized.includes("reranker") && normalized.includes("unavailable")) {
    return "Le reranker NVIDIA est indisponible; l’ordre vectoriel est conservé et le mode dégradé reste signalé.";
  }
  if (/^(le|la|les|un|une|seul|seuls|aucun|aucune)\b/i.test(value.trim())) {
    return value.trim();
  }
  return "Une limitation supplémentaire de la recherche est déclarée; son détail technique reste disponible dans les livrables.";
}

export function StatusPill({
  label,
  tone = "muted",
  value
}: {
  label: string;
  tone?: "ok" | "warn" | "danger" | "muted";
  value: string;
}) {
  return (
    <span className={`status-pill ${tone}`}>
      <small>{label}</small>
      {value}
    </span>
  );
}

export function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "unknown";
}

export function formatRatio(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)} %` : "non publié";
}

export function formatMeasurement(value: number): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 }).format(value);
}

export function assemblyConstraintStatusLabel(status: "passed" | "failed" | "not_available"): string {
  return {
    passed: "contrôle passé",
    failed: "écart détecté",
    not_available: "mesure indisponible"
  }[status];
}

export function assemblyMeasurementScopeLabel(scope: string): string {
  if (scope === "exported_glb_anchor_frames") {
    return "les repères d’ancrage du GLB exporté";
  }
  return scope.replaceAll("_", " ");
}

export function assemblyLimitationLabel(limitation: string): string {
  return {
    "Required non-mechanical connections are reported but are not geometrically evaluated by AssemblyConstraintEvidence v1.":
      "Les connexions requises non mécaniques sont signalées, mais ne sont pas encore mesurées géométriquement.",
    "Anchor frames are semantic coordinate frames reconstructed from exported glTF component roots or dedicated constraint-marker nodes; they are not contact mesh.":
      "Les repères sont reconstruits depuis le GLB exporté ; ils ne prouvent pas à eux seuls le contact physique des surfaces.",
    "Collision, physical contact, fastener engagement, deformation, load capacity and electrical or routing continuity are not evaluated.":
      "Les collisions fines, le contact, la visserie, la déformation, la tenue aux charges et la continuité électrique ou de routage ne sont pas évalués."
  }[limitation] ?? limitation;
}

export function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

export function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function readString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function truth(value: boolean): string {
  return value ? "oui" : "non";
}

export function qaTruth(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "en attente";
  }
  return bundle.mesh_qa_passed ? "validée" : "à examiner";
}

export function generationTruth(bundle: ViewerBundle | null): string {
  if (!bundle) {
    return "aucun";
  }
  if (bundle.generation_mode === "real_blender") {
    return "Construction 3D réelle";
  }
  return bundle.generation_mode ?? "unknown";
}

export function phaseLabel(phase: WorkflowPhase): string {
  return {
    idle: "prêt",
    drafting: "rédaction",
    submitting: "envoi",
    streaming: "streaming",
    running: "en cours",
    completed: "terminé",
    failed: "échec",
    degraded: "dégradé"
  }[phase];
}

export function stageStatusLabel(status: string): string {
  if (status === "completed_with_warning") {
    return "terminé avec alerte";
  }
  if (status.includes("completed") || status === "passed" || status === "generated") {
    return "terminé";
  }
  if (status.includes("running")) {
    return "en cours";
  }
  if (status.includes("failed") || status === "error") {
    return "échec";
  }
  if (status === "not_reported") {
    return "non reporté";
  }
  if (status === "waiting" || status === "pending") {
    return "en attente";
  }
  return status;
}

export function humanPhase(phase: string | null | undefined): string {
  if (!phase) {
    return "orchestration";
  }
  return {
    workflow: "orchestration",
    quality_gate: "contrôle final",
    memory: "mémoire",
    viewer: "visualisation 3D",
    issues: "alertes",
    qa: "qualité"
  }[phase] ?? phase.replaceAll("_", " ");
}

export function humanTimelineMessage(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("certification des preuves")) {
    return message.replace("Certification des preuves", "Vérification des preuves");
  }
  const mechanicalTilt = message.match(/mechanical tilt inferred as ([\d.]+) degrees?/i);
  if (mechanicalTilt) {
    return `Inclinaison mécanique proposée à ${mechanicalTilt[1]}°. Vérifiez-la dans les alertes.`;
  }
  const electricalTilt = message.match(/electrical tilt inferred as ([\d.]+) degrees?/i);
  if (electricalTilt) {
    return `Inclinaison électrique proposée à ${electricalTilt[1]}°. Vérifiez-la dans les alertes.`;
  }
  const beamwidth = message.match(/beamwidth inferred as ([\d.]+) degrees?/i);
  if (beamwidth) {
    return `Ouverture d’antenne proposée à ${beamwidth[1]}°. Vérifiez-la dans les alertes.`;
  }
  if (normalized.includes("sector_count_azimuth_mismatch")) {
    return "Les azimuts ont été complétés pour correspondre au nombre de secteurs demandé.";
  }
  if (normalized.includes("platforms recommended")) {
    return "Une plateforme est recommandée pour la sécurité sur ce pylône.";
  }
  return message.replaceAll("Warnings", "les alertes");
}

export function artifactLabel(name: string): string {
  const labels: Record<string, string> = {
    "design.glb": "Modèle 3D GLB",
    "preview.png": "Vue d’ensemble",
    "preview_front.png": "Vue de face",
    "preview_side.png": "Vue latérale",
    "preview_top.png": "Vue de dessus",
    "preview_closeup.png": "Gros plan principal",
    "scene_metadata.json": "Métadonnées de la scène",
    "requirements_spec.json": "Exigences consolidées",
    "extraction_report.json": "Rapport de compréhension",
    "scene_spec.json": "Plan de scène vérifiable",
    "qa_report.json": "Rapport QA",
    "generation_report.json": "Rapport génération",
    "rag_evidence.json": "Preuves du contexte IA",
    "planning_decision.json": "Décisions de planification",
    "geometry_validation.json": "Validation géométrie",
    "component_proofs.json": "Preuves des composants assemblés",
    "requirement_coverage.json": "Couverture des exigences",
    "completion_certificate.json": "Preuve locale de complétion",
    "technical_report.md": "Rapport technique"
  };
  return labels[name] ?? name;
}

export function artifactKindLabel(contentType: string): string {
  if (contentType === "model/gltf-binary") return "Modèle 3D";
  if (contentType.startsWith("image/")) return "Image de contrôle";
  if (contentType === "text/markdown") return "Rapport lisible";
  if (contentType === "application/json") return "Données vérifiables";
  return "Livrable";
}

