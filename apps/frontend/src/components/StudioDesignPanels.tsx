import { AlertTriangle, CheckCircle2, ChevronRight, FileArchive, ShieldAlert } from "lucide-react";
import type {
  InputAnalysisStatus,
  PublicVersionInfo,
  RequirementAnalysisReceipt,
  UserIssue,
  UserIssues,
  ViewerBundle,
  StudioSummary
} from "../api/schemas";
import { List, Metric, PanelTitle, ResourceRecovery, formatInteger } from "./StudioPrimitives";
import { compactFidelityLabel, humanSemanticRole, serviceStatusLabel, visualReviewStatusLabel } from "./StudioDisplayHelpers";
import { geometryFidelityBadge } from "../features/three-viewer/viewerRules";
import {
  artifactKindLabel,
  artifactLabel,
  assemblyConstraintStatusLabel,
  assemblyLimitationLabel,
  assemblyMeasurementScopeLabel,
  completionCertificateLabel,
  formatMeasurement,
  formatRatio,
  formatScore,
  generationTruth,
  meshQaLevelLabel,
  nextUserAction,
  qaTruth,
  readString,
  readStringArray,
  stringArray,
  summaryHeadline,
  summarySignals,
  workflowStatusLabel
} from "./StudioProductDisplay";
import {
  displayIssueCount,
  humanExtractionFallback,
  normalizedIssueCopy,
  summarizeUserIssues
} from "./StudioWorkflowDisplay";

