# Frontend Architecture

## Implemented

The frontend is a Vite + React + TypeScript desktop studio under `apps/frontend`.

Current structure:

- `src/api`: backend client, TanStack Query hooks, artifact URL helpers, artifact JSON loader.
- `src/app`: product shell, top bar, bottom intelligence dock.
- `src/features/agent-console`: conversational command center, generation/edit/document commands.
- `src/features/three-viewer`: lazy React Three Fiber GLB stage, camera focus controls, real preview
  fallback, metadata-backed scene object rail.
- `src/features/qa-panel`: Smart Inspector for QA, assets, versions, diff, rollback, downloads.
- `src/features/document-pack`: Document Intelligence workspace with provenance, fields,
  missing/conflicts and corrections.
- `src/components`: small reusable primitives for panels, metrics, commands, warnings, empty states.
- `src/lib`: presenters for backend issues and events, formatting helpers.
- `src/stores`: Zustand UI state only.

State ownership:

- TanStack Query owns server state: health, designs, workflow status, events, versions, packs,
  assets, JSON artifacts.
- Zustand owns UI state: active workflow/pack, selected version/object, inspector tab, dock tab,
  viewer toggles, camera focus.

The frontend does not contain permanent mock designs. It uses existing FastAPI endpoints and
explicitly shows unavailable/offline/empty states.

## Available With Fallback

- `react-resizable-panels` provides a 4-zone studio layout. In tests, it is mocked as pass-through
  because jsdom does not provide the required layout primitives.
- The GLB viewer is lazy-loaded; the heavy Three.js chunk is not part of the first app shell.
- The stage displays the real `preview.png` artifact when WebGL/headless rendering does not produce
  a useful canvas screenshot. This is labeled as a preview artifact, not as the interactive GLB.
- Events are grouped through `eventPresenter`; raw event details remain collapsed.

## Known Limitations

- `ThreeViewer` chunk remains large because `three`, `@react-three/fiber`, and `drei` are loaded
  together after lazy activation.
- Object selection is based on GLB object names and import metadata. Deep semantic picking is not
  yet linked to every SceneSpec object.
- Edit preview is still apply/regenerate; there is no backend endpoint for non-committed patch
  preview.
- Browser plugin was unavailable due to a crashed tab during this reset, so visual proof used Chrome
  headless fallback.

## Future

- Add Playwright E2E for create -> edit -> version -> rollback.
- Add semantic object metadata mapping if frontend needs richer object inspection.
- Split Three.js vendor chunks if bundle size becomes a runtime issue.
