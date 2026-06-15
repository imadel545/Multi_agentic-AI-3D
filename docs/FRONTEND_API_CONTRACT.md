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

## Artifact Mapping

| UI label | Artifact name | File |
|---|---|---|
| Scene plan | `scene_spec` | `scene_spec.json` |
| 3D model | `glb` | `design.glb` |
| Preview | `preview` | `preview.png` |
| QA report | `qa_report` | `qa_report.json` |
| Geometry validation | `geometry_validation` | `geometry_validation.json` |
| Generation data | `generation_report` | `generation_report.json` |
| Technical report | `technical_report` | `technical_report.md` |

Public `path` values are API URLs only. The frontend must never depend on local
paths such as `/Users/...`.

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
