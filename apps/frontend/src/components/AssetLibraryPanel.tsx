import { Boxes } from "lucide-react";
import { useState, type FormEvent } from "react";
import type {
  AssetInventory,
  AssetLibraryProbe,
  AssetLibrarySearch,
  AssetLibrarySummary,
  AssetProvenance
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
  onReview,
  onProbe,
  probe = null,
  probeBusy = false,
  probeError = null,
  search = null,
  summary,
  summaryError = null,
  toAbsoluteUrl
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
  onReview?: (assetId: string) => Promise<AssetProvenance>;
  onProbe?: (fileId: string) => void | Promise<void>;
  probe?: AssetLibraryProbe | null;
  probeBusy?: boolean;
  probeError?: string | null;
  search?: AssetLibrarySearch | null;
  summary: AssetLibrarySummary | null;
  summaryError?: string | null;
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const [query, setQuery] = useState("");
  const [review, setReview] = useState<AssetProvenance | null>(null);
  const [reviewBusyAssetId, setReviewBusyAssetId] = useState<string | null>(null);
  const [lastReviewAssetId, setLastReviewAssetId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const dimensions = summary?.claimed_dimension_counts ?? {};
  const qualifiedAssets = (inventory?.entries ?? []).filter(
    (entry) => entry.generation_eligible
  );
  const visibleQualifiedAssets = qualifiedAssets.filter(
    (entry) => !claimsProfessionalIdentity(entry) && matchesInventoryEntry(entry, query)
  );
  const professionalCandidates = (inventory?.entries ?? []).filter(
    claimsProfessionalIdentity
  );
  const visibleProfessionalCandidates = professionalCandidates.filter((entry) =>
    matchesInventoryEntry(entry, query)
  );
  const probeAvailable = summary?.dwg_probe_available !== false;
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim() && onSearch) void onSearch(query.trim());
  };
  const examineCandidate = async (assetId: string) => {
    if (!onReview) return;
    setLastReviewAssetId(assetId);
    setReviewBusyAssetId(assetId);
    setReviewError(null);
    try {
      setReview(await onReview(assetId));
    } catch {
      setReview(null);
      setReviewError("Le dossier de ce candidat n’a pas pu être chargé.");
    } finally {
      setReviewBusyAssetId(null);
    }
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
            <Metric
              label="Preuves locales absentes"
              value={formatInteger(inventory.reference_evidence_missing_count ?? 0)}
            />
          </div>
          <div className="library-results">
            {visibleQualifiedAssets.length ? (
              <div className="library-results-heading">
                <strong>Composants 3D contrôlés</strong>
                <small>Le mode d’utilisation vient du manifest, pas du nom du fichier.</small>
              </div>
            ) : null}
            {visibleQualifiedAssets.map((entry) => (
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
            {visibleProfessionalCandidates.length ? (
              <>
                <div className="library-results-heading">
                  <strong>Candidats professionnels documentés</strong>
                  <small>Les candidats restent visibles même lorsqu’une preuve déclarée est absente ou incohérente.</small>
                </div>
                {visibleProfessionalCandidates.map((entry) => (
                  <article
                    className={`library-result-card${entry.milestone_evidence_eligible ? "" : " incomplete"}`}
                    key={entry.asset_id}
                  >
                    <div>
                      <strong>{entry.manufacturer ?? "Fabricant à confirmer"}</strong>
                      <span className={`status-pill ${entry.milestone_evidence_eligible ? "ok" : "warn"}`}>
                        {candidateStatusLabel(entry.asset_import_mode ?? entry.qualification_status)}
                      </span>
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
                        ? `Enveloppe publiée : ${formatAssetDimensions(entry.dimensions_m)}.`
                        : "Dimensions déclarées à confirmer."} {referenceAssetMessage(entry.qualification_limitations)}
                    </p>
                    {onReview ? (
                      <button
                        disabled={reviewBusyAssetId !== null}
                        aria-label={`Examiner ${entry.manufacturer ?? "le candidat"} ${entry.reference ?? entry.asset_id}`}
                        onClick={() => void examineCandidate(entry.asset_id)}
                        type="button"
                      >
                        {reviewBusyAssetId === entry.asset_id
                          ? "Ouverture du dossier…"
                          : "Examiner le candidat"}
                      </button>
                    ) : null}
                    {entry.original_url ? (
                      <a
                        aria-label={`Ouvrir la source de ${entry.manufacturer ?? "fabricant"} ${entry.reference ?? entry.asset_id}`}
                        href={entry.original_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Ouvrir la source fabricant
                      </a>
                    ) : null}
                  </article>
                ))}
                {review ? <AssetReviewEvidence review={review} toAbsoluteUrl={toAbsoluteUrl} /> : null}
                {reviewError ? (
                  <ResourceRecovery
                    busy={reviewBusyAssetId !== null}
                    label="Le dossier documenté reste indisponible."
                    message={reviewError}
                    onRetry={lastReviewAssetId
                      ? () => void examineCandidate(lastReviewAssetId)
                      : undefined}
                  />
                ) : null}
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
                  {onProbe && entry.extension.toLowerCase() === "dwg" ? (
                    <button
                      disabled={busy || probeBusy || !probeAvailable}
                      onClick={() => void onProbe(entry.file_id)}
                      type="button"
                    >
                      {probeBusy ? "Analyse géométrique…" : "Examiner le contenu 3D"}
                    </button>
                  ) : null}
                  {probe?.file.file_id === entry.file_id ? <CadProbeEvidence probe={probe} /> : null}
                </article>
              )) : <p className="muted">Aucun fichier du catalogue ne correspond à cette recherche.</p>}
              <p className="library-next-action">{search.next_action}</p>
              {probeError ? (
                <ResourceRecovery
                  busy={probeBusy}
                  label="L’analyse géométrique n’a pas abouti; le fichier reste en quarantaine."
                  message={probeError}
                  onRetry={onRetryProbe}
                />
              ) : null}
              {!probeAvailable ? (
                <p className="muted">L’analyse locale des fichiers DWG est indisponible; aucun diagnostic n’est inventé.</p>
              ) : null}
            </div>
          ) : null}
          <div className="summary-card warning-card">
            <strong>Qualification requise</strong>
            <p>
              Les droits, les unités, les repères et la géométrie doivent être vérifiés avant
              qu’un composant puisse entrer dans un design. Cette quarantaine protège les résultats.
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
    <section className="summary-card warning-card" aria-label="Résultat de l’analyse géométrique">
      <strong>Résultat de l’analyse géométrique</strong>
      <p>{cadProbeVerdict(probe)}</p>
      <div className="metric-grid">
        <Metric label="Unités source" value={probeUnitLabel(probe)} />
        <Metric label="Solides CAO" value={probe.contains_acis_3d_solids ? "détectés" : "absents"} />
        <Metric label="Maillage natif" value={probe.contains_mesh_convertible_geometry ? "détecté" : "absent"} />
        <Metric label="Géométrie exploitable" value={probe.blender_ready ? "oui" : "non"} />
      </div>
      <details>
        <summary>Détails techniques</summary>
        <p className="muted">Entités détectées : {formatEntityCounts(probe.entity_counts)}</p>
        <p className="muted">
          {probe.contains_acis_3d_solids
            ? "Le fichier contient des solides ACIS/B-Rep qui nécessitent un convertisseur CAD qualifié."
            : "Aucun solide ACIS/B-Rep n’a été détecté."}
        </p>
      </details>
      <List title="Limites de qualification" items={probe.limitations} empty="Aucune limite publiée." />
    </section>
  );
}

