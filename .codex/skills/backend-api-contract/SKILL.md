---
name: backend-api-contract
description: Use when changing frontend/backend boundaries for the Agentic Telecom 3D Studio. Ensures React consumes stable FastAPI endpoints, artifact URLs, SSE/polling, document-pack data, versions, rollback, QA, and asset import metadata without guessing filesystem paths.
---

# Backend API Contract

Use this skill whenever a UI or backend change touches API responses, artifact URLs, workflow state,
events, versions, document packs, QA, or assets.

## Rules

- The frontend must not infer local file paths. Use backend endpoints and whitelisted artifact routes.
- API errors must be visible and typed enough for the studio UI to explain the failure.
- A completed workflow should expose status, active version, QA summaries, asset imports, warnings,
  events, and download/artifact URLs.
- A failed workflow must not be auto-selected over a completed workflow unless the user chooses it.
- SSE can fall back to polling, but the fallback must be visible in the timeline/status surface.

## Data Surfaces To Preserve

- `GET /health`
- `GET /designs`, `POST /designs`, `GET /designs/{workflow_id}`
- `GET /designs/{workflow_id}/events`, `/events/stream`
- `POST /designs/{workflow_id}/edit`
- `GET /designs/{workflow_id}/versions`, rollback endpoint
- `GET /designs/{workflow_id}/artifacts/{artifact_name}`
- `GET /assets/inventory`
- document-pack list, bundle, corrections, and generate-design endpoints

## Validation

- For frontend-only changes, run typecheck, tests, build, and browser smoke.
- For backend contract changes, also run backend pytest, ruff check, and format check.
- Verify one real completed workflow and one missing/failed artifact state.
