# Backend Capability Matrix

Statuts principaux: `IMPLEMENTED`, `IMPLEMENTED_LIMITED`, `IMPORT_ONLY`,
`UNSUPPORTED_WITHOUT_TOOL`, `ADVISORY`, `FUTURE`, `REJECTED`.
Readiness produit détaillée: `docs/BACKEND_PRODUCT_READINESS_REPORT.md`.

| Capability | Status | Evidence | Limite / vérité frontend |
|---|---|---|---|
| Backend API | IMPLEMENTED | `apps/api/telecom_studio_api/main.py` | Local-first, mono-utilisateur. |
| Product API | IMPLEMENTED | `/studio/summary`, `/user-summary`, `/viewer-bundle`, `/timeline-summary`, `/current-operation`, `/user-issues` | Frontend-safe: warnings humains, artifact URLs, viewer/QA bundle, actions disponibles, timeline lisible, progression `push_sse`. |
| E2E product proof | IMPLEMENTED | `tests/e2e/test_telecom_generation_proof.py` | Basé sur `/designs` + `workflow_id`, sans `/projects` ni `/runs`. |
| Requirement extraction | IMPLEMENTED_LIMITED | `core/services/requirement_parser.py`, `core/llm/groq.py` | Groq si clé présente; regex fallback explicite sinon. |
| Document pack ZIP | IMPLEMENTED_LIMITED | `core/document_pack/service.py` | Synchrone, 80 Mo, extraction en mémoire. |
| PDF text/table extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | Layout/table semantics faibles. |
| OCR | IMPLEMENTED_LIMITED | Tesseract + `pytesseract` | Limité à une sélection de pages; langues système requises. |
| Docling | IMPORT_ONLY | `core/document_pack/tooling.py` | Import détecté seulement; pas conversion active par défaut. |
| DXF | IMPLEMENTED_LIMITED | `core/document_pack/cad.py` | Texte/couches; pas vraie géométrie CAD. |
| DWG | UNSUPPORTED_WITHOUT_TOOL | `dwgread`/ODA/FreeCAD detection | Conversion dépend d'outil local. |
| RAG | IMPLEMENTED_LIMITED | `core/rag` | NVIDIA `baai/bge-m3` principal; fallback local puis hash visible. |
| Reranker | IMPLEMENTED_LIMITED | `core/rag/reranker.py` | Local best-effort; passthrough si modèle indisponible. |
| Memory | IMPLEMENTED_LIMITED | `core/memory` | SQLite writeback; recall encore peu sémantique. |
| LangGraph orchestration | IMPLEMENTED_LIMITED | `core/orchestration` | Prompt, exigences validées et révisions entrent dans le graphe; patch edit/versioning restent service-level. |
| Asset inventory | IMPLEMENTED | `/assets/inventory`, `core/services/asset_inventory.py` | 12 manifests, 12 GLB, 0 fichier manquant, `ready_for_import`. |
| Blender generation | IMPLEMENTED_LIMITED | `core/services/blender_runner.py`, `apps/blender_worker` | Réel si Blender trouvé; fallback Blender refusé par défaut côté qualité. |
| Missing asset fallback | IMPLEMENTED | `apps/blender_worker/generate_scene.py` | Tous les manifests tower disposent d'un GLB; fallback procédural réservé aux cas d'échec d'import. |
| GLB structural QA | IMPLEMENTED_LIMITED | `core/qa/glb_inspector.py` | `glb_parse_structural`, pas validation mesh complète. |
| Geometry QA | IMPLEMENTED_LIMITED | `core/qa/glb_geometry_validator.py` | `object_name_based_geometry` + `metadata_based_height_azimuth`. |
| Preview QA | IMPLEMENTED_LIMITED | `core/qa/preview_inspector.py` | `preview_luminance_only`, pas jugement visuel sémantique. |
| Repair loop | IMPLEMENTED_LIMITED | `core/orchestration/langgraph_orchestrator.py` | Répare certains défauts de SceneSpec; pas boucle autonome générale. |
| Events | IMPLEMENTED_LIMITED | `workflow_events.jsonl`, `/events` | Events par nœud disponibles: `node_started`, résultat du nœud, artefacts prêts, QA, issues; runtime local-first. |
| SSE | IMPLEMENTED | `/events/stream` | `push_sse` local-process: replay JSONL puis queue live jusqu'au terminal; pas encore broker durable/cancellation. |
| Versioning / rollback | IMPLEMENTED | `core/services/scene_versioning.py` | Local filesystem, mono-utilisateur. |
| Frontend | FUTURE | `apps/frontend` vide ou absent | Ancien dashboard refusé; ne pas reconstruire maintenant. |

## Synthèse

Le backend est riche et testable. Le contrat produit backend/frontend est prêt
pour lancer la construction UI chat-first / 3D-first; le frontend reste absent
et doit consommer ces surfaces sans inventer de logique métier.

Le vocabulaire backend stable reste `/designs` et `workflow_id`. Les labels
frontend "project", "run" et "scene plan" sont des mappings UI, pas de nouvelles
entités backend v1.
