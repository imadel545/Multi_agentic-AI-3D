# Asset Strategy

## Current Assets

Implemented:

- Manifest-first registry under `assets/manifests`.
- Validated manifest IDs for:
  - `TOWER_LATTICE_30M`
  - `TOWER_MONOPOLE_30M`
  - `TOWER_ROOFTOP_12M`
  - `TOWER_SMALL_CELL_10M`
  - `ANT_PANEL_5G_001`
  - `ANT_PANEL_4G_001`
  - `ANT_MICROWAVE_DISH_001`
  - `RRU_SMALL_001`
- Asset selection is compatibility-based and only selects `status = validated`.
- RAG indexes manifests as `asset_manifests`.

Known limitation:

- The repository currently contains manifests only. The referenced GLB files under
  `assets/towers`, `assets/antennas`, and `assets/radios` are not present.

## Procedural Generation

Implemented:

- The Blender worker creates controlled procedural geometry from `SceneSpec` for:
  - lattice/monopole/generic tower primitives
  - panel antennas
  - microwave dish
  - RRU boxes
  - cables
  - sector beams
  - azimuth arrows
  - height markers
  - labels/metadata

Rule:

- Procedural objects must be visible in `scene_metadata.json` through
  `procedural_objects_created`.
- Procedural generation is acceptable for current local validation, but it is not a substitute for
  vendor-grade GLB asset import.

## Missing Real Assets

Missing:

- Real lattice tower GLB.
- Real monopole GLB.
- Real rooftop mast GLB.
- Real small-cell pole GLB.
- Real 4G/5G panel antenna GLBs.
- Real microwave dish GLB.
- Real RRU GLB.
- Material/LOD metadata for imported models.

## Asset Manifest Rules

Required:

- `asset_id` must be stable and unique.
- `type` must match the selectable family: `tower`, `antenna`, or `radio`.
- `file` must point to the expected GLB asset path.
- `dimensions_m` must be credible and in meters.
- `compatible_networks` and `compatible_tower_types` must be explicit.
- `status = validated` is required for automatic selection.
- `mount_zones` should define safe install ranges for towers.

Recommended next rule:

- A manifest whose `file` is missing should be marked `status = manifest_only` or be reported by
  an asset inventory validator before selection claims real imported assets.

## Replacement Plan

1. Add real GLB files for the existing manifest IDs without changing IDs.
2. Add an asset inventory validator that verifies every `file` path exists.
3. Extend Blender worker to import existing GLBs and fall back to procedural geometry only when
   explicitly allowed.
4. Record asset import mode per object: `imported_glb` or `procedural`.
5. Extend geometry QA to compare bounding boxes and transforms from parsed GLB nodes.

## Quality Requirements

Implemented:

- Object presence/count validation through GLB inspection and geometry validation.
- Sector-level checks for antennas, RRUs, cables, beams, azimuth arrows, and metadata azimuths.
- Height tolerance: `0.5m`.
- Azimuth tolerance: `5deg`.

Known limitations:

- Current bounding-box QA is metadata/proxy based when GLB transform parsing is unavailable.
- Materials, LOD, normals, mesh quality, and collision-free mounting are not validated yet.
