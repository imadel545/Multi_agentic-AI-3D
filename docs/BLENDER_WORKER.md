# Blender Worker

Completed:

- `core/services/blender_runner.py` detects Blender through:
  - `BLENDER_BINARY`
  - `TELECOM_STUDIO_BLENDER_BINARY`
  - `blender` in `PATH`
  - `/Applications/Blender.app/Contents/MacOS/Blender`
  - common versioned macOS app paths.
- `apps/blender_worker/generate_scene.py` consumes only `SceneSpec`.
- The worker creates controlled procedural geometry:
  - lattice/monopole/generic tower;
  - tower platforms, ladder, lightning rod, and aviation light when present in SceneSpec;
  - panel antennas;
  - microwave dish antenna;
  - RRU boxes;
  - cables;
  - sector beams;
  - azimuth arrows;
  - height marker;
  - GPS antenna and power cabinet only when `SceneSpec.visual_elements` explicitly enables them;
  - metadata labels.
- The worker imports manifest-backed GLB assets when the referenced file exists and import succeeds.
  Current imported internal test assets are:
  - `ANT_PANEL_5G_001`
  - `RRU_SMALL_001`
- Missing or failed imports use controlled procedural fallback only when
  `import_fallback_allowed = true`.
- Real Blender output is `generation_mode = real_blender`.
- Missing Blender output is `generation_mode = fallback_no_blender`.
- Runner verifies required artifacts after Blender exits.
- Fallback preview generation writes a PNG with the SceneSpec preview dimensions so technical
  preview validation remains meaningful without Blender.
- Prompt edits regenerate a version-specific artifact directory; Blender artifacts from older
  versions are not reused as QA evidence for a new version.

Implemented QA outputs:

- `glb_inspection.json`
- `geometry_validation.json`
- `preview_inspection.json`

Requires Local Blender Install:

- True GLB/PNG generation requires a local Blender executable.
- On this machine Blender was detected at:

```text
/Applications/Blender.app/Contents/MacOS/Blender
```

Fallback:

- If Blender is absent or fails, the runner creates explicit fallback artifacts and metadata.
- Fallback artifacts are not represented as real generation.
- Fallback `design.glb` is not treated as a valid GLB. Structural QA uses
  `inspection_mode = metadata_fallback` when metadata is available.

Required artifacts:

- `design.glb`
- `preview.png`
- `scene_metadata.json`
- `glb_inspection.json`
- `geometry_validation.json`
- `preview_inspection.json`

Metadata fields:

- `scene_id`
- `schema_version`
- `generation_mode`
- `assets_used`
- `procedural_objects_created`
- `asset_imports`
- `asset_import_summary`
- `sector_count`
- `network_type`
- `tower_height_m`
- `tower_characteristics`
- `azimuths_deg`
- `antenna_heights_m`
- `warnings`

Each `asset_imports` entry includes `asset_id`, `asset_file`, `asset_source`,
`asset_file_exists`, `asset_import_success`, `asset_dimensions_checked`, `import_mode`,
`effective_generation_mode`, imported object names, and warnings.

Known limitations:

- The worker imports available GLBs, but the current GLB files are internal minimal test assets,
  not vendor-grade assets.
- Tower, 4G panel, and microwave dish GLB files are still missing and therefore use visible
  procedural fallback when allowed.
- `GET /assets/inventory` exposes whether manifests have real GLB files available for import and
  whether fallback will be needed.
- GPS antenna and power cabinet are procedural helper objects until real assets/manifests are added
  for them.
- GLB structural and geometry QA check object presence, counts, heights, azimuth metadata, and
  bounding-box reasonableness, not visual aesthetics or material quality.
