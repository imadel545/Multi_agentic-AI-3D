# Agentic Studio UI

## Implemented

The UI is organized as an agentic studio:

- Top bar: backend status, workflow id, QA score, generation mode and issue count.
- Left rail: prompt generation, ZIP upload, pack-to-design action, prompt edit and event timeline.
- Center: real GLB viewer.
- Right inspector: QA, assets, versions, diff and downloads.
- Bottom dock: documents, provenance, raw events and memory summary.

The interface is connected to backend endpoints and does not use permanent mock results.

## Available With Fallback

- SSE timeline degrades to polling.
- Offline backend is visible in the top-level UI.
- Missing/fallback asset modes are shown in the assets panel.

## Known Limitations

- This is the first frontend implementation, not the final polished studio.
- Split panels are fixed rather than user-resizable.
- Agent explanations are based on trace/events/reports; there is no separate LLM explanation endpoint.

## Future

- Add resizable panels and persisted layout.
- Add command routing for correction, rollback and download from natural language.
- Add inline provenance-to-SceneSpec linking.
