# Asset Registry

The registry is manifest-first. Blender only selects assets described in
`assets/manifests`.

## Current truth

- 12 manifests.
- 12 local GLB files present.
- 0 GLB file missing.
- `/assets/inventory` returns `status = ready_for_import`.
- All tower types have a matching asset manifest (the 3 previously missing tower
  types were generated procedurally with Blender and stored as internal project
  generated assets).
- Towers are generated parametrically by default; GLB import happens only when
  the resolver explicitly selects `imported_glb_exact` or
  `internal_project_generated`.

## Sources

- `cc_by`: attribution required, not vendor-grade.
- `internal_cleaned`: importable but internal, not vendor-grade.
- `internal_test_minimal`: minimal validation-pipeline asset, not vendor-grade.
- `internal_project_generated`: procedural asset generated with Blender in this
  repo, not vendor-grade, reusable as an importable GLB.

## Rules

- Do not present procedural fallback as a real asset.
- Do not select a missing asset without a user-visible warning.
- Keep `entries`, `missing_files`, `real_glb_asset_count`, and
  `missing_file_count` stable for the frontend.
- Internal/generated assets carry an explicit
  `INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE` or similar warning.
- Generation strategy is the source of truth: `parametric_generated`,
  `imported_glb_exact`, `internal_project_generated`, `procedural_fallback`,
  etc.
