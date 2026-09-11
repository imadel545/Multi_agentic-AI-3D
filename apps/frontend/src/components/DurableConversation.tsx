import { useEffect, useState } from "react";
import type { TelecomStudioApi } from "../api/client";
import type { Conversation } from "../api/schemas";
import { ResourceRecovery } from "./StudioPrimitives";

export function DurableConversation({
  apiClient, workflowId, revision, busy
}: {
  apiClient: TelecomStudioApi;
  workflowId: string;
  revision: string;
  busy: boolean;
}) {
  const [snapshot, setSnapshot] = useState<Conversation | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setFailed(false);
    void apiClient.conversation(workflowId).then((value) => {
      if (current && value.workflow_id === workflowId) setSnapshot(value);
    }).catch(() => {
      if (current) setFailed(true);
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [apiClient, workflowId, revision, busy, retry]);
  const conversation = snapshot?.workflow_id === workflowId ? snapshot : null;
  return <div className="conversation-history" aria-label="Conversation enregistrée">
    <span className="conversation-history-label">Conversation enregistrée</span>
    {loading ? <p className="muted" role="status">Chargement de la conversation…</p> : null}
    {failed ? <ResourceRecovery
      label="La conversation n’a pas pu être synchronisée."
      message="Les messages déjà chargés restent visibles. Réessayez pour retrouver la suite."
      onRetry={() => setRetry((value) => value + 1)}
    /> : null}
    {conversation?.history_status === "legacy_partial" ?
      <p className="muted">Historique ancien partiel : seuls les messages effectivement enregistrés sont affichés.</p> : null}
    {conversation?.history_status === "damaged" ?
      <p role="alert">Une partie du journal est illisible. L’historique affiché est incomplet.</p> : null}
    <div className="conversation-history-list">
      {conversation?.messages.map((message) =>
        <article className={`conversation-entry ${message.role}`} key={message.message_id}>
          <strong>{message.role === "user" ? "Vous" : "Notification du studio"}</strong>
          <p>{message.text}</p>
          {message.target_semantic_root ?
            <small>Composant visé : {message.target_semantic_root.replaceAll("_", " ")}</small> : null}
        </article>
      )}
    </div>
  </div>;
}
