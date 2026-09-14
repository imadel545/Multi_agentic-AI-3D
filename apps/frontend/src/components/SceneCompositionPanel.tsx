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

function constructionLabel(strategy: string, proceduralExecution: boolean, exactImport: boolean): string {
  if (proceduralExecution) {
    return "Géométrie procédurale générée pour ce projet";
  }
  if (exactImport) {
    return "Modèle source conservé";
  }
  const labels: Record<string, string> = {
    reuse: "Modèle source conservé",
    adapt: "Modèle source ajusté",
    compose: "Assemblé à partir de plusieurs éléments",
    procedural_generate: "Créé pour ce projet"
  };
  return labels[strategy] ?? "Créé pour ce projet";
}

function sourceLabel(
  asset: QualifiedAssetInventoryEntry | undefined,
  hasCatalogSource: boolean,
  proceduralExecution: boolean
): string {
  if (proceduralExecution) return "Génération procédurale locale";
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

function formatMeasuredExtent(dimensions: readonly number[] | null | undefined): string | null {
  if (!dimensions || dimensions.length !== 3) return null;
  const [width, depth, height] = dimensions.map(dimensionValue);
  if (!width || !depth || !height) return null;
  return `L × P × H : ${formatMeters(width)} × ${formatMeters(depth)} × ${formatMeters(height)} m`;
}

function isProceduralExecution(
  strategy: string,
  generationStrategy: string,
  geometrySources: string[]
): boolean {
  return generationStrategy === "internal_project_generated" ||
    strategy === "procedural_generate" ||
    geometrySources.some((source) => source.includes("parametric") || source.includes("procedural"));
}

function isExactImport(generationStrategy: string, geometrySources: string[]): boolean {
  return generationStrategy === "imported_glb_exact" ||
    geometrySources.some((source) => source === "asset_glb" || source === "imported_glb_exact");
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

  return (
    <section className="drawer-section" aria-label="Composition de la scène">
      <PanelTitle icon={<Layers3 size={17} />} title="Composition" />

      {componentProofs ? (
        <div className="composition-overview" aria-label="Résumé de la composition">
          <strong>{elementCount} {elementCount > 1 ? "composants principaux" : "composant principal"}</strong>
          <small>Les accès et éléments auxiliaires sont présentés séparément. Sélectionnez un composant pour le retrouver dans la vue 3D.</small>
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
            const geometrySources = component.instances.map((instance) => instance.geometry_source);
            const proceduralExecution = isProceduralExecution(
              component.strategy,
              component.generation_strategy,
              geometrySources
            );
            const exactImport = isExactImport(component.generation_strategy, geometrySources);
            return (
              <div className="scene-tree-group" key={component.component_id} role="group">
                <div className="scene-tree-heading">
                  <div>
                    <strong>{humanSemanticRole(component.role_id)}</strong>
                    <small>{constructionLabel(component.strategy, proceduralExecution, exactImport)}</small>
                  </div>
                  <span>{component.quantity}</span>
                </div>
                <p>Source : {sourceLabel(asset, Boolean(component.asset_id), proceduralExecution)}</p>
                {component.instances.map((instance) => {
                  const dimensions = formatMeasuredExtent(instance.bounding_box_m?.dimensions_m);
                  return <button
                    aria-current={selectedSemanticRoot === instance.semantic_root ? "true" : undefined}
                    className={`scene-tree-item${selectedSemanticRoot === instance.semantic_root ? " selected" : ""}`}
                    key={instance.instance_id}
                    onClick={() => onSelect?.(instance.semantic_root)}
                    role="treeitem"
                    type="button"
                  >
                    <span>{humanComponentInstanceLabel(componentProofs, instance.semantic_root)}</span>
                    <small>{selectedSemanticRoot === instance.semantic_root ? "Sélectionné" : "Sélectionner pour modifier"}</small>
                    {dimensions ? <small>Encombrement dans le modèle — {dimensions}</small> : null}
                  </button>
                })}
              </div>
            );
          })}
          {componentProofs.geometry_programs.map((program) => {
            const sourceAssetId = program.exact_asset_sources?.[0]?.asset_id;
            const sourceAsset = sourceAssetId ? inventoryByAssetId.get(sourceAssetId) : undefined;
            const proceduralExecution = isProceduralExecution(
              program.strategy,
              program.generation_strategy,
              []
            );
            const dimensions = formatMeasuredExtent(program.bounding_box_m?.dimensions_m);
            return (
              <div className="scene-tree-group" key={program.component_id} role="group">
                <div className="scene-tree-heading">
                  <div>
                    <strong>{humanSemanticRole(program.role_id)}</strong>
                    <small>{constructionLabel(program.strategy, proceduralExecution, program.origin === "catalog_asset")}</small>
                  </div>
                  <span>{program.quantity}</span>
                </div>
                <p>Source : {sourceLabel(sourceAsset, program.origin === "catalog_asset", proceduralExecution)}</p>
                {dimensions ? <small>Encombrement dans le modèle — {dimensions}</small> : null}
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
