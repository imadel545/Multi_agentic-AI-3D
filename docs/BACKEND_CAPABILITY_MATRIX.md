# Backend Capability Matrix

Statuts principaux: `IMPLEMENTED`, `IMPLEMENTED_LIMITED`, `IMPORT_ONLY`,
`UNSUPPORTED_WITHOUT_TOOL`, `ADVISORY`, `FUTURE`, `REJECTED`.
Cette matrice est la classification active; les anciens rapports readiness ont
été supprimés pour réduire le bruit.

| Capability | Status | Evidence | Limite / vérité frontend |
|---|---|---|---|
| Backend API | IMPLEMENTED | `apps/api/telecom_studio_api/main.py` | Local-first, mono-utilisateur. |
| Product API | IMPLEMENTED | `/studio/summary`, `/user-summary`, `/viewer-bundle`, `/timeline-summary`, `/current-operation`, `/user-issues` | Frontend-safe: warnings humains, artifact URLs, viewer/QA bundle, actions disponibles, timeline lisible, progression `push_sse`. |
| E2E product proof | IMPLEMENTED | `tests/e2e/test_telecom_generation_proof.py` | Basé sur `/designs` + `workflow_id`, sans `/projects` ni `/runs`. |
| Requirement extraction | IMPLEMENTED_LIMITED | `core/services/requirement_parser.py`, `core/services/requirement_provenance.py`, `core/llm/groq.py` | Groq si clé présente; fallback déterministe explicite. Provenance/candidats/conflits typés par champ; contradiction non résolue bloquée avant `/designs`. |
| Document pack ZIP | IMPLEMENTED_LIMITED | `core/document_pack/service.py`, `core/document_pack/mapper.py` | Synchrone, 80 Mo, extraction en mémoire; fondation absente/incompatible partagée par résumé, QA, gate et formulaire de correction. |
| PDF text/table extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | Layout/table semantics faibles. |
| OCR | IMPLEMENTED_LIMITED | Tesseract + `pytesseract` | Limité à une sélection de pages; langues système requises. |
| Docling | IMPORT_ONLY | `core/document_pack/tooling.py` | Import détecté seulement; pas conversion active par défaut. |
| DXF | IMPLEMENTED_LIMITED | `core/document_pack/cad.py` | Texte/couches; pas vraie géométrie CAD. |
| DWG library inventory/probe | IMPLEMENTED_LIMITED | `core/services/asset_library.py`, `/assets/library/*`, LibreDWG `dwgread` | Hash, déduplication, métadonnées et types d'entités; aucune tessellation ACIS revendiquée. |
| DWG 3D conversion | UNSUPPORTED_WITHOUT_TOOL | Route de conversion reportée par le probe; détection import-only dans `core/document_pack/tooling.py` | Les `3DSOLID` exigent une passerelle B-Rep/ACIS contrôlée. `dwgread` et ODA Drawings Explorer ne sont pas déclarés convertisseurs; 0 fichier brut est éligible à Blender. |
| RAG | IMPLEMENTED_LIMITED | `core/rag`, `rag_evidence.json`, `/studio/summary` | NVIDIA API `baai/bge-m3` est le chemin produit; santé `configured_unverified`/`operational`/`failed` fondée sur une vraie opération; index statique atomique; hash déterministe uniquement test/bootstrap explicite. |
| Reranker | IMPLEMENTED_LIMITED | `core/rag/reranker.py`, `/studio/summary` | NVIDIA API par défaut; passthrough seulement explicite ou dégradé visible; modèle local seulement si activé explicitement. |
| Memory | IMPLEMENTED_LIMITED | `core/memory`, collections Qdrant versionnées | SQLite writeback; recall encore peu sémantique. Les collections d'une ancienne dimension sont conservées et les nouvelles écritures sont routées vers une collection provider/dimension compatible; état visible dans `/studio/summary`. |
| LangGraph orchestration | IMPLEMENTED_LIMITED | `core/orchestration`, `SceneEditAgent` | Prompt, exigences validées, révisions et adaptation typée entrent dans des graphes checkpointés; versioning reste service-level. |
| Asset inventory | IMPLEMENTED | `/assets/inventory`, `core/services/asset_inventory.py` | 12 manifests, 12 GLB, 0 fichier manquant, `ready_for_import`. |
| Local CAD library | IMPLEMENTED_LIMITED | `/assets/library/summary`, `/assets/library/search`, `/assets/library/{file_id}/probe` | 11 974 fichiers, 11 531 contenus uniques, 443 doublons; schéma 1.1 relie 15 aperçus à 7 CAD. Recherche metadata-only; licences et conversion à qualifier; corpus brut hors Git. |
| Asset adaptation profiles | IMPLEMENTED_LIMITED | `/assets/adaptation-capabilities`, `/designs/{id}/adaptation-capabilities`, `assets/capabilities` | Catalogue typé et borné; tower paramétrique, layout secteur et transforms accessoires opérationnels. Pas de retopologie GLB opaque ni matériau arbitraire. |
| Blender generation | IMPLEMENTED_LIMITED | `core/services/blender_runner.py`, `apps/blender_worker` | Réel si Blender trouvé; factory-startup, staging unique par tentative et build lock hashé; fallback Blender refusé par défaut côté qualité. |
| Missing asset fallback | IMPLEMENTED | `apps/blender_worker/generate_scene.py` | Tous les manifests tower disposent d'un GLB; fallback procédural réservé aux cas d'échec d'import. |
| GLB binary integrity QA | IMPLEMENTED_LIMITED | `core/qa/gltf_integrity.py`, `core/qa/glb_inspector.py` | Valide header/chunks, buffers, bufferViews, données `POSITION`, indices et couverture mesh sémantique; pas encore topologie/manifold/collision complète. |
| Geometry QA | IMPLEMENTED_LIMITED | `core/qa/glb_geometry_validator.py`, `core/qa/mesh_qa.py` | `mesh_level_spatial_basic` quand transforms et bounds GLB sont complets, avec screening AABB des équipements primaires; sinon niveaux transform/basic. Pas de collision triangle/BVH, RF ou vendor-grade. |
| Segment connectivity gate | IMPLEMENTED | `apps/blender_worker/parametric_builder.py`, `generate_scene.py` | Mesure les extrémités réelles des membres cylindriques avant export; hard-fail au-delà de 1 mm. |
| Requirement coverage | IMPLEMENTED | `core/validation/requirement_coverage.py` | Prouve les mappings critiques `RequirementSpec -> SceneSpec`; déviation seulement avec décision appliquée et tracée. |
| Completion certificate | IMPLEMENTED | `core/validation/completion_certificate.py`, `WorkflowService._enforce_completion_proof` | `completed` exige Blender réel, gates/QA valides et hashes GLB/preview/metadata/build lock; ce n'est pas une signature cryptographique externe. |
| Preview QA | IMPLEMENTED_LIMITED | `core/qa/preview_inspector.py` | Pixel/framing basic: présence, occupation, centrage, clipping, contraste; pas jugement visuel sémantique. |
| Repair loop | IMPLEMENTED_LIMITED | `core/orchestration/langgraph_orchestrator.py` | Répare certains défauts de SceneSpec; pas boucle autonome générale. |
| Events | IMPLEMENTED_LIMITED | `workflow_events.jsonl`, `/events` | Events par nœud disponibles: `node_started`, résultat du nœud, artefacts prêts, QA, issues; runtime local-first. |
| SSE | IMPLEMENTED | `/events/stream` | `push_sse` local-process: replay JSONL puis queue live jusqu'au terminal; pas encore broker durable/cancellation. |
| Versioning / rollback | IMPLEMENTED | `core/services/scene_versioning.py` | Local filesystem, mono-utilisateur; activation canonique atomique par `active_design.json` après revalidation des hashes. |
| LangGraph checkpoint storage | IMPLEMENTED_LIMITED | `core/services/checkpoint_saver.py`, `checkpoints.db` | SQLite local, threads terminaux supprimés, quota au démarrage et compactage conditionnel du freelist; pas de reprise distribuée ni broker durable. |
| Frontend product rework | IMPLEMENTED_LIMITED | `apps/frontend`; Vitest + production build; 2026-07-24 visual smoke on real workflow `wf_3c86a159cd7b` | Chat-first/3D-first baseline; contradiction d'entrée bloquée, fallback/transport humanisés, fondation documentaire corrigeable. Full acceptance exige encore un smoke visuel enregistré de ces mutations. |

