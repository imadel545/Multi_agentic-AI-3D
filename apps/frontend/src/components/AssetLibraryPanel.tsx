import { Boxes } from "lucide-react";
import { useState, type FormEvent } from "react";
import type {
  AssetInventory,
  AssetLibraryProbe,
  AssetLibrarySearch,
  AssetLibrarySummary
} from "../api/schemas";
import { List, Metric, PanelTitle, ResourceRecovery, formatInteger } from "./StudioPrimitives";

export function AssetLibraryPanel({
  busy = false,
  error = null,
  inventory = null,
  inventoryError = null,
  loading = false,
  onSearch,
  onRetry,
  onRetryProbe,
  onRetrySearch,
  onProbe,
  probe = null,
  probeBusy = false,
  probeError = null,
  search = null,
  summary,
  summaryError = null
}: {
  busy?: boolean;
  error?: string | null;
  inventory?: AssetInventory | null;
  inventoryError?: string | null;
  loading?: boolean;
  onSearch?: (query: string) => void | Promise<void>;
  onRetry?: () => void;
  onRetryProbe?: () => void;
  onRetrySearch?: () => void;
  onProbe?: (fileId: string) => void | Promise<void>;
  probe?: AssetLibraryProbe | null;
  probeBusy?: boolean;
  probeError?: string | null;
  search?: AssetLibrarySearch | null;
  summary: AssetLibrarySummary | null;
  summaryError?: string | null;
}) {
  const [query, setQuery] = useState("");
  const dimensions = summary?.claimed_dimension_counts ?? {};
  const qualifiedAssets = (inventory?.entries ?? []).filter(
    (entry) => entry.generation_eligible
  );
  const referenceAssets = (inventory?.entries ?? []).filter(
    (entry) => entry.qualification_status === "reference_only"
  );
  const probeAvailable = summary?.dwg_probe_available !== false;
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim() && onSearch) void onSearch(query.trim());
  };
  return (
    <section className="drawer-section" aria-label="Bibliothèque de designs">
      <PanelTitle icon={<Boxes size={17} />} title="Bibliothèque telecom" />
      {loading ? <p className="muted" aria-live="polite">Synchronisation des manifests et du catalogue…</p> : null}
      {inventoryError ? (
        <ResourceRecovery
          busy={loading}
          label="Les composants qualifiés n’ont pas pu être chargés."
          message={inventoryError}
          onRetry={onRetry}
        />
      ) : null}
      {inventory ? (
        <>
          <div className="summary-card">
            <strong>
              {formatInteger(inventory.generation_eligible_asset_count)} composants exploitables
            </strong>
            <p>
              {formatInteger(inventory.import_qualified_glb_count)} meshes sont autorisés pour
              import exact; les autres suivent un profil paramétrique contrôlé.
            </p>
          </div>
          <div className="metric-grid">
            <Metric label="GLB présents" value={formatInteger(inventory.real_glb_asset_count)} />
            <Metric label="GLB qualifiés" value={formatInteger(inventory.import_qualified_glb_count)} />
            <Metric
              label="Profils exploitables"
              value={formatInteger(inventory.generation_eligible_asset_count)}
            />
            <Metric label="Référence seule" value={formatInteger(inventory.reference_only_asset_count)} />
          </div>
          <div className="library-results">
            <div className="library-results-heading">
              <strong>Composants 3D contrôlés</strong>
              <small>Le mode d’utilisation vient du manifest, pas du nom du fichier.</small>
            </div>
            {qualifiedAssets.map((entry) => (
              <article className="library-result-card" key={entry.asset_id}>
                <div>
                  <strong>{humanAssetId(entry.asset_id)}</strong>
                  <small>
                    {humanAssetType(entry.type)} · {humanAssetMode(entry.allowed_generation_modes)}
                  </small>
                </div>
                <p>{assetQualificationMessage(entry.allowed_generation_modes, entry.source)}</p>
              </article>
            ))}
            {referenceAssets.length ? (
              <>
                <div className="library-results-heading">
                  <strong>Références professionnelles en qualification</strong>
                  <small>Identité et provenance visibles; aucune référence seule n’est utilisée pour produire la géométrie.</small>
                </div>
                {referenceAssets.map((entry) => (
                  <article className="library-result-card incomplete" key={entry.asset_id}>
                    <div>
                      <strong>{entry.manufacturer ?? "Fabricant à confirmer"}</strong>
                      <span className="status-pill warn">Référence uniquement</span>
                      <small>
                        {entry.reference ?? entry.asset_id} · {entry.subtype ?? humanAssetType(entry.type)}
                      </small>
                      <small>
                        {entry.source_format?.toUpperCase() ?? "Source constructeur"}
                        {entry.attribution_required ? " · attribution requise" : ""}
                      </small>
                    </div>
                    <p>
                      {entry.dimensions_m
                        ? `Boîtier déclaré : ${formatAssetDimensions(entry.dimensions_m)}.`
                        : "Dimensions déclarées à confirmer."} {referenceAssetMessage(entry.qualification_limitations)}
                    </p>
                    {entry.original_url ? (
                      <a href={entry.original_url} rel="noreferrer" target="_blank">
                        Ouvrir la source fabricant
                      </a>
                    ) : null}
                  </article>
                ))}
              </>
            ) : null}
          </div>
        </>
      ) : null}
      {summary ? (
        <>
          <div className="summary-card">
            <strong>{formatInteger(summary.file_count ?? 0)} fichiers catalogués</strong>
            <p>
              La recherche exploite les noms et chemins catalogués. Aucun fichier brut n'est
              analysé comme géométrie ni utilisé dans le modèle avant qualification et conversion contrôlée.
            </p>
          </div>
          <div className="metric-grid">
            <Metric label="Contenus uniques" value={formatInteger(summary.unique_content_count ?? 0)} />
            <Metric label="Classés 3D" value={formatInteger(dimensions["3d"] ?? 0)} />
            <Metric label="Classés 2D" value={formatInteger(dimensions["2d"] ?? 0)} />
            <Metric label="Géométries exploitables" value={formatInteger(summary.generation_eligible_count)} />
            <Metric label="CAD avec aperçu" value={formatInteger(summary.cad_with_reference_preview_count)} />
          </div>
          <form className="library-search" onSubmit={submitSearch}>
            <label htmlFor="asset-library-query">Rechercher un pylône, équipement ou dimension</label>
            <div className="library-search-row">
              <input
                id="asset-library-query"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex. pylône Orange 30 m"
                type="search"
                value={query}
              />
              <button disabled={busy || !query.trim() || !onSearch} type="submit">
                {busy ? "Recherche…" : "Rechercher"}
              </button>
            </div>
          </form>
          {error ? (
            <ResourceRecovery
              busy={busy}
              label="La dernière recherche du catalogue n’a pas abouti."
              message={error}
              onRetry={onRetrySearch}
            />
          ) : null}
          {search ? (
            <div className="library-results" aria-live="polite">
              <div className="library-results-heading">
                <strong>{formatInteger(search.result_count)} résultat{search.result_count > 1 ? "s" : ""}</strong>
                <small>Aucun résultat n'est sélectionné automatiquement.</small>
              </div>
              {search.results.length ? search.results.map((entry) => (
                <article className="library-result-card" key={entry.file_id}>
                  <div>
                    <strong>{libraryFileName(entry.relative_path)}</strong>
                    <small>{entry.category} · {entry.claimed_dimension.toUpperCase()} · {entry.extension.toUpperCase()}</small>
                  </div>
                  <p>{entry.relative_path}</p>
                  <div className="library-result-meta">
                    <span>{entry.generation_eligible ? "Qualifié pour génération" : "En quarantaine"}</span>
                    <span>{entry.reference_preview_file_ids.length} aperçu{entry.reference_preview_file_ids.length > 1 ? "s" : ""}</span>
                  </div>
                  {entry.retrieval_evidence ? <LibraryRetrievalEvidence entry={entry} /> : null}
                  {onProbe ? (
                    <button
                      disabled={busy || probeBusy || !probeAvailable}
                      onClick={() => void onProbe(entry.file_id)}
                      type="button"
                    >
                      {probeBusy ? "Analyse géométrique…" : "Analyser la géométrie locale"}
                    </button>
                  ) : null}
                  {probe?.file.file_id === entry.file_id ? <CadProbeEvidence probe={probe} /> : null}
                </article>
              )) : <p className="muted">Aucun fichier du catalogue ne correspond à cette recherche.</p>}
              <p className="library-next-action">{search.next_action}</p>
              {probeError ? (
                <ResourceRecovery
                  busy={probeBusy}
                  label="Le probe géométrique n’a pas abouti; le fichier reste en quarantaine."
                  message={probeError}
                  onRetry={onRetryProbe}
                />
              ) : null}
              {!probeAvailable ? (
                <p className="muted">Le probe DWG local est indisponible; aucun diagnostic n’est inventé.</p>
              ) : null}
            </div>
          ) : null}
          <div className="summary-card warning-card">
            <strong>Qualification requise</strong>
            <p>
              Les licences sont à vérifier et les solides DWG ACIS exigent une passerelle CAD
              avant maillage. Cette quarantaine protège les designs produits.
            </p>
          </div>
          <List title="Limites actuelles" items={summary.limitations} empty="Aucune limitation remontée." />
        </>
      ) : summaryError ? (
        <ResourceRecovery
          busy={loading}
          label="Le catalogue local n’a pas pu être chargé; son absence n’est pas supposée."
          message={summaryError}
          onRetry={onRetry}
        />
      ) : loading ? null : (
        <p className="muted">Aucun catalogue n’a encore été publié par le backend.</p>
      )}
    </section>
  );
}

