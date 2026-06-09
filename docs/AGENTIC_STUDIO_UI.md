# Agentic Studio UI

## Implemented

The UI is organized as an agentic studio:

- Top bar: backend status, workflow id, QA score, active version, generation mode, LLM/fallback
  status, issue count, and download access.
- Left rail: Agent Command Center with current operation, event-derived agent stages, generation,
  ZIP upload, pack-to-design action, quick edit prompts, prompt edit, command log and event timeline.
- Center: real GLB viewer with bounded missing-artifact handling.
- Right inspector: QA, compact warnings/errors, assets, versions, diff and downloads.
- Bottom dock: documents, provenance, readable events and memory summary.

The interface is connected to backend endpoints and does not use permanent mock results.

## Available With Fallback

- SSE timeline degrades to polling.
- Offline backend is visible in the top-level UI.
- Missing/fallback asset modes are shown in the assets panel.
- Missing GLB artifacts are shown as explicit viewer errors instead of crashing the studio.

## Known Limitations

- This is now a stronger local-first studio, but not a final product-grade UI.
- Split panels are fixed rather than user-resizable.
- Agent explanations are based on trace/events/reports; there is no separate LLM explanation endpoint.
- Visual quality is limited by internal/minimal GLB assets and current Blender scene composition.

## Future

- Add resizable panels and persisted layout.
- Add command routing for correction, rollback and download from natural language.
- Add inline provenance-to-SceneSpec linking.
