import type { SceneAdaptationCapabilities, TimelineSummary, UserIssue, UserIssues, ViewerBundle } from "../api/schemas";
import type { NormalizedWorkflowEvent } from "../api/sse";
import type { WorkflowPhase } from "../state/workflowMachine";

export type TimelineDisplayRow = {
  id: string;
  label: string;
  message: string;
  status: string;
  phase: string | null | undefined;
};

export function summarizeTimelineRows(rows: TimelineDisplayRow[]): TimelineDisplayRow[] {
  const grouped = {
    attribution: 0,
    nonVendorGrade: 0,
    otherAsset: 0
  };
  const visibleRows: TimelineDisplayRow[] = [];

  for (const row of rows) {
    if (isAssetIssueRow(row)) {
      const text = `${row.label} ${row.message}`;
      if (text.includes("ATTRIBUTION_REQUIRED")) {
        grouped.attribution += 1;
      } else if (text.includes("NOT_VENDOR_GRADE") || text.includes("INTERNAL_TEST_MINIMAL") || text.includes("INTERNAL_CLEANED") || text.includes("CC_BY")) {
        grouped.nonVendorGrade += 1;
      } else {
        grouped.otherAsset += 1;
      }
      continue;
    }
    visibleRows.push({
      ...row,
      label:
        row.label === "Certification des preuves"
          ? "Vérification des preuves"
          : row.label
    });
  }

  const groupedRows: TimelineDisplayRow[] = [];
  if (grouped.nonVendorGrade) {
    groupedRows.push({
      id: "grouped-non-vendor-grade-assets",
      label: `Modèles non constructeur : ${grouped.nonVendorGrade} éléments`,
      message: "Le design utilise des modèles réels ou importés, sans garantie constructeur. Consultez les alertes.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.attribution) {
    groupedRows.push({
      id: "grouped-attribution-assets",
      label: `Attributions requises : ${grouped.attribution} élément${grouped.attribution > 1 ? "s" : ""}`,
      message: "Certains modèles imposent une attribution de licence. Consultez les alertes.",
      phase: "issues",
      status: "completed"
    });
  }
  if (grouped.otherAsset) {
    groupedRows.push({
      id: "grouped-other-assets",
      label: `Autres alertes de modèles : ${grouped.otherAsset} élément${grouped.otherAsset > 1 ? "s" : ""}`,
      message: "D’autres avertissements sur les modèles sont disponibles dans les alertes.",
      phase: "issues",
      status: "completed"
    });
  }

  return [...visibleRows, ...groupedRows];
}

export function isAssetIssueRow(row: TimelineDisplayRow): boolean {
  const text = `${row.label} ${row.message}`.toLowerCase();
  return text.includes("asset") || text.includes("not_vendor_grade") || text.includes("attribution_required");
}

export function summarizeStages(events: NormalizedWorkflowEvent[], timeline: TimelineSummary | null, phase: WorkflowPhase) {
  const stages = [
    {
      phase: "requirements",
      label: "Compréhension de la demande",
      phases: ["requirements", "extraction", "rag", "memory"],
      nodes: ["extract_requirements", "validate_requirements", "requirements", "retrieve_rag_context", "memory_recall"]
    },
    {
      phase: "planning",
      label: "Conception du plan 3D",
      phases: ["planning", "validation", "scene"],
      nodes: ["plan_scene", "validate_scene", "scene_repair_handler", "scene_planner"]
    },
    {
      phase: "generation",
      label: "Construction du modèle 3D",
      phases: ["generation", "blender", "viewer"],
      nodes: ["generate_blender", "blender_worker", "blender_failure_handler"]
    },
    {
      phase: "qa",
      label: "Vérification du résultat",
      phases: ["qa", "workflow", "completion"],
      nodes: ["qa_generation", "quality_gate", "workflow"]
    }
  ];
  const statusByPhase = new Map<string, string>();
  for (const event of events) {
    recordStageStatus(statusByPhase, stages, event.phase, event.node, event.status ?? event.event_type);
  }
  for (const step of timeline?.timeline_steps ?? []) {
    recordStageStatus(statusByPhase, stages, step.phase, step.node, step.status);
  }
  const terminalStatus = timeline?.status ?? (phase === "completed" || phase === "failed" ? phase : null);
  return stages.map((item) => {
    const observed =
      statusByPhase.get(item.phase) ?? terminalStageFallback(item.phase, terminalStatus, phase);
    const status =
      terminalStatus === "completed" && isFailureStageStatus(observed)
        ? "completed_with_warning"
        : observed;
    return { phase: item.phase, label: item.label, status };
  });
}

export type StageDefinition = {
  phase: string;
  label: string;
  phases: string[];
  nodes: string[];
};

export function recordStageStatus(statusByPhase: Map<string, string>, stages: StageDefinition[], phase: string | null | undefined, node: string | null | undefined, status: string) {
  const stage = stages.find((candidate) => {
    const normalizedPhase = (phase ?? "").toLowerCase();
    const normalizedNode = (node ?? "").toLowerCase();
    return candidate.phases.includes(normalizedPhase) || candidate.nodes.some((knownNode) => normalizedNode.includes(knownNode));
  });
  if (!stage) {
    return;
  }
  const current = statusByPhase.get(stage.phase);
  statusByPhase.set(stage.phase, strongestStageStatus(current, status));
}

export function strongestStageStatus(current: string | undefined, next: string): string {
  if (!current) {
    return next;
  }
  const rank = (status: string) => {
    if (status.includes("failed") || status === "error") {
      return 5;
    }
    if (status.includes("completed") || status === "passed" || status === "generated") {
      return 4;
    }
    if (status.includes("running")) {
      return 3;
    }
    if (status === "pending") {
      return 2;
    }
    return 1;
  };
  return rank(next) >= rank(current) ? next : current;
}

export function isFailureStageStatus(status: string): boolean {
  return status.includes("failed") || status === "error";
}

export function terminalStageFallback(itemPhase: string, terminalStatus: string | null, phase: WorkflowPhase): string {
  if (phase === "idle" || phase === "drafting") {
    return "waiting";
  }
  if (terminalStatus === "completed") {
    return itemPhase === "qa" ? "completed" : "not_reported";
  }
  if (terminalStatus === "failed") {
    return itemPhase === "qa" ? "failed" : "not_reported";
  }
  return itemPhase === "qa" ? "waiting" : "pending";
}

export function macroStageMessage(label: string, status: string): string {
  if (status.includes("failed") || status === "error") {
    return `${label} a rencontré un blocage. Consultez l’action proposée dans la conversation.`;
  }
  if (status.includes("completed") || status === "passed" || status === "generated") {
    return `${label} terminée avec une preuve backend enregistrée.`;
  }
  if (status.includes("running")) {
    return `${label} en cours.`;
  }
  if (status === "not_reported") {
    return "Cette étape n’a pas publié de preuve exploitable pour ce résultat.";
  }
  return "En attente de l’étape précédente.";
}

export function summarizeUserIssues(issues: UserIssue[]): UserIssue[] {
  const groups = {
    nonVendorGrade: 0,
    attribution: 0,
    otherAsset: 0
  };
  const visible: UserIssue[] = [];

  for (const issue of issues) {
    const text = `${issue.title} ${issue.impact} ${issue.recommended_action} ${issue.technical_code ?? ""}`;
    const normalized = text.toUpperCase();
    if (!isAssetIssueText(text)) {
      visible.push(humanizeUserIssue(issue));
      continue;
    }
    if (normalized.includes("ATTRIBUTION_REQUIRED")) {
      groups.attribution += 1;
    } else if (normalized.includes("NOT_VENDOR_GRADE") || normalized.includes("INTERNAL_TEST_MINIMAL") || normalized.includes("INTERNAL_CLEANED") || normalized.includes("CC_BY")) {
      groups.nonVendorGrade += 1;
    } else {
      groups.otherAsset += 1;
    }
  }

  const grouped: UserIssue[] = [];
  if (groups.nonVendorGrade) {
    grouped.push({
      title: `Modèles non constructeur: ${groups.nonVendorGrade} éléments`,
      severity: "warning",
      impact: "La scène peut être inspectée, mais certains modèles ne sont pas des assets constructeur.",
      recommended_action: "Ne promettez pas une fidélité exacte à un catalogue constructeur.",
      technical_code: "ASSET_NON_VENDOR_GRADE_GROUP"
    });
  }
  if (groups.attribution) {
    grouped.push({
      title: `Attributions de licence requises: ${groups.attribution}`,
      severity: "warning",
      impact: "Des assets utilisés dans la scène imposent une attribution.",
      recommended_action: "Conserver les attributions dans le rapport avant partage externe.",
      technical_code: "ASSET_ATTRIBUTION_REQUIRED_GROUP"
    });
  }
  if (groups.otherAsset) {
    grouped.push({
      title: `Autres alertes de modèles: ${groups.otherAsset}`,
      severity: "warning",
      impact: "Des limites assets sont remontées par le backend.",
      recommended_action: "Inspecter les détails dans les artefacts et rapports backend.",
      technical_code: "ASSET_WARNING_GROUP"
    });
  }
  return [...grouped, ...visible];
}

export function displayIssueCount(
  issues: UserIssues | null,
  bundle: ViewerBundle | null
): number {
  if (issues) {
    return summarizeUserIssues(issues.human_readable_issues).length;
  }
  return bundle?.human_warnings_count ?? 0;
}

export function humanizeUserIssue(issue: UserIssue): UserIssue {
  const text = `${issue.title} ${issue.impact} ${issue.technical_code ?? ""}`;
  const normalized = text.toLowerCase();
  const inferredValue = text.match(/inferred as ([\d.]+) degrees?/i)?.[1];
  if (
    normalized.includes("mechanical tilt inferred") ||
    normalized.includes("mechanical tilt was not confirmed")
  ) {
    return {
      ...issue,
      title: "Inclinaison mécanique proposée",
      impact: `Une inclinaison mécanique de ${inferredValue ?? "3"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Confirmez cette valeur avec le cahier de charge radio."
    };
  }
  if (
    normalized.includes("electrical tilt inferred") ||
    normalized.includes("electrical tilt was not confirmed")
  ) {
    return {
      ...issue,
      title: "Inclinaison électrique proposée",
      impact: `Une inclinaison électrique de ${inferredValue ?? "0"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Confirmez cette valeur avec le cahier de charge radio."
    };
  }
  if (normalized.includes("beamwidth inferred")) {
    return {
      ...issue,
      title: "Ouverture d’antenne proposée",
      impact: `Une ouverture de ${inferredValue ?? "65"}° a été proposée faute de valeur explicite.`,
      recommended_action: "Vérifiez cette ouverture pour chaque secteur radio."
    };
  }
  if (normalized.includes("no antenna model was confirmed")) {
    return {
      ...issue,
      title: "Famille d’antenne générique",
      impact: "Aucun modèle d’antenne précis n’a été confirmé; une famille générique a été utilisée.",
      recommended_action: "Sélectionnez un modèle qualifié avant de présenter le résultat comme fidèle à un constructeur."
    };
  }
  if (
    normalized.includes("sector beams and labels") &&
    normalized.includes("controlled product default")
  ) {
    return {
      ...issue,
      title: "Aides visuelles activées",
      impact: "Les faisceaux et labels sont affichés pour faciliter l’inspection; ils ne proviennent pas du cahier de charge.",
      recommended_action: "Conservez-les pour la revue ou désactivez-les dans une prochaine modification."
    };
  }
  if (normalized.includes("sector_count_azimuth_mismatch")) {
    return {
      ...issue,
      title: "Azimuts complétés",
      impact: "Le nombre d’azimuts fourni ne couvrait pas tous les secteurs; le backend a complété la répartition.",
      recommended_action: "Confirmez les azimuts affichés avant utilisation technique."
    };
  }
  if (
    normalized.includes("rag") &&
    (normalized.includes("degrad") || normalized.includes("dégrad"))
  ) {
    return {
      ...issue,
      title: "Recherche documentaire temporairement dégradée",
      impact: "Le classement secondaire des sources n’a pas répondu; l’ordre de recherche initial a été conservé.",
      recommended_action: "Le design reste inspectable; vérifiez les sources publiées dans les livrables."
    };
  }
  if (
    normalized.includes("extraction déterministe") ||
    normalized.includes("deterministic_extraction_requested")
  ) {
    return {
      ...issue,
      title: "Compréhension en mode de secours",
      impact: "La demande a été structurée avec des règles déterministes, sans décision du modèle Groq.",
      recommended_action: "Vérifiez les paramètres compris avant de modifier ou livrer le design."
    };
  }
  if (
    normalized.includes("qa spatiale") ||
    normalized.includes("mesh_level_spatial_basic")
  ) {
    return {
      ...issue,
      title: "Contrôle géométrique borné",
      impact: "Les positions et recouvrements généraux sont contrôlés, mais pas les collisions détaillées entre triangles.",
      recommended_action: "Effectuez une revue technique complémentaire avant validation d’ingénierie."
    };
  }
  return issue;
}

export function failureRecoveryMessage(issue: UserIssue | null): string {
  if (!issue) {
    return "Votre demande est conservée. Corrigez-la avant de relancer la conception.";
  }
  const impact = issue.impact.trim();
  const title = issue.title.trim();
  if (impact) {
    return impact;
  }
  if (title) {
    return title;
  }
  return "Votre demande est conservée. Corrigez-la avant de relancer la conception.";
}

export function normalizedIssueCopy(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

export function isAssetIssueText(text: string): boolean {
  const normalized = text.toUpperCase();
  return normalized.includes("ASSET") || normalized.includes("NOT_VENDOR_GRADE") || normalized.includes("ATTRIBUTION_REQUIRED") || normalized.includes("INTERNAL_TEST_MINIMAL") || normalized.includes("CC_BY");
}

export function uniqueRequirementWarnings<T extends { code: string; message: string }>(warnings: T[]): T[] {
  const seen = new Set<string>();
  return warnings.filter((warning) => {
    const key = `${warning.code}:${warning.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function humanRequirementWarning(warning: { code: string; message: string }): string {
  const messages: Record<string, string> = {
    DEFAULT_NETWORK_USED: "Technologie proposée: 5G. Confirmez-la si le cahier de charge vise un autre réseau.",
    DEFAULT_TOWER_USED: "Structure proposée: pylône treillis. Confirmez-la si le support attendu est différent.",
    DEFAULT_TOWER_HEIGHT_USED: "Hauteur proposée: 30 m. Cette valeur doit être confirmée avant usage technique.",
    DEFAULT_SECTOR_COUNT_USED: "Configuration proposée: 3 secteurs.",
    DEFAULT_INSTALL_HEIGHT_USED: "La hauteur d’installation des antennes a été proposée faute de valeur explicite.",
    DEFAULT_AZIMUTHS_USED: "Les azimuts ont été répartis automatiquement selon le nombre de secteurs.",
    DEFAULT_MECHANICAL_TILT_USED: "Inclinaison mécanique proposée: 3°. Confirmez-la si une valeur radio est imposée.",
    DEFAULT_ELECTRICAL_TILT_USED: "Inclinaison électrique proposée: 0°. Confirmez-la si une valeur radio est imposée.",
    DEFAULT_BEAMWIDTH_USED: "Ouverture d’antenne proposée: 65°.",
    DEFAULT_CABLES_USED: "Les câbles ont été ajoutés à la scène faute d’instruction contraire.",
    DEFAULT_BEAMS_USED: "La visualisation des faisceaux a été activée.",
    DEFAULT_LABELS_USED: "Les labels techniques ont été activés.",
    LLM_FIELD_REPAIRED: "Des valeurs manquantes ont été complétées à partir de votre texte. Vérifiez les valeurs affichées.",
    LLM_SOURCE_FIELD_PROTECTED: "Une valeur proposée automatiquement contredisait votre demande ; votre valeur a été conservée."
  };
  if (messages[warning.code]) {
    return messages[warning.code];
  }
  if (warning.code.startsWith("DEFAULT_")) {
    return "Une valeur par défaut a été proposée par le backend. Vérifiez les paramètres affichés avant génération.";
  }
  if (warning.code.startsWith("LLM_")) {
    return "Une valeur proposée automatiquement a été vérifiée et corrigée. Contrôlez les paramètres affichés avant génération.";
  }
  return warning.message;
}

export function humanExtractionFallback(reason: string | null | undefined): string {
  const normalized = (reason ?? "").toLowerCase();
  if (normalized.includes("requested")) {
    return "Les paramètres ont été extraits directement de votre demande, comme demandé. Vérifiez-les avant génération.";
  }
  if (normalized.includes("timeout")) {
    return "L’analyse assistée n’a pas répondu à temps ; les paramètres ont été extraits directement de votre demande. Vérifiez-les avant génération.";
  }
  if (normalized.includes("unavailable") || normalized.includes("disabled")) {
    return "L’analyse assistée n’est pas disponible ; les paramètres ont été extraits directement de votre demande. Vérifiez-les avant génération.";
  }
  return "L’analyse assistée n’a pas pu être utilisée ; les paramètres ont été extraits directement de votre demande. Vérifiez-les avant génération.";
}

export function humanExtractionError(error: { code: string; message: string }): string {
  if (error.code === "TELECOM_BRIEF_REQUIRED") {
    return "Précisez le site à concevoir : réseau, type de support ou dimensions. Une demande d’analyse d’image ne suffit pas pour générer un site. Pour un objet sans site télécom, choisissez Intention libre.";
  }
  const normalized = `${error.code} ${error.message}`.toLowerCase();
  if (normalized.includes("timeout")) {
    return "Le service d’analyse intelligente n’a pas répondu dans le délai prévu.";
  }
  return "Le service d’analyse intelligente n’a pas pu valider cette extraction.";
}

export function humanRequirementField(field: string): string {
  return (
    {
      tower_height_m: "hauteur du pylône",
      sector_count: "nombre de secteurs",
      antenna_install_height_m: "hauteur d’installation des antennes",
      azimuths_deg: "azimuts",
      "sector_count/azimuths_deg": "nombre de secteurs et azimuts"
    }[field] ?? field.replaceAll("_", " ")
  );
}

export function humanTowerType(towerType: string): string {
  return {
    lattice_tower: "pylône treillis",
    monopole: "monopôle",
    rooftop_mast: "mât toiture",
    small_cell_pole: "support small cell"
  }[towerType] ?? towerType.replaceAll("_", " ");
}

export function humanAdaptationTool(tool: string): string {
  return {
    parametric_rebuild: "reconstruction paramétrique du composant",
    sector_layout: "placement radio contrôlé",
    asset_transform: "transformation d’asset",
    scene_visibility: "composition de scène",
    geometry_program_rebuild: "régénération géométrique LLM contrôlée"
  }[tool] ?? "outil backend déclaré";
}

export function summarizeAdaptationCapabilityGroups(
  capabilities: SceneAdaptationCapabilities | null
): string[] {
  const groups = new Map<
    string,
    { label: string; labels: Set<string>; sectors: Set<number>; tools: Set<string> }
  >();
  for (const capability of capabilities?.capabilities ?? []) {
    const sectorMatch = capability.path.match(/^\/sectors\/(\d+)\//);
    const key = sectorMatch
      ? "sectors"
      : capability.path.startsWith("/geometry_programs/")
        ? "generated"
      : capability.path.startsWith("/tower/")
        ? "tower"
        : capability.path.startsWith("/visual_elements/")
          ? "scene"
          : "other";
    const group =
      groups.get(key) ??
      {
        label:
          key === "sectors"
            ? "Secteurs radio"
            : key === "generated"
              ? "Composants générés"
            : key === "tower"
              ? "Pylône"
              : key === "scene"
                ? "Affichage de la scène"
                : "Autres composants",
        labels: new Set<string>(),
        sectors: new Set<number>(),
        tools: new Set<string>()
      };
    group.labels.add(capability.label);
    group.tools.add(humanAdaptationTool(capability.execution_tool));
    if (sectorMatch) group.sectors.add(Number(sectorMatch[1]) + 1);
    groups.set(key, group);
  }
  return ["scene", "tower", "sectors", "generated", "other"].flatMap((key) => {
    const group = groups.get(key);
    if (!group) return [];
    const sectorScope = group.sectors.size ? ` sur ${group.sectors.size} secteurs` : "";
    return [
      `${group.label} · ${group.labels.size} paramètres${sectorScope}: ${[
        ...group.labels
      ].join(", ")} · ${[...group.tools].join(" / ")}`
    ];
  });
}

export function yesNo(value: boolean): string {
  return value ? "oui" : "non";
}


