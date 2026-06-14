# LangGraph Workflow

LangGraph est présent et structure le pipeline, mais il ne faut pas prétendre que tous les
chemins passent proprement par le graphe compilé.

## Noeuds principaux

```text
extract_requirements
retrieve_rag_context
memory_recall
select_assets
asset_fallback_handler
validate_requirements
plan_scene
validate_scene
scene_repair_handler
quality_gate_failure_handler
generate_blender
blender_failure_handler
qa_generation
qa_failure_handler
post_blender_gate
memory_writeback
```

## Vérité runtime

- `DesignOrchestrator.run()` utilise le workflow principal.
- `run_requirements()` et `run_scene_revision()` exécutent encore une séquence impérative
  équivalente pour certains cas.
- Le checkpoint saver existe, mais il n'est pas encore une vraie base de reprise/cancellation.
- Les nœuds émettent maintenant des events runtime `node_completed`, `node_failed`,
  `node_skipped` avec phase, détail, durée, warnings et errors.
- `workflow_trace.json` reste la preuve complète post-run.

## Frontend impact

- Ne pas vendre un "live agent trace" complet tant que le transport reste polling.
- Afficher `events/stream` comme `polling_sse`.
- Utiliser `/timeline-summary` pour une timeline lisible dérivée des events runtime + trace.
- Utiliser `/current-operation` pour `current_phase`, `current_node` et action suivante.
- Garder raw trace JSON en détail secondaire seulement.

## À corriger plus tard

- Faire passer tous les chemins par le graphe compilé.
- Ajouter cancellation/retry/recovery.
- Passer de `polling_sse` à un vrai transport push uniquement si l'expérience frontend le prouve.
- Décider queue/job manager seulement si le runtime local-thread devient bloquant.
