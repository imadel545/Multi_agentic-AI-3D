# Asset Registry

The asset registry is manifest-first. Blender assets are selected only through validated
JSON manifests in `assets/manifests`.

Manifest fields:

- `asset_id`
- `type`
- `file`
- `height_m`
- `dimensions_m`
- `compatible_networks`
- `compatible_tower_types`
- `mount_zones`
- `status`
- `version`
- `source`
- `import_fallback_allowed`

Only `status = validated` assets are eligible for automatic selection.

Implemented:

- Two internal minimal GLB files are present for pipeline validation:
  - `ANT_PANEL_5G_001`
  - `RRU_SMALL_001`
- Inventory reports these as `imported_glb` readiness and warns that they are
  `internal_test_minimal`, not vendor-grade.
- Missing manifest files are reported as `missing_file`, with `effective_generation_mode =
  procedural_fallback` when fallback is allowed.

Current limitation:

- Vendor-grade tower, 4G panel, and microwave dish GLB files are not present yet.
- The Blender worker imports available GLBs and uses controlled procedural fallback for missing
  files only when the manifest allows it.

See `docs/ASSET_PIPELINE.md` and `docs/ASSET_STRATEGY.md` for import standards, replacement plan,
and quality requirements.
