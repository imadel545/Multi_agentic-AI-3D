# Agentic Studio UI

## Implemented

The UI is now organized as a product studio, not a developer dashboard:

- Agent Command Center: conversational summaries, command modes, quick edits, document commands and
  user-facing failure explanations.
- 3D Design Stage: dominant central stage, GLB artifact loading, camera focus controls, overlay
  toggles, scene object rail and preview artifact fallback.
- Smart Inspector: QA, warning explanations, asset inventory/imports, versions, diff, rollback and
  downloads.
- Intelligence Dock: documents, provenance, grouped events and memory.

Design system primitives:

- `PanelShell`
- `MetricCard`
- `CommandMessage`
- `WarningCard`
- `EmptyState`
- `ActionButton`

Presentation layers:

- `issuePresenter` translates backend warning/error codes.
- `eventPresenter` translates and groups backend events.

## Available With Fallback

- Technical JSON is still accessible through collapsed details, but no longer the primary UX.
- The preview image is shown only as a real artifact reference, not as fake 3D.
- Empty states explain what action unlocks each surface.

## Known Limitations

- This is still an MVP studio, not a fully polished commercial design tool.
- The current asset library and Blender scene composition limit visual realism.
- The command center is not yet a durable chat transcript stored server-side.
- Some interactions remain simple browser-native controls, such as rollback confirmation.

## Future

- Add patch preview/apply/reject once backend exposes a non-committed edit preview endpoint.
- Add richer selected-object details and object diff visualization.
- Add E2E visual tests for desktop and one responsive breakpoint.
