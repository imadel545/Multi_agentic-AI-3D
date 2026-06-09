import { Bot, FileArchive, Send, WandSparkles } from "lucide-react";
import { useState } from "react";

import { useStudioMutations } from "../../api/hooks";
import { StatusBadge } from "../../components/Badge";
import { useStudioStore } from "../../stores/studioStore";

const defaultPrompt =
  "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, faisceaux et labels.";

export function AgentConsole() {
  const activeWorkflowId = useStudioStore((state) => state.activeWorkflowId);
  const activePackId = useStudioStore((state) => state.activePackId);
  const setActiveWorkflowId = useStudioStore((state) => state.setActiveWorkflowId);
  const setActivePackId = useStudioStore((state) => state.setActivePackId);
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [editPrompt, setEditPrompt] = useState("mets les antennes à 26m");
  const [useLlm, setUseLlm] = useState(true);
  const mutations = useStudioMutations(activeWorkflowId, activePackId);

  const createDesign = async () => {
    const response = await mutations.createDesign.mutateAsync({ prompt, useLlm });
    setActiveWorkflowId(response.workflow_id);
  };

  const applyEdit = async () => {
    if (!activeWorkflowId) return;
    await mutations.editDesign.mutateAsync({ prompt: editPrompt });
  };

  const uploadPack = async (file?: File) => {
    if (!file) return;
    const response = await mutations.uploadPack.mutateAsync(file);
    setActivePackId(response.pack_id);
  };

  const generateFromPack = async () => {
    if (!activePackId) return;
    const response = await mutations.generateFromPack.mutateAsync();
    setActiveWorkflowId(response.workflow_id);
  };

  return (
    <aside className="agent-console">
      <div className="panel-heading">
        <Bot size={18} />
        <div>
          <h2>Agent Console</h2>
          <p>Generation, document intelligence, prompt edits</p>
        </div>
      </div>

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
          disabled={mutations.createDesign.isPending || prompt.trim().length === 0}
        >
          <Send size={16} />
          Generate Design
        </button>
        {mutations.createDesign.isError ? (
          <p className="error-line">{mutations.createDesign.error.message}</p>
        ) : null}
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
    </aside>
  );
}
