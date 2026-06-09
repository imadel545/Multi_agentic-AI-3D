# Frontend API Mapping

## Implemented

| Frontend surface | Backend data |
| --- | --- |
| Top bar | `GET /health`, `GET /designs/{workflow_id}` |
| Workflow selection | `GET /designs` with completed-workflow preference |
| Agent Command Center | `POST /designs`, `POST /designs/{workflow_id}/edit`, `POST /document-packs`, `POST /document-packs/{pack_id}/generate-design`, workflow events |
| 3D Design Stage | `/designs/{workflow_id}/artifacts/glb`, `/preview`, `/metadata` |
| Scene object rail | `scene_metadata.json.asset_imports` plus workflow `asset_imports` fallback |
| Smart Inspector QA | workflow `quality_gates`, QA summaries, warnings/errors |
| Smart Inspector assets | `GET /assets/inventory`, workflow `asset_imports` |
| Versions | `GET /designs/{workflow_id}/versions`, rollback endpoint |
| Diff | selected version `diff_summary` |
| Downloads | artifact endpoint whitelist |
| Document Intelligence Dock | document-pack list, bundle endpoints, correction endpoint |
| Events Dock | workflow events or document-pack events, grouped by `eventPresenter` |

## Available With Fallback

- `useArtifactJson` reads whitelisted JSON artifacts through the same artifact endpoint used by
  downloads. Missing JSON returns a visible query error instead of local file guessing.
- SSE helper still exists for `/events/stream`, while normal polling remains available through
  TanStack Query.
- Unknown warnings/events are humanized with a safe fallback but keep raw detail collapsed.

## Known Limitations

- The frontend does not yet use a generated OpenAPI client. Types are manually maintained in
  `src/api/types.ts`.
- Some artifact names are conventional strings (`metadata`, `scene_spec`, `geometry_validation`).
  Backend changes must keep those names stable or update the client.
- Document-pack generate still depends on backend readiness flags; frontend does not bypass missing
  fields.

## Future

- Generate TypeScript types from the FastAPI OpenAPI schema.
- Add explicit backend endpoint for selected object details if SceneSpec/metadata mapping becomes
  richer than artifact JSON.
