import { Bot, FileArchive, RadioTower, Send, Sparkles, WandSparkles } from "lucide-react";
import { useState, type Dispatch, type SetStateAction } from "react";

import { useStudioMutations } from "../../api/hooks";
import type { StudioEvent, WorkflowStatus } from "../../api/types";
import { Badge } from "../../components/Badge";
import { StatusBadge } from "../../components/Badge";
import { shortId, stringifyCompact } from "../../lib/format";
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
  status: string;
};

const quickPrompts = [
  "mets les antennes à 26m",
  "change les azimuts à 30, 150, 270",
  "supprime les câbles",
  "ajoute GPS et armoire énergie",
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
  const [commandLog, setCommandLog] = useState<CommandLogItem[]>([]);
  const mutations = useStudioMutations(activeWorkflowId, activePackId);

  const createDesign = async () => {
    const response = await mutations.createDesign.mutateAsync({ prompt, useLlm });
    setActiveWorkflowId(response.workflow_id);
    pushCommandLog(setCommandLog, "Generate design", response.status);
  };

  const applyEdit = async () => {
    if (!activeWorkflowId) return;
    const response = await mutations.editDesign.mutateAsync({ prompt: editPrompt });
    pushCommandLog(setCommandLog, `Edit: ${editPrompt}`, response.status);
  };

  const uploadPack = async (file?: File) => {
    if (!file) return;
    const response = await mutations.uploadPack.mutateAsync(file);
    setActivePackId(response.pack_id);
    pushCommandLog(setCommandLog, `Upload pack ${file.name}`, response.status);
  };

  const generateFromPack = async () => {
    if (!activePackId) return;
    const response = await mutations.generateFromPack.mutateAsync();
    setActiveWorkflowId(response.workflow_id);
    pushCommandLog(setCommandLog, "Generate from document pack", response.status);
  };

  const latestEvent = events.at(-1);
  const commandDisabled = mutations.createDesign.isPending || prompt.trim().length === 0;

  return (
    <aside className="agent-console">
      <div className="panel-heading">
        <Bot size={18} />
        <div>
          <h2>Agent Command Center</h2>
          <p>
            {workflow?.status
              ? `${workflow.status} · ${shortId(workflow.workflow_id)}`
              : "Create, inspect and iterate a real workflow"}
          </p>
        </div>
      </div>

      <section className="agent-state-card">
        <div>
          <span>Current operation</span>
          <strong>{latestEvent?.event_type ?? workflow?.status ?? "ready"}</strong>
          <p>
            {latestEvent?.payload
              ? stringifyCompact(latestEvent.payload).slice(0, 120)
              : "Waiting for command."}
          </p>
        </div>
        <StatusBadge status={workflow?.status ?? "idle"} />
      </section>

      <section className="agent-lanes">
        {agentStages.map((stage) => (
          <div className="agent-lane" key={stage.label}>
            <span>{stage.label}</span>
            <StatusBadge status={stageStatus(stage.keys, events, workflow)} />
          </div>
        ))}
      </section>

      <section className="console-section">
        <label htmlFor="requirements">Technical brief</label>
        <textarea
          id="requirements"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={7}
        />
        <label className="toggle-line">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(event) => setUseLlm(event.target.checked)}
          />
          Use Groq GPT-OSS path when configured
        </label>
        <button
          className="primary-action"
          type="button"
          onClick={createDesign}
          disabled={commandDisabled}
        >
          <Send size={16} />
          {mutations.createDesign.isPending ? "Generating..." : "Generate Design"}
        </button>
        {mutations.createDesign.isError ? (
          <p className="error-line">{mutations.createDesign.error.message}</p>
        ) : null}
      </section>

      <section className="console-section">
        <div className="quick-command-grid">
          {quickPrompts.map((item) => (
            <button key={item} type="button" onClick={() => setEditPrompt(item)}>
              <Sparkles size={14} />
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="console-section">
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
        <div className="inline-actions">
          <StatusBadge status={activePackId ? "pack_selected" : "no_pack"} />
          <button
            type="button"
            onClick={generateFromPack}
            disabled={!activePackId || mutations.generateFromPack.isPending}
          >
            <WandSparkles size={15} />
            Generate From Pack
          </button>
        </div>
        {mutations.uploadPack.isError ? (
          <p className="error-line">{mutations.uploadPack.error.message}</p>
        ) : null}
      </section>

      <section className="console-section">
        <label htmlFor="edit">Prompt edit</label>
        <textarea
          id="edit"
          value={editPrompt}
          onChange={(event) => setEditPrompt(event.target.value)}
          rows={4}
        />
        <button
          type="button"
          onClick={applyEdit}
          disabled={!activeWorkflowId || mutations.editDesign.isPending}
        >
          <WandSparkles size={15} />
          Apply Validated Edit
        </button>
        {mutations.editDesign.isError ? (
          <p className="error-line">{mutations.editDesign.error.message}</p>
        ) : null}
      </section>

      <section className="console-section">
        <div className="panel-heading compact">
          <RadioTower size={15} />
          <h2>Command log</h2>
          <Badge tone={commandLog.length ? "good" : "idle"}>{commandLog.length}</Badge>
        </div>
        <div className="command-log">
          {commandLog.length ? (
            commandLog.map((item) => (
              <article key={item.id}>
                <span>{item.label}</span>
                <StatusBadge status={item.status} />
              </article>
            ))
          ) : (
            <p className="hint">Commands executed in this browser session appear here.</p>
          )}
        </div>
      </section>
    </aside>
  );
}

function pushCommandLog(
  setCommandLog: Dispatch<SetStateAction<CommandLogItem[]>>,
  label: string,
  status: string,
) {
  setCommandLog((current) =>
    [{ id: `${Date.now()}-${label}`, label, status }, ...current].slice(0, 6),
  );
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
