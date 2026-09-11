# API — Frontend Contract

Contrat minimal entre le backend FastAPI et le futur frontend React. Le contrat
stable actuel est `/designs` + `workflow_id`.

`workflow_id` doit respecter `wf_[0-9a-f]{12}` et `version_id`
`v[0-9a-f]{8}`. La validation HTTP rejette aussi les traversées encodées avant
toute lecture locale. Un workflow bien formé mais inconnu retourne `404` pour
le statut, la conversation, les événements et les versions.

> `apps/frontend` est une rework connectée au backend réel, non encore acceptée
> comme produit. Ce contrat reste la frontière stable `/designs` + `workflow_id`.

---

## Endpoints produit (obligatoires pour le futur frontend)

Ces endpoints retournent des données orientées utilisateur. Le frontend ne doit plus parser `workflow_trace.json` ou `status.json` comme source principale.

Toute réponse ou événement portant un `workflow_id` doit correspondre au workflow
actif avant d'être appliqué. Un changement de workflow invalide les chargements
terminaux précédents; le client applique une sémantique dernier-appel-gagnant pour
le bundle, les versions et les ressources associées. Une réponse tardive ne doit
jamais remplacer le viewer, la timeline, les issues ou le curseur SSE du design
actif.

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
| `GET` | `/health` | Vérifier que le backend est en ligne; expose aussi un résumé mémoire agrégé du pool Groq sans probe réseau ni identité de clé. |
| `GET` | `/designs` | Lister les designs récents. |
| `POST` | `/designs` | Créer un design depuis un prompt. |
| `GET` | `/designs/{id}` | Statut complet public: artefacts en URLs backend, pas en chemins locaux. |
| `GET` | `/designs/{id}/conversation` | Projection lecture seule du journal durable : demandes enregistrées et notifications d’exécution, sans réponse assistant inventée. |
| `GET` | `/designs/{id}/events` | Timeline des events bruts. |
| `GET` | `/designs/{id}/events/stream` | `push_sse`: replay JSONL puis events live jusqu'au terminal. |
| `GET` | `/designs/{id}/versions` | Historique des versions. |
| `POST` | `/designs/{id}/edit` | Éditer par prompt, globalement ou sur une identité certifiée liée à sa version. |
| `POST` | `/designs/{id}/versions/{vid}/rollback` | Rollback vers une version. |
| `GET` | `/designs/{id}/artifacts/{name}` | Télécharger GLB, PNG, metadata, rapports. |
| `GET` | `/assets/inventory` | Inventaire des assets et leur état. |
| `GET` | `/assets/{asset_id}/provenance` | Provenance publique, licence, fidélité, route de conversion et état de qualification, sans chemin local. |
| `GET` | `/assets/{asset_id}/previews/{view}` | Preview qualifiée publiée par le manifest; existence et hash sont vérifiés avant service. |
| `GET` | `/assets/adaptation-capabilities` | Catalogue versionné des profils d'adaptation. |
| `GET` | `/designs/{id}/adaptation-capabilities` | Paramètres réellement modifiables dans la version active. |
| `GET` | `/assets/library/summary` | État honnête du catalogue CAD local et compte de fichiers éligibles; chargé au démarrage pour le drawer Bibliothèque. |
| `GET` | `/assets/library/search?q=...` | Recherche metadata-only consommée par le drawer Bibliothèque; expose quarantaine et liens d'aperçus, sans bouton de sélection Blender tant que `generation_eligible=false`. |
| `POST` | `/assets/library/{file_id}/probe` | Action explicite du drawer Bibliothèque. Retourne unités, entités, présence ACIS/maillage et route de conversion; ne promeut pas le fichier. |
| `POST` | `/document-packs` | Uploader un ZIP brut ou plusieurs fichiers via `multipart/form-data`. |
| `GET` | `/document-packs/{pack_id}` | Résumé du pack. |
| `GET` | `/document-packs/{pack_id}/consolidated-spec` | Spec consolidée. |
| `GET` | `/document-packs/{pack_id}/qa` | QA du pack. |
| `POST` | `/document-packs/{pack_id}/corrections` | Appliquer une correction manuelle. |
| `POST` | `/document-packs/{pack_id}/generate-design` | Générer un design depuis le pack. |

