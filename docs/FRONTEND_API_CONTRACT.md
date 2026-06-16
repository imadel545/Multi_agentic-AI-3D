# Frontend API Contract

This is the frontend-facing contract for the next chat-first / 3D-first UI.
It preserves the existing backend vocabulary.

## Canonical Concepts

| Frontend concept | Backend contract |
|---|---|
| Design / generation run | `workflow_id` |
| Scene plan | `scene_spec` artifact (`scene_spec.json`) |
| Live progress | `/designs/{workflow_id}/events/stream` |
| Timeline drawer | `/designs/{workflow_id}/timeline-summary` |
| Viewer data | `/designs/{workflow_id}/viewer-bundle` |
| QA/issues drawer | `/user-summary` and `/user-issues` |
| Artifact panel | `/designs/{workflow_id}/artifacts/{name}` |

No `/projects` or `/runs` API is added in v1. If the frontend wants "project"
or "run" labels, they are UI labels mapped to existing backend concepts.

## Required Endpoints

- `POST /designs`
- `GET /designs/{workflow_id}`
- `GET /designs/{workflow_id}/events`
- `GET /designs/{workflow_id}/events/stream`
- `GET /designs/{workflow_id}/viewer-bundle`
- `GET /designs/{workflow_id}/timeline-summary`
- `GET /designs/{workflow_id}/current-operation`
- `GET /designs/{workflow_id}/user-summary`
- `GET /designs/{workflow_id}/user-issues`
- `GET /designs/{workflow_id}/artifacts/{name}`
- `GET /designs/{workflow_id}/versions`
- `POST /designs/{workflow_id}/edit`
- `POST /designs/{workflow_id}/versions/{version_id}/rollback`

## Frontend Startup Sequence

1. Call `GET /health`.
   - Show backend online/offline in the top bar.
2. Call `GET /studio/summary`.
   - Show global readiness: `blender_available`, `groq_available`,
     `asset_inventory_status`, `missing_file_count`, and warnings.
3. Call `GET /assets/inventory`.
   - Keep asset quality visible in an Assets drawer, not as a main dashboard.
4. Call `GET /document-packs/capabilities`.
   - Configure the upload affordance and show local limits honestly.
5. Call `GET /designs`.
   - Restore recent local designs, but do not auto-select a failed design over a
     completed one unless the user chooses it.

## Prompt Generation Flow

1. User sends a chat prompt.
2. Frontend calls `POST /designs` with:

```json
{
  "requirements_text": "Créer un site 5G...",
  "options": {
    "detail_level": "high",
    "use_llm": null
  }
}
```

3. Backend returns `{ "workflow_id": "...", "status": "pending" }`.
4. Frontend immediately subscribes to
   `GET /designs/{workflow_id}/events/stream`.
5. Frontend also polls `GET /designs/{workflow_id}/current-operation` if SSE is
   unavailable or disconnected. The UI must label this as a fallback.
6. When a terminal event arrives, load:
   - `GET /designs/{workflow_id}`
   - `GET /designs/{workflow_id}/viewer-bundle`
   - `GET /designs/{workflow_id}/timeline-summary`
   - `GET /designs/{workflow_id}/user-issues`
   - `GET /designs/{workflow_id}/versions`

## Event Stream Consumption

Use `/events/stream` as the primary live source during an active workflow.
The frontend should render these events as a compact agent-progress strip, not
as raw logs.

Important event types:

| Event type | UI meaning |
|---|---|
| `design_created` | New generation accepted |
| `node_started` | Current agent/stage started |
| `node_completed` | Stage completed |
| `node_failed` | Stage failed or degraded |
| `node_skipped` | Stage intentionally skipped |
| `artifact_ready` | Viewer artifacts can be loaded |
| `qa_completed` / `qa_failed` | Validation drawer can be updated |
| `user_issue_created` | Add readable issue/warning |
| `workflow_completed` | Stop streaming; load viewer bundle |
| `workflow_failed` | Stop streaming; show repair/retry path |

Display fields:

- Primary label: `payload.human_label`.
- Secondary text: `payload.progress_message`.
- Phase badge: `payload.phase`.
- Technical detail drawer only: `payload.node`, `payload.duration_ms`,
  `payload.warnings`, `payload.errors`, `payload.artifact_refs`.

The frontend must not show Python node names as the main UX.

## State Handling

| Backend status | UI behavior |
|---|---|
| `pending` | Show queued state, disable duplicate submit for that prompt, connect SSE |
| `running` | Show current operation, agent strip, cancel unavailable/not implemented |
| `completed` | Load viewer bundle, display 3D, QA summary, artifacts and edit actions |
| `failed` | Do not load fake viewer; show user issues, timeline, retry/edit prompt path |

Rules:

- `completed` is not equal to perfect. Still show warnings, `mesh_qa_level`,
  `generation_mode`, asset import summary, and limitations.
- `failed` must keep the chat usable and offer a corrected prompt or document
  correction path.
