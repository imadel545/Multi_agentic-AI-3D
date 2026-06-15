# LangGraph Workflow

LangGraph structure le pipeline de génération. Les entrées prompt, exigences validées issues
du document-pack, et génération de révision entrent toutes dans le graphe compilé avec un
`entry_mode` explicite. La création du patch d'édition, la copie d'artefacts et le versioning
restent des responsabilités `WorkflowService` hors graphe.

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

- `DesignOrchestrator.run()` utilise le workflow principal depuis texte libre.
- `run_requirements()` entre dans le graphe avec `entry_mode=validated_requirements`.
- `run_scene_revision()` entre dans le graphe avec `entry_mode=scene_revision`.
- Le checkpoint saver existe, mais il n'est pas encore une vraie base de reprise/cancellation.
- Les nœuds émettent maintenant `node_started`, puis `node_completed`,
  `node_failed` ou `node_skipped` avec phase, label humain, message de
  progression, détail, durée, warnings et errors.
- `workflow_trace.json` reste la preuve complète post-run.

## Frontend impact

- Afficher `events/stream` comme `push_sse` local-process: replay JSONL puis
  queue live jusqu'au terminal.
- Utiliser `/timeline-summary` pour une timeline lisible dérivée des events runtime + trace.
- Utiliser `/current-operation` pour `current_phase`, `current_node` et action suivante.
- Garder raw trace JSON en détail secondaire seulement.

## À corriger plus tard

- Décider si la création de patch d'édition et le versioning doivent devenir des nœuds LangGraph
  si le frontend exige une progression plus fine sur ces actions.
- Ajouter cancellation/retry/recovery et reprise durable si l'expérience frontend
  dépasse le modèle local-thread.
- Décider queue/job manager seulement si le runtime local-thread devient bloquant.