`POST /designs` accepte `options.multimodal_consent` et
`POST /document-packs/{pack_id}/generate-design` accepte le même consentement
dans son body optionnel. Les valeurs publiques sont `disabled`,
`allow_input_analysis` et `allow_input_and_visual_review`; la valeur par défaut
est toujours `disabled`. Le consentement est persisté avec le workflow. Le
contrat actuel du document pack retourne `remote_vision_analysis=not_executed`:
cocher le consentement n'envoie pas encore automatiquement une pièce jointe à
Qwen.

`GET /health` est aussi un contrôle d'identité du service, pas seulement un
ping. Le frontend exige `status=ok`,
`service=agentic_telecom_3d_studio_api` et
`api_contract_version=2026-07-29`; une autre application sur le même port doit
être refusée.
`groq_credential_pool` est additif et contient uniquement `status`, compteurs
configurés/prêts/cooldown/désactivés/restreints/saturés, réponses provider
observées et requêtes en vol. Ce résumé ne rend jamais la liveness dépendante de
Groq et ne signifie pas qu'une sortie métier a passé sa validation Pydantic.

## Artifacts importants

Pour les scènes génériques, `scene_spec` peut contenir une liste additive
`rigid_component_relations`. Son absence signifie qu'aucune de ces relations
bornées n'est déclarée. Le composant piloté par `aligned_with` expose
`strategy=compose` dans `component_proofs`, tout en conservant
`generation_strategy=imported_glb_exact`. Le résultat mesuré figure dans les
checks `rigid_relation:*` de `geometry_validation.mesh_qa`; le code technique ne
doit pas devenir le message principal de l'UI. Cette relation prouve position
relative et orientation, sans preuve de contact ou fixation physique. Elle
n'ajoute aucun endpoint ni état de workflow; le probe CAD existant reste un
diagnostic de bibliothèque explicitement demandé par l'utilisateur.

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
- `design_blueprint` → `design_blueprint.json`
- `assembly_plan` → `assembly_plan.json`
- `component_proofs` → `component_proofs.json`
- `constraint_evidence` → `constraint_evidence.json`
- `blueprint_requirement_coverage` → `blueprint_requirement_coverage.json`
- `blueprint_scene_coverage` → `blueprint_scene_coverage.json`

Dans les réponses publiques (`/designs/{id}`, `/designs/{id}/edit`,
`/designs/{id}/versions`, `/viewer-bundle`), ces artefacts sont exposés via
`/designs/{id}/artifacts/{name}` ou `/designs/{id}/download`. Les chemins locaux
restent internes au backend.

## Conversation durable par workflow

`GET /designs/{id}/conversation` est une projection lecture seule du
`workflow_events.jsonl` canonique. Les nouveaux designs enregistrent soit le
texte reçu de l’utilisateur, soit une origine documentaire clairement marquée
comme système ; les nouvelles modifications enregistrent le texte reçu avant
l’exécution. Leurs issues sont des notifications système fondées sur le
résultat réel. Le frontend ne doit jamais présenter ces notifications comme une
réponse LLM.

Chaque message expose `message_id`, `role` (`user` ou `system`), `text`,
`timestamp`, ainsi que l’`operation_id`, l’identité ciblée et la version quand
ces données existent. `history_status=recorded` signifie que l’origine de
création du workflow a été enregistrée; `legacy_partial` indique que seuls les
événements historiques réellement présents peuvent être montrés; `damaged`
signale une portion de journal illisible tout en préservant les messages lus.
Le contrat ne crée ni projet, ni session de compte, ni transcript assistant.

## Champs clés du statut workflow

- `status` : `pending`, `running`, `completed`, `failed`,
  `legacy_unverified` (ancien résultat sans preuve complète) ou
  `integrity_failed` (preuve active modifiée/incohérente).
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
- Les deux statuts de quarantaine exposent `artifacts={}` et ne fournissent ni
  `download_url` ni `trace_url`; le frontend doit proposer une régénération
  certifiée, jamais afficher le viewer comme prêt.
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
- `runtime_capabilities.multimodal_intelligence` : état public
  `disabled`, `configured_unverified`, `operational` ou `failed`, capabilities
  disponibles et limites d'entrée. La présence d'une clé ne suffit pas à
  publier `operational`.
- `unsupported_actions` : actions explicitement non disponibles avec raison.
- `available_actions` : actions que l'UI peut proposer pour cet état.
  `rollback_version` n'est présent que pour un résultat certifié avec version
  active.

## Limites connues du contrat

- `events/stream` est du `push_sse` local-process, pas un broker durable
  multi-processus.
