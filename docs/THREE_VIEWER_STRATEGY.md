# Three Viewer Strategy

## Implemented

- The viewer is lazy-loaded through React Suspense so Three.js does not block initial app chrome.
- GLB loading uses `@react-three/drei` `useGLTF` against the backend artifact URL.
- The canvas uses camera focus presets: fit, tower, sectors, GPS/cabinet and reset.
- Viewer toggles control beams, cables, labels, sectors and bounding boxes by object-name matching.
- Scene object rail is metadata-backed through `scene_metadata.json.asset_imports`.
- Asset import modes are visible through the stage banner and Smart Inspector.
- The stage displays `preview.png` as a real Blender preview artifact fallback when WebGL capture is
  visually blank or while GLB rendering is not useful.

## Available With Fallback

- Missing GLB URL shows a clear no-GLB state.
- GLB load errors are caught by a React error boundary.
- Headless Chrome/WebGL can produce `SharedImage`/`ReadPixels` warnings and blank canvas captures;
  the preview artifact remains visible and explicitly labeled.

## Known Limitations

- The current preview artifact itself can be poorly framed by Blender. The UI zooms it for
  inspection, but this does not solve Blender camera composition.
- Object toggles rely on naming conventions. They do not yet use a formal object-role map for every
  mesh.
- The tower/sector/accessory camera presets are pragmatic defaults, not semantic bounding-box
  fitting per object class.
- The ThreeViewer chunk is large because R3F, drei and Three load together.

## Future

- Add semantic bounding boxes from `scene_metadata.json`.
- Add per-object focus and inspector metadata once the backend exports stable object IDs.
- Improve Blender preview camera and scene composition so fallback preview is inherently strong.
