import {
  Bot,
  FileArchive,
  MessageSquarePlus,
  RadioTower,
  Send,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { useMemo, useState, type Dispatch, type SetStateAction } from "react";

import { useStudioMutations } from "../../api/hooks";
import type { StudioEvent, WorkflowStatus } from "../../api/types";
import { StatusBadge } from "../../components/Badge";
import { ActionButton, CommandMessage, PanelShell } from "../../components/Primitives";
import { presentEvent } from "../../lib/eventPresenter";
import { explainMutationError } from "../../lib/issuePresenter";
import { shortId } from "../../lib/format";
import { useStudioStore } from "../../stores/studioStore";

const defaultPrompt =
  "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, faisceaux, GPS, armoire énergie et labels. Tilt mécanique 5°.";

type AgentConsoleProps = {
  workflow?: WorkflowStatus;
  events?: StudioEvent[];
};

type CommandLogItem = {
  id: string;
  label: string;
  status: "running" | "passed" | "warning" | "failed" | "info";
  body: string;
};

const quickPrompts = [
  { label: "Change HBA", prompt: "mets les antennes à 26m" },
  { label: "Change azimuths", prompt: "change les azimuts à 30, 150, 270" },
  { label: "Add GPS", prompt: "ajoute une antenne GPS" },
  { label: "Add power", prompt: "ajoute une armoire énergie au sol" },
  { label: "Remove cables", prompt: "supprime les câbles" },
  { label: "Explain QA", prompt: "explique les warnings et propose la prochaine action" },
];

const agentStages = [
  { label: "Requirements", keys: ["design_created", "requirements", "extraction"] },
  { label: "RAG / Memory", keys: ["rag", "memory"] },
  { label: "RF / Tower", keys: ["rf", "tower", "validated"] },
  { label: "Scene Planner", keys: ["scene_planning", "scene"] },
  { label: "Blender", keys: ["blender_started", "blender_completed"] },
  { label: "QA", keys: ["qa", "workflow_completed"] },
];

export function AgentConsole({ workflow, events = [] }: AgentConsoleProps) {
  const activeWorkflowId = useStudioStore((state) => state.activeWorkflowId);
  const activePackId = useStudioStore((state) => state.activePackId);
  const setActiveWorkflowId = useStudioStore((state) => state.setActiveWorkflowId);
  const setActivePackId = useStudioStore((state) => state.setActivePackId);
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [editPrompt, setEditPrompt] = useState("mets les antennes à 26m");
  const [useLlm, setUseLlm] = useState(true);
  const [commandMode, setCommandMode] = useState<"generate" | "edit" | "documents">("generate");
  const [commandLog, setCommandLog] = useState<CommandLogItem[]>([]);
  const mutations = useStudioMutations(activeWorkflowId, activePackId);

  const presentedEvents = useMemo(() => events.slice(-6).map(presentEvent).reverse(), [events]);

  const createDesign = async () => {
    pushCommandLog(setCommandLog, {
      label: "Génération demandée",
      status: "running",
      body: "Les agents vont extraire les exigences, planifier la SceneSpec, lancer Blender et relancer QA.",
    });
    try {
      const response = await mutations.createDesign.mutateAsync({ prompt, useLlm });
      setActiveWorkflowId(response.workflow_id);
      pushCommandLog(setCommandLog, {
        label: "Workflow créé",
        status: "passed",
        body: `Workflow ${shortId(response.workflow_id)} ouvert avec statut ${response.status}.`,
      });
    } catch (error) {
      pushCommandLog(setCommandLog, {
        label: "Génération refusée",
        status: "failed",
        body: explainMutationError(error),
      });
    }
  };

  const applyEdit = async () => {
    if (!activeWorkflowId) return;
    pushCommandLog(setCommandLog, {
      label: "Édition envoyée",
      status: "running",
      body: editPrompt,
    });
    try {
      const response = await mutations.editDesign.mutateAsync({ prompt: editPrompt });
      pushCommandLog(setCommandLog, {
        label: response.status === "completed" ? "Nouvelle version validée" : "Édition traitée",
        status: response.errors?.length ? "warning" : "passed",
        body: response.version_id
          ? `Version ${response.version_id} créée. QA ${response.qa_score ?? "n/a"}.`
          : "Le backend a traité la demande ; vérifie le panneau Versions/QA.",
      });
    } catch (error) {
      pushCommandLog(setCommandLog, {
        label: "Édition refusée",
        status: "failed",
        body: explainMutationError(error),
      });
    }
  };

  const uploadPack = async (file?: File) => {
    if (!file) return;
    pushCommandLog(setCommandLog, {
      label: "Pack documentaire envoyé",
      status: "running",
      body: file.name,
    });
    try {
      const response = await mutations.uploadPack.mutateAsync(file);
      setActivePackId(response.pack_id);
      setCommandMode("documents");
      pushCommandLog(setCommandLog, {
        label: "Pack prêt pour inspection",
        status: response.can_generate_design ? "passed" : "warning",
        body: `${response.document_count} documents, ${response.missing_blocking_count} champs bloquants.`,
      });
    } catch (error) {
      pushCommandLog(setCommandLog, {
        label: "Pack refusé",
        status: "failed",
        body: explainMutationError(error),
      });
    }
  };

  const generateFromPack = async () => {
    if (!activePackId) return;
    pushCommandLog(setCommandLog, {
      label: "Génération depuis pack",
      status: "running",
      body: "Le ProjectDesignSpec consolidé sera converti en RequirementSpec validé.",
    });
    try {
      const response = await mutations.generateFromPack.mutateAsync();
      setActiveWorkflowId(response.workflow_id);
      pushCommandLog(setCommandLog, {
        label: "Design généré depuis pack",
        status: "passed",
        body: `Workflow ${shortId(response.workflow_id)} créé depuis le pack documentaire.`,
      });
    } catch (error) {
      pushCommandLog(setCommandLog, {
        label: "Pack incomplet",
        status: "failed",
        body: explainMutationError(error),
      });
    }
  };

  const commandDisabled = mutations.createDesign.isPending || prompt.trim().length === 0;
  const currentOperation = presentedEvents[0];

  return (
    <PanelShell
      className="agent-console"
      title="Agent Command Center"
      eyebrow={workflow?.status ? `${workflow.status} · ${shortId(workflow.workflow_id)}` : "ready"}
      icon={<Bot size={18} />}
      action={<StatusBadge status={workflow?.status ?? "idle"} />}
    >
      <div className="agent-status-strip">
        {agentStages.map((stage) => (
          <div className="agent-stage-chip" key={stage.label}>
            <span>{stage.label}</span>
            <StatusBadge status={stageStatus(stage.keys, events, workflow)} />
          </div>
        ))}
      </div>

      <div className="conversation-thread">
        <CommandMessage
          role="system"
          status={workflow?.status === "failed" ? "failed" : "info"}
          title={currentOperation?.title ?? "Studio prêt"}
          meta={currentOperation?.actor ?? "Orchestrator"}
          body={
            currentOperation?.summary ??
            "Décris un site télécom ou charge un pack documentaire pour générer un design 3D réel."
          }
        />

        {commandLog.map((item) => (
          <CommandMessage
            key={item.id}
            role={item.status === "running" ? "user" : "assistant"}
            status={item.status}
            title={item.label}
            body={item.body}
          />
        ))}

        {presentedEvents.slice(0, 4).map((event, index) => (
          <CommandMessage
            key={`${event.title}-${event.time}-${index}`}
            role="assistant"
            status={event.status}
            title={event.title}
            meta={event.phase}
            body={event.summary}
          />
        ))}
      </div>

      <div className="command-mode-tabs" aria-label="Command mode">
        {(["generate", "edit", "documents"] as const).map((mode) => (
          <button
            className={commandMode === mode ? "active" : ""}
            key={mode}
            type="button"
            onClick={() => setCommandMode(mode)}
          >
            {mode === "generate" ? "Generate" : mode === "edit" ? "Edit" : "Documents"}
          </button>
        ))}
      </div>

      {commandMode === "generate" ? (
        <section className="command-composer">
          <label htmlFor="requirements">Technical brief</label>
          <textarea
            id="requirements"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={6}
          />
          <label className="toggle-line">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(event) => setUseLlm(event.target.checked)}
            />
            Use Groq GPT-OSS path when configured
          </label>
          <ActionButton variant="primary" onClick={createDesign} disabled={commandDisabled}>
            <Send size={16} />
            {mutations.createDesign.isPending ? "Generating..." : "Generate Design"}
          </ActionButton>
        </section>
      ) : null}

      {commandMode === "edit" ? (
        <section className="command-composer">
          <div className="quick-command-grid">
            {quickPrompts.map((item) => (
              <button key={item.label} type="button" onClick={() => setEditPrompt(item.prompt)}>
                <Sparkles size={14} />
                {item.label}
              </button>
            ))}
          </div>
          <label htmlFor="edit">Prompt edit</label>
          <textarea
            id="edit"
            value={editPrompt}
            onChange={(event) => setEditPrompt(event.target.value)}
            rows={4}
          />
          <ActionButton
            onClick={applyEdit}
            disabled={!activeWorkflowId || mutations.editDesign.isPending}
          >
            <WandSparkles size={15} />
            Apply Validated Edit
          </ActionButton>
        </section>
      ) : null}

      {commandMode === "documents" ? (
        <section className="command-composer">
          <label htmlFor="pack">Document pack ZIP</label>
          <div className="file-input-shell">
            <FileArchive size={16} />
            <input
              id="pack"
              type="file"
              accept=".zip,application/zip"
              onChange={(event) => void uploadPack(event.target.files?.[0])}
            />
          </div>
          <ActionButton
            onClick={generateFromPack}
            disabled={!activePackId || mutations.generateFromPack.isPending}
          >
            <RadioTower size={15} />
            Generate From Pack
          </ActionButton>
          {!activePackId ? (
            <p className="composer-hint">
              Charge un ZIP APD/PDF/DXF pour inspecter les preuves avant génération.
            </p>
          ) : null}
        </section>
      ) : null}
    </PanelShell>
  );
}

function pushCommandLog(
  setCommandLog: Dispatch<SetStateAction<CommandLogItem[]>>,
  item: Omit<CommandLogItem, "id">,
) {
  setCommandLog((current) => [{ id: `${Date.now()}-${item.label}`, ...item }, ...current].slice(0, 6));
}

function stageStatus(keys: string[], events: StudioEvent[], workflow?: WorkflowStatus) {
  const normalizedEvents = events.map((event) => event.event_type.toLowerCase());
  if (
    workflow?.status === "failed" &&
    keys.some((key) => normalizedEvents.some((event) => event.includes(key)))
  ) {
    return "failed";
  }
  if (keys.some((key) => normalizedEvents.some((event) => event.includes(key)))) {
    return "completed";
  }
  if (workflow?.status === "generating" || workflow?.status === "pending") return "pending";
  return "idle";
}
