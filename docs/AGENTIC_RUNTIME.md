# Agentic Runtime

## Implemented

The LangGraph runtime has explicit routing foundations:

- `missing_data_handler`
- `rule_violation_handler`
- `asset_fallback_handler`
- `scene_repair_handler`
- `pre_blender_gate`
- `blender_failure_handler`
- `qa_failure_handler`
- `post_blender_gate`
- `quality_gate_failure_handler`

Centralized quality gates are implemented in `core/validation/quality_gates.py`.

Prompt edits use the same deterministic validation/QA stack through
`DesignOrchestrator.run_scene_revision`. The revision path does not re-extract requirements from
free text and does not ask the LLM to write Blender code. It starts from the patched `SceneSpec`,
derives controlled requirements, reruns Rule/Tower/RF validation, pre/post quality gates, Blender,
GLB inspection, geometry validation, preview inspection, and memory writeback when configured.

Document-pack intelligence now has a dedicated LangGraph orchestrator:

```text
index
-> extract_pdf_ocr_cad
-> groq_extract
-> consolidate
-> qa
-> write_artifacts
-> memory_writeback
```

`DocumentPackService` remains the API/storage facade. The graph produces `trace.json` and
`events.json` for frontend timeline display.

Pack-to-design generation now uses `ProjectDesignSpec -> RequirementSpec` directly through
`WorkflowService.create_design_from_requirements()` and `DesignOrchestrator.run_requirements()`.
It does not reparse a generated prompt.

`pre_blender_gate` checks:

- extracted requirements are valid
- business rules passed
- assets are selected, validated, and compatible
- SceneSpec contract and validation report passed
- repair attempts are within `max_repair_attempts`
- no critical upstream validation errors exist

`post_blender_gate` checks:

- generation mode is explicit
- model, preview, and metadata artifacts exist
- real Blender model output is not trivially small
- GLB structural inspection passed
- expected 3D objects are present
- minimum GLB node count is valid
- real Blender outputs parse as GLB
- geometry validation passed
- preview PNG resolution is valid
- QA score is at least `0.95`
- no error-severity QA warning remains

`scene_repair_handler` now records real controlled repairs from structured `RepairEvent`
objects emitted during deterministic requirement normalization:

- antenna install height capped below tower height
- azimuths normalized into `[0, 360)`
- sector-count/azimuth mismatch repaired by standard distribution or truncation

`asset_fallback_handler` now selects validated compatible fallback assets when exact selection
fails.

Workflow state includes:

- `max_repair_attempts = 2`
- `repair_attempts`
- `route_history`
- `quality_gate_reports`
- `glb_inspection`
- `geometry_validation`
- `preview_inspection`
- asset import metadata through generated `scene_metadata.json` and API status
- `requirements_hash`
- `scene_spec_hash`
- `asset_manifest_hash`
- `knowledge_index_hash`
- cache hit/miss metrics

Edit/version events include `version_id` in their payload when a version is involved.

Trace steps include:

- `node`
- `status`
- `detail`
- `duration_ms`
- `warnings`
- `errors`
- `route`
- `attempt`

## Routing

- Missing extracted requirements route to `missing_data_handler`.
- Asset selection failures route to `asset_fallback_handler`.
- Requirement rule failures route to `rule_violation_handler` and do not run Blender.
- Scene validation failures route to `scene_repair_handler` until repair attempts are exhausted.
- Passed scene validation routes to `pre_blender_gate`.
- Failed pre-Blender quality gates route to `quality_gate_failure_handler` and do not run Blender.
- Blender fallback or failure routes to `blender_failure_handler`, then QA validates artifacts.
- QA failure routes to `qa_failure_handler`, then memory writeback records the failed report.
- Passed QA routes to `post_blender_gate`.
- Failed post-Blender quality gates route to `quality_gate_failure_handler`.
- Structural GLB, geometry, and preview reports are attached during `qa_generation`.

## Fallback

- Blender fallback is explicit and still goes through QA.
- Asset fallback only selects assets with `status=validated` and compatible network type.
- Asset import fallback is separate from asset selection fallback: a selected manifest can still use
  `procedural_fallback` when its GLB file is missing and the manifest allows fallback.
- Groq edit patching fallback is explicit through `edit_llm_provider` and
  `edit_llm_fallback_used` in the patch/result.
- Scene repair is bounded by `max_repair_attempts`.
- Quality gates fail closed. A failed pre-Blender gate blocks generation.
- Non-GLB fallback artifacts use explicit `metadata_fallback` inspection mode.
- Geometry validation warnings remain visible in QA reports and quality gate details.

## Future

- Expand SceneSpec repair to mutate already-built SceneSpec drafts directly.
- Add richer LOD/ranking policy for asset fallback.
- Add policy controls for max repair attempts per route type.
- Add per-gate policy overrides for lower-risk development scenarios.
- Add a separate preview-only edit endpoint if the frontend needs non-committed patch previews.

## Known Limitations

- Scene repair currently applies before strict SceneSpec construction because Pydantic contracts
  reject invalid geometry.
- Corrective routes are deterministic and conservative.
- No handler can bypass rule validation.
- Revision orchestration is a controlled service path that reuses deterministic validators and QA.
- Document-pack orchestration is graph-based but synchronous; async/SSE can be added if ingestion
  becomes long-running.
- Quality gate checks are local contract/artifact checks, not visual semantic inspection.
- Geometry validation checks object counts, sector object presence, tower/antenna heights, azimuth
  metadata, and bounding-box reasonableness. Exact transform/material parsing remains future work.
- Asset import QA validates metadata modes and visibility, not vendor-grade mesh quality yet.
