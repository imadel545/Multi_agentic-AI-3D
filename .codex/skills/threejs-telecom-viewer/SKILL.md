---
name: threejs-telecom-viewer
description: Use when changing the React Three Fiber GLB viewer for telecom tower scenes. Covers real GLB loading, camera fit, object selection, overlays, fallback/error handling, asset import modes, and visual smoke validation.
---

# Three.js Telecom Viewer

Use this skill for `apps/frontend/src/features/three-viewer` and viewer-related CSS.

## Rules

- Load GLB through the backend artifact endpoint only.
- Never show a placeholder model as if it were the generated design.
- If the GLB is missing or invalid, show a clear error state and keep the studio usable.
- Fit the scene for telecom towers: prioritize tower readability over a large ground/foundation object.
- Keep beams, cables, labels, sectors, and bounding boxes as real object-name filters, not fake overlays.
- Surface imported/procedural/fallback asset modes in the inspector, not as hidden implementation details.

## Viewer Quality Checklist

- Canvas is present and nonblank for a completed workflow.
- Tower is visible and large enough on first load.
- No global page scroll breaks the studio viewport.
- Orbit controls target the generated scene center and allow useful zoom.
- Selected object state updates from real GLB object names.
- Missing artifact or 404 does not crash React.

## Validation

- Run `npm run typecheck`, `npm run test`, and `npm run build`.
- Browser smoke at `http://127.0.0.1:5173`.
- Confirm the selected workflow is completed, `real_blender`, and the canvas is visible.
