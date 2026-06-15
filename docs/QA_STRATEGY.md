# QA Strategy

QA must say what it actually checks. The current pipeline is honest about its
limitations and never advertises checks it cannot perform.

## Levels

- Contract QA: Pydantic validation of all API/runtime contracts.
- Requirement QA: business rules on `RequirementSpec` (tower height ≤ 150 m,
  sector count ≤ 12, azimuth consistency, etc.).
- Scene QA: `SceneSpec` validation, asset compatibility, tower/RF rules.
- Quality gates: pre-Blender and post-Blender pass/fail thresholds.
- Generation QA: metadata consistency, artefacts, generation mode, fallback
  warnings, and asset import records.
- GLB structural QA: `glb_parse_structural` — node/mesh/material counts and
  expected object presence.
- Mesh-level QA: `mesh_level_basic` parses GLB accessors to compute a real
  world-space bounding box, approximate tower height, object counts, ground
  checks, and scale realism.
- Geometry QA: combines object-name counts, metadata proxies, and Mesh QA
  results.
- Height/azimuth QA: metadata-based checks plus bounding-box sanity.
- Preview QA: PNG resolution, luminance, contrast, non-dark-pixel ratio.
- Document-pack QA: evidence, conflicts, blocking fields, plausibility, OCR/CAD
  limits.

## What is real

- GLB/GLTF JSON parse verifies nodes, meshes, materials and object names.
- Mesh QA v1 reads vertex data from GLB accessors to compute a real bounding
  box and checks tower height, ground plane, scale, and antenna count.
- Geometry validator merges object-name counts, metadata proxies, and Mesh QA
  results; it fails when the real bounding box is unrealistic.
- Preview inspector checks PNG resolution, luminance, contrast, and non-dark
  pixel ratio.
- Asset import QA verifies `asset_imports`, generation modes (`parametric_generated`,
  `internal_project_generated`, `imported_glb`, `procedural_fallback`,
  `missing_file`), missing files, and fallback visibility.
- Fallback Blender is rejected by default via quality-gate policy.

## What is not yet real

- Mesh QA v1 does **not** verify individual antenna HBA or azimuth from vertices.
- No collision detection between components.
- No vendor-grade mesh/material validation.
- No semantic visual judgement of the preview image.
- No full CAD geometric validation.

## Fallbacks

- Missing Blender or a Blender error produces explicit fallback artefacts that
  are **not** accepted as a default result.
- A missing asset GLB can produce `procedural_fallback` if the manifest allows
  fallback.
- All fallbacks are propagated to `status.json`, the Product API, reports, and
  the frontend.

## Expected tests

- A lattice workflow with real Blender completes and passes Mesh QA.
- A workflow selecting a tower without a matching GLB exposes fallback/degraded.
- Invalid requirements (e.g., tower height > 150 m, sector count > 12) fail with
  a clean `INVALID_REQUIREMENTS` validation error.
- Viewer bundles contain no filesystem paths.
- QA reports name proxy/real modes correctly (`mesh_level_basic`,
  `glb_parse_structural`, etc.).
