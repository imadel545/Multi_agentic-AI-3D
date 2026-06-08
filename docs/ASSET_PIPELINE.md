# Asset Pipeline MVP

## Implemented

- Asset manifests remain the source of truth under `assets/manifests`.
- Each manifest can declare:
  - `source`: `vendor_expected`, `vendor_supplied`, or `internal_test_minimal`
  - `import_fallback_allowed`: whether controlled procedural fallback is allowed when import fails
- `GET /assets/inventory` exposes:
  - `asset_file_exists`
  - `asset_import_mode`: `imported_glb` when the manifest file exists, otherwise `missing_file`
  - `effective_generation_mode`: `imported_glb`, `procedural_fallback`, or `missing_file`
  - `asset_dimensions_checked`
  - `mount_zones`
  - warnings
- The Blender worker attempts controlled GLB import when `asset_file` exists.
- If import fails or the file is missing, procedural fallback is used only when the manifest allows
  it, and the fallback is written to `scene_metadata.json`.
- `scene_metadata.json` includes `asset_imports` and `asset_import_summary`.
- API workflow status exposes the same asset import metadata for frontend panels.

## Current Inventory

Imported/test-ready GLB files in this repository:

- `assets/antennas/ant_panel_5g_001.glb`
- `assets/radios/rru_small_001.glb`

These are internal minimal assets, not vendor-grade assets. Their manifests are marked
`source = internal_test_minimal`, and inventory/metadata exposes
`INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE`.

Missing vendor GLB files remain for towers, 4G panel, and microwave dish manifests.
The expected inventory status is therefore `partial_import_ready`, not fully ready.

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

Future:

- Exact imported GLB bounding-box validation against manifest dimensions.
- Transform and material validation from parsed GLB nodes.
- Manifest notes for pivots, mount points, LOD, and vendor provenance.