function cadProbeVerdict(probe: AssetLibraryProbe): string {
  if (probe.conversion_route === "requires_acis_brep_bridge") {
    return "Le fichier contient de vrais solides 3D, mais le studio ne dispose pas encore d’une conversion qualifiée pour les utiliser.";
  }
  if (probe.contains_mesh_convertible_geometry) {
    return "Un maillage natif est détecté. La conversion, les unités, les droits et la QA restent obligatoires avant toute admission.";
  }
  return "L’analyse ne trouve pas de géométrie 3D directement exploitable. Ce fichier reste une référence en quarantaine.";
}

function AssetReviewEvidence({
  review,
  toAbsoluteUrl
}: {
  review: AssetProvenance;
  toAbsoluteUrl?: (url: string | null | undefined) => string | null;
}) {
  const previewActions = review.review.available_actions.filter((action) =>
    action.kind === "internal_preview"
  );
  const sourceActions = review.review.available_actions.filter(
    (action) => action.kind === "external_source"
  );
  const admitted = review.review.status === "admitted";
  return (
    <section
      className={`summary-card${admitted ? "" : " warning-card"}`}
      aria-label="Dossier du candidat professionnel"
      aria-live="polite"
    >
      <div className="library-results-heading">
        <strong>{review.manufacturer ?? "Fabricant à confirmer"} {review.reference ?? ""}</strong>
        <span className={`status-pill ${admitted ? "ok" : "warn"}`}>
          {reviewStatusLabel(review.review.status)}
        </span>
      </div>
      <p>{review.review.summary}</p>
      <div className="metric-grid">
        <Metric label="Source" value={review.source_format.toUpperCase()} />
        <Metric
          label="Dimensions publiées"
          value={formatAssetDimensions(review.dimensions_m)}
        />
        <Metric
          label="Maillage contrôlé"
          value={review.qualification.mesh_integrity_verified ? "oui" : "non"}
        />
        <Metric label="Contrôle qualité" value={review.qa.status === "passed" ? "passé" : "incomplet"} />
        <Metric label="Preuves locales" value={localEvidenceStatusLabel(review.local_evidence_status)} />
      </div>
      <p>{professionalSourceSummary(review)}</p>
      <p>{professionalGeometrySummary(review)}</p>
      <div className="library-results">
        {review.review.checks.map((check) => (
          <article
            className={`library-result-card${check.status === "passed" ? "" : " incomplete"}`}
            key={check.check_id}
          >
            <div>
              <strong>{check.title}</strong>
              <span className={`status-pill ${check.status === "passed" ? "ok" : "warn"}`}>
                {check.status === "passed" ? "Vérifié" : "À compléter"}
              </span>
            </div>
            <p>{check.detail}</p>
          </article>
        ))}
      </div>
      <List
        title="À vérifier avant utilisation"
        items={review.review.blockers.map((blocker) => blocker.message)}
        empty="Aucun blocage publié."
      />
      {previewActions.length ? (
        <div className="library-results">
          {previewActions.map((action) => (
            toAbsoluteUrl?.(action.url) ? (
              <a
                href={toAbsoluteUrl(action.url) ?? undefined}
                key={action.action_id}
                rel="noreferrer"
                target="_blank"
              >
                {action.label}
              </a>
            ) : null
          ))}
        </div>
      ) : null}
      {sourceActions.map((action) => (
        <a href={action.url} key={action.action_id} rel="noreferrer" target="_blank">
          {action.label}
        </a>
      ))}
      <details>
        <summary>Détails techniques et droits</summary>
        <p className="muted">
          {review.source_provenance ?? "La provenance technique détaillée reste à confirmer."}
        </p>
        <p className="muted">
          {review.conversion_method ?? "Aucune méthode d’observation géométrique n’est publiée."}
        </p>
        <p className="muted">{review.license ?? "Droits non publiés."}</p>
        <p className="muted">
          Décision d’usage : {usageRightsStatusLabel(review.usage_rights.status)}. {review.usage_rights.evidence ?? "Aucune preuve de décision publiée."}
        </p>
        <p className="muted">
          {review.representations.length} représentation(s) publiée(s) · {review.previews.length} vue(s) publiée(s).
        </p>
      </details>
    </section>
  );
}