- L'upload document pack est synchrone. Un ZIP compressé est limité à 80 Mo;
  les fichiers directs sont limités à 256 pièces, 15 Mo par pièce, 200 Mo
  non compressés et 80 Mo après assemblage ZIP interne contrôlé.
- Les endpoints produit sont une couche de présentation au-dessus des données techniques ; ils ne remplacent pas la validation backend.

## Champs Product API critiques

`/studio/summary` expose notamment:

- `asset_inventory_status`
- `asset_count`
- `real_glb_asset_count`
- `import_qualified_glb_count`
- `generation_eligible_asset_count`
- `professional_evidence_asset_count`
- `reference_only_asset_count`
- `qualified_integrity_failure_count`

Chaque entrée expose aussi `qualification_status`, `generation_eligible`,
`allowed_generation_modes`, `qualification_method`, les limites de
qualification et le résultat du contrôle du hash. La présence d'un `.glb` ne
signifie donc plus qu'il est automatiquement utilisable par Blender.
Les entrées qui ont une identité externe exposent également `family`, `subtype`,
`manufacturer`, `reference`, `source_provenance`, `source_format`,
`original_url`, `dimensions_m` et `qualification_version`; ces champs décrivent
la preuve disponible et ne confèrent aucun droit de réutilisation.
Les entrées M1 peuvent aussi exposer `preview_set`, `provenance_url`,
`geometry_status`, `fidelity_status`, `milestone_evidence_eligible` et
`milestone_evidence_failures`. Le catalogue courant contient 14 assets
runtime mais 0 preuve professionnelle M1; le frontend ne doit donc pas les
présenter comme composants constructeur qualifiés.

`milestone_evidence_eligible` est une preuve runtime, pas une recopie du
manifest. Le backend vérifie le confinement des chemins, l'existence et les
SHA-256 du master, du viewer, des cinq PNG et du rapport QA, ainsi que
l'intégrité GLB/PNG, la lignée, les dimensions et les anchors. Une preview ne
peut être présentée comme professionnelle que si le flag asset est vrai et si
la vue est `available && qa_status == "passed"`.
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
  `memory_vector_status`, `memory_vector_errors`, `memory_vector_reindex_url`.
  La santé vectorielle reflète l'outbox SQLite durable (`pending`, `attempt`,
  `failed`, `succeeded` ou état inactif) et ne transforme jamais Qdrant en
  source d'autorité.
- `runtime_capabilities`, `unsupported_actions`

`POST /memory/vector/reindex` reconstruit uniquement la projection Qdrant à
partir de SQLite. La réponse typée expose les volumes source,
`skipped_source_counts` pour les lignes legacy invalides préservées mais non
indexées, les candidats après compaction, le provider/dimension, le fingerprint
source et confirme que SQLite et les collections legacy sont préservés. Cette route de maintenance ne
crée ni `project`, ni `run`, ni nouvelle source d'état produit.

`POST /requirements/parse` retourne un `RequirementSpec` avec
`field_evidence`, `conflicts`, `assumptions`, `requires_confirmation` et
`confirmation_fields`. `POST /designs` rejette un `confirmed_requirements`
encore marqué `requires_confirmation=true`.
Le `requirements_hash` de confirmation est un jeton HMAC process-local lié au
texte exact, au niveau de détail et au `RequirementSpec` complet (warnings,
réparations, preuves et conflits inclus). Il est invalide après redémarrage et
ne constitue ni un identifiant persistant ni une signature externe.

`RequirementSpec.geometry_requests[]` porte les composants demandés hors
catalogue. Chaque entrée expose `request_id`, `semantic_role`, `description`,
`quantity`, `placement_context` et `maximum_dimensions_m`. Les identifiants et
rôles sont uniques, la liste est bornée à 8 demandes et les quantités à 32.
`maximum_dimensions_m` est vérifié déterministiquement contre l'enveloppe
compilable du programme; un adaptateur uniforme borné peut uniquement corriger
ce dépassement. `placement_context` est conservé comme provenance, pas encore
interprété ni certifié comme contrainte spatiale.

Le résumé document-pack expose `blocking_fields`; son compteur de champs
bloquants, le rapport QA, le gate de génération et le formulaire de correction
doivent rester cohérents.

