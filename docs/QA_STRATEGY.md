# QA Strategy

QA must say what it actually checks. The current pipeline is honest about its
limitations and never advertises checks it cannot perform.

## Levels

- Contract QA: Pydantic validation of all API/runtime contracts.
- GeometryProgram contract QA: unique identifiers, parent/source/material
  references, acyclic graphs, meter units, typed primitives/transforms,
  requested semantic quantity, maximum envelope and bounded resource budgets.
- Requirement QA: business rules on `RequirementSpec` (tower height ≤ 150 m,
  sector count ≤ 12, azimuth consistency, etc.).
- Scene QA: `SceneSpec` validation, asset compatibility, tower/RF rules.
- Requirement coverage QA: field-level proof from `RequirementSpec` to
  `SceneSpec`, including evidence-bound controlled planning deviations.
- Quality gates: pre-Blender and post-Blender pass/fail thresholds.
- Generation QA: metadata consistency, artefacts, generation mode, fallback
  warnings, and asset import records.
- Trusted assembly QA: `AssemblyPlan 1.1` manifest/catalog and builder snapshot
  hashes, exact-file identity, allowed parameters, connector/anchor contracts,
  operation hashes and isolated-worker revalidation before Blender construction.
- Component proof QA: verifies every catalog/GeometryProgram component,
  semantic strategy (`reuse`, `adapt`, `compose`, `procedural_generate`),
  geometry source, resolved parameters, transforms, bounds, fingerprint,
  declared/executed operations and local pass state.
- GLB binary integrity QA: strict GLB container/chunk parsing, buffer and
  buffer-view ranges, real `POSITION` bytes, finite values, optional index
  ranges, primitive completeness, and semantic entity mesh coverage.
- Profile detail QA: internal panel/RRU profiles must export the declared
  radome/chassis/mount/port and enclosure/heatsink/mount/connector parts; a
  named single box is rejected.
- Mesh-level QA: `mesh_level_spatial_basic` when GLB semantic transforms and
  primary-equipment bounds are complete, `mesh_level_transform_basic` when only
  transforms are complete, otherwise `mesh_level_basic`. It parses real GLB
  accessors to compute world-space bounds, tower height, object counts, ground,
  scale, antenna HBA/azimuth transforms and broad-phase AABB interference.
- Geometry QA: combines object-name counts, metadata proxies, and Mesh QA
  results.
- Blender segment QA: measures generated cylinder endpoints from transformed
  mesh vertices before export and hard-fails above 1 mm.
- GeometryProgram compilation QA: only the fixed compiler may create supported
  primitives, curves, instances and materials. Model output cannot evaluate
  Python, expressions, paths, URLs or arbitrary Blender operators.
- Height/azimuth QA: metadata-based checks plus bounding-box sanity.
- Preview QA: PNG resolution, luminance, contrast, subject occupancy, bounding
  box framing, clipping, horizontal centering, and edge margins.
- Document-pack QA: evidence, conflicts, blocking fields, plausibility, OCR/CAD
  limits.
- Completion proof: binds requirement/SceneSpec and certified artifact hashes to
  successful real-Blender, gate, QA and coverage results. Schema `1.2.0` also
  binds `component_proofs.json` when trusted assembly or generated geometry
  requires it.

## What is real

- GLB QA reads the binary payload; JSON-declared accessors without backing
  bytes cannot pass. Index values must resolve to real position vertices.
- Mesh QA v1 reads vertex data from GLB accessors to compute a real bounding
  box and checks tower height, ground plane, scale, antenna count, role-node
  transforms, and approximate antenna HBA when transforms are readable.
- Spatial QA computes one real-vertex world-space AABB per primary semantic
  equipment and rejects undeclared overlaps. Antenna/RRU contact is allowed only
  when both belong to the same sector and minimum-axis penetration is at most
  0.20 m; total overlap is rejected.
- Geometry validator merges object-name counts, metadata proxies, and Mesh QA
  results; it fails when the real bounding box is unrealistic.
- Preview inspector parses PNG pixels and checks resolution, luminance,
  contrast, foreground occupancy, subject framing, clipping, centering, and
  margins.
- Camera fitting excludes beams, arrows, labels and height markers from the
  physical subject bounds. A role-specific equipment close-up and pixel gate
  are still not implemented.
- Asset import QA verifies `asset_imports`, generation modes (`parametric_generated`,
  `internal_project_generated`, `imported_glb`, `procedural_fallback`,
  `missing_file`), missing files, and fallback visibility.
- Fallback Blender is rejected by default via quality-gate policy.
- `completed` is impossible without an issued completion certificate, and the
  workflow service re-verifies the full certificate, specifications, build lock
  and artifact size/hash evidence before activation, active reads, rollback and
  artifact serving.
- Build provenance QA verifies a unique attempt/build ID, factory-startup
  command profile, immutable worker-source snapshot actually executed,
  SceneSpec hash, Blender runtime version/build hash and generated artifact
  hashes before promotion. Build lock schema `1.2.0` also self-binds trusted
  inputs: manifest catalog/files, builder catalog/profiles, exact asset bytes,
  assembly operations and GeometryPrograms.
- Version activation revalidates the issued completion certificate and every
  schema-required generated/provenance artifact before atomically committing
  `active_design.json`.
- Certificate schema 1.1 additionally hash-binds the typed
  `DesignBlueprint`, requires both blueprint coverage reports, binds persisted
  QA/geometry/GLB reports, and compares persisted `scene_spec.json` with the
  selected `SceneVersion.scene`.
