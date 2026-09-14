import { Layers3, Loader2 } from "lucide-react";
import type {
  AssetInventory,
  ComponentProofs,
  QualifiedAssetInventoryEntry,
  SectorPreviewSummary,
  TowerAccessSummary
} from "../api/schemas";
import { humanComponentInstanceLabel, humanSemanticRole } from "./StudioDisplayHelpers";
import { PanelTitle, ResourceRecovery } from "./StudioPrimitives";

export function sceneInstanceCount(proofs: ComponentProofs): number {
  return proofs.components.reduce((count, component) => count + component.instances.length, 0) +
    proofs.geometry_programs.reduce((count, program) => count + program.quantity, 0);
}

type CompositionEvidenceSummary = {
  exactCatalog: number;
  parametric: number;
  procedural: number;
  schematic: number;
  technicalGeneric: number;
  vendorQualified: number;
  unclassified: number;
};

function fidelityFor(asset: QualifiedAssetInventoryEntry | undefined) {
  if (asset?.fidelity_status === "vendor_qualified" && asset.milestone_evidence_eligible) {
    return "vendor_qualified";
  }
  if (asset?.fidelity_status === "schematic") return "schematic";
  if (asset?.fidelity_status === "technical_generic") return "technical_generic";
  return "unclassified";
}

export function compositionEvidenceSummary(
  proofs: ComponentProofs,
  inventoryByAssetId: Map<string, QualifiedAssetInventoryEntry>
): CompositionEvidenceSummary {
  const summary: CompositionEvidenceSummary = {
    exactCatalog: 0,
    parametric: 0,
    procedural: 0,
    schematic: 0,
    technicalGeneric: 0,
    vendorQualified: 0,
    unclassified: 0
  };
  const recordFidelity = (
    quantity: number,
    asset: QualifiedAssetInventoryEntry | undefined
  ) => {
    const fidelity = fidelityFor(asset);
    if (fidelity === "vendor_qualified") summary.vendorQualified += quantity;
    else if (fidelity === "schematic") summary.schematic += quantity;
    else if (fidelity === "technical_generic") summary.technicalGeneric += quantity;
    else summary.unclassified += quantity;
  };
  for (const component of proofs.components) {
    const asset = component.asset_id
      ? inventoryByAssetId.get(component.asset_id)
      : undefined;
    if (component.instances.length > 0) {
      for (const instance of component.instances) {
        if (["asset_glb", "imported_glb_exact"].includes(instance.geometry_source)) {
          summary.exactCatalog += 1;
        } else if (instance.geometry_source.includes("parametric")) {
          summary.parametric += 1;
        } else {
          summary.procedural += 1;
        }
      }
    } else if (component.generation_strategy === "imported_glb_exact") {
      summary.exactCatalog += component.quantity;
    } else if (component.generation_strategy.includes("parametric")) {
      summary.parametric += component.quantity;
    } else {
      summary.procedural += component.quantity;
    }
    recordFidelity(component.quantity, asset);
  }
  for (const program of proofs.geometry_programs) {
    const sourceAssetId = program.exact_asset_sources?.[0]?.asset_id;
    const asset = sourceAssetId ? inventoryByAssetId.get(sourceAssetId) : undefined;
    if (program.origin === "catalog_asset" && sourceAssetId) {
      summary.exactCatalog += program.quantity;
    } else {
      summary.procedural += program.quantity;
    }
    recordFidelity(program.quantity, asset);
  }
  return summary;
}

function constructionLabel(strategy: string): string {
  const labels: Record<string, string> = {
    reuse: "Modèle source conservé",
    adapt: "Modèle source ajusté",
    compose: "Assemblé à partir de plusieurs éléments",
    procedural_generate: "Créé pour ce projet"
  };
  return labels[strategy] ?? "Créé pour ce projet";
}

function sourceLabel(asset: QualifiedAssetInventoryEntry | undefined, hasCatalogSource: boolean): string {
  if (asset?.manufacturer || asset?.reference) {
    return [asset.manufacturer, asset.reference].filter(Boolean).join(" · ");
  }
  if (asset?.source_provenance) return asset.source_provenance;
  const labels: Record<string, string> = {
    vendor_supplied: "Source fournie par le constructeur",
    vendor_expected: "Source constructeur à confirmer",
    internal_cleaned: "Source interne préparée pour ce projet",
    internal_test_minimal: "Source interne simplifiée",
    internal_project_generated: "Créé pour ce projet",
    cc0: "Catalogue public CC0",
    cc_by: "Catalogue public avec attribution",
    royalty_free: "Catalogue sous licence"
  };
  if (asset?.source) return labels[asset.source] ?? "Source documentée dans le projet";
  return hasCatalogSource ? "Source du catalogue du projet" : "Créé pour ce projet";
}

function dimensionValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(value);
}

