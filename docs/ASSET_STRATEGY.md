# Asset Strategy

## Implemented

- Manifest-first registry under `assets/manifests`.
- Compatibility-based selection for assets with `status = validated`.
- Asset metadata fields:
  - `source`
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
- `RRU_SMALL_001`

GLB files currently present:

- `assets/antennas/ant_panel_5g_001.glb`
- `assets/radios/rru_small_001.glb`

These files are internal minimal test assets. They are useful to verify import behavior, but they
are not vendor-grade. Inventory and generation metadata expose this through
`source = internal_test_minimal`.

## Available With Fallback

- Tower, 4G panel, microwave dish, and other missing vendor files currently use controlled
  procedural fallback when their manifest allows it.
- GPS antenna and power cabinet are procedural visual objects controlled by SceneSpec flags. They
  are not manifest-backed GLB assets yet.
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
- Manifest-backed GPS/power cabinet assets.

## Replacement Plan

1. Replace internal minimal GLBs with vendor-grade assets without changing stable IDs.
2. Add real tower, 4G panel, and microwave dish GLBs.
3. Add pivot/mount metadata to manifests.
4. Tighten GLB dimension/material QA once vendor assets are present.
5. Expose vendor provenance to the frontend.

## Known Limitations

- Inventory is `partial_import_ready`, not fully vendor-ready.
- Current internal GLBs are simple boxes for pipeline validation.
- Procedural fallback still carries most visual quality for towers.
- GLB parser QA does not yet verify exact transforms or material quality.
