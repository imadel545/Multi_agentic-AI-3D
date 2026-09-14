import { Boxes, CheckCircle2, Cpu, RotateCcw, Sparkles, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type {
  AdaptationCapabilityCatalog,
  AssetInventory,
  DocumentPackCapabilities,
  LLMDecisionProvenance,
  PublicVersionInfo,
  SceneAdaptationCapabilities,
  StudioSummary,
  ViewerBundle
} from "../api/schemas";
import { actionIsSupported } from "../state/workflowMachine";
import { List, Metric, PanelTitle, ResourceRecovery } from "./StudioPrimitives";
import { humanSemanticRole, serviceStatusLabel } from "./StudioDisplayHelpers";
import { humanRagLimitation, summarizeRagEvidence, truth } from "./StudioProductDisplay";
import { summarizeAdaptationCapabilityGroups } from "./StudioWorkflowDisplay";

export function RagEvidencePanel({
  bundle,
  error = null,
  evidence,
  loading = false,
  onRetry
}: {
  bundle: ViewerBundle | null;
  error?: string | null;
  evidence: unknown | null;
  loading?: boolean;
  onRetry?: () => void;
}) {
  const summary = summarizeRagEvidence(evidence);
  return (
    <section className="drawer-section" aria-label="Sources et décisions de conception">
      <PanelTitle icon={<Cpu size={17} />} title="Sources et décisions" />
      <div className="metric-grid">
        <Metric label="Provider" value={bundle?.rag_reranker_provider ?? "unknown"} />
        <Metric label="Recherche" value={serviceStatusLabel(bundle?.rag_retrieval_status)} />
        <Metric label="Classement des sources" value={serviceStatusLabel(bundle?.rag_reranker_status)} />
        <Metric label="Sources" value={String(bundle?.rag_context_count ?? 0)} />
        <Metric label="Extraction" value={summary.ragUsedForExtraction ? "oui" : "non"} />
        <Metric label="Planning" value={summary.ragUsedForPlanning ? "oui" : "non"} />
      </div>
      {bundle?.rag_retrieval_status === "degraded_local_lexical" ? (
        <p className="inline-alert">
          <WifiOff size={16} aria-hidden="true" /> La recherche vectorielle est indisponible;
          la recherche utilise temporairement le corpus local réel par correspondance lexicale.
        </p>
      ) : null}
      {bundle?.rag_reranker_degraded_reason ? (
        <p className="inline-alert">
          <WifiOff size={16} aria-hidden="true" />{" "}
          {humanRagLimitation(bundle.rag_reranker_degraded_reason)}
        </p>
      ) : null}
      {loading ? (
        <p className="muted" aria-live="polite">Chargement des sources et décisions vérifiées…</p>
      ) : error ? (
        <ResourceRecovery
          label="Les sources et décisions n’ont pas pu être chargées."
          message={error}
          onRetry={onRetry}
        />
      ) : evidence ? (
        <>
          <List
            title="Indices appliqués au plan"
            items={summary.appliedHints}
            empty="Aucun indice récupéré n’est prouvé comme appliqué au plan 3D."
          />
          <List
            title="Indices candidats récupérés"
            items={summary.candidateHints}
            empty="Aucun indice candidat remonté."
          />
          <div className="source-list">
            {summary.sources.length ? (
              summary.sources.map((source, index) => (
                <article className="source-card" key={`${source.title}-${index}`}>
                  <strong>{source.title}</strong>
                  <p>{source.reason}</p>
                  <small>{source.score}</small>
                </article>
              ))
            ) : (
              <p className="muted">Aucune source exploitable affichable.</p>
            )}
          </div>
          <List
            title="Limites de la recherche"
            items={summary.limitations.map(humanRagLimitation)}
            empty="Aucune limite de recherche remontée."
          />
        </>
      ) : (
        <p className="muted">Aucune source de conception chargée; le studio n’en invente pas.</p>
      )}
    </section>
  );
}

export function LlmProvenancePanel({
  bundle,
  error = null,
  loading = false,
  onRetry,
  provenance
}: {
  bundle: ViewerBundle | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  provenance: LLMDecisionProvenance | null;
}) {
  return (
    <section className="drawer-section" aria-label="Provenance de décision LLM">
      <PanelTitle icon={<Sparkles size={17} />} title="Provenance de décision" />
      {loading ? (
        <p className="muted" aria-live="polite">Chargement de la décision structurée…</p>
      ) : error ? (
        <ResourceRecovery
          label="La provenance LLM n’a pas pu être chargée; aucune décision n’est reconstruite côté navigateur."
          message={error}
          onRetry={onRetry}
        />
      ) : provenance ? (
        <>
          <div className="metric-grid">
            <Metric label="Provider" value={provenance.provider} />
            <Metric label="Modèle" value={provenance.model ?? "non déclaré"} />
            <Metric label="Capacité" value={humanSemanticRole(provenance.capability_called)} />
            <Metric label="Contrat" value={provenance.decision_contract_version} />
            <Metric label="Candidats" value={String(provenance.candidates_considered.length)} />
            <Metric label="Fallback" value={provenance.fallback_used ? "signalé" : "non"} />
          </div>
          <List
            title="Stratégies retenues"
            items={provenance.strategy_selected.map(humanSemanticRole)}
            empty="Aucune stratégie retenue n’est déclarée."
          />
          <List
            title="Justification enregistrée"
            items={provenance.rationale}
            empty="Aucune justification n’est déclarée."
          />
          <p className="resource-proof">
            <CheckCircle2 size={15} aria-hidden="true" /> Décision liée à la version active et conservée par le backend.
          </p>
        </>
      ) : bundle?.llm_decision_provenance_url ? (
        <p className="muted">La provenance est publiée mais n’a pas encore été chargée.</p>
      ) : (
        <p className="muted">Aucune provenance de décision versionnée n’est publiée pour ce résultat.</p>
      )}
    </section>
  );
}

export function RuntimeCapabilitiesPanel({
  adaptationCapabilities = null,
  adaptationCapabilitiesError = null,
  adaptationLoading = false,
  adaptationCatalog = null,
  adaptationCatalogError = null,
  summary,
  bundle,
  inventory,
  documentCapabilities,
  onRetryAdaptation
}: {
  adaptationCapabilities?: SceneAdaptationCapabilities | null;
  adaptationCapabilitiesError?: string | null;
  adaptationLoading?: boolean;
  adaptationCatalog?: AdaptationCapabilityCatalog | null;
  adaptationCatalogError?: string | null;
  summary: StudioSummary | null;
  bundle: ViewerBundle | null;
  inventory: AssetInventory | null;
  documentCapabilities: DocumentPackCapabilities | null;
  onRetryAdaptation?: () => void;
}) {
  const unsupported = bundle?.unsupported_actions ?? summary?.unsupported_actions ?? [];
  const runtime = bundle?.runtime_capabilities ?? summary?.runtime_capabilities;
  const showDownload =
    runtime?.can_download_artifacts === true &&
    actionIsSupported("download_artifacts", unsupported);
  return (
    <section className="drawer-section" aria-label="Capacités runtime">
      <PanelTitle icon={<Boxes size={17} />} title="Capacités réelles" />
      {adaptationCapabilitiesError || adaptationCatalogError ? (
        <ResourceRecovery
          busy={adaptationLoading}
          label="Les capacités d’adaptation ne sont pas disponibles; aucune capacité n’est supposée absente ou égale à zéro."
          message={[adaptationCapabilitiesError, adaptationCatalogError].filter(Boolean).join(" · ")}
          onRetry={onRetryAdaptation}
        />
      ) : null}
      <div className="metric-grid">
        <Metric label="Assets" value={inventory?.status ?? "unknown"} />
        <Metric
          label="Paramètres 3D actifs"
          value={adaptationLoading
            ? "chargement"
            : adaptationCapabilitiesError
              ? "indisponible"
              : adaptationCapabilities
                ? String(adaptationCapabilities.capabilities.length)
                : "non résolu"}
        />
        <Metric
          label="Profils d’adaptation"
          value={adaptationLoading
            ? "chargement"
            : adaptationCatalogError
              ? "indisponible"
              : adaptationCatalog
                ? String(adaptationCatalog.profiles.length)
                : "non résolu"}
        />
        <Metric label="Documents" value={documentCapabilities?.document_pack_status ?? "unknown"} />
        <Metric label="Download" value={showDownload ? "supporté" : "non supporté"} />
        <Metric label="WebSocket" value={truth(runtime?.websocket_runtime === true)} />
      </div>
      <List
        title="Modifications vérifiées du design actif"
        items={summarizeAdaptationCapabilityGroups(adaptationCapabilities)}
        empty={adaptationCapabilitiesError
          ? "Liste indisponible jusqu’à la prochaine synchronisation réussie."
          : bundle
            ? "Aucune capacité n’est déclarée pour ce design actif."
            : "Aucun design actif: les paramètres seront résolus après génération."}
      />
      <List
        title="Limites d’adaptation"
        items={adaptationCapabilities?.unsupported_operations ?? []}
        empty="Aucune limite supplémentaire déclarée."
      />
      <List
        title="Actions non supportées"
        items={unsupported.map((item) => `${item.action}: ${item.reason ?? item.future_requirement ?? ""}`)}
        empty="Aucune action non supportée remontée."
      />
    </section>
  );
}

export function VersionSummary({
  busyVersionId,
  canRollback,
  message,
  onRollback,
  versions
}: {
  busyVersionId: string | null;
  canRollback: boolean;
  message: string | null;
  onRollback: (versionId: string) => void;
  versions: PublicVersionInfo[];
}) {
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);
  const visibleVersions = useMemo(
    () => [...versions].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)).slice(0, 8),
    [versions]
  );
  const activeVersionId = versions.find((version) => version.active)?.version_id ?? null;
  useEffect(() => {
    setPendingVersionId(null);
  }, [activeVersionId]);
  return (
    <section className="drawer-section" aria-label="Versions">
      <PanelTitle icon={<RotateCcw size={17} />} title="Versions et rollback" />
      {visibleVersions.length ? (
        <div className="artifact-list">
          {visibleVersions.map((version) => (
            <div className="artifact-link" key={version.version_id}>
              <span>
                {version.version_id}
                {version.edit_description ? <small>{version.edit_description}</small> : null}
              </span>
              <small>{version.active ? "active" : version.status ?? version.generation_mode ?? "version"}</small>
              {!version.active && canRollback && version.status === "completed" ? (
                pendingVersionId === version.version_id ? (
                  <button
                    className="secondary-action"
                    disabled={busyVersionId !== null}
                    onClick={() => onRollback(version.version_id)}
                    type="button"
                  >
                    {busyVersionId === version.version_id ? "Restauration..." : "Confirmer"}
                  </button>
                ) : (
                  <button
                    className="ghost-action"
                    disabled={busyVersionId !== null}
                    onClick={() => setPendingVersionId(version.version_id)}
                    type="button"
                  >
                    Restaurer
                  </button>
                )
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Versions chargées après génération.</p>
      )}
      {versions.length > 8 ? <p className="muted">Les 8 versions les plus récentes sont affichées.</p> : null}
      {!canRollback && versions.length > 1 ? <p className="muted">Le rollback n’est pas annoncé comme disponible par le runtime.</p> : null}
      {message ? <p className="muted" aria-live="polite">{message}</p> : null}
    </section>
  );
}

