# Frontend Audit

## Implemented

Runtime audit was performed before the reset:

- Backend `GET /health` returned `{"status":"ok","version":"0.2.0"}`.
- Frontend Vite served `http://127.0.0.1:5173`.
- In-app Browser was attempted first, but the tab stayed in a crashed `This page crashed` state and
  could not navigate to localhost.
- Google Chrome headless was used as fallback for screenshots at `1440x900`.

Confirmed pre-reset issues:

| Finding | Risk | Action taken |
| --- | --- | --- |
| Layout still read as a developer dashboard. | User could not understand the product flow. | Replaced fixed grid with resizable studio shell: command center, 3D stage, smart inspector, intelligence dock. |
| Command center exposed raw `edit_patch_rejected` and JSON-like payloads. | Agentic workflow felt like logs, not conversation. | Added conversation messages, command modes, quick actions, action summaries, and user-facing error explanations. |
| Viewer could be visually blank in headless/WebGL screenshot. | Validation evidence and first impression were weak. | Added stronger GLB stage controls plus a real `preview.png` card labeled as a Blender preview artifact fallback. |
| Warnings exposed backend codes directly. | Non-developer users could not judge impact or next action. | Added `issuePresenter` and `WarningCard` with title, impact, action, and collapsible technical detail. |
| Timeline was a raw event list. | Agentic flow was not readable. | Added `eventPresenter` and grouped narrative phases. |
| Document intelligence dock had weak empty states and little provenance context. | User did not know how documents affect generation. | Added pack metrics, extraction source labels, missing/conflict UX, correction form, and generate-from-pack action. |

## Available With Fallback

- Browser plugin remains preferred for visual validation. When it crashes, Chrome headless is used
  and the exact fallback is reported.
- WebGL screenshots can still show an empty canvas under headless Chrome; the UI now also exposes a
  real Blender preview artifact so evidence is not visually empty.
- SSE remains the intended timeline path; polling is still available through existing query hooks.

## Known Limitations

- The GLB viewer is still limited by the actual asset library and Blender composition. The UI now
  reports internal/minimal/non-vendor assets instead of hiding the limitation.
- The preview fallback is an image artifact, not the interactive GLB. It is explicitly labeled.
- Full browser interaction proof for upload -> generate -> edit -> rollback still needs a dedicated
  Playwright E2E workflow or a working Browser plugin session.
- Mobile/tablet layout remains secondary; this reset targets desktop studio use.

## Future

- Add committed Playwright E2E once the frontend/backend smoke path is stable enough for CI.
- Add backend object metadata endpoints if semantic picking needs more than `scene_metadata.json`.
- Improve Blender camera/preview composition so the generated preview itself is more premium.