function LibraryRetrievalEvidence({ entry }: { entry: AssetLibrarySearch["results"][number] }) {
  const evidence = entry.retrieval_evidence;
  if (!evidence) return null;
  const matched = Object.entries(evidence.matched_terms)
    .map(([requested, terms]) => `${requested} → ${terms.join(", ")}`)
    .join(" · ");
  return (
    <p className="muted" aria-label="Preuve de recherche catalogue">
      Recherche lexicale dans le catalogue · couverture {Math.round(evidence.query_coverage * 100)} %
      {matched ? ` · termes trouvés : ${matched}` : ""}. Géométrie non vérifiée.
    </p>
  );
}

function CadProbeEvidence({ probe }: { probe: AssetLibraryProbe }) {
  return (
    <section className="summary-card warning-card" aria-label="Résultat du probe géométrique">
      <strong>Résultat du probe géométrique</strong>
      <p>{cadProbeVerdict(probe)}</p>
      <div className="metric-grid">
        <Metric label="Unités source" value={probeUnitLabel(probe)} />
        <Metric label="Solides ACIS" value={probe.contains_acis_3d_solids ? "détectés" : "absents"} />
        <Metric label="Maillage natif" value={probe.contains_mesh_convertible_geometry ? "détecté" : "absent"} />
        <Metric label="Géométrie exploitable" value={probe.blender_ready ? "oui" : "non"} />
      </div>
      <p className="muted">Entités détectées : {formatEntityCounts(probe.entity_counts)}</p>
      <List title="Limites de qualification" items={probe.limitations} empty="Aucune limite publiée." />
    </section>
  );
}