function professionalSourceSummary(review: AssetProvenance): string {
  const sourceKind = review.source_format.toUpperCase();
  if (review.manufacturer && review.reference && review.source_provenance) {
    return `Source ${sourceKind} attribuée à ${review.manufacturer}, référence ${review.reference}; sa provenance est conservée dans le dossier.`;
  }
  if (review.source_provenance) {
    return `La provenance de la source ${sourceKind} est conservée dans le dossier.`;
  }
  return `La provenance détaillée de la source ${sourceKind} reste à confirmer.`;
}

function professionalGeometrySummary(review: AssetProvenance): string {
  if (review.qualification.mesh_integrity_verified) {
    return "La structure géométrique et son passage dans le moteur 3D ont été contrôlés. Ce contrôle ne valide pas encore le repère d’installation ni les interfaces mécaniques.";
  }
  if (review.conversion_method) {
    return "Une méthode d’observation géométrique est documentée, mais son intégrité n’est pas encore validée pour la génération.";
  }
  return "Aucune observation géométrique contrôlée n’est encore publiée.";
}

function candidateStatusLabel(importMode: string | undefined): string {
  return {
    imported_glb_exact: "Admis pour import exact",
    professional_evidence_rejected: "Preuves incohérentes",
    qualified_file_rejected: "Fichier qualifié indisponible",
    quarantined_unverified: "Qualification requise",
    reference_only: "Référence uniquement"
  }[importMode ?? ""] ?? "Qualification requise";
}

function claimsProfessionalIdentity(entry: AssetInventory["entries"][number]): boolean {
  return entry.source === "vendor_supplied" || Boolean(entry.manufacturer) ||
    Boolean(entry.reference) || entry.asset_import_mode === "professional_evidence_rejected";
}

function localEvidenceStatusLabel(status: AssetProvenance["local_evidence_status"]): string {
  return {
    available: "vérifiées sur ce poste",
    partial: "partielles sur ce poste",
    unavailable: "absentes sur ce poste",
    not_published: "non publiées"
  }[status];
}

function usageRightsStatusLabel(status: AssetProvenance["usage_rights"]["status"]): string {
  return {
    project_authorized: "autorisée pour ce projet",
    review_only: "revue seulement",
    unknown: "à confirmer"
  }[status];
}

function reviewStatusLabel(status: AssetReviewStatus): string {
  return {
    admitted: "Admis pour import exact",
    blocked: "Qualification bloquée",
    evidence_invalid: "Preuves incohérentes",
    reference_only: "Non utilisable dans un design",
    technical_asset: "Composant technique"
  }[status];
}

type AssetReviewStatus = AssetProvenance["review"]["status"];

function matchesInventoryEntry(
  entry: AssetInventory["entries"][number],
  query: string
): boolean {
  const tokens = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const searchable = [
    entry.asset_id,
    entry.manufacturer,
    entry.reference,
    entry.family,
    entry.subtype,
    entry.type
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  return tokens.every((token) => searchable.includes(token));
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
