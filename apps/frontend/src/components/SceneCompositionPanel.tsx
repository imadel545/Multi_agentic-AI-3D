import { Layers3, Loader2 } from "lucide-react";
import type {
  AssemblyPlanEvidence,
  AssetDecisionSummary,
  AssetInventory,
  ComponentProofs,
  SectorPreviewSummary
} from "../api/schemas";
import { compactFidelityLabel, humanSemanticRole, visualReviewStatusLabel } from "./StudioDisplayHelpers";
import { PanelTitle, ResourceRecovery } from "./StudioPrimitives";

export function sceneInstanceCount(proofs: ComponentProofs): number {
  return proofs.components.reduce((count, component) => count + component.instances.length, 0) +
    proofs.geometry_programs.reduce((count, program) => count + program.quantity, 0);
}

function strategyLabel(strategy: string): string {
  const labels: Record<string, string> = {
    reuse: "Réutilisé",
    adapt: "Adapté",
    compose: "Composé",
    procedural_generate: "Généré",
    reuse_full_design: "Design réutilisé",
    adapt_full_design: "Design adapté",
    reuse_component: "Composant réutilisé",
    adapt_component: "Composant adapté",
    compose_assets: "Assets composés",
    compose_and_generate: "Composition et génération",
    clarify: "Clarification requise",
    unsupported: "Non pris en charge"
  };
  return labels[strategy] ?? strategy;
}

function assetQualificationLabel(status: string): string {
  const labels: Record<string, string> = {
    qualified_for_generation: "qualifié pour la génération",
    qualified: "qualifié pour la génération",
    reference_only: "référence uniquement",
    quarantined_unverified: "en quarantaine"
  };
  return labels[status] ?? "qualification non confirmée";
}

function assetSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    vendor_supplied: "fournie par le constructeur",
    vendor_expected: "source constructeur attendue",
    internal_cleaned: "géométrie interne nettoyée",
    internal_test_minimal: "géométrie minimale de test",
    internal_project_generated: "géométrie générée dans le projet",
    cc0: "catalogue sous licence CC0",
    cc_by: "catalogue avec attribution",
    royalty_free: "catalogue sous licence libre de redevance"
  };
  return labels[source] ?? source;
}

function professionalEvidenceFailureLabel(failure: string): string {
  const labels: Record<string, string> = {
    "Professional asset QA has not passed.": "La QA professionnelle de l’asset n’a pas réussi.",
    "Professional QA report file is missing.": "Le rapport QA professionnel est absent.",
    "Five QA-passed qualification previews are not published.":
      "Les cinq vues de qualification validées ne sont pas publiées.",
    "Master and viewer representations are not both published.":
      "Le master CAO et sa représentation viewer ne sont pas tous les deux publiés.",
    "Geometry fidelity is not vendor-qualified.":
      "La fidélité constructeur n’est pas qualifiée.",
    "Source provenance is not explicitly documented.":
      "La provenance de la source n’est pas documentée.",
    "Asset licence is not explicitly documented.":
      "La licence d’utilisation n’est pas documentée.",
    "Qualified dimensions and bounding box are incomplete.":
      "Les dimensions qualifiées sont incomplètes.",
    "Qualified anchors and connectors are incomplete.":
      "Les points d’ancrage et connecteurs qualifiés sont incomplets."
  };
  return labels[failure] ?? "Une preuve requise n’a pas été vérifiée.";
}

