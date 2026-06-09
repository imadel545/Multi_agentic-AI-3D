# Memory

## Implemented

- Local SQLite memory is implemented in `core/memory/service.py`.
- Memory contracts are defined in `core/contracts/memory.py`.
- Workflow writeback stores compact metadata only:
  - `workflow_id`
  - `network_type`
  - `tower_type`
  - `sector_count`
  - `generation_mode`
  - `qa_score`
  - `warnings`
  - `scene_spec_path`
  - `validation_report_path`
  - `reusable_pattern`
  - `created_at`
- SQLite migration is local and additive. Missing columns are added with `ALTER TABLE`.
- Recall is strict for reusable examples:
  - same `network_type`
  - same `tower_type`
  - same `sector_count`
  - `qa_score >= 0.95`
  - `reusable_pattern = true`
- Qdrant runtime memory indexing writes to:
  - `design_memory`
  - `error_memory`
  - `document_pack_memory`
- Runtime memory collections are not included in `/rag/reindex`.
- Memory recall runs before planning when memory is configured.
- Memory writeback runs after successful or failed terminal reports when memory is configured.
- Scene planning reads memory issue history through the typed `error_patterns` key. The old
  `error_memory` key is not used by the planner.
- Successful edit revisions can write back compact version SceneSpec/report paths when memory is
  configured.
- Document packs write a compact `memory_summary.json` artifact, SQLite metadata rows, and optional
  Qdrant `document_pack_memory` runtime points.

## Stored Data

- `workflow_memory`: compact workflow metadata and paths to JSON reports.
- `design_memory`: compact SceneSpec and validation JSON for planned scenes.
- `error_memory`: validation warnings and errors by workflow/network/tower.
- `document_pack_memory`: compact pack metadata, categories, confirmed fields, QA score, source mode,
  corrections, conflicts, missing fields, and generated workflow id when available.
- `document_pack_issue_memory`: failed document-pack QA checks and issue patterns.
- Qdrant payloads contain compact memory metadata and issue metadata.
- Repair and asset fallback warnings are stored as compact validation warnings when they appear
  in the final report.
- Document-pack memory summaries contain compact pack/design fields, missing/conflict lists,
  processing capability status, and no large source files.

## Not Stored

These files are not stored durably in SQLite or Qdrant memory payloads by default:

- `design.glb`
- `preview.png`
- `artifacts.zip`

Large outputs remain in `outputs/temp`.

## API Surface

- `GET /memory/stats`
- `GET /document-packs/{pack_id}/memory-summary`
- Workflow status exposes:
  - `memory_hits`
  - `memory_context_count`
  - `metrics`
  - `trace_path`

## Fallback

- SQLite writeback continues if Qdrant indexing fails.
- Qdrant indexing errors are captured in `memory_writeback.index`.
- Document-pack SQLite writeback continues if Qdrant runtime indexing fails or is unavailable.
- RAG memory context does not override deterministic rules or validation.
- Memory can expose warnings such as previous RF azimuth spacing issues, but it only influences
  controlled planner flags and remains visible in trace/metrics.
- Document-pack writeback is non-blocking from the API perspective; failures are reported in QA and
  processing reports.

## Future

- Add TTL cleanup for old SQLite rows.
- Wire output folder cleanup into an explicit CLI/admin action.
- Add Qdrant server mode for concurrent API processes.
- Add deeper ranking of reusable patterns by design similarity.
- Use document-pack memory during future APD extraction prioritization and correction suggestions.

## Known Limitations

- SQLite is local and single-machine.
- Qdrant local mode can be locked by another running process.
- Some geometry repairs happen before strict SceneSpec construction, then are recorded as
  `RepairEvent` route history entries.
- Memory paths point to local filesystem artifacts; they are not a portable artifact store.
- Document-pack memory is indexed and counted, but the ScenePlanner does not yet recall
  `document_pack_memory` during normal design planning.