function formatDimensions(dimensions: Record<string, unknown> | null | undefined): string | null {
  if (!dimensions) return null;
  const width = dimensionValue(dimensions.width ?? dimensions.x);
  const depth = dimensionValue(dimensions.depth ?? dimensions.y);
  const height = dimensionValue(dimensions.height ?? dimensions.z);
  if (width && depth && height) {
    return `L × P × H : ${formatMeters(width)} × ${formatMeters(depth)} × ${formatMeters(height)} m`;
  }
  const available = [
    width ? `largeur ${formatMeters(width)} m` : null,
    depth ? `profondeur ${formatMeters(depth)} m` : null,
    height ? `hauteur ${formatMeters(height)} m` : null
  ].filter((value): value is string => Boolean(value));
  return available.length ? available.join(" · ") : null;
}

export function SceneCompositionPanel({
  assetInventory,
  componentProofs,
  error = null,
  loading = false,
  onRetry,
  onSelect,
  selectedSemanticRoot = null,
  sectorPreviews = [],
  towerAccess = null,
  toAbsoluteUrl = (url) => url ?? null
}: {
  assetInventory?: AssetInventory | null;
  componentProofs: ComponentProofs | null;
  error?: string | null;
  loading?: boolean;
  onRetry?: () => void;
  onSelect?: (semanticRoot: string | null) => void;
  selectedSemanticRoot?: string | null;
  sectorPreviews?: SectorPreviewSummary[];
  towerAccess?: TowerAccessSummary | null;
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const inventoryByAssetId = new Map(
    (assetInventory?.entries ?? []).map((asset) => [asset.asset_id, asset])
  );
  const selectedSectorPreview = selectedSemanticRoot
    ? sectorPreviews.find((preview) => preview.semantic_roots.includes(selectedSemanticRoot))
    : undefined;
  const selectedSectorPreviewUrl = toAbsoluteUrl(selectedSectorPreview?.preview_url);
  const selectedTowerAccess = selectedSemanticRoot === towerAccess?.semantic_root;
  const selectedComponentLabel = selectedTowerAccess
    ? "accès et maintenance du pylône"
    : humanComponentInstanceLabel(componentProofs, selectedSemanticRoot);
  const elementCount = componentProofs ? sceneInstanceCount(componentProofs) : 0;
  const evidenceSummary = componentProofs
    ? compositionEvidenceSummary(componentProofs, inventoryByAssetId)
    : null;

  return (
    <section className="drawer-section" aria-label="Composition de la scène">
      <PanelTitle icon={<Layers3 size={17} />} title="Composition" />

      {componentProofs ? (
        <div className="composition-overview" aria-label="Résumé de la composition">
          <strong>{elementCount} élément{elementCount > 1 ? "s" : ""} présent{elementCount > 1 ? "s" : ""}</strong>
          <small>Sélectionnez un élément pour le retrouver dans la vue 3D et le modifier depuis le chat.</small>
        </div>
      ) : null}

      {evidenceSummary ? (
        <div className="composition-evidence" aria-label="Origine et fidélité des éléments exécutés">
          <div>
            <strong>{evidenceSummary.exactCatalog}</strong>
            <span>source{evidenceSummary.exactCatalog > 1 ? "s" : ""} exacte{evidenceSummary.exactCatalog > 1 ? "s" : ""}</span>
          </div>
          <div>
            <strong>{evidenceSummary.parametric}</strong>
            <span>paramétrique{evidenceSummary.parametric > 1 ? "s" : ""}</span>
          </div>
          <div>
            <strong>{evidenceSummary.procedural}</strong>
            <span>créé{evidenceSummary.procedural > 1 ? "s" : ""} pour ce projet</span>
          </div>
          <p>
            {evidenceSummary.vendorQualified > 0
              ? `${evidenceSummary.vendorQualified} élément${evidenceSummary.vendorQualified > 1 ? "s" : ""} avec géométrie constructeur qualifiée.`
              : "Aucune géométrie constructeur qualifiée dans cette version."}
            {evidenceSummary.technicalGeneric > 0
              ? ` ${evidenceSummary.technicalGeneric} élément${evidenceSummary.technicalGeneric > 1 ? "s" : ""} de fidélité technique générique.`
              : ""}
            {evidenceSummary.schematic > 0
              ? ` ${evidenceSummary.schematic} représentation${evidenceSummary.schematic > 1 ? "s" : ""} schématique${evidenceSummary.schematic > 1 ? "s" : ""}.`
              : ""}
            {evidenceSummary.unclassified > 0
              ? ` Fidélité non classée pour ${evidenceSummary.unclassified} élément${evidenceSummary.unclassified > 1 ? "s" : ""}.`
              : ""}
          </p>
        </div>
      ) : null}

      {selectedSemanticRoot ? (
        <div className="scene-plan-summary" role="status">
          <strong>{selectedComponentLabel}</strong>
          <small>{selectedTowerAccess
            ? "Cet ensemble peut être inspecté, mais il n’est pas encore modifiable séparément."
            : "Les prochains changements demandés dans le chat viseront cet élément."}</small>
          <button className="secondary-action" type="button" onClick={() => onSelect?.(null)}>
            Revenir au design complet
          </button>
        </div>
      ) : null}

      {selectedSectorPreview && selectedSectorPreviewUrl ? (
        <article className="asset-evidence-card verified sector-preview-card" aria-label={`Aperçu du secteur ${selectedSectorPreview.sector_id}`}>
          <img alt={`Vue rapprochée du secteur ${selectedSectorPreview.sector_id}`} src={selectedSectorPreviewUrl} />
          <div>
            <strong>Aperçu du secteur {selectedSectorPreview.sector_id}</strong>
            <small>Vue issue du modèle 3D de la version active</small>
            <p>Cette vue aide à contrôler l’ensemble. Elle ne valide pas la pose ni les caractéristiques du constructeur.</p>
          </div>
        </article>
      ) : null}

      {loading ? (
        <p className="resource-loading" aria-live="polite" role="status">
          <Loader2 className="spin" size={15} aria-hidden="true" /> Mise à jour de la composition…
        </p>
      ) : null}
      {error ? (
        <ResourceRecovery
          busy={loading}
          label="La composition n’a pas pu être entièrement mise à jour."
          message={error}
          onRetry={onRetry}
        />
      ) : null}

      {towerAccess ? (
        <article className="scene-tree-group" aria-label="Accès et maintenance du pylône">
          <div className="scene-tree-heading">
            <div>
              <strong>Accès et maintenance du pylône</strong>
              <small>Créé pour ce projet · inspection uniquement</small>
            </div>
            <span>1</span>
          </div>
          <p>{towerAccess.requested_ladder ? `${towerAccess.rung_count} barreaux` : "Aucune échelle demandée"}</p>
          {towerAccess.platform_levels_m.length ? (
            <small>Plateformes à {towerAccess.platform_levels_m.map((level) => `${formatMeters(level)} m`).join(" · ")}</small>
          ) : null}
          <button className="secondary-action" onClick={() => onSelect?.(towerAccess.semantic_root)} type="button">
            Voir dans le modèle 3D
          </button>
        </article>
      ) : null}

      {componentProofs ? (
        <div className="scene-tree" role="tree" aria-label="Éléments présents dans le modèle 3D">
          {componentProofs.components.map((component) => {
            const asset = component.asset_id ? inventoryByAssetId.get(component.asset_id) : undefined;
            const dimensions = formatDimensions(asset?.dimensions_m);
            return (
              <div className="scene-tree-group" key={component.component_id} role="group">
                <div className="scene-tree-heading">
                  <div>
                    <strong>{humanSemanticRole(component.role_id)}</strong>
                    <small>{constructionLabel(component.strategy)}</small>
                  </div>
                  <span>{component.quantity}</span>
                </div>
                <p>Source : {sourceLabel(asset, Boolean(component.asset_id))}</p>
                {dimensions ? <small>{dimensions}</small> : null}
                {component.instances.map((instance) => (
                  <button
                    aria-current={selectedSemanticRoot === instance.semantic_root ? "true" : undefined}
                    className={`scene-tree-item${selectedSemanticRoot === instance.semantic_root ? " selected" : ""}`}
                    key={instance.instance_id}
                    onClick={() => onSelect?.(instance.semantic_root)}
                    role="treeitem"
                    type="button"
                  >
                    <span>{humanComponentInstanceLabel(componentProofs, instance.semantic_root)}</span>
                    <small>{selectedSemanticRoot === instance.semantic_root ? "Sélectionné" : "Sélectionner pour modifier"}</small>
                  </button>
                ))}
              </div>
            );
          })}
          {componentProofs.geometry_programs.map((program) => {
            const sourceAssetId = program.exact_asset_sources?.[0]?.asset_id;
            const sourceAsset = sourceAssetId ? inventoryByAssetId.get(sourceAssetId) : undefined;
            const dimensions = formatDimensions(sourceAsset?.dimensions_m);
            return (
              <div className="scene-tree-group" key={program.component_id} role="group">
                <div className="scene-tree-heading">
                  <div>
                    <strong>{humanSemanticRole(program.role_id)}</strong>
                    <small>{constructionLabel(program.strategy)}</small>
                  </div>
                  <span>{program.quantity}</span>
                </div>
                <p>Source : {sourceLabel(sourceAsset, program.origin === "catalog_asset")}</p>
                {dimensions ? <small>{dimensions}</small> : null}
              </div>
            );
          })}
        </div>
      ) : !loading && !error ? (
        <div className="composition-empty">
          <strong>Aucun élément 3D disponible</strong>
          <p>La composition apparaîtra ici dès qu’une version du design aura été produite.</p>
        </div>
      ) : null}
    </section>
  );
}
