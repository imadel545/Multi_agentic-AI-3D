# Frontend UX Flow

## Implemented

Primary studio flow:

1. User enters telecom requirements or uploads a document-pack ZIP.
2. Frontend calls the real backend.
3. Document panel shows detected documents, extraction status, fields, missing values and conflicts.
4. User can generate a design from requirements or a validated document pack.
5. Top bar shows workflow id, status, QA score, generation mode, warning/error counts.
6. Timeline shows workflow events through SSE or polling fallback.
7. GLB viewer loads `design.glb` through the backend artifact endpoint.
8. Inspector shows QA reports, quality gates, asset import modes, inventory, version history, diff,
   rollback and downloads.
9. Prompt edit calls `POST /designs/{workflow_id}/edit`, then invalidates status/events/versions.

The first screen is the usable studio, not a landing page.

## Available With Fallback

- Backend offline state is visible.
- Empty workflow state is visible and does not fake a generated result.
- Missing artifacts remain backend 404s; the UI does not claim they exist.

## Known Limitations

- Correction UI is wired at API level but the first visible form is still minimal; richer field-level
  correction controls are a next UI iteration.
- Diff is rendered from backend JSON summary, not a visual 3D before/after comparator yet.
- Download center lists expected artifacts; missing files are resolved by backend response.

## Future

- Add side-by-side GLB comparison for selected versions.
- Add object metadata inspector from `scene_metadata.json`.
- Add richer correction forms with typed field suggestions.
