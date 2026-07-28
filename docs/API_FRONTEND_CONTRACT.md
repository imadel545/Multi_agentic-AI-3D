# API — Frontend Contract

Contrat minimal entre le backend FastAPI et le futur frontend React. Le contrat
stable actuel est `/designs` + `workflow_id`.

> `apps/frontend` est une rework connectée au backend réel, non encore acceptée
> comme produit. Ce contrat reste la frontière stable `/designs` + `workflow_id`.

---

## Endpoints produit (obligatoires pour le futur frontend)

Ces endpoints retournent des données orientées utilisateur. Le frontend ne doit plus parser `workflow_trace.json` ou `status.json` comme source principale.

Ne pas créer `/projects` ou `/runs` dans cette phase. Si l'UI parle de
"project", c'est un contexte frontend local. Si l'UI parle de "run", c'est le
`workflow_id`. Si l'UI parle de "scene plan", c'est l'artefact `scene_spec`.

| Méthode | Endpoint | Usage frontend |
|---|---|---|
| `GET` | `/studio/summary` | Résumé du studio : designs, assets, capacités, avertissements globaux. |
| `GET` | `/designs/{id}/user-summary` | Résumé lisible du design, opération en cours, action recommandée, issues. |
| `GET` | `/designs/{id}/current-operation` | Opération actuelle, phase/nœud courant dérivé des events, action suivante. |
| `GET` | `/designs/{id}/user-issues` | Issues lisibles avec titre, impact, action recommandée. |
| `GET` | `/designs/{id}/viewer-bundle` | URLs des artefacts 3D, mode génération, QA, résumé asset. |
| `GET` | `/designs/{id}/timeline-summary` | Timeline lisible issue des events + trace workflow. |

## Endpoints techniques (toujours disponibles)

| Méthode | Endpoint | Usage frontend |
|---|---|---|
| `GET` | `/health` | Vérifier que le backend est en ligne. |
| `GET` | `/designs` | Lister les designs récents. |
| `POST` | `/designs` | Créer un design depuis un prompt. |
| `GET` | `/designs/{id}` | Statut complet public: artefacts en URLs backend, pas en chemins locaux. |
| `GET` | `/designs/{id}/events` | Timeline des events bruts. |
| `GET` | `/designs/{id}/events/stream` | `push_sse`: replay JSONL puis events live jusqu'au terminal. |
| `GET` | `/designs/{id}/versions` | Historique des versions. |
| `POST` | `/designs/{id}/edit` | Éditer par prompt. |
| `POST` | `/designs/{id}/versions/{vid}/rollback` | Rollback vers une version. |
| `GET` | `/designs/{id}/artifacts/{name}` | Télécharger GLB, PNG, metadata, rapports. |
| `GET` | `/assets/inventory` | Inventaire des assets et leur état. |
| `GET` | `/assets/adaptation-capabilities` | Catalogue versionné des profils d'adaptation. |
| `GET` | `/designs/{id}/adaptation-capabilities` | Paramètres réellement modifiables dans la version active. |
| `GET` | `/assets/library/summary` | État honnête du catalogue CAD local et compte de fichiers éligibles. |
| `GET` | `/assets/library/search?q=...` | Recherche metadata-only consommée par le drawer Bibliothèque; expose quarantaine et liens d'aperçus, sans bouton de sélection Blender tant que `generation_eligible=false`. |
| `POST` | `/assets/library/{file_id}/probe` | Probe isolé du format/entités et route de conversion requise; ne promeut pas le fichier. |
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
- `build_lock` → `build.lock.json`
- `scene_spec` → `scene_spec.json`
- `qa_report` → `qa_report.json`
- `geometry_validation` → `geometry_validation.json`
- `requirement_coverage` → `requirement_coverage.json`
- `completion_certificate` → `completion_certificate.json`
- `rag_evidence` → `rag_evidence.json`
- `quality_gates` → `quality_gates.json`
- `trace` → `workflow_trace.json`
- `download` → `artifacts.zip`
- `adaptation_plan` → `adaptation_plan.json`
- `adaptation_capabilities` → `adaptation_capabilities.json`
- `scene_patch` → `scene_patch.json`
- `scene_diff` → `scene_diff.json`

Dans les réponses publiques (`/designs/{id}`, `/designs/{id}/edit`,
`/designs/{id}/versions`, `/viewer-bundle`), ces artefacts sont exposés via
`/designs/{id}/artifacts/{name}` ou `/designs/{id}/download`. Les chemins locaux
restent internes au backend.

## Champs clés du statut workflow

- `status` : `pending`, `running`, `completed`, `failed`.
- `generation_mode` : `real_blender` ou fallback.
- `generation_strategy`, `geometry_source`, `mesh_qa_level`, `mesh_qa_passed` :
  vérité 3D/QA affichable. `mesh_qa_level` peut être
  `mesh_level_spatial_basic`, `mesh_level_transform_basic`, `mesh_level_basic`,
  `metadata_only` ou `not_available`.