Pour restaurer une revue documentaire après rechargement, le frontend peut
conserver uniquement un pointeur versionné `{version, packId}` dans le stockage
local. Le contenu du pack, ses conflits, ses champs manquants, sa QA, ses
documents, extractions, provenances, étapes de traitement et sa spec consolidée
doivent être relus depuis `/document-packs/{pack_id}/*`. Le stockage navigateur
n'est jamais une source de vérité documentaire et son indisponibilité ne doit
pas interrompre le studio.

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
- `geometry_fidelity_summary`
- `geometry_program_summary`
- `human_warnings_count`
- `human_errors_count`
- `primary_glb_url`
- `preview_url`
- `report_url`
- `metadata_url`
- `scene_spec_url`
- `assembly_plan_url`
- `component_proofs_url`
- `constraint_evidence_url`
- `assembly_constraint_summary`
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
- `multimodal_consent`
- `multimodal_intelligence`
- `asset_decision_summary`
- `visual_review`
- `limitations`
- `runtime_capabilities`
- `unsupported_actions`
- `available_actions`

`component_proofs_url` vaut `null` quand l'artefact n'existe pas ou n'est pas
certifié pour la version servie. Le frontend doit alors afficher une preuve
indisponible, jamais inventer une provenance. Lorsqu'elle est disponible, cette
URL ouvre la preuve par composant (`reuse`, `adapt`, `compose` ou
`procedural_generate`), ses paramètres, sa transformation, son empreinte et ses
contrôles locaux.

`constraint_evidence_url` et `assembly_constraint_summary` sont présents
uniquement pour une version certifiée qui contient une preuve valide. Le résumé
expose `status`, `measurement_scope=exported_glb_anchor_frames`, le nombre de
connexions requises, le nombre d'instances mécaniques mesurées,
`resolved_support_count`, les erreurs
maximales de position/orientation et les limitations. L'UI doit distinguer les
connexions requises non mécaniques des liaisons mécaniques mesurées et rappeler
qu'un support observé prouve seulement un mesh exporté avec l'identité attendue:
ni contact, visserie, transmission de charge, fabrication, validation
d'ingénierie ou preuve professionnelle ne sont établis. Un fichier
`constraint_evidence.json` parasite d'une version non-assembly est exclu du
viewer bundle, du service d'artefact et de l'archive publique.

`asset_decision_summary` présente par composant la stratégie sémantique
publique (`reuse_full_design`, `adapt_full_design`, `reuse_component`,
`adapt_component`, `compose_assets`, `compose_and_generate`,
`procedural_generate`, `clarify` ou `unsupported` selon la preuve persistée),
sans exposer les prompts privés ni les chemins locaux.
`visual_review` est séparé de la QA déterministe et utilise
`not_requested`, `passed_advisory`, `review_required` ou `failed`. Il reste
consultatif: il ne peut ni promouvoir un asset, ni annuler un échec
déterministe, ni certifier une dimension ou une scène.

`assembly_plan.json` schema `1.1.0` expose notamment les candidats scorés, le
candidat choisi, la stratégie choisie, `selection_provider`, `selection_model`,
la capability et la version `bounded_asset_selection@1.2.0`, les snapshots de manifest/builder, les
connecteurs et les opérations hashées. Une décision Groq reste limitée aux IDs
fournis; la validation, les unités et les opérations restent déterministes.
Le provider reçoit un mapping fermé `role_id -> choice_id`; le tuple
asset/génération/stratégie est reconstruit localement. Seul
`model_output_rejected` autorise un second appel immédiat. Auth, rate-limit,
timeout et transport ne sont pas rejoués par ce client; après deux rejets, le
fallback déterministe reste public.

`geometry_program_summary` expose uniquement une preuve bornée:

- `program_count`, `generated_component_count`, `total_node_count`,
  `repaired_program_count`;
- par programme: `program_id`, `semantic_role`, `requested_quantity`,
  `node_count`, `authorship`, `generator_provider`, `generator_model`,
  `structured_output_mode`, `source_prompt_sha256`, `source_description`,
  `source_description_origin` (`user_requirement`, `revision_preserved` ou
  `legacy_unavailable`), `placement_context`, `maximum_dimensions_m`,
  `deterministic_adjustments` et `limitations`.

Les modes possibles sont `strict_json_schema`, `json_object_validated` et
`json_object_repaired`. Le frontend doit montrer une réparation, pas la présenter
comme une sortie strictement décodée.

`rag_planning_summary` est obligatoire pour l'UI intelligente:

- `rag_used_for_extraction=false` en v1.
- `rag_used_for_planning=true` seulement si un `payload.planning_hints`
  structuré, validé et autorisé a réellement été appliqué.
