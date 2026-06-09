import { stringifyCompact } from "./format";

export type PresentedIssue = {
  code: string;
  title: string;
  impact: string;
  action: string;
  detail: string;
  severity: "info" | "warning" | "error";
  count: number;
};

type IssueInput = Record<string, unknown>;

type IssueRule = {
  match: (code: string) => boolean;
  title: string;
  impact: string;
  action: string;
};

const issueRules: IssueRule[] = [
  {
    match: (code) => code.includes("ASSET_IMPORT_INTERNAL_TEST_MINIMAL"),
    title: "Asset interne minimal",
    impact:
      "Le GLB est exploitable pour valider le pipeline technique, mais il ne représente pas encore un asset constructeur.",
    action: "Remplacer cet asset par un GLB vendor-grade avant une démonstration finale réaliste.",
  },
  {
    match: (code) => code.includes("ASSET_IMPORT_INTERNAL_CLEANED"),
    title: "Asset interne nettoyé",
    impact:
      "L’objet est intégré et contrôlé, mais sa source reste interne au projet et non certifiée fournisseur.",
    action: "Conserver pour MVP, puis intégrer un asset réel avec licence claire.",
  },
  {
    match: (code) => code.includes("ASSET_IMPORT_CC_BY"),
    title: "Asset CC-BY non vendor-grade",
    impact:
      "L’asset est réel et importé, mais il demande attribution et ne garantit pas une fidélité constructeur.",
    action: "Afficher l’attribution et planifier un remplacement par modèle constructeur si nécessaire.",
  },
  {
    match: (code) => code.includes("ASSET_IMPORT_ATTRIBUTION_REQUIRED"),
    title: "Attribution asset requise",
    impact: "La licence de l’asset exige une attribution visible dans la documentation ou le frontend.",
    action: "Garder l’attribution accessible dans le panneau Assets ou les téléchargements.",
  },
  {
    match: (code) => code.includes("GEOMETRY_VALIDATION_BOUNDING_BOX"),
    title: "Bounding box partiellement interprétée",
    impact:
      "La QA géométrique a validé la scène, mais un détail de bounding box n’a pas pu être présenté finement.",
    action: "Inspecter le rapport geometry_validation si une mesure exacte est nécessaire.",
  },
  {
    match: (code) => code.includes("DEFAULT_TOWER_CHARACTERISTICS"),
    title: "Caractéristiques pylône inférées",
    impact: "Le système a complété des paramètres structurels manquants à partir du type et de la hauteur.",
    action: "Fournir un plan APD ou corriger les caractéristiques si elles sont contractuelles.",
  },
  {
    match: (code) => code.includes("LLM_FIELD_REPAIRED"),
    title: "Champ LLM réparé",
    impact: "Une sortie LLM incohérente a été corrigée par la baseline déterministe avant validation.",
    action: "Vérifier les champs extraits si le cahier des charges est ambigu.",
  },
  {
    match: (code) => code.includes("TOWER_PLATFORM_RECOMMENDED"),
    title: "Plateforme pylône recommandée",
    impact: "Le design reste générable, mais l’accès maintenance peut être incomplet pour un pylône haut.",
    action: "Ajouter une plateforme si le livrable doit représenter un site exploitable terrain.",
  },
  {
    match: (code) => code.includes("RF_BEAMWIDTH_NARROW"),
    title: "Ouverture de faisceau étroite",
    impact: "Les faisceaux affichés ne couvrent pas tout l’angle théorique attendu pour trois secteurs.",
    action: "Ajuster le beamwidth ou accepter cette limite comme visualisation technique.",
  },
  {
    match: (code) => code.includes("DOC_ACCESSORY_GPS_ENABLED"),
    title: "GPS activé par preuve documentaire",
    impact: "L’antenne GPS a été ajoutée parce que le document pack la demandait explicitement.",
    action: "Aucune action requise si la preuve documentaire est correcte.",
  },
  {
    match: (code) => code.includes("DOC_ACCESSORY_POWER_CABINET_ENABLED"),
    title: "Armoire énergie activée par preuve documentaire",
    impact: "L’armoire énergie a été ajoutée parce que le document pack la demandait explicitement.",
    action: "Aucune action requise si la preuve documentaire est correcte.",
  },
  {
    match: (code) => code.includes("MOUNT_ZONES_VALID"),
    title: "Zone de montage invalide",
    impact: "La version éditée a été refusée avant acceptation finale car un montage ne respecte pas les règles.",
    action: "Modifier la hauteur ou l’asset demandé, puis relancer l’édition.",
  },
];

export function presentIssues(items: IssueInput[] = []): PresentedIssue[] {
  const grouped = new Map<string, PresentedIssue>();

  for (const item of items) {
    const code = stringifyCompact(item.code ?? item.severity ?? "ISSUE");
    const detail = stringifyCompact(item.message ?? item);
    const severity = item.severity === "error" || item.severity === "critical" ? "error" : "warning";
    const rule = issueRules.find((candidate) => candidate.match(code));
    const fallbackTitle = humanizeCode(code);
    const key = `${severity}:${rule?.title ?? fallbackTitle}:${detail}`;
    const current = grouped.get(key);
    if (current) {
      current.count += 1;
      continue;
    }

    grouped.set(key, {
      code,
      title: rule?.title ?? fallbackTitle,
      impact:
        rule?.impact ??
        "Le backend a remonté un signal technique qui doit rester visible pour éviter un échec silencieux.",
      action: rule?.action ?? "Ouvrir le détail technique, puis corriger la donnée ou l’asset concerné.",
      detail,
      severity,
      count: 1,
    });
  }

  return Array.from(grouped.values()).sort((left, right) => {
    if (left.severity !== right.severity) return left.severity === "error" ? -1 : 1;
    return right.count - left.count;
  });
}

export function explainMutationError(error: unknown): string {
  const message = error instanceof Error ? error.message : stringifyCompact(error);
  if (message.toLowerCase().includes("could not interpret")) {
    return "L’agent d’édition n’a pas pu convertir cette demande en patch SceneSpec sûr. Essaie une commande plus précise : hauteur, azimuts, câbles, GPS, armoire ou tilt.";
  }
  if (message.toLowerCase().includes("quality") || message.toLowerCase().includes("validation")) {
    return "La modification a été refusée par les validations. Le design existant reste inchangé.";
  }
  return message;
}

function humanizeCode(code: string): string {
  return code
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
