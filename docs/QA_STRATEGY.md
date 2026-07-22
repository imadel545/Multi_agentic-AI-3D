# QA Strategy

QA must say what it actually checks. The current pipeline is honest about its
limitations and never advertises checks it cannot perform.

## Levels

- Contract QA: Pydantic validation of all API/runtime contracts.
- Requirement QA: business rules on `RequirementSpec` (tower height ≤ 150 m,
  sector count ≤ 12, azimuth consistency, etc.).
- Scene QA: `SceneSpec` validation, asset compatibility, tower/RF rules.
- Requirement coverage QA: field-level proof from `RequirementSpec` to
  `SceneSpec`, including evidence-bound controlled planning deviations.
- Quality gates: pre-Blender and post-Blender pass/fail thresholds.
- Generation QA: metadata consistency, artefacts, generation mode, fallback
  warnings, and asset import records.
- GLB binary integrity QA: strict GLB container/chunk parsing, buffer and
  buffer-view ranges, real `POSITION` bytes, finite values, optional index
  ranges, primitive completeness, and semantic entity mesh coverage.
- Mesh-level QA: `mesh_level_spatial_basic` when GLB semantic transforms and
  primary-equipment bounds are complete, `mesh_level_transform_basic` when only
  transforms are complete, otherwise `mesh_level_basic`. It parses real GLB
  accessors to compute world-space bounds, tower height, object counts, ground,
  scale, antenna HBA/azimuth transforms and broad-phase AABB interference.
- Geometry QA: combines object-name counts, metadata proxies, and Mesh QA
  results.
- Blender segment QA: measures generated cylinder endpoints from transformed
  mesh vertices before export and hard-fails above 1 mm.
- Height/azimuth QA: metadata-based checks plus bounding-box sanity.
- Preview QA: PNG resolution, luminance, contrast, subject occupancy, bounding
  box framing, clipping, horizontal centering, and edge margins.
- Document-pack QA: evidence, conflicts, blocking fields, plausibility, OCR/CAD
  limits.
- Completion proof: binds requirement/SceneSpec and GLB/preview/metadata/build-lock
  SHA-256 hashes to successful real-Blender, gate, QA and coverage results.

## What is real

- GLB QA reads the binary payload; JSON-declared accessors without backing
  bytes cannot pass. Index values must resolve to real position vertices.
- Mesh QA v1 reads vertex data from GLB accessors to compute a real bounding
  box and checks tower height, ground plane, scale, antenna count, role-node
  transforms, and approximate antenna HBA when transforms are readable.
- Spatial QA computes one real-vertex world-space AABB per primary semantic
  equipment and rejects undeclared overlaps. Antenna/RRU contact is allowed only
  when both belong to the same sector.
- Geometry validator merges object-name counts, metadata proxies, and Mesh QA
  results; it fails when the real bounding box is unrealistic.
- Preview inspector parses PNG pixels and checks resolution, luminance,
  contrast, foreground occupancy, subject framing, clipping, centering, and
  margins.
- Asset import QA verifies `asset_imports`, generation modes (`parametric_generated`,
  `internal_project_generated`, `imported_glb`, `procedural_fallback`,
  `missing_file`), missing files, and fallback visibility.
- Fallback Blender is rejected by default via quality-gate policy.
- `completed` is impossible without an issued completion certificate, and the
  workflow service re-verifies artifact size/hash evidence before activating a
  version.
- Build provenance QA verifies a unique attempt/build ID, factory-startup
  command profile, worker/SceneSpec hashes, Blender runtime version/build hash,
  and the three generated artifact hashes before promotion.
- Version activation revalidates the issued completion certificate and all four
  certified artifacts before atomically committing `active_design.json`.

## What is not yet real

- Mesh QA v1 does **not** verify exact per-vertex panel normals or RF propagation.
- AABB broad-phase interference is implemented for primary equipment, but exact
  triangle/BVH collision, self-intersection and engineering clearance are not.
- No full manifold, self-intersection, weld/node or structural load validation.
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

- Unit tests force deterministic embeddings and passthrough reranking; they do
  not contact NVIDIA or Groq. Live-provider checks are explicit integration
  tests, so external HTTP failures cannot make the unit suite nondeterministic.

- A lattice workflow with real Blender completes and passes Mesh QA.
- A workflow selecting a tower without a matching GLB exposes fallback/degraded.
- Invalid requirements (e.g., tower height > 150 m, sector count > 12) fail with
  a clean `INVALID_REQUIREMENTS` validation error.
- Viewer bundles contain no filesystem paths.
- QA reports name proxy/real modes correctly (`mesh_level_spatial_basic`,
  `mesh_level_transform_basic`, `mesh_level_basic`, `glb_parse_structural`, etc.).
- Anti-golden GLBs with JSON-only accessors, missing semantic meshes, invalid
  indices, or tampered certified artefacts fail.