- Certificate schema 1.2 preserves those checks and additionally requires a
  verified, hash-bound component proof artifact. Version activation, reads,
  rollback and artifact serving revalidate this evidence; tampering is
  fail-closed.
- Requested GeometryProgram maximum dimensions are measured from the program
  envelope before Blender. A deterministic uniform adapter can only correct this
  envelope overflow, records the adjustment and revalidates the full contract.
  The workflow aggregate is capped at 1024 program nodes.

## What is not yet real

- Mesh QA v1 does **not** verify exact per-vertex panel normals or RF propagation.
- AABB broad-phase interference is implemented for primary equipment, but exact
  triangle/BVH collision, self-intersection and engineering clearance are not.
- No full manifold, self-intersection, weld/node or structural load validation.
- No vendor-grade mesh/material validation.
- No semantic visual judgement of the preview image.
- No semantic judgement that a GeometryProgram matches the natural-language
  design description.
- No interpretation or independent validation of free-text
  `placement_context`; it is preserved as provenance only.
- Custom generated roles are not yet included in the primary-equipment AABB
  interference set, so collision-free placement is not claimed.
- No certified sector-detail preview proving that each small RRU is legible.
- No full CAD geometric validation.
- Component fingerprints and AABBs prove recorded construction evidence only;
  they do not prove semantic equivalence, manufacturer identity, RF behavior,
  loads, clearance, installation compliance or fabrication fitness.

## Fallbacks

- Missing Blender or a Blender error produces explicit fallback artefacts that
  are **not** accepted as a default result.
- A missing asset GLB can produce `procedural_fallback` if the manifest allows
  fallback.
- An `imported_glb_exact` asset with missing or changed bytes fails closed; its
  identity cannot be downgraded silently to procedural geometry.
- All fallbacks are propagated to `status.json`, the Product API, reports, and
  the frontend.
- `json_object_repaired` is not a Blender fallback: it is a bounded LLM repair
  mode and must remain visible in GeometryProgram provenance.

## Expected tests

- Unit tests force deterministic embeddings and passthrough reranking; they do
  not contact NVIDIA or Groq. The harness disables external credentials and all
  provider capabilities unless `TELECOM_STUDIO_TEST_LIVE_PROVIDERS=1` is set
  explicitly. Live-provider checks use the `provider_live` marker, so external
  HTTP failures cannot make the fast suite nondeterministic.
- `pytest -q` is the fast gate and excludes `blender_runtime`, `provider_live`
  and `browser_smoke`. An autouse guard fails if an unmarked test reaches the
  real Blender subprocess boundary. The 2026-08-10 gate completed 583 tests in
  23.86 seconds after 53 runtime cases were classified separately.
- `pytest -q -m blender_runtime --durations=30` is the serialized real-Blender
  gate. The 2026-08-10 audit exercised all 53 current Blender cases in 14 minutes
  43 seconds. It must never accept fallback artefacts as proof of a successful
  design.
- A real API/browser gate remains required for Canvas/WebGL, GLB loading,
  selection, SSE/polling, document upload, edit/version and rollback flows.
  Vitest/jsdom remains a fast contract gate, not visual runtime evidence.

- A lattice workflow with real Blender completes and passes Mesh QA.
- A workflow selecting a tower without a matching GLB exposes fallback/degraded.
- Invalid requirements (e.g., tower height > 150 m, sector count > 12) fail with
  a clean `INVALID_REQUIREMENTS` validation error.
- Viewer bundles contain no filesystem paths.
- QA reports name proxy/real modes correctly (`mesh_level_spatial_basic`,
  `mesh_level_transform_basic`, `mesh_level_basic`, `glb_parse_structural`, etc.).
- Anti-golden GLBs with JSON-only accessors, missing semantic meshes, invalid
  indices, or tampered certified artefacts fail.
- GeometryProgram contract, envelope adaptation, aggregate-budget and real
  Blender compilation/revision tests must pass.
- M0 fault tests must reject changed exact assets, manifest/catalog tampering,
  invalid component proofs/build locks/certificates and Qdrant failure without
  losing the canonical SQLite mutation.
- The current M0 tree passed 151 targeted backend integration tests, 23
  requirement/Groq tests after the live-input parser fix, the isolated
  real-Blender E2E (`1 passed`), and the real HTTP 4G generation/edit/version
  scenario with QA 1.0 and an issued certificate.
- The frontend has 157 passing Vitest tests plus green typecheck/build and a
  connected smoke on the current tree. The real generic multi-project user
  scenario remains open; no global convergence is claimed.

## Generic cognitive QA V1

- La QA générique utilise les `geometry_program_ids` réellement enregistrés par
  le worker pour prouver la couverture mesh de chaque composant, au lieu des
  rôles télécom historiques.
- Le certificat cognitif schema 1.3 lie plan, `SceneSpec` V2, observations de
  capacités, GLB, previews, QA et build lock. Il reste un certificat local
  d'intégrité, pas une approbation d'ingénierie.
- Cinq previews Blender sont publiées et hashées. La vue principale garde la
  gate pixel/framing; les quatre vues supplémentaires prouvent actuellement
  présence et provenance, pas qualité sémantique.
- Il manque une critique visuelle multimodale bornée, un solveur de relations
  spatiales et une boucle unique de réparation/régénération avant que les trois
  scénarios génériques puissent devenir une gate produit.