- `rag_context_count` seul ne prouve pas que le RAG a changé le `SceneSpec`.
- `rag_retrieval_status` distingue `primary_vector`, cache vectoriel et
  `degraded_local_lexical`; `rag_retrieval_degraded_reason` expose la catégorie
  de panne sans secret.
- `candidate_hint_fields` et `controlled_hint_fields` expliquent les champs
  candidats et les champs autorisés.
- `top_contexts[].source_path` est relatif au repo, jamais `/Users/...`.
- `rag_evidence_url` ouvre `rag_evidence.json`: sources RAG, hints contrôlés,
  hints rejetés, politique, statut retrieval et statut reranker. Les champs
  workflow `llm_fallback_*` décrivent l'extraction principale; la sélection
  d'assets possède sa vérité distincte dans `assembly_plan.selection_authority`,
  `assembly_plan.llm_fallback_*` et `asset_decision_summary`.

## Séquence frontend recommandée

1. `GET /health`.
2. `GET /studio/summary` pour backend, Blender, Groq, RAG NVIDIA, assets et warnings.
3. `GET /assets/inventory` pour le drawer assets.
4. `GET /assets/library/summary` pour le catalogue CAD local et le statut du probe.
5. `GET /assets/adaptation-capabilities` pour le catalogue déclaré.
6. `GET /document-packs/capabilities` pour configurer l'upload.
7. `GET /designs` pour restaurer les designs locaux.
8. `POST /designs` quand l'utilisateur envoie un prompt.
9. Ouvrir `/designs/{workflow_id}/events/stream`.
   Après fallback polling, appeler `/designs/{workflow_id}/events?after_sequence=N`
   et traiter le lot delta au lieu de relire l'historique complet.
10. Charger `/designs/{id}/conversation` pour le workflow restauré, puis le
   relire après les événements de création, d’édition ou de résultat.
11. À l’événement terminal, charger `/viewer-bundle`, `/timeline-summary`,
    `/user-issues` et `/versions`.
12. Charger `/designs/{id}/adaptation-capabilities` avant d’afficher les
    possibilités d’édition du design actif.

Le frontend doit rendre:

- chat en surface principale;
- viewer 3D depuis `primary_glb_url`;
- exécution spécialisée depuis `payload.human_label`,
  `payload.progress_message`, `payload.actor_kind` et
  `payload.decision_authority`; ne pas appeler Blender/QA/services « agents LLM »;
- drawers QA, timeline, scene plan, documents, assets, versions;
- la provenance composant via `component_proofs_url`, avec état de chargement,
  erreur et retry indépendants des autres drawers;
- intent hors catalogue avant génération, puis modèle, mode de sortie, enveloppe,
  ajustements et provenance GeometryProgram après génération;
- raw JSON seulement en détail secondaire.

Le frontend M0 ne doit conserver aucun succès obsolète après une erreur ou un
changement de version. Les ressources GLB/WebGL, assets, QA, RAG, provenance,
documents et versions ont des états de chargement/erreur/retry indépendants. La
frontière HTTP reste mono-utilisateur/loopback: les hosts sont allowlistés et une
mutation avec un `Origin` navigateur étranger échoue avant le service. Ce garde
ne constitue pas une authentification utilisateur et n'ajoute aucun JWT.
La suite courante compte 180 tests Vitest et passe le typecheck/build. Un smoke
layout current-tree en lecture seule a chargé le GLB certifié à 1440 x 1000 et
1047 x 2748. Le smoke connecté de l'arbre de convergence immédiatement
précédent a confirmé la création, le flux SSE, le GLB/WebGL réel, le RAG et les
drawers; les mutations navigateur exhaustives restent une gate distincte
ouverte.

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

La requête accepte `target_semantic_root` et `expected_version_id` ensemble
(sinon HTTP 422). Sans ces champs, l'édition globale existante est conservée.
Le viewer bundle publie `version_id` depuis son snapshot vérifié; l'UI capture
cette version lors de la sélection et efface la sélection au changement de
bundle. La cible est résolue dans `component_proofs.json`, dont le hash est
lié au certificat de la version active, sous le verrou d'opération.
Une version périmée ou une identité inconnue, ambiguë ou non prise en charge
donne un résultat `rejected` et conserve la version active.

