# Frontend UX Flow

## Implemented

Primary desktop flow:

1. User opens the studio and sees backend/workflow/QA/version/LLM status in the top bar.
2. User uses Agent Command Center to generate from a technical brief, edit an existing workflow, or
   work from a document pack.
3. The central 3D Design Stage loads the real GLB artifact when available and exposes camera focus
   controls, overlay toggles, scene objects and real preview fallback.
4. Smart Inspector explains QA, warnings, assets, versions, diff, rollback and downloads without
   showing raw backend codes as primary UX.
5. Intelligence Dock exposes documents, provenance, grouped events and memory.

Prompt edit flow:

```text
user prompt
-> backend edit endpoint
-> structured patch and version attempt
-> events/QA/versions refresh
-> command center summary
-> inspector shows accepted version or rejection explanation
```

Document pack flow:

```text
select/upload ZIP
-> inspect documents and extracted fields
-> fix missing/conflict values if needed
-> generate from ProjectDesignSpec
-> inspect design, QA, assets and versions
```

## Available With Fallback

- If no document pack is selected, the dock shows a clear APD/PDF/DXF/ZIP empty state.
- If no GLB exists, the stage shows a no-GLB empty state.
- If WebGL screenshot rendering is unreliable, a real Blender preview artifact is visible.
- If an edit is rejected, the command center translates the failure into a concrete next action.

## Known Limitations

- The command center is operational and conversational, but not a full persistent chat history.
- There is no live document-pack SSE stream yet.
- The rollback action uses browser confirmation and backend rollback, not a custom modal.
- Some backend details remain available in collapsed JSON for debugging.

## Future

- Add guided patch preview before apply when backend supports it.
- Add richer selected-object inspector tied to SceneSpec object IDs.
- Add mobile/tablet responsive UX after desktop studio is stable.
