# Asset Pipeline MVP

## Implemented

- Asset manifests remain the source of truth under `assets/manifests`.
- Each manifest can declare:
  - `source`: `vendor_expected`, `vendor_supplied`, `cc0`, `cc_by`, `royalty_free`,
    `internal_cleaned`, or `internal_test_minimal`
  - `license`, `attribution_required`, `attribution`, `original_url`, `original_author`
  - `normalized_by`, `pivot_policy`, and `front_axis`
  - `import_fallback_allowed`: whether controlled procedural fallback is allowed when import fails
- `GET /assets/inventory` exposes:
  - `asset_file_exists`
  - `asset_import_mode`: `imported_glb` when the manifest file exists, otherwise `missing_file`
  - `effective_generation_mode`: `imported_glb`, `procedural_fallback`, or `missing_file`
  - `asset_dimensions_checked`
  - `license`, `attribution_required`, `original_url`, `pivot_policy`, `front_axis`
  - `mount_zones`
  - warnings
- The Blender worker attempts controlled GLB import when `asset_file` exists.
- Requested GPS antenna and power cabinet are SceneSpec accessory placements and are imported from
  their GLB files when available.
- If import fails or the file is missing, procedural fallback is used only when the manifest allows
  it, and the fallback is written to `scene_metadata.json`.
- `scene_metadata.json` includes `asset_imports` and `asset_import_summary`.
- API workflow status exposes the same asset import metadata for frontend panels.

## Current Inventory

Imported/test-ready GLB files in this repository:

- `assets/towers/tower_lattice_30m.glb`
- `assets/antennas/ant_panel_4g_001.glb`
- `assets/antennas/ant_microwave_dish_001.glb`
- `assets/antennas/ant_panel_5g_001.glb`
- `assets/antennas/gps_antenna_001.glb`
- `assets/brackets/mounting_bracket_001.glb`
- `assets/cabinets/power_cabinet_001.glb`
- `assets/cables/cable_tray_001.glb`
- `assets/radios/rru_small_001.glb`

`TOWER_LATTICE_30M` is a normalized CC Attribution GLB from GetGLB. Attribution is required
and exposed in the manifest, inventory, and Blender metadata. The other newly added GLBs are
project-authored internal cleaned assets. Existing 5G panel/RRU assets remain
`internal_test_minimal`.

Monopole, rooftop mast, and small-cell pole manifests now have project-authored internal GLBs.
The expected inventory status is therefore `ready_for_import`, while still not fully vendor-ready.

## Standards

Required for vendor GLB intake:

- Units: meters.
- Coordinate system: Blender/glTF compatible, Z-up after import into Blender.
- Origin/pivot:
  - towers: base center at ground level
  - antennas/RRUs: mount-facing center or documented bracket point
- Dimensions: manifest `dimensions_m` must match the imported object within documented tolerance.
- Naming: object/node names should include the stable `asset_id` or role.
- Materials: neutral PBR materials; no hidden emissive/decorative effects unless required.
- Textures: keep local-first size bounded; no large uncompressed texture sets for MVP.
- LOD: optional for MVP, but vendor assets should document LOD availability before selection.
- Orientation:
  - antennas face local +Y before placement
  - tower vertical axis is +Z
  - RRU front/access side is documented in manifest notes when added

## QA

Implemented:

- Import metadata checks in generation QA.
- Imported GLB records must report `asset_file_exists = true`, `asset_import_success = true`, and
  imported object names.
- Procedural fallback records must include visible fallback warnings.
- `missing_file` without allowed fallback fails generation QA.
- CC-BY and internal cleaned/minimal assets emit non-vendor-grade or attribution warnings.
- Requested GPS/power-cabinet accessories are included in GLB inspection and geometry QA counts.

Future:

- Exact imported GLB bounding-box validation against manifest dimensions.
- Transform and material validation from parsed GLB nodes.
- Vendor-grade replacement assets for all manifest IDs.
