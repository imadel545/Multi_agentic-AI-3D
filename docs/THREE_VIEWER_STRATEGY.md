# Three Viewer Strategy

## Implemented

The first viewer is implemented in `apps/frontend/src/features/three-viewer/ThreeViewer.tsx`.

Capabilities:

- Loads generated `design.glb` through `GET /designs/{workflow_id}/artifacts/glb`.
- Supports version-scoped GLB loading with `version_id`.
- Uses React Three Fiber, Drei `Bounds`, `OrbitControls`, `Grid`, and environment lighting.
- Provides layer toggles for beams, cables, labels, bounding boxes and sectors using GLB object
  names.
- Supports object click selection and exposes selected object name in the UI.
- Does not show a fake scene when no GLB artifact exists.

## Available With Fallback

- If no workflow/artifact is available, the viewer displays an explicit empty state.
- If an artifact route returns `404`, the browser/network error is visible rather than replaced by a
  fake model.

## Known Limitations

- Layer toggles rely on object naming conventions. This is workable with current Blender metadata,
  but a richer object-role index from `scene_metadata.json` would be stronger.
- The viewer chunk is lazy-loaded but still large due to Three.js/Drei.
- No semantic bounding-box overlay is rendered yet.

## Future

- Load `scene_metadata.json`, `geometry_validation.json`, and `asset_import_summary` into a semantic
  object index.
- Add sector highlighting, azimuth arrows, HBA/tilt labels and measured overlays.
- Add side-by-side version comparison.
