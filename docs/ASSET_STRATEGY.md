# Asset Strategy

## Implemented

- Manifest-first registry under `assets/manifests`.
- Compatibility-based selection for assets with `status = validated`.
- Asset metadata fields:
  - `source`
  - `license`
  - `attribution_required`
  - `attribution`
  - `original_url`
  - `original_author`
  - `normalized_by`
  - `pivot_policy`
  - `front_axis`
  - `import_fallback_allowed`
  - `dimensions_m`
  - `mount_zones`
- `/assets/inventory` reports import readiness before `/assets/{asset_id}` can shadow the route.
- Scene planning copies manifest file/source/fallback metadata into `SceneSpec`, so Blender knows
  whether to import a real GLB or use fallback.
- Blender writes per-placement import records to `scene_metadata.json`.
- API status exposes `asset_import_summary` and `asset_imports`.

## Current Assets

Validated manifests:

- `TOWER_LATTICE_30M`
- `TOWER_MONOPOLE_30M`
- `TOWER_ROOFTOP_12M`
- `TOWER_SMALL_CELL_10M`
- `ANT_PANEL_5G_001`
- `ANT_PANEL_4G_001`
- `ANT_MICROWAVE_DISH_001`
- `POWER_CABINET_001`
- `GPS_ANTENNA_001`
- `MOUNTING_BRACKET_001`
- `CABLE_TRAY_001`
- `RRU_SMALL_001`

GLB files currently present:

- `assets/towers/tower_lattice_30m.glb`
- `assets/antennas/ant_panel_4g_001.glb`
- `assets/antennas/ant_microwave_dish_001.glb`
- `assets/antennas/ant_panel_5g_001.glb`
- `assets/antennas/gps_antenna_001.glb`
- `assets/brackets/mounting_bracket_001.glb`
- `assets/cabinets/power_cabinet_001.glb`
- `assets/cables/cable_tray_001.glb`
- `assets/radios/rru_small_001.glb`

`TOWER_LATTICE_30M` is an integrated CC Attribution asset from GetGLB. The source file is kept
under `assets/source_downloads/getglb/cell_tower_replica/`, and attribution is required.
`ANT_PANEL_4G_001`, `ANT_MICROWAVE_DISH_001`, `POWER_CABINET_001`, `GPS_ANTENNA_001`,
`MOUNTING_BRACKET_001`, and `CABLE_TRAY_001` are project-authored internal cleaned GLBs.
`ANT_PANEL_5G_001` and `RRU_SMALL_001` are still internal minimal test assets.

## Available With Fallback

- Monopole, rooftop mast, and small-cell pole tower manifests still use controlled procedural
  fallback when their GLB files are absent and fallback is allowed.
- GPS antenna and power cabinet now have manifest-backed internal cleaned GLBs for inventory,
  but the worker still creates those objects procedurally from `SceneSpec.visual_elements`.
  They are not injected into a scene unless explicitly requested.
- Non-Blender generation writes explicit fallback metadata instead of pretending assets were
  imported.

## Import Modes

- `imported_glb`: a manifest file exists and the Blender worker imported it successfully.
- `procedural_fallback`: no usable GLB was imported, and controlled procedural geometry was used.
- `missing_file`: no GLB was imported and fallback was not allowed. This should fail QA.
- `manifest_only`: inventory-level state for manifests whose referenced file is absent.

## Asset Manifest Rules

Required:

- `asset_id` must be stable and unique.
- `type` must match the selectable family.
- `file` must point to the expected GLB path.
- `dimensions_m` must be credible and in meters.
- `compatible_networks` and `compatible_tower_types` must be explicit.
- `status = validated` is required for automatic selection.
- `source` must distinguish expected vendor assets from internal minimal assets.
- `license` and attribution fields must be filled for any external asset.
- `pivot_policy` and `front_axis` must be documented before an asset is used by the worker.
- `import_fallback_allowed` must be intentional.
- Tower `mount_zones` should define safe install ranges.

## Quality Requirements

Implemented:

- Object presence/count validation through GLB inspection and geometry validation.
- Sector-level checks for antennas, RRUs, cables, beams, azimuth arrows, and metadata azimuths.
- Import metadata checks for file existence, import success, dimensions check flag, modes, and
  visible fallback warnings.
- Height tolerance: `0.5m`.
- Azimuth tolerance: `5deg`.

Future:

- Exact GLB bounding-box checks against manifest dimensions.
- Material, LOD, pivot, mount-point, and texture budget validation.
- Worker-level import placement for GPS/power cabinet/bracket/cable-tray accessory manifests.

## Replacement Plan

1. Replace internal minimal/cleaned GLBs with vendor-grade or project-owned production assets
   without changing stable IDs.
2. Add real monopole, rooftop mast, and small-cell pole GLBs.
3. Wire manifest-backed accessory import placement for GPS, power cabinet, brackets, and cable
   trays when the SceneSpec requests them.
4. Tighten GLB dimension/material QA once production assets are present.
5. Keep provenance and attribution visible to the frontend.

## Known Limitations

- Inventory is `partial_import_ready`, not fully vendor-ready.
- Current internal cleaned/minimal GLBs are useful for pipeline validation and MVP visuals, but
  not vendor-grade.
- Procedural fallback still carries monopole/rooftop/small-cell tower visual quality.
- GLB parser QA does not yet verify exact transforms or material quality.
