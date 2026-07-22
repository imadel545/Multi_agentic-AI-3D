# LangGraph Workflow

LangGraph structure le pipeline de génération. Les entrées prompt, exigences validées issues
du document-pack, et génération de révision entrent toutes dans le graphe compilé avec un
`entry_mode` explicite. L'interprétation d'une édition utilise en plus un sous-système LangGraph
compilé et checkpointé. La copie d'artefacts et le versioning restent des responsabilités
`WorkflowService` hors graphe.

## Graphe d'adaptation d'asset

```text
discover_capabilities
  -> plan_adaptation
  -> validate_adaptation
  -> execute_adaptation
```

- `discover_capabilities` résout les profils actifs depuis les manifests et le
  catalogue versionné; aucun chemin n'est inventé dans le prompt.
- `plan_adaptation` utilise Groq `openai/gpt-oss-120b` avec JSON Schema strict.
  La valeur est transportée comme littéral JSON puis parsée et typée localement
  pour éviter les ambiguïtés de vecteurs du modèle.
- `validate_adaptation` vérifie capability id, chemin, outil, type, bornes et
  ancrage dans le prompt. Un plan LLM invalide déclenche le fallback contrôlé
  avant toute mutation.
- `execute_adaptation` applique uniquement les chemins résolus, revalide
  `SceneSpec`, puis le graphe de révision exécute Blender et toute la QA.
- Les threads d'adaptation sont isolés sous
  `{workflow_id}:adaptation:{invocation_uuid}` et utilisent le même saver SQLite.

## Noeuds principaux

```text
extract_requirements
retrieve_rag_context
decide_planning_context
memory_recall
select_assets
asset_fallback_handler
validate_requirements
plan_scene
validate_scene
scene_repair_handler
pre_blender_gate
quality_gate_failure_handler
generate_blender
blender_failure_handler
qa_generation
qa_failure_handler
post_blender_gate
certify_completion
memory_writeback
```

## Vérité runtime

- `DesignOrchestrator.run()` utilise le workflow principal depuis texte libre.
- `run_requirements()` entre dans le graphe avec `entry_mode=validated_requirements`.
- `run_scene_revision()` entre dans le graphe avec `entry_mode=scene_revision`.
- `retrieve_rag_context` utilise le texte original enrichi par le
  `RequirementSpec` structuré. Le nœud peut fournir du contexte et des
  `payload.planning_hints`; il ne modifie pas directement la géométrie.
  `rag_evidence.json` expose les sources, champs candidats, scores et statut
  reranker.
- `decide_planning_context` demande à GPT-OSS d'arbitrer uniquement des
  candidats RAG typés et validés; le modèle ne peut ni écrire de géométrie
  libre ni contourner les règles déterministes.
- Le checkpoint saver persiste des snapshots locaux sérialisables. Chaque
  création utilise `{workflow_id}:initial` et chaque révision
  `{workflow_id}:revision:{version_id}` afin qu'une révision ne reprenne jamais
  l'état d'une opération précédente. Il ne
  constitue pas encore un gestionnaire de cancellation/reprise durable.
- Une révision persiste son opération active dans le statut existant, reprend
  le stream après le dernier event durable, normalise les dépendances d'assets,
  puis entre dans `run_scene_revision()`.
- Après un redémarrage, une révision interrompue ne détruit pas le dernier
  design valide : sa version candidate devient `failed`, la version active
  `completed` est restaurée et le stream se termine par
  `edit_patch_rejected`. Une création initiale interrompue reste `failed`.
- Les nœuds émettent maintenant `node_started`, puis `node_completed`,
  `node_failed` ou `node_skipped` avec phase, label humain, message de
  progression, détail, durée, warnings et errors.
- `workflow_trace.json` reste la preuve complète post-run.
- `validate_scene` produit une couverture champ par champ des exigences. Toute
  divergence critique sans décision de planning appliquée et prouvée bloque le
  passage vers Blender.
- Après le post-gate, `certify_completion` émet ou rejette une preuve terminale
  liée aux hashes des exigences, de `SceneSpec`, du GLB, de la preview, des
  métadonnées et du build lock. Sans certificat `issued`, le statut final reste `failed` et la
  version n'est pas activée.

## Frontend impact

- Afficher `events/stream` comme `push_sse` local-process: replay JSONL puis
  queue live jusqu'au terminal.
- Utiliser `/timeline-summary` pour une timeline lisible dérivée des events runtime + trace.
- Utiliser `/current-operation` pour `current_phase`, `current_node` et action suivante.
- Utiliser `rag_planning_summary` pour afficher si RAG a seulement fourni du
  contexte ou s'il a fourni des hints structurés consommés par le planner.
- Utiliser `rag_evidence_url` dans le viewer/QA drawer pour montrer les sources
  et la raison d'un mode reranker dégradé.
- Garder raw trace JSON en détail secondaire seulement.

## À corriger plus tard

- Décider si le versioning doit devenir un nœud LangGraph; les quatre étapes
  d'adaptation émettent déjà une progression fine et persistée.
- Ajouter cancellation/retry/recovery et reprise durable si l'expérience frontend
  dépasse le modèle local-thread.
- Décider queue/job manager seulement si le runtime local-thread devient bloquant.