- If SSE drops, switch to polling `current-operation` and `events`; show that
  realtime is degraded.

## Viewer Loading

Use `GET /designs/{workflow_id}/viewer-bundle` as the only source for viewer
URLs.

Required fields:

- `primary_glb_url`: load in the Three.js/R3F viewer.
- `preview_url`: show while GLB loads or if GLB fails.
- `scene_spec_url`: scene-plan drawer.
- `qa_report_url`: QA drawer.
- `generation_report_url`: generation details drawer.
- `geometry_validation_url`: geometry checks drawer.
- `metadata_url`: object/asset metadata drawer.
- `viewer_artifacts[]`: download/availability list.

Viewer rules:

- Only load GLB from `primary_glb_url`.
- If `primary_glb_url` is missing or unavailable, show a clear non-3D state.
- If `generation_mode` is not `real_blender`, show degraded status.
- If `mesh_qa_passed` is false, keep the viewer visible only with a validation
  warning; do not present the model as final.
- Use `active_version` and versioned artifact URLs exactly as returned. Do not
  construct filesystem paths.

## Validation Display

Main QA summary comes from `viewer-bundle.qa_summary` and
`GET /designs/{workflow_id}/user-issues`.

Display:

- `qa_score`
- `mesh_qa_level`
- `mesh_qa_passed`
- `checks_passed`
- `checks_failed`
- `geometry_source`
- `generation_strategy`
- `object_counts`
- `missing_objects`
- `limitations`

Language rule:

- Say "QA géométrique basique" for `mesh_level_basic`.
- Do not say "advanced geometry QA".
- Explain that collision, RF propagation, structural wind/load and exact
  per-antenna vertex-level HBA/azimuth are not implemented.

## Artifact Mapping

| UI label | Artifact name | File |
|---|---|---|
| Scene plan | `scene_spec` | `scene_spec.json` |
| 3D model | `glb` | `design.glb` |
| Preview | `preview` | `preview.png` |
| Metadata | `metadata` | `scene_metadata.json` |
| QA report | `qa_report` | `qa_report.json` |
| Geometry validation | `geometry_validation` | `geometry_validation.json` |
| Generation data | `generation_report` | `generation_report.json` |
| Technical report | `technical_report` | `technical_report.md` |
| Download bundle | `download` | `artifacts.zip` |

The UI may label `scene_spec` as "scene plan", but `SceneSpec` remains the
source of truth.
Public `path` values are API URLs only. The frontend must never depend on local
paths such as `/Users/...`.

## Document-Pack Flow

1. Call `GET /document-packs/capabilities`.
2. Upload ZIP with `POST /document-packs`.
3. Display:
   - `GET /document-packs/{pack_id}`
   - `GET /document-packs/{pack_id}/qa`
   - `GET /document-packs/{pack_id}/conflicts`
   - `GET /document-packs/{pack_id}/missing-fields`
   - `GET /document-packs/{pack_id}/provenance`
4. If corrections are needed, call
   `POST /document-packs/{pack_id}/corrections`.
5. When ready, call `POST /document-packs/{pack_id}/generate-design`.
6. The returned `workflow_id` enters the same `/designs` flow.

Document-pack UI must show limitations: synchronous local processing, limited
OCR/DXF/DWG truth, Docling import-only by default.

## Edit / Version / Rollback Flow

- Edit prompt: `POST /designs/{workflow_id}/edit`.
- On `edit_status=applied`, load:
  - `viewer_bundle_url`
  - `timeline_url`
  - `user_issues_url`
  - `current_operation_url`
- Versions drawer: `GET /designs/{workflow_id}/versions`.
- Rollback: `POST /designs/{workflow_id}/versions/{version_id}/rollback`.
- After rollback, reload `viewer-bundle`, `timeline-summary`, `user-issues`,
  and `versions`.

The frontend must not maintain a separate active version state beyond what the
backend returns.

## UX Structure

First viewport:

- Left: chat command rail with prompt, document upload, current operation,
  latest user-readable issues.
- Right: large 3D viewer using the active GLB.
- Top: compact status strip with backend, generation mode, QA, active version,
  Blender/Groq/fallback indicators.
- Drawers: Timeline, QA, Scene Plan, Documents, Assets, Versions, Technical.

Avoid:

- dashboard grids,
- raw JSON as main panels,
- permanent empty panes,
- fake placeholder GLB,
- frontend-invented workflow states.

## Event Contract

Every event must expose:

- `event_id`
- `workflow_id`
- `timestamp`
- `event_type`
- `event_source`
- `payload.node`
- `payload.phase`
- `payload.status`
- `payload.human_label`
- `payload.progress_message`
- `payload.duration_ms`
- `payload.warnings`
- `payload.errors`
- `payload.artifact_refs`

`/events/stream` is local-process `push_sse`: JSONL replay, then live queue
events until `workflow_completed` or `workflow_failed`.

## Frontend Rule

The frontend must use product endpoints for primary UI. It may open raw JSON
artifacts only in secondary technical drawers.
