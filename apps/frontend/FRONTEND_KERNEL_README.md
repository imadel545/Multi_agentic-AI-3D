# Frontend Product Rework

This app is a real-backend React/Three.js studio shell in progress. It is not an
accepted product gate until a visual smoke proves the full user flow.

The rejected pattern is fixed dashboard UI: permanent topbar badges, fixed tab
grids, raw JSON as the main surface, and a form pretending to be chat. The active
direction is:

- conversation-first command for prompt and document-pack intake;
- dominant 3D viewer using backend GLB artifacts only;
- narrative agent progress and current operation;
- contextual drawers for QA, warnings, artifacts, RAG, runtime, and versions;
- visible degraded/fallback states without inventing product data.

## Contract

The frontend consumes the existing FastAPI v1 surface:

- `GET /health`
- `GET /studio/summary`
- `GET /assets/inventory`
- `GET /document-packs/capabilities`
- `POST /document-packs`
- `POST /document-packs/{pack_id}/generate-design`
- `GET /designs`
- `POST /designs`
- `GET /designs/{workflow_id}`
- `GET /designs/{workflow_id}/events`
- `GET /designs/{workflow_id}/events/stream`
- `GET /designs/{workflow_id}/viewer-bundle`
- `GET /designs/{workflow_id}/timeline-summary`
- `GET /designs/{workflow_id}/current-operation`
- `GET /designs/{workflow_id}/user-issues`
- `GET /designs/{workflow_id}/versions`
- `POST /designs/{workflow_id}/edit`

`/designs + workflow_id` remains the source of truth. Labels such as project,
run, or scene plan are UI language only.

## Run

Start the backend from the repository root:

```bash
.venv/bin/python -m uvicorn apps.api.telecom_studio_api.main:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
cd apps/frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`.

`VITE_API_BASE_URL` can override the backend URL. The default is
`http://127.0.0.1:8000`.

## Anti-Fake Rules

- No permanent mock product data.
- Every backend payload is validated with Zod before UI use.
- Public payloads are rejected if they expose `/Users/`, `artifact_dir`,
  `resolved_path`, `filesystem_path`, or `local_path`.
- The viewer loads only `viewerBundle.primary_glb_url`.
- If GLB is absent, load fails, WebGL is unavailable, or the render probe
  detects a non-visible canvas, the UI shows backend preview or an explicit
  degraded/error state.
- RAG evidence is shown only when the backend provides the artifact.
- SSE failure activates visible polling fallback.
- Unsupported actions from the backend must not become buttons.

## Current Limits

- This is still a frontend product rework, not the final premium UI.
- Document-pack intake accepts direct multi-file upload or ZIP and follows the
  existing backend limits.
- Edit by prompt and rollback are available only when the backend advertises
  their actions for the active completed workflow. Both reuse the durable event
  cursor and fall back visibly to polling if live SSE cannot resume.
- No WebSocket, auth, cloud, project entity, run entity, or new backend store.
- Viewer material visibility may be strengthened client-side for inspection,
  without mutating the backend GLB.

## Checks

```bash
npm run typecheck
npm run test -- --run
npm run build
npm audit --omit=optional
```

Manual smoke:

1. Confirm backend health and studio summary load.
2. Submit the critical 5G telecom prompt.
3. Receive a `workflow_id`.
4. Observe SSE events or visible polling fallback.
5. Reach `completed`, `failed`, or `degraded`.
6. Confirm the viewer shows a visible GLB, or an explicit preview/error fallback.
7. Open drawers for QA, Warnings, Artifacts, RAG, Runtime, and Versions.
8. Confirm warnings are grouped and readable, not raw backend code as the main UI.
9. Confirm no `/Users/` path appears in UI or validated payloads.
10. Capture or pixel-check the viewer area; a blank white canvas without explicit
    fallback is a failure.
