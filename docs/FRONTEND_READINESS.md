# Frontend Readiness

## Implemented

The backend exposes the data needed for an advanced local-first frontend:

- `POST /designs` starts a workflow and writes pending status immediately.
- `GET /designs/{workflow_id}` returns active version status, artifacts, QA summaries, quality
  gates, LLM provider/fallback state, RAG/memory counts, event trace path, and asset import
  metadata.
- `GET /designs/{workflow_id}/events` returns the append-only workflow timeline.
- `GET /designs/{workflow_id}/events/stream` streams events with clean `404` behavior for unknown
  workflows and a bounded idle timeout.
- `POST /designs/{workflow_id}/edit` applies a prompt as a validated patch, generates a new
  version, reruns QA, and activates the version only when it passes.
- `GET /designs/{workflow_id}/versions` exposes version history, active flag, artifacts, QA score,
  generation mode, and diff summary.
- `POST /designs/{workflow_id}/versions/{version_id}/rollback` changes the active version without
  deleting history.
- `GET /assets/inventory` exposes GLB readiness and fallback state for every manifest.

## Asset Data Exposed

Workflow status includes:

- `asset_import_summary`
- `asset_imports`
- `artifacts.metadata` pointing to `scene_metadata.json`

Each asset import record reports:

- `asset_id`
- `asset_file`
- `asset_source`
- `object_role`
- `asset_file_exists`
- `asset_import_success`
- `asset_dimensions_checked`
- `import_mode`
- `effective_generation_mode`
- `warnings`

The frontend should render `internal_test_minimal` and `procedural_fallback` as visible
limitations, not as vendor-grade imported assets.

## Available With Fallback

- Groq `openai/gpt-oss-120b` extraction/editing can fall back to deterministic logic, and fallback
  state is visible.
- Blender can fall back to explicit non-GLB artifacts when missing or failing.
- Missing asset files can fall back to controlled procedural geometry only when the manifest allows
  it.

## Known Limitations

- Asset library is `partial_import_ready`: two internal minimal GLBs are present, but vendor tower,
  4G panel, and microwave dish GLBs are still missing.
- Preview inspection is structural/image-stat based, not semantic design judging.
- The API is synchronous for edit application. A separate preview-only edit workflow can be added
  later if the UI needs apply/reject before generation.
- Events are file-backed and local-first; they are suitable for one local frontend session, not a
  distributed multi-user stream.

## Future

- Add frontend viewer routes that serve artifacts by version without exposing raw filesystem paths.
- Add patch preview/apply endpoints if the UX needs non-committed edit previews.
- Add vendor asset provenance, pivot/mount-point metadata, and stricter imported-GLB dimension QA.
