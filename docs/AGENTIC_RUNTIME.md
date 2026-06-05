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
- `requirements_hash`
- `scene_spec_hash`
- `asset_manifest_hash`
- `knowledge_index_hash`
- cache hit/miss metrics

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
- Scene repair is bounded by `max_repair_attempts`.
- Quality gates fail closed. A failed pre-Blender gate blocks generation.
- Non-GLB fallback artifacts use explicit `metadata_fallback` inspection mode.
- Geometry validation warnings remain visible in QA reports and quality gate details.

## Future

- Expand SceneSpec repair to mutate already-built SceneSpec drafts directly.
- Add richer LOD/ranking policy for asset fallback.
- Add policy controls for max repair attempts per route type.
- Add per-gate policy overrides for lower-risk development scenarios.

## Known Limitations

- Scene repair currently applies before strict SceneSpec construction because Pydantic contracts
  reject invalid geometry.
- Corrective routes are deterministic and conservative.
- No handler can bypass rule validation.
- Quality gate checks are local contract/artifact checks, not visual semantic inspection.
- Geometry validation checks object counts, sector object presence, tower/antenna heights, azimuth
  metadata, and bounding-box reasonableness. Exact transform/material parsing remains future work.
