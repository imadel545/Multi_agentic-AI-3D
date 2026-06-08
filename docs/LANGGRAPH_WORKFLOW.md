# LangGraph Workflow

The workflow is implemented in `core/orchestration/langgraph_orchestrator.py`.

Initial generation uses the compiled LangGraph. Prompt edits use `run_scene_revision`, a controlled
revision path in the same orchestrator that reuses the validation, generation, QA, gate, metrics,
trace, and memory components from a patched `SceneSpec`.

## Implemented Nodes

Main path:

1. `extract_requirements`
2. `retrieve_rag_context`
3. `memory_recall`
4. `select_assets`
5. `validate_requirements`
6. `plan_scene`
7. `validate_scene`
8. `pre_blender_gate`
9. `generate_blender`
10. `qa_generation`
11. `post_blender_gate`
12. `memory_writeback`

Revision path for edits:

1. `edit_prepare_revision`
2. `validate_requirements`
3. `validate_scene`
4. `pre_blender_gate`
5. `generate_blender`
6. `blender_failure_handler` when fallback/failure is explicit
7. `qa_generation`
8. `post_blender_gate`
9. `memory_writeback` when memory is configured and the revision passes

Corrective foundation:

- `missing_data_handler`
- `asset_fallback_handler`
- `rule_violation_handler`
- `scene_repair_handler`
- `blender_failure_handler`
- `qa_failure_handler`
- `quality_gate_failure_handler`

Real corrective behavior currently implemented:

- `scene_repair_handler` records structured repairs for antenna height, azimuth normalization,
  and sector-count/azimuth mismatch.
- `asset_fallback_handler` selects validated compatible fallback assets and returns to
  requirement validation when fallback succeeds.

## Routing

- Missing requirements route to `missing_data_handler`.
- Asset selection errors route to `asset_fallback_handler`, then back to validation if repaired.
- Requirement validation failures route to `rule_violation_handler`.
- Scene repair events route to `scene_repair_handler`, then back to SceneSpec validation.
- Passed scene validation routes to `pre_blender_gate`.
- Failed pre-Blender gates route to `quality_gate_failure_handler` and block Blender.
- Blender fallback or failure routes to `blender_failure_handler`, then QA.
- QA failure routes to `qa_failure_handler`.
- Passed QA routes to `post_blender_gate`.
- Failed post-Blender gates route to `quality_gate_failure_handler`.
- Terminal routes go through `memory_writeback` when memory is configured.

## Trace

The API writes `workflow_trace.json` for every workflow. It contains:

- `workflow_id`
- `total_duration_ms`
- `steps`
- `route_history`
- `quality_gates`
- `glb_inspection`
- `geometry_validation`
- `preview_inspection`
- `metrics`

Each step contains:

- `node`
- `status`
- `detail`
- `duration_ms`
- `warnings`
- `errors`
- `route`
- `attempt`

`quality_gates` contains the serialized pre/post gate reports:

- `stage`
- `passed`
- `checks`
- `critical_errors`
- `warnings`
- `duration_ms`

For edit versions, `workflow_trace.json`, reports, GLB, preview, metadata, patch, diff, status, and
archive are written under that version's artifact directory. The root `status.json` points to the
active version.

## Fallback

- If memory is not configured, memory nodes are omitted.
- If Blender is missing, fallback artifacts are generated and QA still runs.
- If Qdrant is unavailable, RAG failure is traced and deterministic planning continues.
- If a quality gate fails, the workflow is failed explicitly and the gate report is written.
- A real Blender output must parse as GLB at the post-Blender gate.
- Fallback generation remains explicit and visible in trace, QA, and status.
- Edit fallback patching remains explicit in `scene_patch.json` and the API edit response.
- Asset import fallback is visible in `scene_metadata.json`, QA warnings, and API status through
  `asset_imports` and `asset_import_summary`.

## Future

- Add direct mutation of invalid SceneSpec drafts after construction.
- Add LOD-aware asset fallback ranking.
- Add policy-level route controls for retry limits.
- Add richer branch-specific repair handlers after quality gate failure.

## Known Limitations

- Strict Pydantic contracts mean several geometry repairs happen before SceneSpec construction,
  then are recorded in the graph as repair events.
- Asset fallback is conservative and only uses validated network-compatible assets.
- RAG and memory provide context only; they do not override deterministic rules.
- ScenePlanner only accepts structured `planning_hints` from RAG payloads for controlled planning
  changes. It no longer parses arbitrary retrieved text into scene dimensions/accessories.
- Current quality gates validate structure, rules, artifacts, geometry metadata, and QA metadata;
  they do not inspect visual aesthetics.
- Asset import routing is deterministic inside the Blender worker; the graph selects compatible
  manifests, and the worker records whether each placement became `imported_glb` or
  `procedural_fallback`.
