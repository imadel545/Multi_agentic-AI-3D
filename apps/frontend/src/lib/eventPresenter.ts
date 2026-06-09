import type { StudioEvent } from "../api/types";
import { stringifyCompact } from "./format";

export type EventPhase =
  | "Document Intelligence"
  | "LLM / Groq"
  | "RAG / Memory"
  | "Planning"
  | "Blender"
  | "QA"
  | "Versioning"
  | "Workflow";

export type PresentedEvent = {
  phase: EventPhase;
  title: string;
  summary: string;
  status: "running" | "passed" | "warning" | "failed" | "info";
  time: string;
  actor: string;
  detail?: string;
};

const eventLabels: Record<string, { title: string; summary: string; phase: EventPhase }> = {
  design_created: {
    title: "Design demandé",
    summary: "Le studio a reçu un cahier des charges et ouvert un workflow.",
    phase: "Workflow",
  },
  document_pack_ingested: {
    title: "Pack documentaire ingéré",
    summary: "Les documents ont été indexés pour extraction et consolidation.",
    phase: "Document Intelligence",
  },
  documents_classified: {
    title: "Documents classifiés",
    summary: "Les fichiers ont été classés par utilité technique.",
    phase: "Document Intelligence",
  },
  ocr_completed: {
    title: "OCR terminé",
    summary: "Le texte scanné exploitable a été extrait.",
    phase: "Document Intelligence",
  },
  dxf_extraction_completed: {
    title: "DXF extrait",
    summary: "Les layers et annotations CAD ont été lus.",
    phase: "Document Intelligence",
  },
  groq_extraction_completed: {
    title: "Extraction Groq terminée",
    summary: "Le LLM a proposé des champs bornés avec preuves.",
    phase: "LLM / Groq",
  },
  validated_requirements_received: {
    title: "Exigences validées reçues",
    summary: "Le backend utilise un RequirementSpec validé, pas un prompt fragile.",
    phase: "Planning",
  },
  scene_planning_completed: {
    title: "SceneSpec planifiée",
    summary: "Les objets 3D, dimensions et options visuelles sont prêts pour Blender.",
    phase: "Planning",
  },
  blender_started: {
    title: "Blender lancé",
    summary: "La génération GLB réelle a démarré.",
    phase: "Blender",
  },
  blender_completed: {
    title: "Blender terminé",
    summary: "Le GLB et les artifacts visuels ont été produits.",
    phase: "Blender",
  },
  blender_failed: {
    title: "Blender a échoué",
    summary: "La version n’a pas produit un artifact 3D complet.",
    phase: "Blender",
  },
  qa_failed: {
    title: "QA refusée",
    summary: "La version générée n’a pas passé les contrôles qualité.",
    phase: "QA",
  },
  workflow_completed: {
    title: "Workflow terminé",
    summary: "Le design est prêt à inspecter.",
    phase: "Workflow",
  },
  edit_patch_created: {
    title: "Patch d’édition créé",
    summary: "L’agent a transformé le prompt en modification structurée.",
    phase: "Versioning",
  },
  edit_patch_rejected: {
    title: "Modification refusée",
    summary: "La demande n’a pas pu être appliquée sans casser les validations.",
    phase: "Versioning",
  },
  version_created: {
    title: "Nouvelle version créée",
    summary: "Une version indépendante a été préparée pour génération et QA.",
    phase: "Versioning",
  },
};

export function presentEvent(event: StudioEvent): PresentedEvent {
  const type = event.event_type;
  const known = eventLabels[type];
  const payload = event.payload ?? {};
  const phase = known?.phase ?? inferPhase(type, payload);
  const status = inferStatus(type, payload);
  const actor = stringifyCompact(payload.agent ?? payload.node ?? actorForPhase(phase));
  const detail = Object.keys(payload).length ? stringifyCompact(payload) : undefined;

  return {
    phase,
    title: known?.title ?? humanizeEvent(type),
    summary: enrichSummary(known?.summary ?? "Étape agentique exécutée.", type, payload),
    status,
    time: event.created_at ?? event.timestamp ?? "time pending",
    actor,
    detail,
  };
}

export function groupPresentedEvents(events: StudioEvent[]): Array<[EventPhase, PresentedEvent[]]> {
  const orderedPhases: EventPhase[] = [
    "Document Intelligence",
    "LLM / Groq",
    "RAG / Memory",
    "Planning",
    "Blender",
    "QA",
    "Versioning",
    "Workflow",
  ];
  const groups = new Map<EventPhase, PresentedEvent[]>();
  for (const event of events) {
    const presented = presentEvent(event);
    const current = groups.get(presented.phase) ?? [];
    current.push(presented);
    groups.set(presented.phase, current);
  }
  return orderedPhases
    .filter((phase) => groups.has(phase))
    .map((phase) => [phase, groups.get(phase) ?? []]);
}

function inferPhase(type: string, payload: Record<string, unknown>): EventPhase {
  const raw = `${type} ${stringifyCompact(payload.node)} ${stringifyCompact(payload.agent)}`.toLowerCase();
  if (raw.includes("doc") || raw.includes("ocr") || raw.includes("dxf")) return "Document Intelligence";
  if (raw.includes("groq") || raw.includes("llm")) return "LLM / Groq";
  if (raw.includes("rag") || raw.includes("memory")) return "RAG / Memory";
  if (raw.includes("scene") || raw.includes("requirements") || raw.includes("planner")) return "Planning";
  if (raw.includes("blender")) return "Blender";
  if (raw.includes("qa") || raw.includes("validation")) return "QA";
  if (raw.includes("version") || raw.includes("edit") || raw.includes("rollback")) return "Versioning";
  return "Workflow";
}

function inferStatus(type: string, payload: Record<string, unknown>): PresentedEvent["status"] {
  const raw = `${type} ${stringifyCompact(payload.status)} ${stringifyCompact(payload.reason)}`.toLowerCase();
  if (raw.includes("failed") || raw.includes("rejected") || raw.includes("error")) return "failed";
  if (raw.includes("started") || raw.includes("running") || raw.includes("pending")) return "running";
  if (raw.includes("warning")) return "warning";
  if (raw.includes("completed") || raw.includes("created") || raw.includes("validated")) return "passed";
  return "info";
}

function actorForPhase(phase: EventPhase): string {
  if (phase === "Blender") return "BlenderWorker";
  if (phase === "QA") return "QAEngine";
  if (phase === "LLM / Groq") return "GroqExtractor";
  if (phase === "Document Intelligence") return "DocumentAgent";
  if (phase === "Versioning") return "SceneEditAgent";
  return "Workflow";
}

function enrichSummary(
  summary: string,
  type: string,
  payload: Record<string, unknown>,
): string {
  if (type === "edit_patch_rejected" && payload.reason) {
    return `Modification refusée : ${stringifyCompact(payload.reason)}. Le design actif reste protégé.`;
  }
  if (type === "workflow_completed" && payload.duration_ms) {
    return `${summary} Durée : ${Math.round(Number(payload.duration_ms) / 1000)} s.`;
  }
  if (type === "version_created" && payload.version_id) {
    return `${summary} Version ${stringifyCompact(payload.version_id)}.`;
  }
  return summary;
}

function humanizeEvent(type: string): string {
  return type
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