export function SummaryPanel({
  bundle,
  inputAnalysis = null,
  inputAnalysisStatus,
  issues,
  summary,
  versions
}: {
  bundle: ViewerBundle | null;
  inputAnalysis?: RequirementAnalysisReceipt | null;
  inputAnalysisStatus?: InputAnalysisStatus;
  issues: UserIssues | null;
  summary: StudioSummary | null;
  versions: PublicVersionInfo[];
}) {
  const activeVersion = versions.find((version) => version.active)?.version_id ?? versions[0]?.version_id ?? "aucune";
  const issueCount = displayIssueCount(issues, bundle);
  const persistedInputAnalysis = inputAnalysis ?? bundle?.input_analysis ?? null;
  const persistedInputAnalysisStatus =
    inputAnalysisStatus ?? bundle?.input_analysis_status ?? "unavailable";
  return (
    <section className="drawer-section" aria-label="Résumé produit">
      <PanelTitle icon={<CheckCircle2 size={17} />} title="Résumé du design" />
      <div className="summary-card">
        <strong>{summaryHeadline(bundle)}</strong>
        <p>{nextUserAction(bundle, issueCount)}</p>
      </div>
      <InputAnalysisPanel
        analysis={persistedInputAnalysis}
        status={persistedInputAnalysisStatus}
      />
      <div className="metric-grid">
        <Metric label="Conception" value={workflowStatusLabel(bundle?.status)} />
        <Metric label="Génération" value={generationTruth(bundle)} />
        <Metric label="QA" value={qaTruth(bundle)} />
        <Metric label="Version" value={activeVersion} />
      </div>
      {bundle?.geometry_program_summary?.program_count ? (
        <div className="summary-card">
          <strong>
            {bundle.geometry_program_summary.generated_component_count} composant(s) créé(s)
            {" · "}{bundle.geometry_program_summary.reused_component_count ?? 0} composant(s) réutilisé(s)
          </strong>
          <p>
            {bundle.geometry_program_summary.total_node_count} nœuds déclaratifs ·{" "}
            {bundle.geometry_program_summary.repaired_program_count} sortie(s) LLM réparée(s)
            et revalidée(s).
          </p>
          <ul className="compact-proof-list">
            {bundle.geometry_program_summary.programs.map((program) => (
              <li key={program.program_id}>
                <span>{humanSemanticRole(program.semantic_role)}</span>
                <small>
                  {program.origin === "catalog_asset" ? "Géométrie source importée, placement contrôlé" : <>
                    {program.authorship === "llm_generated" ? "Géométrie écrite par LLM" : "Géométrie déterministe"}
                    {" · "}
                    {program.generator_provider}:{program.generator_model}
                    {" · "}
                    {humanGeometryOutputMode(program.structured_output_mode)}
                  </>}
                  {" · preuve "}
                  {program.source_prompt_sha256.slice(0, 10)}
                </small>
                {program.source_description_origin === "legacy_unavailable" ? (
                  <small>Intention source indisponible pour ce composant historique.</small>
                ) : program.source_description ? (
                  <small>Intention source : {program.source_description}</small>
                ) : null}
                {program.placement_context ? (
                  <small>Implantation demandée : {program.placement_context}</small>
                ) : null}
                {program.maximum_dimensions_m ? (
                  <small>
                    Enveloppe contrôlée : {program.maximum_dimensions_m.x} ×{" "}
                    {program.maximum_dimensions_m.y} × {program.maximum_dimensions_m.z} m max.
                  </small>
                ) : null}
                {program.limitations.map((limitation) => (
                  <small key={limitation}>Limite déclarée : {limitation}</small>
                ))}
                {program.deterministic_adjustments.map((adjustment) => (
                  <small key={adjustment}>
                    Adaptation déterministe appliquée pour respecter les contraintes.
                  </small>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <List title="État des livrables" items={summarySignals(bundle, issueCount)} empty="Aucun livrable chargé." />
      <List
        title="Services de conception"
        items={[
          `Composants 3D : ${serviceStatusLabel(summary?.asset_inventory_status)}`,
          `Contexte documentaire : ${serviceStatusLabel(summary?.rag_status)}`,
          `Classement des références : ${serviceStatusLabel(summary?.rag_reranker_status)}`
        ]}
        empty="État des services indisponible."
      />
    </section>
  );
}

export function InputAnalysisPanel({
  analysis,
  status
}: {
  analysis: RequirementAnalysisReceipt | null;
  status: InputAnalysisStatus;
}) {
  if (status === "verified" && analysis) {
    return (
      <section className="summary-card" aria-label="Compréhension initiale">
        <strong>Compréhension initiale vérifiée</strong>
        <p>
          Cette version conserve l’origine de l’analyse confirmée avant sa génération.
        </p>
        <div className="metric-grid">
          <Metric label="Service d’analyse" value={analysis.provider} />
          <Metric label="Modèle" value={analysis.model ?? "non communiqué"} />
          <Metric
            label="Mode de secours"
            value={analysis.fallback_used ? "signalé" : "non utilisé"}
          />
        </div>
        {analysis.fallback_used ? (
          <p className="inline-alert" role="status">
            <AlertTriangle size={15} aria-hidden="true" /> {humanExtractionFallback(analysis.fallback_reason)}
          </p>
        ) : (
          <p className="resource-proof" role="status">
            <CheckCircle2 size={15} aria-hidden="true" /> L’analyse confirmée est liée à cette version.
          </p>
        )}
      </section>
    );
  }

  if (status === "legacy_unattested") {
    return (
      <section className="summary-card" aria-label="Compréhension initiale">
        <strong>Compréhension initiale non attestée</strong>
        <p>
          Cette version conserve ses exigences, mais l’origine de leur analyse n’était pas
          enregistrée avec la version. Aucun fournisseur ni modèle n’est revendiqué.
        </p>
      </section>
    );
  }

  return (
    <section className="summary-card" aria-label="Compréhension initiale">
      <strong>Origine de la compréhension indisponible</strong>
      <p>
        Cette version ne publie aucun reçu de son analyse initiale. La source de la
        compréhension ne peut pas être confirmée.
      </p>
    </section>
  );
}

export function QaPanel({
  bundle,
  evidence,
  error = null,
  loading = false,
  onRetry,
  toAbsoluteUrl = (url) => url ?? null
}: {
  bundle: ViewerBundle | null;
  evidence?: unknown | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const qa = bundle?.qa_summary;
  const assembly = bundle?.assembly_constraint_summary;
  const assemblyEvidenceUrl = toAbsoluteUrl(bundle?.constraint_evidence_url);
  const passed = bundle?.mesh_qa_passed === true;
  const fidelityBadge = geometryFidelityBadge(bundle);
  const qaExecuted =
    qa?.qa_executed !== false &&
    bundle?.status === "completed" &&
    bundle.generation_mode === "real_blender" &&
    typeof bundle.mesh_qa_passed === "boolean";
  return (
    <section className="drawer-section" aria-label="Validation QA">
      <PanelTitle icon={<ShieldAlert size={17} />} title="Vérification du résultat" />
      {loading ? (
        <p className="muted" aria-live="polite">Synchronisation du rapport QA vérifié…</p>
      ) : error ? (
        <ResourceRecovery
          label="Le détail QA n’a pas pu être resynchronisé. Aucun contrôle manquant n’est supposé réussi."
          message={error}
          onRetry={onRetry}
        />
      ) : evidence ? (
        <p className="resource-proof" role="status">
          <CheckCircle2 size={15} aria-hidden="true" /> Rapport QA détaillé chargé depuis l’artefact backend.
        </p>
      ) : null}
      {qaExecuted && bundle ? (
        <>
          <div className="metric-grid">
            <Metric label="Score" value={formatScore(bundle.qa_score)} />
            <Metric label="Niveau mesh" value={meshQaLevelLabel(bundle.mesh_qa_level)} />
            <Metric
              label="Géométrie"
              value={
                passed && bundle.mesh_qa_level === "mesh_level_spatial_basic"
                  ? "interférences contrôlées"
                  : passed
                    ? "validée de base"
                    : "attention"
              }
            />
            <Metric label="Mode" value={generationTruth(bundle)} />
            <Metric
              label="Exigences"
              value={bundle.requirement_coverage_passed ? "couvertes" : "attention"}
            />
            <Metric
              label="Preuve d’intégrité"
              value={completionCertificateLabel(bundle.completion_certificate_status)}
            />
            {fidelityBadge ? (
              <div className="metric">
                <small>Fidélité des composants</small>
                <strong data-geometry-fidelity={fidelityBadge.fidelity}>
                  {compactFidelityLabel(fidelityBadge.fidelity)}
                </strong>
              </div>
            ) : null}
          </div>
          <List title="Échecs QA" items={stringArray(qa?.checks_failed)} empty="Aucun échec QA remonté." />
          <details className="drawer-disclosure">
            <summary>Portée et limites de cette validation</summary>
            <List title="Ce que la QA ne garantit pas" items={bundle.limitations} empty="Aucune limitation remontée." />
          </details>
        </>
      ) : bundle ? (
        <div className="qa-not-run" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>Validation 3D non exécutée</strong>
            <p>
              {bundle.status === "failed"
                ? qa?.blocked_before_qa === true
                  ? "La conception a été bloquée avant la QA; aucun contrôle 3D ne peut être annoncé."
                  : "La conception s’est arrêtée avant la construction du modèle; aucun contrôle 3D ne peut être annoncé."
                : "Aucune preuve complète de construction et de vérification 3D n’est disponible pour ce résultat."}
            </p>
          </div>
        </div>
      ) : (
        <p className="muted">La vérification apparaîtra après la construction réelle du modèle 3D.</p>
      )}
      {bundle ? (
        <div className="qa-evidence-split">
          {assembly ? (
            <section
              aria-label="Assemblage post-export"
              className={`qa-evidence-card${assembly.status === "passed" ? "" : " advisory"}`}
            >
              <div className="qa-evidence-heading">
                <strong>Assemblage post-export</strong>
                <span>{assemblyConstraintStatusLabel(assembly.status)}</span>
              </div>
              <p>
                Mesures déterministes réalisées sur {assemblyMeasurementScopeLabel(assembly.measurement_scope)}.
              </p>
              {assembly.status !== "not_available" ? (
                <div className="metric-grid">
                  <Metric label="Connexions requises (toutes)" value={formatInteger(assembly.required_connection_count)} />
                  <Metric label="Liaisons mécaniques mesurées" value={formatInteger(assembly.measured_instance_count)} />
                  {assembly.resolved_support_count > 0 ? (
                    <Metric label="Supports d’adaptation observés" value={formatInteger(assembly.resolved_support_count)} />
                  ) : null}
                  <Metric label="Erreur de position max." value={`${formatMeasurement(assembly.max_position_error_m)} m`} />
                  <Metric label="Erreur angulaire max." value={`${formatMeasurement(assembly.max_angular_error_deg)}°`} />
                </div>
              ) : null}
              {assembly.limitations.length ? (
                <List
                  title="Limites de la mesure"
                  items={assembly.limitations.map(assemblyLimitationLabel)}
                  empty="Aucune limitation publiée."
                />
              ) : null}
              <small>
                Ce contrôle décrit des écarts géométriques mesurés après export. Il ne constitue ni une validation d’ingénierie ni une preuve professionnelle.
              </small>
              {assemblyEvidenceUrl ? (
                <a href={assemblyEvidenceUrl} rel="noreferrer" target="_blank">
                  Consulter la preuve de mesure
                </a>
              ) : null}
            </section>
          ) : null}
          <section aria-label="Cadrage technique" className="qa-evidence-card">
            <div className="qa-evidence-heading">
              <strong>Cadrage technique</strong>
              <span>
                {qa?.preview_pixel_framing_qa
                  ? qa.preview_subject_framing_valid === true
                    ? "conforme"
                    : qa.preview_subject_framing_valid === false
                      ? "à corriger"
                      : "exécuté"
                  : "non exécuté"}
              </span>
            </div>
            <p>
              Contrôle déterministe de l’occupation, des marges et du centrage de la preview.
              Il ne valide ni la qualité esthétique ni la conformité métier.
            </p>
            {qa?.preview_pixel_framing_qa ? (
              <small>
                Occupation : {formatRatio(qa.preview_subject_bbox_width_ratio)} × {formatRatio(qa.preview_subject_bbox_height_ratio)} · marge minimale {formatRatio(qa.preview_subject_min_edge_margin_ratio)}
              </small>
            ) : null}
          </section>
          <section aria-label="Revue visuelle assistée" className="qa-evidence-card advisory">
            <div className="qa-evidence-heading">
              <strong>Revue visuelle assistée</strong>
              <span>{visualReviewStatusLabel(bundle.visual_review?.status ?? "not_requested")}</span>
            </div>
            <p>
              {bundle.visual_review?.summary ??
                "Aucune revue sémantique du rendu n’a été demandée pour ce résultat."}
            </p>
            {bundle.visual_review?.findings.length ? (
              <ul>
                {bundle.visual_review.findings.map((finding) => <li key={finding}>{finding}</li>)}
              </ul>
            ) : null}
            <small>Cette revue est consultative et ne peut jamais remplacer la QA déterministe.</small>
          </section>
        </div>
      ) : null}
    </section>
  );
}

export function IssuesPanel({ issues }: { issues: UserIssues | null }) {
  const summarizedIssues = summarizeUserIssues(issues?.human_readable_issues ?? []);
  const primaryIssues = summarizedIssues.slice(0, 4);
  const additionalIssues = summarizedIssues.slice(4);
  const renderIssue = (issue: UserIssue, index: number) => {
    const titleKey = normalizedIssueCopy(issue.title);
    const impactKey = normalizedIssueCopy(issue.impact);
    const actionKey = normalizedIssueCopy(issue.recommended_action);
    return (
      <article className={`issue-card ${issue.severity}`} key={`${issue.title}-${issue.technical_code ?? "issue"}-${index}`}>
        <strong>{issue.title}</strong>
        {impactKey && impactKey !== titleKey ? <p>{issue.impact}</p> : null}
        {actionKey && actionKey !== titleKey && actionKey !== impactKey ? (
          <small>{issue.recommended_action}</small>
        ) : null}
      </article>
    );
  };
  return (
    <section className="drawer-section" aria-label="Limites et actions">
      <PanelTitle icon={<AlertTriangle size={17} />} title="Limites et actions" />
      {summarizedIssues.length ? (
        <div className="issue-list">
          {primaryIssues.map(renderIssue)}
          {additionalIssues.length ? (
            <details className="issue-more">
              <summary>Afficher {additionalIssues.length} autre{additionalIssues.length > 1 ? "s" : ""} limite{additionalIssues.length > 1 ? "s" : ""}</summary>
              <div>{additionalIssues.map((issue, index) => renderIssue(issue, index + primaryIssues.length))}</div>
            </details>
          ) : null}
        </div>
      ) : issues ? (
        <p className="muted">Aucune alerte à examiner.</p>
      ) : (
        <p className="inline-alert">
          <AlertTriangle size={15} aria-hidden="true" />
          Le nombre d’alertes est connu, mais leur détail n’a pas pu être synchronisé.
        </p>
      )}
    </section>
  );
}

export function ArtifactsPanel({
  bundle,
  toAbsoluteUrl
}: {
  bundle: ViewerBundle | null;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
}) {
  const previews = availablePreviewArtifacts(bundle, toAbsoluteUrl);
  return (
    <section className="drawer-section" aria-label="Livrables">
      <PanelTitle icon={<FileArchive size={17} />} title="Livrables vérifiables" />
      {bundle ? (
        <>
        {previews.length ? (
          <div className="artifact-preview-grid" aria-label="Aperçus du design">
            {previews.map((preview) => (
              <a href={preview.url} key={preview.name} rel="noreferrer" target="_blank">
                <img alt={artifactLabel(preview.name)} loading="lazy" src={preview.url} />
                <span>{artifactLabel(preview.name)}</span>
              </a>
            ))}
          </div>
        ) : null}
        <div className="artifact-list">
          {bundle.viewer_artifacts.map((artifact) => {
            const url = artifact.available ? toAbsoluteUrl(artifact.url) : null;
            const content = (
              <>
                <span>{artifactLabel(artifact.name)}</span>
                <small>{url ? artifactKindLabel(artifact.content_type) : "Indisponible"}</small>
                <ChevronRight size={15} aria-hidden="true" />
              </>
            );
            return url ? (
              <a
                className="artifact-link"
                href={url}
                key={artifact.name}
                rel="noreferrer"
                target="_blank"
              >
                {content}
              </a>
            ) : (
              <div
                aria-disabled="true"
                className="artifact-link unavailable"
                key={artifact.name}
              >
                {content}
              </div>
            );
          })}
        </div>
        </>
      ) : (
        <p className="muted">Aucun artefact tant qu’un workflow n’est pas terminé.</p>
      )}
    </section>
  );
}

export function availablePreviewArtifacts(
  bundle: ViewerBundle | null,
  toAbsoluteUrl: (url: string | null | undefined) => string | null
): Array<{ name: string; url: string }> {
  if (!bundle) return [];
  return bundle.viewer_artifacts.flatMap((artifact) => {
    if (!artifact.available || !artifact.content_type.toLowerCase().startsWith("image/")) {
      return [];
    }
    const url = toAbsoluteUrl(artifact.url);
    return url ? [{ name: artifact.name, url }] : [];
  });
}

export function humanGeometryOutputMode(mode: string): string {
  return {
    strict_json_schema: "schéma JSON strict",
    json_object_validated: "JSON validé localement",
    json_object_repaired: "JSON réparé puis revalidé"
  }[mode] ?? mode;
}

