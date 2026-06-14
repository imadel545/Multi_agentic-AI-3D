# Project Source Of Truth

Document actif principal. Toute autre documentation doit rester alignée avec ce fichier.

## Produit

Studio local-first et mono-utilisateur pour transformer un cahier des charges telecom
ou un pack documentaire (PDF, ZIP, DXF, images) en `SceneSpec`, artefacts Blender/GLB,
QA, versions et rollback.

Le projet vise un produit final chat-first et 3D-first, mais cette UI n'existe pas
aujourd'hui.

## Ce que le projet n'est pas

- Pas un SaaS multi-utilisateur.
- Pas un dashboard dev.
- Pas un générateur libre de code Blender par LLM.
- Pas une preuve marketing où un fallback est présenté comme un vrai résultat.
- Pas encore une bibliothèque d'assets vendor-grade complète.

## Backend actuel

- FastAPI expose les workflows design, document-pack, RAG, mémoire, assets et Product API.
- LangGraph existe, mais certains chemins (`run_requirements`, révision de scène) exécutent
  encore la séquence de manière impérative.
- Groq `openai/gpt-oss-120b` est utilisé quand une clé réelle existe; sinon extraction
  déterministe explicite.
- RAG principal: NVIDIA API `baai/bge-m3`.
- Fallback RAG: `sentence-transformers` local, puis hash déterministe en dernier recours.
- Reranker: `BAAI/bge-reranker-v2-m3` local best-effort; passthrough si indisponible.
- Mémoire: SQLite local avec writeback; Qdrant optionnel pour certains résumés.
- Document-pack: ZIP synchrone, extraction PDF/OCR/DXF limitée, consolidation,
  conflits, corrections, QA.
- Blender: génération réelle si Blender est trouvé; fallback Blender interdit par défaut
  pour la qualité (`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0`).

## Frontend actuel

- Aucun frontend opérationnel.
- L'ancien dashboard React/Vite est refusé.
- `apps/frontend` peut exister comme dossier vide local, mais il ne contient pas
  d'application.
- Ne pas reconstruire le frontend tant que les APIs produit, timeline, asset fallback et QA
  ne sont pas fiables.

## Assets actuels

- 12 manifests.
- 9 fichiers GLB présents.
- 3 tours sans GLB local: monopole, rooftop, small-cell.
- Statut attendu de `/assets/inventory`: `partial_import_ready`.
- Les tours manquantes utilisent un fallback procédural visible si sélectionnées et autorisées.
- Les assets actuels sont internes/CC-BY et non vendor-grade.

## 3D et QA actuelles

- `SceneSpec` est la source de vérité de génération.
- Blender produit `design.glb`, `preview.png`, `scene_metadata.json` et rapports.
- Les catégories de QA réelles sont:
  - `glb_parse_structural`
  - `object_name_based_geometry`
  - `metadata_based_height_azimuth`
  - `preview_luminance_only`
- La QA ne valide pas encore finement les transforms, matériaux ou dimensions mesh exactes.
- Ne pas appeler cette QA "advanced geometry".

## Events et runtime

- Les events sont persistés en JSONL.
- Les nœuds d'orchestration émettent `node_completed`, `node_failed` ou `node_skipped`
  avec `node`, `phase`, `status`, `detail`, `duration_ms`, warnings et errors.
- `/current-operation` expose `current_phase`, `current_node` et `event_source`.
- `/events/stream` est un `polling_sse`, pas un vrai push temps réel.
- Le futur frontend doit afficher cette limite clairement.

## Verdict actuel

`BACKEND_NEEDS_TRUTH_FIXES`

Le backend peut générer et tester des workflows locaux, mais il n'est pas encore prêt pour un
frontend avancé tant que les surfaces produit, warnings, asset fallback, timeline et docs ne
sont pas toutes alignées avec le runtime réel.