function cadProbeVerdict(probe: AssetLibraryProbe): string {
  if (probe.conversion_route === "requires_acis_brep_bridge") {
    return "Des solides ACIS sont présents. Une passerelle CAD B-Rep vérifiée est requise avant toute conversion Blender.";
  }
  if (probe.contains_mesh_convertible_geometry) {
    return "Un maillage natif est détecté. La conversion, les unités, les droits et la QA restent obligatoires avant toute admission.";
  }
  return "Le probe ne trouve pas de maillage natif exploitable. Ce fichier reste une référence ou un dessin 2D en quarantaine.";
}

function probeUnitLabel(probe: AssetLibraryProbe): string {
  const unit = probe.declared_unit ?? "inconnues";
  return probe.unit_metadata_conflict ? `${unit} · à confirmer` : unit;
}

function formatEntityCounts(counts: Record<string, number>): string {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  if (!entries.length) return "aucune entité exploitable";
  return entries
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([kind, count]) => `${kind} : ${count}`)
    .join(" · ");
}

function libraryFileName(relativePath: string): string {
  return relativePath.split("/").pop() ?? relativePath;
}

function humanAssetId(assetId: string): string {
  return assetId.toLowerCase().replaceAll("_", " ");
}

function humanAssetType(assetType: string): string {
  return (
    {
      antenna: "Antenne",
      cabinet: "Armoire",
      gps: "GPS",
      radio: "Radio",
      tower: "Support"
    } as Record<string, string>
  )[assetType] ?? "Composant";
}

function humanAssetMode(modes: string[]): string {
  if (modes.includes("imported_glb_exact")) return "mesh vérifié";
  if (modes.includes("parametric_generated")) return "génération paramétrique";
  return "référence uniquement";
}

function assetQualificationMessage(modes: string[], source: string | null | undefined): string {
  const origin = source?.startsWith("internal")
    ? "Géométrie générique interne, sans revendication constructeur."
    : "Provenance et attribution conservées dans le manifest.";
  if (modes.includes("imported_glb_exact")) {
    return `Fichier, dimensions, pivot et orientation vérifiés. ${origin}`;
  }
  return `Dimensions pilotées par la spécification 3D validée et un générateur borné. ${origin}`;
}

function formatAssetDimensions(dimensions: unknown): string {
  if (!dimensions || typeof dimensions !== "object") return "non publiées";
  const value = dimensions as { width?: unknown; depth?: unknown; height?: unknown };
  const numbers = [value.width, value.depth, value.height];
  if (!numbers.every((item) => typeof item === "number" && Number.isFinite(item))) {
    return "non publiées";
  }
  return numbers.map((item) => `${((item as number) * 1000).toFixed(0)} mm`).join(" × ");
}

function referenceAssetMessage(limitations: string[]): string {
  if (limitations.some((item) => item.toLowerCase().includes("anchor"))) {
    return "Ancrages et raccordement restent à qualifier avant réutilisation.";
  }
  return "Cette référence reste en revue locale avant réutilisation.";
}