## Agent / Runtime Truth Matrix

Le terme "agent" reste strict: une étape est agentique seulement si elle a un
rôle réel dans le graphe ou encapsule un provider contrôlé. Le backend ne
prétend pas à une autonomie générale.

| Step / UI phase | Runtime level | Evidence | Frontend truth |
|---|---|---|---|
| `design_created` | Workflow service | `WorkflowService.create_design` | Démarrage local d'un `workflow_id`, pas création de project/run. |
| `extract_requirements` | LangGraph node + controlled LLM wrapper | `RequirementExtractor`, `GroqStructuredClient` | GPT-OSS `openai/gpt-oss-120b` si disponible; fallback déterministe visible via `extraction_provider`, `llm_fallback_used`, `llm_fallback_reason`. |
| `retrieve_rag_context` | LangGraph node + RAG service | `RagService`, `rag_evidence.json` | NVIDIA query/passage retrieval sur corpus contrôlé; pas utilisé pour l'extraction LLM v1. |
| `decide_planning_context` | LangGraph node + bounded GPT-OSS decision | `PlanningDecisionClient`, `planning_decision.json` | GPT-OSS arbitre seulement les candidats RAG typés; validators et SceneSpec restent l'autorité. |
| `memory_recall` | LangGraph node + SQLite/RAG service | `MemoryService` | Mémoire locale limitée; compteurs exposés dans `/studio/summary`. |
| `select_assets` / `asset_fallback_handler` | LangGraph node + asset registry | `AssetRegistry`, manifests | Asset réel/import/fallback visible; `/assets/inventory` est typé. |
| `validate_requirements` | LangGraph node + deterministic validators | `core/validation`, tower/RF validators | Validation métier contrôlée, pas décision libre LLM. |
| `plan_scene` | LangGraph node + deterministic planner | `core/agents/scene_planner.py` | `SceneSpec` reste la source de vérité de génération. |
| `validate_scene` / repair | LangGraph node + deterministic repair | `scene_repair_handler`, `requirement_coverage.py` | Répare certains défauts SceneSpec et bloque les exigences non couvertes; pas boucle autonome générale. |
| `generate_blender` | LangGraph node + Blender subprocess service | `BlenderRunner`, `apps/blender_worker` | `real_blender` requis pour résultat product-grade; fallback signalé. |
| `qa_generation` | LangGraph node + QA services | `glb_inspector`, `glb_geometry_validator`, `preview_inspector` | QA `mesh_level_spatial_basic`, transform ou basic selon les preuves disponibles; jamais une certification ingénierie avancée. |
| `certify_completion` | LangGraph node + deterministic proof builder | `completion_certificate.py` | Émet ou rejette la preuve terminale; aucune auto-déclaration `completed` par le LLM. |
| `artifact_ready` | Workflow service event | `WorkflowService._emit_result_product_events` | Artifacts publics par URL `/designs/{workflow_id}/artifacts/{name}`. |
| `discover_capabilities` → `execute_adaptation` | LangGraph + bounded GPT-OSS + deterministic tools | `SceneEditAgent`, `AdaptationCapabilityService`, `adaptation_plan.json` | Groq choisit seulement des capacités déclarées; validation locale avant mutation, puis Blender réel/QA. Aucun Python Blender LLM. |
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
consolidé. Le frontend sous `apps/frontend` a désormais une baseline produit
chat-first et 3D-first vérifiée sur un GLB Blender réel. La Gate complète reste
limitée tant que chaque mutation produit n'a pas son smoke enregistré.

Le vocabulaire backend stable reste `/designs` et `workflow_id`. Les labels
frontend "project", "run" et "scene plan" sont des mappings UI, pas de nouvelles
entités backend v1.
