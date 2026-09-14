import { useEffect, useState, type ReactNode } from "react";
import type { TelecomStudioApi } from "../api/client";
import type { ComponentProofs, Conversation } from "../api/schemas";
import { humanComponentInstanceLabel } from "./StudioDisplayHelpers";
import { ResourceRecovery } from "./StudioPrimitives";

export function DurableConversation({
  activeContext, apiClient, workflowId, revision, busy, componentProofs = null
}: {
  activeContext?: ReactNode;
  apiClient: TelecomStudioApi;
  workflowId: string;
  revision: string;
  busy: boolean;
  componentProofs?: ComponentProofs | null;
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
  const shouldShowActiveContext = failed || conversation?.history_status !== "recorded";
  return <div className="conversation-history" aria-label="Conversation enregistrée">
    {loading && !conversation ? <p className="muted" role="status">Chargement de la conversation…</p> : null}
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
          <strong>{message.role === "user" ? "Vous" : "Studio"}</strong>
          <p>{message.text}</p>
          {message.target_semantic_root ?
            <small>Composant visé : {humanComponentInstanceLabel(componentProofs, message.target_semantic_root)}</small> : null}
        </article>
      )}
    </div>
    {shouldShowActiveContext ? activeContext : null}
  </div>;
}
