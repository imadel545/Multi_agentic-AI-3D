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
  - panel antennas;
  - microwave dish antenna;
  - RRU boxes;
  - cables;
  - sector beams;
  - azimuth arrows;
  - height marker;
  - metadata labels.
- Real Blender output is `generation_mode = real_blender`.
- Missing Blender output is `generation_mode = fallback_no_blender`.
- Runner verifies required artifacts after Blender exits.
- Fallback preview generation writes a PNG with the SceneSpec preview dimensions so technical
  preview validation remains meaningful without Blender.

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
- `sector_count`
- `network_type`
- `tower_height_m`
- `azimuths_deg`
- `antenna_heights_m`
- `warnings`

Known limitations:

- The worker currently generates procedural primitives, not imported vendor GLB assets.
- GLB structural and geometry QA check object presence, counts, heights, azimuth metadata, and
  bounding-box reasonableness, not visual aesthetics or material quality.
