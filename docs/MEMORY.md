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
- Runtime memory collections are not included in `/rag/reindex`.

## Stored Data

- `workflow_memory`: compact workflow metadata and paths to JSON reports.
- `design_memory`: compact SceneSpec and validation JSON for planned scenes.
- `error_memory`: validation warnings and errors by workflow/network/tower.
- Qdrant payloads contain compact memory metadata and issue metadata.
- Repair and asset fallback warnings are stored as compact validation warnings when they appear
  in the final report.

## Not Stored

These files are not stored durably in SQLite or Qdrant memory payloads by default:

- `design.glb`
- `preview.png`
- `artifacts.zip`

Large outputs remain in `outputs/temp`.

## API Surface

- `GET /memory/stats`
- Workflow status exposes:
  - `memory_hits`
  - `memory_context_count`
  - `metrics`
  - `trace_path`

## Fallback

- SQLite writeback continues if Qdrant indexing fails.
- Qdrant indexing errors are captured in `memory_writeback.index`.
- RAG memory context does not override deterministic rules or validation.

## Future

- Add TTL cleanup for old SQLite rows and old output folders.
- Add Qdrant server mode for concurrent API processes.
- Add deeper ranking of reusable patterns by design similarity.

## Known Limitations

- SQLite is local and single-machine.
- Qdrant local mode can be locked by another running process.
- Some geometry repairs happen before strict SceneSpec construction, then are recorded as
  `RepairEvent` route history entries.
