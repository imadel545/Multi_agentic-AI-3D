# Frontend API Mapping

## Implemented

The frontend client in `apps/frontend/src/api/client.ts` maps these backend endpoints:

- `GET /health`
- `GET /designs`
- `POST /designs`
- `GET /designs/{workflow_id}`
- `GET /designs/{workflow_id}/events`
- `GET /designs/{workflow_id}/events/stream`
- `POST /designs/{workflow_id}/edit`
- `GET /designs/{workflow_id}/versions`
- `POST /designs/{workflow_id}/versions/{version_id}/rollback`
- `GET /designs/{workflow_id}/artifacts/{artifact_name}`
- `GET /assets/inventory`
- `GET /document-packs`
- `POST /document-packs`
- `GET /document-packs/{pack_id}`
- `GET /document-packs/{pack_id}/documents`
- `GET /document-packs/{pack_id}/extractions`
- `GET /document-packs/{pack_id}/consolidated-spec`
- `GET /document-packs/{pack_id}/conflicts`
- `GET /document-packs/{pack_id}/missing-fields`
- `GET /document-packs/{pack_id}/qa`
- `GET /document-packs/{pack_id}/processing`
- `GET /document-packs/{pack_id}/trace`
- `GET /document-packs/{pack_id}/events`
- `GET /document-packs/{pack_id}/memory-summary`
- `POST /document-packs/{pack_id}/corrections`
- `POST /document-packs/{pack_id}/generate-design`

The artifact endpoint accepts whitelisted artifact names only:

- `glb`
- `preview`
- `scene_spec`
- `metadata`
- `qa_report`
- `geometry_validation`
- `quality_gates`
- `trace`
- `download`
- plus technical reports such as `validation_report`, `glb_inspection`, `scene_patch`, `scene_diff`.

`version_id` is optional. Without it, the backend serves the active workflow artifact.

## Available With Fallback

- Design timeline uses SSE first, polling second.
- Frontend upload sends raw ZIP bytes with `x-filename`, matching the current backend contract.
- Artifact links do not check existence client-side; backend response is the source of truth.

## Known Limitations

- There is no multipart upload metadata contract yet.
- There is no document-pack SSE endpoint yet.
- There is no preview-only edit endpoint.

## Future

- Add OpenAPI schema export and client generation.
- Add version-scoped artifact metadata endpoint if the UI needs richer file availability before link
  rendering.
