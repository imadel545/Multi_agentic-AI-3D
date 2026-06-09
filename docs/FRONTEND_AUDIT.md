# Frontend Audit

## Real Findings

| Finding | Risk | Action Taken | Remaining Risk |
| --- | --- | --- | --- |
| The app auto-selected the first workflow returned by `/designs`, even when that workflow had failed. | The viewer could open on a broken artifact and show an empty/crashed studio. | The shell now prefers a completed workflow with a generation mode before falling back to the first workflow. | A future workflow picker should let users intentionally inspect failed workflows. |
| Missing GLB artifacts could crash the React Three Fiber canvas. | One stale workflow could break the main studio surface. | Added a viewer error boundary with a clear unavailable-artifact state. | Console may still contain historical dev-server logs until a clean reload. |
| The studio used global page scroll and the 3D canvas could be partially hidden. | The app felt like a long dashboard instead of a controlled studio. | The shell is constrained to `100vh` with internal scrolling. | Mobile/tablet layout remains secondary. |
| The GLB was framed around broad scene geometry instead of tower readability. | The telecom tower appeared small and weak. | Viewer fit now prioritizes vertical tower readability while bounding broad geometry. | Vendor-grade assets and richer Blender composition are still needed for premium visuals. |
| QA warnings were shown as large raw-code cards. | The inspector became noisy and dev-centric. | Warnings/errors are deduplicated, compacted, and severity-tagged before JSON details. | Full user-facing translation of all technical warning codes remains future work. |
| Events dock exposed raw JSON as the primary view. | Timeline evidence was hard for a non-developer user to read. | Added a compact event table and kept raw JSON secondary. | Document-pack events are still normal JSON endpoints, not document-pack SSE. |

## Current State

The frontend is now a stronger local-first Agentic Telecom 3D Studio:

- real backend status and completed-workflow preference;
- command center with real workflow state, command log, quick edit prompts, and agent-stage lanes from events;
- central GLB viewer with real artifact loading and missing-artifact handling;
- smart inspector with QA, compact issues, asset import modes, versions, diff, rollback, and downloads;
- intelligence dock for documents, provenance, events, and memory.

## Not Solved Yet

- The 3D result is still constrained by internal/minimal GLB assets and procedural/fallback geometry.
- There is no non-committed edit preview endpoint; edit still applies and regenerates.
- Object metadata picking is name-based, not semantically linked to `scene_metadata.json`.
- The UI is desktop-first. Mobile/tablet polish is not complete.
- Browser smoke validates an existing completed workflow; full upload -> generate -> edit -> rollback E2E
  should be added later.
