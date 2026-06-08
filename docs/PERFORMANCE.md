# Performance

## Implemented

Workflow trace metrics include:

- `total_workflow_duration_ms`
- `rag_duration_ms`
- `planning_duration_ms`
- `blender_duration_ms`
- `qa_duration_ms`
- `memory_duration_ms`
- `memory_hits`
- `memory_context_count`
- `artifact_size_bytes`
- `geometry_validation_passed`
- `geometry_missing_objects`
- `geometry_critical_errors`
- `requirements_hash`
- `scene_spec_hash`
- `asset_manifest_hash`
- `knowledge_index_hash`
- `asset_cache_hits`
- `asset_cache_misses`
- `rag_cache_hits`
- `rag_cache_misses`
- `cache_hits`
- `cache_misses`

Compatibility fields are still present:

- `total_duration_ms`
- `generation_duration_ms`
- per-artifact byte counts such as `glb_bytes`, `preview_bytes`, and `metadata_bytes`

## Measurement Sources

- RAG duration comes from `retrieve_rag_context`.
- Planning duration includes asset selection, requirement validation, scene planning,
  scene validation, and corrective planning handlers.
- Blender duration uses `GenerationResult.duration_ms` when generation runs.
- QA duration includes generation QA and QA failure handling.
- Memory duration includes recall and writeback.
- Artifact size is the sum of generated artifact paths that exist on disk.
- Edit revisions emit the same metrics for their version artifact directory.
- Geometry validation metrics are emitted when `qa_generation` runs.
- Repair and asset fallback handler durations are included in `planning_duration_ms`.
- Requirement and SceneSpec hashes are canonical JSON SHA-256 hashes.
- Asset manifest hash is based on all JSON manifests under `assets/manifests`.
- Knowledge index hash is based on markdown knowledge sources under `data/knowledge` and `docs`.
- RAG cache keys include query, limit, collection, filters, embedding provider, and knowledge hash.

## Cache

Implemented cache surfaces:

- Asset registry manifest cache with hash-based invalidation.
- RAG query TTL cache with default 30 second TTL.
- Runtime memory collections (`design_memory`, `error_memory`) are not query-cached, and runtime
  memory upserts clear the RAG query cache.
- `core/services/cleanup_service.py` can remove old managed workflow folders named
  `wf_<12 hex>` under the configured outputs directory.
- API workflow deletion uses `CleanupService.delete_workflow()` so only managed workflow folders
  under the output root are removed.
- FastAPI shutdown closes the Qdrant client explicitly through `RagService.close()`.

The cache does not bypass validation. Requirement rules, SceneSpec validation, quality gates,
Blender execution, QA, and memory writeback still run on each workflow.

## Fallback

- Missing Blender still reports fallback generation duration.
- Missing RAG service reports zero RAG results and a skipped or failed RAG trace step.
- Failed Qdrant memory indexing is reported in memory writeback but does not fail the workflow.
- Expired or invalidated cache entries are treated as misses.
- Cleanup skips symlinks, non-workflow folders, and paths outside the configured output root.
- Qdrant client shutdown is explicit to avoid local-client destructor noise.

## Future

- Add p95/p99 aggregation across workflows.
- Add SQLite query timings.
- Add Qdrant indexing duration split from SQLite writeback duration.
- Add cache eviction metrics and bounded cache size.

## Known Limitations

- Metrics are local process timings, not distributed tracing.
- Qdrant local lock contention appears as RAG or memory indexing errors.
- File size metrics only include artifacts known to `GenerationResult`.
- Asset import counts are exposed in status/metadata, but they are not aggregated into long-term
  performance metrics yet.
- The RAG cache is process-local.
- The asset cache re-hashes manifest files before reuse.
- Cleanup is implemented as a service and tests, but is not scheduled automatically.
- Version artifacts increase local disk use per edit. Retention policy remains manual/local for now.
