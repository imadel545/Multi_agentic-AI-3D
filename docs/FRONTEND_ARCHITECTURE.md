# Frontend Architecture

## Implemented

The frontend lives in `apps/frontend` and is a Vite + React + TypeScript application.

Structure:

- `src/api`: typed backend client, TanStack Query hooks, artifact URL helpers.
- `src/app`: studio shell, top bar, bottom dock.
- `src/features/agent-console`: command center, generation/edit commands, quick prompts, agent-stage
  lanes and timeline.
- `src/features/document-pack`: pack list, document inventory, extracted fields, missing/conflicts.
- `src/features/three-viewer`: lazy-loaded React Three Fiber GLB viewer with artifact error boundary
  and tower-oriented initial fit.
- `src/features/qa-panel`: QA, compact issues, asset imports, versions, diff, rollback, downloads.
- `src/stores`: Zustand UI state for active workflow, active pack, selected version/object, tabs and
  viewer toggles.

State split:

- TanStack Query owns server state: health, designs, workflow status, events, versions, packs, assets.
- Zustand owns local interaction state: active ids, selected object/version, inspector tab, dock tab,
  viewer layers.

The frontend does not embed static design results. It calls the FastAPI backend and shows explicit
offline/empty states when data is not available.

## Available With Fallback

- Workflow events use `EventSource` for `/designs/{workflow_id}/events/stream`; if SSE fails, the
  UI falls back to polling `/designs/{workflow_id}/events`.
- The GLB viewer is lazy-loaded so initial app chrome does not block on Three.js.
- Missing artifacts are linked through backend artifact routes and surface backend `404` instead of
  guessing local filesystem paths.
- A missing GLB now renders an explicit viewer error state instead of taking down the canvas.

## Known Limitations

- The Three.js viewer chunk remains large because `three`, `@react-three/fiber`, and `drei` are
  loaded together when the viewer activates.
- Document-pack ingestion is synchronous backend-side, so the frontend shows post-processing trace
  and events rather than live document-pack SSE.
- Prompt edit is apply-and-generate. There is no non-committed patch preview endpoint yet.
- Object metadata selection is based on GLB object names; deeper semantic picking can be added from
  `scene_metadata.json`.
- The current command log is browser-session local; durable command history would need backend
  persistence or workflow events for user-issued commands.

## Future

- Add route-level splitting if the studio grows beyond one app shell.
- Add a generated OpenAPI TypeScript client once backend schemas stabilize.
- Add Playwright E2E tests for upload -> generate -> edit -> rollback.