- `extraction_provider` : `groq`, `deterministic` ou `fallback`.
- `llm_provider`, `llm_available`, `llm_fallback_used`, `llm_fallback_reason` :
  vérité GPT-OSS/fallback affichable.
- `qa_score` : score entre 0 et 1.
- `requirement_coverage_passed`, `requirement_coverage_ratio` : preuve que les
  exigences critiques sont présentes dans `SceneSpec`.
- `completion_certificate_status` : `issued` uniquement lorsque le résultat
  terminal et les hashes des artefacts ont été vérifiés.
- `rag_reranker_provider`, `rag_reranker_model`, `rag_reranker_status`,
  `rag_reranker_degraded_reason` : vérité reranker NVIDIA/passthrough.
- `asset_import_summary` : résumé des imports GLB/fallback.
- `warnings` / `errors` : liste d'issues techniques.
- `active_version_id` : version active.
- `download_url` : lien de téléchargement de l'archive.
- `trace_url` : URL backend vers `workflow_trace.json`.
- `trace_path` : toujours `null` dans la réponse publique.
- `artifacts` : URLs backend, jamais `/Users/...`.
- `active_version_artifacts` : URLs versionnées quand une version active existe.
- `runtime_capabilities` : capacités runtime réelles du backend v1.
- `unsupported_actions` : actions explicitement non disponibles avec raison.
- `available_actions` : actions que l'UI peut proposer pour cet état.

## Limites connues du contrat

- `events/stream` est du `push_sse` local-process, pas un broker durable
  multi-processus.
- L'upload document pack est synchrone et limité à 80 Mo.
- Les endpoints produit sont une couche de présentation au-dessus des données techniques ; ils ne remplacent pas la validation backend.

## Champs Product API critiques

`/studio/summary` expose notamment:

- `asset_inventory_status`
- `asset_count`
- `real_glb_asset_count`
- `missing_file_count`
- `blender_available`
- `groq_available`
- `llm_available`
- `warnings`
- `rag_embedding_provider`, `rag_status`, `rag_degraded`, `rag_reranker`,
  `rag_reranker_provider`, `rag_reranker_model`, `rag_reranker_status`,
  `rag_reranker_degraded_reason`, `rag_operational_status`,
  `rag_last_operation`, `rag_reindex_url`
- `memory_status`, `memory_backend`, `workflow_memory_count`,
  `design_memory_count`, `document_pack_memory_count`,
  `memory_vector_status`, `memory_vector_errors`
- `runtime_capabilities`, `unsupported_actions`

`POST /requirements/parse` retourne un `RequirementSpec` avec
`field_evidence`, `conflicts`, `assumptions`, `requires_confirmation` et
`confirmation_fields`. `POST /designs` rejette un `confirmed_requirements`
encore marqué `requires_confirmation=true`.

Le résumé document-pack expose `blocking_fields`; son compteur de champs
bloquants, le rapport QA, le gate de génération et le formulaire de correction
doivent rester cohérents.

Mutating generation routes can return HTTP `507` when local storage is below
the configured safe threshold. The frontend must keep the current valid design
visible and ask the user to clean temporary artifacts before retrying.

`/viewer-bundle` expose uniquement des URLs d'artefacts, jamais des chemins filesystem:

- `generation_mode`
- `generation_strategy`
- `geometry_source`
- `mesh_qa_level`
- `mesh_qa_passed`
- `qa_score`
- `asset_import_summary`
- `human_warnings_count`
- `human_errors_count`
- `primary_glb_url`
- `preview_url`
- `report_url`
- `metadata_url`
- `scene_spec_url`
- `qa_report_url`
- `generation_report_url`
- `geometry_validation_url`
- `requirement_coverage_url`
- `completion_certificate_url`
- `requirement_coverage_passed`
- `requirement_coverage_ratio`
- `completion_certificate_status`
- `rag_evidence_url`
- `requirements_spec_url`
- `extraction_report_url`
- `extraction_provider`
- `llm_provider`
- `llm_available`
- `llm_fallback_used`
- `llm_fallback_reason`
- `rag_context_count`
- `rag_planning_summary`
- `rag_reranker_provider`
- `rag_reranker_model`
- `rag_reranker_status`
- `rag_reranker_degraded_reason`
- `memory_context_count`
- `qa_summary`
- `viewer_artifacts[]`
- `limitations`
- `runtime_capabilities`
- `unsupported_actions`
- `available_actions`

`rag_planning_summary` est obligatoire pour l'UI intelligente:

- `rag_used_for_extraction=false` en v1.
- `rag_used_for_planning=true` seulement si un `payload.planning_hints`
  structuré, validé et autorisé a réellement été appliqué.