Le périmètre filtre les capacités avant planification et contraint de nouveau
le patch final, indépendamment du planificateur. Les cibles prises en charge
sont les poses d'antennes, les décalages RRU et un GeometryProgram de quantité
un. Les programmes répétés et les autres composants ne disposent pas encore
d'édition ciblée. Déplacer une antenne peut déplacer ses dépendances de
montage; ce n'est pas une modification libre de mesh. Le picking frontend
utilise les identités d'instances publiées, pas des noms inventés depuis le clic.

Pour un composant généré, les capacités résolues ajoutent un chemin
`/geometry_programs/{index}`, un `value_type=geometry_program` et
`execution_tool=geometry_program_rebuild`. Le LLM peut régénérer uniquement le
programme ciblé; le backend revalide le contrat, applique la mutation à
`SceneSpec`, relance Blender/QA et crée une nouvelle version. La description
source, le contexte de placement et l'enveloppe maximale sont conservés.

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
- `supported_upload_format=zip_or_multiple_files`
- `supported_inputs`
- `supported_extensions`
- `limits.max_zip_size_mb=80`
- `limits.max_member_size_mb=15`
- `limits.max_member_count=256`
- `limits.max_uncompressed_size_mb=200`
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

## Generic cognitive evidence V1

Le Product API peut publier dans le viewer bundle, lorsqu'ils existent:

- le plan cognitif et son domaine détecté;
- les décisions de stratégie et leur provenance provider/modèle;
- le résumé des `GeometryProgram` et observations de capacités;
- l'arbre sémantique de scène et les identifiants de nœuds GLB sélectionnables;
- les URLs publiques de `preview`, `preview_front`, `preview_side`,
  `preview_top` et `preview_closeup`.

Le frontend ne construit jamais une URL depuis un chemin filesystem et ne
présente aucune preuve absente comme vide ou réussie. Une erreur d'une ressource
secondaire reste dans son drawer; elle ne masque ni ne contredit un viewer
bundle principal déjà certifié et chargé.

### Generic exact-source reuse — 2026-09-10

`ComponentAssetDecision.placement` optionally carries a rigid transform in metres,
Z-up. It is mandatory for `reuse`; non-unit scaling is rejected. A successful
reuse appears in `component_proofs.geometry_programs` with `origin: catalog_asset`,
`strategy: reuse`, `generation_strategy: imported_glb_exact`, and one
`exact_asset_sources` entry pinning asset ID, source file/hash and manifest
filename/hash. Historical generated proofs retain their existing origin/strategy.
The source's fidelity and license are preserved; exact import does not imply
manufacturer accuracy. Rebuilding these programs through the LLM is unavailable.

`geometry_program_summary.programs[].origin` distinguishes these two origins;
`generated_component_count` counts generated geometry and `reused_component_count`
counts imported sources. The optional “Intention libre” creation path sends
`requirements_text` and `use_llm: true` without telecom confirmation; the backend
remains responsible for route selection and honest failure when unavailable.

### Runtime origin and raw library retrieval — 2026-09-10

Workflow status exposes `origin`: PRODUCT, TEST, EVALUATION, IMPORT, MIGRATION or
UNKNOWN (historical default). `TELECOM_STUDIO_RUNTIME_ORIGIN` is service-side
configuration, not a user-controlled request field. Memory records also persist
`recall_eligible`; product recall requires both PRODUCT origin and eligibility.
Non-product memory cannot be promoted by a normal write with the same identity.

`/assets/library/search` preserves its metadata-only/quarantine contract. Each
result adds `retrieval_evidence` with method, matched query/source terms, query
coverage and `geometry_verified: false`. Scores rank metadata relevance only;
duplicate content is collapsed and missing terms remain visible in coverage.

## Accès de maintenance vérifié

Quand la scène active exige un profil d'accès de tour, `viewer-bundle` peut
retourner `tower_access_summary` et `tower_access_evidence_url`. Le résumé
contient l'identité sémantique, le nombre mesuré de barreaux, les niveaux de
plateformes et les limites de la preuve. Il ne paraît que si la preuve
post-Blender hashée est passée et correspond au `SceneSpec` actif.

`tower_access_summary.interaction_mode` vaut actuellement
`inspection_only`. Le frontend peut permettre la sélection et l'inspection de
l'ensemble, mais ne doit pas proposer une édition ciblée ou présenter cette
géométrie procédurale interne comme un équipement constructeur ou une
validation d'installation.

Artifact additionnel:

- `tower_access_evidence` → `tower_access_evidence.json`
