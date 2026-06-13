# API — Frontend Contract

Contrat minimal entre le backend FastAPI et le futur frontend React.

---

## Endpoints obligatoires

| Méthode | Endpoint | Usage frontend |
|---|---|---|
| `GET` | `/health` | Vérifier que le backend est en ligne. |
| `GET` | `/designs` | Lister les designs récents. |
| `POST` | `/designs` | Créer un design depuis un prompt. |
| `GET` | `/designs/{id}` | Récupérer le statut, QA, artifacts, warnings. |
| `GET` | `/designs/{id}/events` | Timeline des events. |
| `GET` | `/designs/{id}/events/stream` | SSE (actuellement polling côté backend). |
| `GET` | `/designs/{id}/versions` | Historique des versions. |
| `POST` | `/designs/{id}/edit` | Éditer par prompt. |
| `POST` | `/designs/{id}/versions/{vid}/rollback` | Rollback vers une version. |
| `GET` | `/designs/{id}/artifacts/{name}` | Télécharger GLB, PNG, metadata, rapports. |
| `GET` | `/assets/inventory` | Inventaire des assets et leur état. |
| `POST` | `/document-packs` | Uploader un ZIP. |
| `GET` | `/document-packs/{pack_id}` | Résumé du pack. |
| `GET` | `/document-packs/{pack_id}/consolidated-spec` | Spec consolidée. |
| `GET` | `/document-packs/{pack_id}/qa` | QA du pack. |
| `POST` | `/document-packs/{pack_id}/corrections` | Appliquer une correction manuelle. |
| `POST` | `/document-packs/{pack_id}/generate-design` | Générer un design depuis le pack. |

## Artifacts importants

Noms d'artifact utilisés par le frontend :

- `glb` → `design.glb`
- `preview` → `preview.png`
- `metadata` → `scene_metadata.json`
- `scene_spec` → `scene_spec.json`
- `qa_report` → `qa_report.json`
- `geometry_validation` → `geometry_validation.json`
- `quality_gates` → `quality_gates.json`
- `trace` → `workflow_trace.json`
- `download` → `artifacts.zip`

## Champs clés du statut workflow

- `status` : `pending`, `generating`, `completed`, `failed`.
- `generation_mode` : `real_blender` ou fallback.
- `qa_score` : score entre 0 et 1.
- `asset_import_summary` : résumé des imports GLB/fallback.
- `warnings` / `errors` : liste d'issues.
- `active_version_id` : version active.
- `download_url` : lien de téléchargement de l'archive.

## Limites connues du contrat

- `events/stream` est du polling toutes les secondes côté backend ; pas de vrai push.
- L'upload document pack est synchrone et limité à 80 Mo.
- Pas d'endpoint de résumé produit dédié (peut être ajouté plus tard).

## Futurs endpoints possibles

- `GET /studio/summary`
- `GET /designs/{id}/user-summary`
- `GET /designs/{id}/current-operation`
- `GET /designs/{id}/user-issues`

Ces endpoints ne sont pas implémentés dans cette mission.
