# Backend Capability Matrix

Statuts principaux: `IMPLEMENTED`, `IMPLEMENTED_LIMITED`, `IMPORT_ONLY`,
`UNSUPPORTED_WITHOUT_TOOL`, `ADVISORY`, `FUTURE`, `REJECTED`.
Cette matrice est la classification active; les anciens rapports readiness ont
été supprimés pour réduire le bruit.

| Capability | Status | Evidence | Limite / vérité frontend |
|---|---|---|---|
| Backend API | IMPLEMENTED | `apps/api/telecom_studio_api/main.py` | Local-first, mono-utilisateur. |
| Docker Compose runtime | IMPLEMENTED_LIMITED | `infra/docker-compose.yml`, Dockerfiles, healthchecks, `infra/requirements-docker.lock` | Cinq services locaux, Blender 4.5.12 LTS vérifié, snapshots SQLite/Adminer RO et Qdrant 1.18.0 persistant. L'API amd64 est lente sous émulation Apple Silicon; mono-worker et un workflow concurrent. |
| Product API | IMPLEMENTED | `/studio/summary`, `/user-summary`, `/viewer-bundle`, `/timeline-summary`, `/current-operation`, `/user-issues` | Frontend-safe: warnings humains, artifact URLs, viewer/QA bundle, actions disponibles, timeline lisible, progression `push_sse`. |
| E2E product proof | IMPLEMENTED | `tests/e2e/test_telecom_generation_proof.py` | Basé sur `/designs` + `workflow_id`, sans `/projects` ni `/runs`. |
| Requirement extraction | IMPLEMENTED_LIMITED | `core/services/requirement_parser.py`, `core/services/requirement_provenance.py`, `core/llm/groq.py`, `extract_requirements` | Groq si clé présente; fallback déterministe explicite. Provenance/candidats/conflits typés par champ; valeur explicite invalide conservée ou réparée avec trace; contradiction non confirmée bloque le graphe avant RAG, assets et Blender. |
| Document pack multi-fichiers / ZIP | IMPLEMENTED_LIMITED | `core/document_pack/service.py`, `core/document_pack/mapper.py`, `POST /document-packs` | ZIP brut ou multipart direct; synchrone, 256 pièces, 15 Mo/pièce, 200 Mo non compressés et 80 Mo compressés; lectures/corrections sérialisées par pack et fichiers remplacés atomiquement, mais pas encore de transaction crash-safe unique sur toute la révision. |
| PDF text/table extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | Layout/table semantics faibles. |
| OCR | IMPLEMENTED_LIMITED | Tesseract + `pytesseract` | Limité à une sélection de pages; langues système requises. |
| Docling | IMPORT_ONLY | `core/document_pack/tooling.py` | Import détecté seulement; pas conversion active par défaut. |
| DXF | IMPLEMENTED_LIMITED | `core/document_pack/cad.py` | Texte/couches; pas vraie géométrie CAD. |
| DWG library inventory/probe | IMPLEMENTED_LIMITED | `core/services/asset_library.py`, `/assets/library/*`, LibreDWG `dwgread` | Hash, déduplication, métadonnées et types d'entités. Le dialecte réel Latin-1/non-fini de `minJSON` est normalisé avec compteur visible; `INSUNITS` gouverne l'échelle et tout conflit avec le libellé d'affichage est exposé. Aucune tessellation ACIS revendiquée. |
| DWG 3D conversion | UNSUPPORTED_WITHOUT_TOOL | Route de conversion reportée par le probe; détection import-only dans `core/document_pack/tooling.py` | Les `3DSOLID` exigent une passerelle B-Rep/ACIS contrôlée. `dwgread` et ODA Drawings Explorer ne sont pas déclarés convertisseurs; 0 fichier brut est éligible à Blender. |
| RAG | IMPLEMENTED_LIMITED | `core/rag`, `rag_evidence.json`, `/studio/summary` | NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` en 1024D est le chemin produit; santé `configured_unverified`/`operational`/`failed` fondée sur une vraie opération; index statique atomique; hash déterministe uniquement test/bootstrap explicite. |
| Reranker | IMPLEMENTED_LIMITED | `core/rag/reranker.py`, `/studio/summary` | NVIDIA API par défaut; passthrough seulement explicite ou dégradé visible; aucun modèle neural local n'est chargé par le runtime produit. |
| Memory | IMPLEMENTED_LIMITED | `core/memory`, table SQLite `memory_vector_outbox`, `POST /memory/vector/reindex`, collections Qdrant atomiques et versionnées | SQLite reste canonique et committe la mutation avec l'intention de projection. L'outbox durable reprend les tentatives Qdrant interrompues, expose échec/retry et évite une seconde autorité. Une scène legacy devenue invalide est préservée, ignorée pour la projection et comptée dans `skipped_source_counts` au lieu d'arrêter le worker. Le worker reste local-process; recall workflow encore principalement SQL. |
| LangGraph orchestration | IMPLEMENTED_LIMITED | `core/orchestration`, `SceneEditAgent` | Prompt, exigences validées, révisions et adaptation typée entrent dans des graphes checkpointés; versioning reste service-level. |
| Design blueprint | IMPLEMENTED_LIMITED | `compose_design_blueprint`, `core/contracts/design_blueprint.py`, `AssemblyPlan 1.1`, `design_blueprint.json`, `assembly_plan.json`, deux rapports de couverture | Intents génériques, contraintes et DAG de spécialistes déterministes routés; scoring multicandidat explicable incluant compatibilité, fidélité déclarée, stratégie de génération et dimensions; sélection Groq bornée aux IDs fournis, snapshots de manifests/builders, connecteurs et opérations hashées. La diversité de candidats qualifiés reste faible et aucun superviseur LLM ne crée librement de domaines. |
| Typed out-of-catalog geometry | IMPLEMENTED_LIMITED | `GeometryRequest`, `GeometryProgramPlanner`, `core/contracts/geometry_program.py`, `apps/blender_worker/geometry_program_compiler.py`, `plan_generated_geometry` | GPT-OSS écrit un DSL V2 typé: primitives, profils/extrusion, révolution, sweep, arrays, booléens exacts, modificateurs bornés, terrain, hiérarchie, ancres/connecteurs/groupes. Enveloppe et budget sont validés déterministiquement; aucun Python LLM. Pas de jugement sémantique du prompt, solveur de placement, BVH ou certification fournisseur. |
| Asset inventory | IMPLEMENTED | `/assets/inventory`, `core/services/asset_inventory.py` | 13 manifests éligibles, 12 GLB présents, 3 GLB autorisés en import exact, 10 profils paramétriques et 0 référence seule; statut `qualified_mixed_catalog`. Le composant procédural sans fichier n'est pas compté manquant. |
| Local CAD library | IMPLEMENTED_LIMITED | `/assets/library/summary`, `/assets/library/search`, `/assets/library/{file_id}/probe` | 11 974 fichiers, 11 531 contenus uniques, 443 doublons; schéma 1.1 relie 15 aperçus à 7 CAD. Recherche metadata-only; licences et conversion à qualifier; corpus brut hors Git. |
| Asset adaptation profiles | IMPLEMENTED_LIMITED | `/assets/adaptation-capabilities`, `/designs/{id}/adaptation-capabilities`, `assets/capabilities`, capacités dynamiques GeometryProgram | Catalogue typé et borné; tower paramétrique, layout secteur, offsets RRU, transforms accessoires et `/geometry_programs/{index}` rebuild opérationnels. La famille panel/parabole vient du profil builder signé, jamais d'une sous-chaîne d'ID/réseau. Les valeurs manifest sont revalidées fail-closed dans contrat/compiler/worker. Pas de retopologie GLB opaque ni matériau arbitraire. |
| Blender generation | IMPLEMENTED_LIMITED | `core/services/blender_runner.py`, `apps/blender_worker`, `trusted_assembly.py`, `component_proofs.py`, `geometry_program_compiler.py`, smoke Product API | Réel seulement si le smoke headless Blender aboutit; `AssemblyPlan 1.1` et registry déterministe gouvernent l'exécution. Le worker isolé revalide manifests, assets exacts, builders et opérations avant construction. Build lock `1.2.0` lie bundle, runtime, artefacts et entrées fiables; fallback Blender refusé par défaut. |
| Missing asset fallback | IMPLEMENTED | `apps/blender_worker/generate_scene.py`, `GeometryProgram` | La route câble est un builder paramétrique qualifié. Un composant réellement absent peut suivre un `GeometryProgram` typé et borné; un import exact invalide ou altéré échoue fermé et n'est jamais remplacé silencieusement. |
| Component construction proofs | IMPLEMENTED_LIMITED | `component_proofs.json`, `apps/blender_worker/component_proofs.py`, `/viewer-bundle.component_proofs_url` | Preuve par composant de stratégie, source, paramètres, transform, bounds, fingerprint, opérations et QA. Certifiée par le schéma 1.2; ce n'est ni une identité fournisseur ni une certification RF/structure/fabrication. |
| GLB binary integrity QA | IMPLEMENTED_LIMITED | `core/qa/gltf_integrity.py`, `core/qa/glb_inspector.py` | Valide header/chunks, buffers, bufferViews, données `POSITION`, indices et couverture mesh sémantique; pas encore topologie/manifold/collision complète. |
| Geometry QA | IMPLEMENTED_LIMITED | `core/qa/glb_geometry_validator.py`, `core/qa/mesh_qa.py`, `core/qa/glb_inspector.py` | `mesh_level_spatial_basic` quand transforms et bounds GLB sont complets, avec screening AABB; les profils panel/RRU internes exigent aussi leurs sous-pièces déclarées. Les programmes sont contractuellement validés, mais leurs rôles libres ne reçoivent pas encore de QA sémantique prompt/placement ni d'AABB primaire. Pas de collision triangle/BVH, RF ou vendor-grade. |
| Segment connectivity gate | IMPLEMENTED | `apps/blender_worker/parametric_builder.py`, `generate_scene.py` | Mesure les extrémités réelles des membres cylindriques avant export; hard-fail au-delà de 1 mm. |
| Requirement coverage | IMPLEMENTED | `core/validation/requirement_coverage.py` | Prouve les mappings critiques `RequirementSpec -> SceneSpec`; déviation seulement avec décision appliquée et tracée. |
| Completion certificate | IMPLEMENTED | `core/validation/completion_certificate.py`, `core/services/scene_versioning.py`, `WorkflowService._enforce_completion_proof` | `completed` exige Blender réel, gates/QA valides et hashes certifiés. Le schéma 1.2 est obligatoire pour AssemblyPlan 1.1/GeometryProgram et lie aussi `component_proofs`; le build lock 1.2 et ses entrées fiables sont revalidés à l'activation, lecture, rollback et service d'artefact. Les résultats historiques incomplets sont mis en quarantaine. Ce n'est pas une signature externe. |
| Preview QA | IMPLEMENTED_LIMITED | `core/qa/preview_inspector.py` | Pixel/framing basic: présence, occupation, centrage, clipping, contraste; pas jugement visuel sémantique. |
| Repair loop | IMPLEMENTED_LIMITED | `core/orchestration/langgraph_orchestrator.py` | Répare certains défauts de SceneSpec; pas boucle autonome générale. |
| Events | IMPLEMENTED_LIMITED | `workflow_events.jsonl`, `/events` | Events par nœud disponibles; `after_sequence` fournit des deltas bornés pour le polling et le reducer frontend les insère en lot O(N). Runtime local-first. |
| SSE | IMPLEMENTED | `/events/stream` | `push_sse` local-process: replay JSONL puis queue live jusqu'au terminal; curseur strict, rattrapage sur trou, deux erreurs transitoires tolérées avant fallback polling. Pas encore broker durable/cancellation. |
| Versioning / rollback | IMPLEMENTED | `core/services/scene_versioning.py` | Activation atomique par `active_design.json` après revalidation des hashes, de la scène versionnée, des rapports critiques 1.1/1.2 et de `component_proofs` quand le schéma 1.2 l'exige. Les projections root/event best-effort ne peuvent plus déclasser un commit canonique. |
| LangGraph checkpoint storage | IMPLEMENTED_LIMITED | `core/services/checkpoint_saver.py`, `checkpoints.db` | SQLite local, threads terminaux et adaptations éphémères supprimés, purge par workflow, quota au démarrage et compactage conditionnel du freelist; pas de reprise distribuée ni broker durable. |
| Frontend product rework | IMPLEMENTED_LIMITED | `apps/frontend`; 151 tests Vitest, typecheck et build passés; smoke Docker connecté le 2026-08-04 | Baseline chat-first/3D-first; GLB réel restauré, console navigateur sans erreur/warning et bundles servis sous `/static` sans collision avec l'API `/assets`. Les aides techniques sont masquées par défaut et comptées séparément des composants physiques. Le parcours exhaustif de création/révision générique reste ouvert. |

## Agent / Runtime Truth Matrix

Le terme "agent" reste strict: une étape est agentique seulement si elle a un
rôle réel dans le graphe ou encapsule un provider contrôlé. Le backend ne
prétend pas à une autonomie générale.

Chaque trace expose `actor_kind` et `decision_authority`; Blender, QA et
services ne sont donc plus assimilés à des agents LLM dans le contrat runtime.

| Step / UI phase | Runtime level | Evidence | Frontend truth |
|---|---|---|---|
| `design_created` | Workflow service | `WorkflowService.create_design` | Démarrage local d'un `workflow_id`, pas création de project/run. |
| `extract_requirements` | LangGraph node + controlled LLM wrapper | `RequirementExtractor`, `GroqStructuredClient` | GPT-OSS `openai/gpt-oss-120b` si disponible; fallback déterministe visible via `extraction_provider`, `llm_fallback_used`, `llm_fallback_reason`. |
| `retrieve_rag_context` | LangGraph node + RAG service | `RagService`, `rag_evidence.json` | NVIDIA query/passage retrieval sur corpus contrôlé; pas utilisé pour l'extraction LLM v1. |
| `decide_planning_context` | LangGraph node + bounded GPT-OSS decision | `PlanningDecisionClient`, `planning_decision.json` | GPT-OSS arbitre seulement les candidats RAG typés; validators et SceneSpec restent l'autorité. |
| `memory_recall` | LangGraph node + SQLite/RAG service | `MemoryService` | Mémoire locale limitée; compteurs exposés dans `/studio/summary`. |
| `select_assets` / `asset_fallback_handler` | LangGraph node + asset registry | `AssetRegistry`, manifests | Seuls les manifests qualifiés sont sélectionnables; leur fidélité déclarée contribue au score et est transmise au LLM borné. Le mode et la raison sont inscrits dans `SceneSpec`, l'import exact vérifie le SHA-256, et tout fallback reste visible. |
| `validate_requirements` | LangGraph node + deterministic validators | `core/validation`, tower/RF validators | Validation métier contrôlée, pas décision libre LLM. |
| `compose_design_blueprint` | LangGraph node + routed deterministic specialists | `BlueprintComposer`, `design_blueprint.json` | Composition typée et hashée; une demande hors catalogue peut déclarer une famille via `GeometryRequest`, mais aucun superviseur autonome n'ajoute librement un spécialiste ou une opération Blender. |
| `plan_scene` | LangGraph node + deterministic planner | `core/agents/scene_planner.py` | `SceneSpec` reste la source de vérité de génération. |
| `plan_generated_geometry` / failure handler | LangGraph node + bounded GPT-OSS authorship + deterministic validation | `GeometryProgramPlanner`, `GeometryProgram`, `geometry_program_failure_handler` | Programme déclaratif borné, provenance conservée, enveloppe et budget validés; toute sortie invalide bloque avant Blender. |
| `validate_scene` / repair | LangGraph node + deterministic repair | `scene_repair_handler`, `requirement_coverage.py` | Répare certains défauts SceneSpec et bloque les exigences non couvertes; pas boucle autonome générale. |
| `generate_blender` | LangGraph node + Blender subprocess service | `BlenderRunner`, `apps/blender_worker` | `real_blender` requis pour résultat product-grade; fallback signalé. |
| `qa_generation` | LangGraph node + QA services | `glb_inspector`, `glb_geometry_validator`, `preview_inspector` | QA `mesh_level_spatial_basic`, transform ou basic selon les preuves disponibles; jamais une certification ingénierie avancée. |
| `certify_completion` | LangGraph node + deterministic proof builder | `completion_certificate.py` | Émet ou rejette la preuve terminale; aucune auto-déclaration `completed` par le LLM. |
| `artifact_ready` | Workflow service event | `WorkflowService._emit_result_product_events` | Artifacts publics par URL `/designs/{workflow_id}/artifacts/{name}`. |
| `discover_capabilities` → `execute_adaptation` | LangGraph + bounded GPT-OSS + deterministic tools | `SceneEditAgent`, `AdaptationCapabilityService`, `adaptation_plan.json` | Groq choisit seulement des capacités déclarées; validation locale avant mutation, puis Blender réel/QA. Les composants générés utilisent une branche bornée de rebuild GeometryProgram avec provenance conservée. Aucun Python Blender LLM. |
| versioning / rollback | Service-level filesystem | `SceneVersioningService` | Local-first, mono-utilisateur; pas broker durable. |

## Runtime Contract V1

- Source de vérité runtime: `/designs` + `workflow_id`.
- Streaming: `push_sse` local-process, replay `workflow_events.jsonl` puis queue mémoire live jusqu'au terminal.
- Actions supportées: viewer, download artifacts, timeline, edit, versions, rollback selon état.
- Actions non supportées et visibles via `unsupported_actions`: cancel, pause, resume, retry du même workflow, human-in-loop, WebSocket runtime.
- Le frontend ne doit pas inventer ces capacités; il lit `runtime_capabilities` et `available_actions`.
- Le frontend doit lire `rag_planning_summary`: `rag_context_count` seul ne
  prouve pas que le RAG a modifié le plan.

## Synthèse

Le backend est riche et testable. Le contrat produit backend/frontend est
consolidé. M0 reste `IMPLEMENTED_LIMITED`: le rerun E2E Blender isolé et le
scénario HTTP réel génération/édition/version sont passés; seul le smoke
frontend connecté du tree final reste une gate. Aucune convergence globale
n'est déclarée.

Le vocabulaire backend stable reste `/designs` et `workflow_id`. Les labels
frontend "project", "run" et "scene plan" sont des mappings UI, pas de nouvelles
entités backend v1.

## Generic Cognitive 3D Core V1

| Capability | Status | Evidence | Limitation actuelle |
|---|---|---|---|
| Cognitive supervisor and routing | IMPLEMENTED_LIMITED | `core/agents/cognitive_supervisor.py`, `core/agents/cognitive_domain_router.py`, `core/services/cognitive_runtime.py` | Les spécialistes et leurs dépendances sont gouvernés par registre; GPT-OSS choisit dans cet espace fermé. La complétion provider réelle n'est pas encore fiable sur trois scénarios. |
| Cognitive decomposition | IMPLEMENTED_LIMITED | `core/agents/cognitive_design_planner.py`, `CognitiveDesignPlan` | Appels séparés intent/components/relationships, validation locale et réparation bornée. Groq peut encore retourner HTTP 400 ou une sortie incomplète après retries. |
| Capability harness | IMPLEMENTED | `core/contracts/capabilities.py`, `core/services/capability_registry.py` | Schémas, permissions, timeout, budget et observations sont déterministes; ce n'est pas un sandbox général de code. |
| Generic asset intelligence | PROCEDURAL_ONLY | `ProceduralOnlyCandidateRetriever`, décisions de stratégie cognitives | Hors route télécom qualifiée, aucun asset générique n'est encore recherché, scoré et adapté depuis la bibliothèque CAD. Le statut interdit de prétendre à une réutilisation réelle. |
| GeometryProgram V2 | IMPLEMENTED_LIMITED | `core/contracts/geometry_program.py`, `apps/blender_worker/geometry_program_compiler.py`, `core/services/geometry_capabilities.py` | DSL déclaratif avec extrusion, révolution, sweep, arrays, booléens, modificateurs, terrain, hiérarchie, ancres/connecteurs/groupes; pas de Python LLM, pas de CAO B-Rep ni de jugement sémantique automatique. |
| Generic SceneSpec compilation | IMPLEMENTED_LIMITED | `core/services/cognitive_scene_compiler.py`, `SceneSpec` V2 | Les composants deviennent des programmes gouvernés; la cohérence spatiale d'un assemblage arbitraire multi-composant n'est pas encore prouvée par un solveur de contraintes. |
| Generic Blender and previews | IMPLEMENTED_LIMITED | `BlenderRunner`, worker, `preview.png` + front/side/top/closeup | Cinq vues réelles et hashées; seule la vue principale entre dans la gate visuelle sémantique basique. |
| Generic QA and certificate | IMPLEMENTED_LIMITED | `generation_qa.py`, `completion_certificate.py` schema 1.3 | Couverture mesh des GeometryPrograms et intégrité GLB prouvées; pas de critique visuelle multimodale, collision triangle/BVH ou certification ingénierie. |
| Generic revision/versioning | IMPLEMENTED_LIMITED | `run_scene_revision(cognitive_plan=...)`, `WorkflowService`, `SceneVersioningService` | Révision V2 testée avec plan LLM contrôlé et Blender réel; parcours HTTP/UI générique provider réel non encore accepté. |
| Cognitive frontend evidence | IMPLEMENTED_LIMITED | `StudioKernel`, `TelecomGlbViewer`, contrats frontend | Conversation persistée, scène, provenance, sélection et galerie réelles; création/sélection de trois projets génériques réels non validée. |