- `rag_context_count` seul ne prouve pas que le RAG a changé le `SceneSpec`.
- `candidate_hint_fields` et `controlled_hint_fields` expliquent les champs
  candidats et les champs autorisés.
- `top_contexts[].source_path` est relatif au repo, jamais `/Users/...`.
- `rag_evidence_url` ouvre `rag_evidence.json`: sources RAG, hints contrôlés,
  hints rejetés, politique et statut reranker.

## Séquence frontend recommandée

1. `GET /health`.
2. `GET /studio/summary` pour backend, Blender, Groq, RAG NVIDIA, assets et warnings.
3. `GET /assets/inventory` pour le drawer assets.
4. `GET /assets/adaptation-capabilities` pour le catalogue déclaré.
5. `GET /document-packs/capabilities` pour configurer l'upload.
6. `GET /designs` pour restaurer les designs locaux.
7. `POST /designs` quand l'utilisateur envoie un prompt.
8. Ouvrir `/designs/{workflow_id}/events/stream`.
9. À l'événement terminal, charger `/viewer-bundle`, `/timeline-summary`,
   `/user-issues` et `/versions`.
10. Charger `/designs/{id}/adaptation-capabilities` avant d'afficher les
    possibilités d'édition du design actif.

Le frontend doit rendre:

- chat en surface principale;
- viewer 3D depuis `primary_glb_url`;
- strip d'agents depuis `payload.human_label` et `payload.progress_message`;
- drawers QA, timeline, scene plan, documents, assets, versions;
- raw JSON seulement en détail secondaire.

`/designs/{id}/edit` expose, en cas de succès:

- `status=applied`
- `edit_status`
- `message`
- `version_id`
- `artifacts` en URLs versionnées
- `viewer_bundle_url`
- `timeline_url`
- `user_issues_url`
- `current_operation_url`
- `runtime_capabilities`
- `unsupported_actions`
- `available_actions`

`/designs/{id}/versions` expose l'historique sans `artifact_dir`; les artefacts
de chaque version sont des URLs versionnées.

`/designs/{id}/versions/{vid}/rollback` expose, en cas de succès:

- `rolled_back=true`
- `status=rolled_back`
- `active_version_id`
- `message`
- `viewer_bundle_url`
- `timeline_url`
- `user_issues_url`
- `current_operation_url`
- `runtime_capabilities`
- `unsupported_actions`
- `available_actions`

`/current-operation` expose:

- `current_operation`
- `phase`
- `current_phase`
- `current_node`
- `human_label`
- `progress_message`
- `progress_label`
- `event_source`
- `state_source`
- `progress_indicator`
- `is_running`
- `is_terminal`
- `last_event_at`
- `runtime_capabilities`
- `unsupported_actions`
- `available_actions`

`runtime_capabilities` expose `streaming_transport=push_sse`,
`workflow_id_source=workflow_id`, `local_process_only=true` et les flags
`can_cancel=false`, `can_pause=false`, `can_resume=false`,
`can_retry_same_workflow=false`, `can_human_in_loop=false`,
`websocket_runtime=false`.

`unsupported_actions` liste au minimum `cancel`, `pause`, `resume`, `retry`,
`human_in_loop` et `websocket_runtime`, chacun avec `reason` et
`future_requirement`.

`/timeline-summary` expose des étapes lisibles:

- `step`
- `node`
- `label`
- `human_label`
- `progress_message`
- `phase`
- `status`
- `timestamp`
- `started_at`
- `completed_at`
- `duration_ms`
- `warnings_count`
- `errors_count`
- `artifact_refs`
- `human_readable`

`/document-packs/capabilities` expose:

- `document_pack_status=limited`
- `supported_upload_format=zip`
- `supported_inputs`
- `supported_extensions`
- `limits.max_zip_size_mb=80`
- `limits.max_member_size_mb=15`
- `max_size`
- `available_tools`
- `disabled_tools`
- `limitations`
- `truth.advanced_ingestion=false`
- `truth.docling_default_enabled=false`
- `next_action`
- `capabilities` avec les outils réels et leurs statuts

Events runtime attendus:

- `design_created`
- `node_started`
- `node_completed`
- `node_failed`
- `node_skipped`
- `artifact_ready`
- `qa_completed`
- `qa_failed`
- `user_issue_created`
- `workflow_completed`
- `workflow_failed`

Les events portent `event_id`, `workflow_id`, `timestamp`, `event_source` et
`payload`. Tous les payloads publics portent `payload.node`, `payload.phase`,
`payload.status`, `payload.human_label`, `payload.progress_message`,
`payload.duration_ms`, `payload.warnings`, `payload.errors` et
`payload.artifact_refs`. Les events de nœud ajoutent aussi `payload.detail`.

Un `node_failed` doit aussi apparaître dans `/user-issues` comme issue humaine. Si le workflow
termine malgré l'échec du nœud, la sévérité est `warning`; si le workflow échoue, elle est
`error`.