export function SceneCompositionPanel({
  assemblyPlan,
  assetDecisionSummary,
  assetInventory,
  componentProofs,
  error = null,
  loading = false,
  onRetry,
  onSelect,
  selectedSemanticRoot = null,
  sectorPreviews = [],
  toAbsoluteUrl = (url) => url ?? null
}: {
  assemblyPlan: AssemblyPlanEvidence | null;
  assetDecisionSummary?: AssetDecisionSummary | null;
  assetInventory?: AssetInventory | null;
  componentProofs: ComponentProofs | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  onSelect?: (semanticRoot: string | null) => void;
  selectedSemanticRoot?: string | null;
  sectorPreviews?: SectorPreviewSummary[];
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const strategyCounts = new Map<string, number>();
  componentProofs?.components.forEach((component) => {
    strategyCounts.set(component.strategy, (strategyCounts.get(component.strategy) ?? 0) + component.quantity);
  });
  componentProofs?.geometry_programs.forEach((program) => {
    strategyCounts.set(program.strategy, (strategyCounts.get(program.strategy) ?? 0) + program.quantity);
  });
  const planByRole = new Map(
    (assemblyPlan?.components ?? []).map((component) => [component.role_id, component])
  );
  const inventoryByAssetId = new Map(
    (assetInventory?.entries ?? []).map((asset) => [asset.asset_id, asset])
  );
  const selectedSectorPreview = selectedSemanticRoot
    ? sectorPreviews.find((preview) => preview.semantic_roots.includes(selectedSemanticRoot))
    : undefined;
  const selectedSectorPreviewUrl = toAbsoluteUrl(selectedSectorPreview?.preview_url);
  return (
    <section className="drawer-section" aria-label="Composition de la scène">
      <PanelTitle icon={<Layers3 size={17} />} title="Composition vérifiable" />
      {selectedSemanticRoot ? (
        <>
          <div className="scene-plan-summary" role="status">
            <strong>Composant sélectionné : {selectedSemanticRoot.replaceAll("_", " ")}</strong>
            <small>La prochaine modification sera limitée à ce composant et vérifiée sur la version sélectionnée. Ses dépendances mécaniques peuvent suivre.</small>
            <button className="secondary-action" type="button" onClick={() => onSelect?.(null)}>Désélectionner</button>
          </div>
          {selectedSectorPreview && selectedSectorPreviewUrl ? (
            <article className="asset-evidence-card verified sector-preview-card" aria-label={`Aperçu Blender du secteur ${selectedSectorPreview.sector_id}`}>
              <img
                alt={`Rendu Blender d’inspection du secteur ${selectedSectorPreview.sector_id}`}
                src={selectedSectorPreviewUrl}
              />
              <div>
                <strong>Rendu Blender du secteur {selectedSectorPreview.sector_id}</strong>
                <small>
                  Identité réexportée par le GLB : {selectedSectorPreview.post_blender_identity_verified ? "vérifiée" : "non vérifiée"}
                </small>
                <small>
                  Cadrage et contraste : {selectedSectorPreview.visual_framing_verified ? "vérifiés" : "à examiner"}
                  {selectedSectorPreview.subject_bbox_height_ratio != null
                    ? ` · sujet ${Math.round(selectedSectorPreview.subject_bbox_height_ratio * 100)} % de la hauteur`
                    : ""}
                </small>
                <small>Sous-assemblage cadré : {selectedSectorPreview.framed_roles.join(", ")}</small>
                <p>Les rôles exportés du secteur incluent aussi {selectedSectorPreview.exported_roles.join(", ")}. Ce rendu cadre la pose ; il ne constitue pas une qualification constructeur ni une validation de pose.</p>
              </div>
            </article>
          ) : null}
        </>
      ) : null}
      {loading ? (
        <p className="resource-loading" aria-live="polite" role="status">
          <Loader2 className="spin" size={15} aria-hidden="true" /> Synchronisation du plan et des composants…
        </p>
      ) : null}
      {error ? (
        <ResourceRecovery
          busy={loading}
          label="Le plan de composition n’a pas pu être entièrement resynchronisé."
          message={error}
          onRetry={onRetry}
        />
      ) : null}
      {assemblyPlan ? (
        <div className="scene-plan-summary">
          <strong>Sélection automatique tracée</strong>
          <small>{assemblyPlan.connections.length} connexion(s) vérifiable(s)</small>
        </div>
      ) : null}
      {assetDecisionSummary?.components.length ? (
        <div className="asset-decision-list" aria-label="Décisions automatiques par composant">
          {assetDecisionSummary.components.map((decision, index) => (
            <article key={decision.component_id ?? `${decision.role_id ?? "component"}-${index}`}>
              <strong>{humanSemanticRole(decision.role_id ?? decision.component_id ?? "composant")}</strong>
              <span>{decision.strategy ? strategyLabel(decision.strategy) : "Décision tracée"}</span>
              {decision.strategy_evidence === "planned_not_execution_verified" ? (
                <small>Stratégie planifiée, non certifiée par l’exécution</small>
              ) : null}
              {decision.rationale ? <small>{decision.rationale}</small> : null}
              {typeof decision.considered_count === "number" ? (
                <small>
                  {decision.considered_count} candidat(s) considéré(s)
                  {typeof decision.rejected_count === "number"
                    ? ` · ${decision.rejected_count} rejeté(s)`
                    : ""}
                </small>
              ) : null}
              {decision.risks.length ? (
                <ul className="asset-risk-list" aria-label="Limites de la décision">
                  {decision.risks.slice(0, 3).map((risk) => (
                    <li key={risk}>{professionalEvidenceFailureLabel(risk)}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
      {strategyCounts.size ? (
        <div className="strategy-chips" aria-label="Stratégies de construction">
          {Array.from(strategyCounts.entries()).map(([strategy, count]) => (
            <span data-strategy={strategy} key={strategy}>{strategyLabel(strategy)} <strong>{count}</strong></span>
          ))}
        </div>
      ) : null}
      {componentProofs ? (
        <div className="scene-tree" role="tree" aria-label="Arbre réel de la scène">
          {componentProofs.components.map((component) => {
            const plan = planByRole.get(component.role_id);
            const asset = component.asset_id
              ? inventoryByAssetId.get(component.asset_id)
              : undefined;
            const preview = asset?.milestone_evidence_eligible
              ? asset.preview_set?.find(
                  (candidate) => candidate.available && candidate.qa_status === "passed"
                )
              : undefined;
            const previewUrl = toAbsoluteUrl(preview?.url);
            const provenanceUrl = toAbsoluteUrl(asset?.provenance_url);
            return (
              <div className="scene-tree-group" key={component.component_id} role="group">
                <div className="scene-tree-heading">
                  <div>
                    <strong>{humanSemanticRole(component.role_id)}</strong>
                    <small>{strategyLabel(component.strategy)} · {component.asset_id ?? component.origin}</small>
                  </div>
                  <span>{component.quantity}</span>
                </div>
                {plan?.selection_reason ? <p>{plan.selection_reason}</p> : null}
                {asset ? (
                  <article
                    className={`asset-evidence-card${asset.milestone_evidence_eligible ? " verified" : " incomplete"}`}
                    aria-label={`État de preuve de l’asset ${asset.asset_id}`}
                  >
                    {previewUrl ? (
                      <img
                        alt={`Aperçu ${preview?.view ?? "qualifié"} de ${humanSemanticRole(component.role_id)}`}
                        loading="lazy"
                        src={previewUrl}
                      />
                    ) : (
                      <div className="asset-preview-unavailable">
                        {asset.milestone_evidence_eligible
                          ? "Aperçu vérifié indisponible"
                          : "Aucune preview professionnelle vérifiée"}
                      </div>
                    )}
                    <div>
                      <strong>
                        {asset.milestone_evidence_eligible
                          ? "Preuve professionnelle vérifiée"
                          : "Asset technique — preuve professionnelle incomplète"}
                      </strong>
                      <span>{asset.asset_id}</span>
                      <small>
                        {compactFidelityLabel(asset.fidelity_status ?? "")} ·{" "}
                        {assetQualificationLabel(asset.qualification_status)}
                      </small>
                      {asset.source ? <small>Source : {assetSourceLabel(asset.source)}</small> : null}
                      {!asset.milestone_evidence_eligible && asset.milestone_evidence_failures.length ? (
                        <ul className="asset-risk-list" aria-label="Preuves professionnelles manquantes">
                          {asset.milestone_evidence_failures.slice(0, 3).map((failure) => (
                            <li key={failure}>{professionalEvidenceFailureLabel(failure)}</li>
                          ))}
                        </ul>
                      ) : null}
                      {asset.visual_review_status ? (
                        <small>Revue assistée : {visualReviewStatusLabel(asset.visual_review_status)}</small>
                      ) : null}
                      {provenanceUrl ? (
                        <a href={provenanceUrl} rel="noreferrer" target="_blank">
                          Consulter la provenance
                        </a>
                      ) : null}
                    </div>
                  </article>
                ) : component.asset_id ? (
                  <p className="asset-proof-missing">
                    La preuve d’inventaire de cet asset n’est pas publiée dans ce résultat.
                  </p>
                ) : null}
                {component.instances.map((instance) => (
                  <button
                    aria-current={selectedSemanticRoot === instance.semantic_root ? "true" : undefined}
                    className={`scene-tree-item${selectedSemanticRoot === instance.semantic_root ? " selected" : ""}`}
                    key={instance.instance_id}
                    onClick={() => onSelect?.(instance.semantic_root)}
                    role="treeitem"
                    type="button"
                  >
                    <span>{humanSemanticRole(instance.object_role)}</span>
                    <small>{instance.instance_id}</small>
                  </button>
                ))}
              </div>
            );
          })}
          {componentProofs.geometry_programs.map((program) => (
            <div className={`scene-tree-group${program.origin === "geometry_program" ? " generated" : ""}`} key={program.component_id} role="group">
              <div className="scene-tree-heading">
                <div>
                  <strong>{humanSemanticRole(program.role_id)}</strong>
                  <small>{strategyLabel(program.strategy)} · {program.origin === "catalog_asset"
                    ? "géométrie source importée"
                    : "programme géométrique"}</small>
                </div>
                <span>{program.quantity}</span>
              </div>
              {program.origin === "catalog_asset" ? (
                <p>
                  Source : {program.exact_asset_sources?.[0]?.asset_id ?? "non publiée"}.
                  {" "}La réutilisation conserve la géométrie source ; elle ne constitue pas une qualification constructeur.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : !loading && !error ? (
        <p className="muted">Aucune preuve de composition n’est publiée pour ce design.</p>
      ) : null}
    </section>
  );
}
