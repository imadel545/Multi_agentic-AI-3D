# QA Strategy

## Rigid catalog composition proof — 2026-09-10

`tests/e2e/test_generic_rigid_composition.py` runs two actual Blender generations
using the existing internal `ANT_PANEL_4G_001`, a controlled cognitive planner
and a required `aligned_with` relation. Offsets of 0.80 m and 1.20 m change only
the driven component placement, preserving both sets of source-local vertices.
Both generated results receive certificates and persist real mesh-QA reports.
The 1.20 m output has measured position error `4.76837159e-08` m and zero
orientation-matrix error. Editing its exported placement by 0.05 m makes the
full `MeshQA.validate` result fail. Meshes detached from their placement parent,
missing/duplicate identities and mismatched orientation are rejected too.
The final real regression passed in 32.31 s. These are separate generations,
not a frontend/versioned-edit proof, and no professional source was admitted.

## Native CAD inspection proof — 2026-09-10

`tests/e2e/test_native_cad_inspection.py` uses the original local
`3D/Batiment/Mobilier/Chaise/ac3_billo2.dwg`, SHA-256
`b5d422142d550efb3e7dd0aa0eab09efd500e1333f8a93bc9d1efa1956902903`.
It skips when the real corpus or LibreDWG is absent, never substitutes a model.
Source/DXF equality covers 7,952 vertices and 12,720 face-index records; the
bounded hidden-edge int16 decoding normalizes 12,496 references. Four meshes,
12,720 triangles, node identity/hierarchy and surface areas survive Blender
4.5.12 export/reimport, with zero measured vertex displacement in the local run.
The original file SHA remains unchanged. Two actual inspection renders are
produced; materials are neutral and are not manufacturer material evidence.

The source declares INSUNITS=4 (mm), retained as 0.001 metres per unit; its height
is consequently 0.000675 m. Scale and two overlapping mesh pairs remain
unqualified. No catalog promotion or professional asset claim follows.
The initial billiard candidate was rejected for incomplete converted blocks.
An approximately 1,800-file bounded infrastructure scan did not find a complete
native telecom mesh candidate; that sampling does not prove none exists.

Unit regressions separately exercise nested DXF transforms/basepoints, closed
polymesh seams, reflections, signed face edges, units conflict, source coordinate
and vertex-order changes, mixed solids, broken/clipped/cyclic/multiple blocks
and corrupt indices. Synthetic fixtures are used only for these negative and
transform tests. Reproduce the real smoke with:

```bash
.venv/bin/pytest tests/e2e/test_native_cad_inspection.py -m blender_runtime -q
```

QA must say what it actually checks. The current pipeline is honest about its
limitations and never advertises checks it cannot perform.

## Targeted-edit regression — 2026-09-09

`tests/unit/test_targeted_edit.py` verifies stale selections, component-proof
hashes, ambiguous identities, scoped fallback and an independent workflow check
against a planner returning changes outside its allowed paths.
`tests/e2e/test_m0_trusted_assembly_recovery.py` adds a third real Blender build:
rotate S2 to 80 degrees, compare the unchanged SceneSpec fields and exported
world transforms of S1/S3 components, verify the new certificate, then reject
an edit tied to the older version. Controlled planning transports and the
explicit deterministic editing fallback are not evidence of live LLM quality.
The angular consistency regression renormalizes measured vectors before `acos`
in the evidence contract, matching the inspector; the one-degree assembly
tolerance and numerical consistency limits are unchanged.

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
- Post-export assembly QA: for `AssemblyPlan 1.1`, reconstructs glTF world
  transforms and measures every required mechanical source/target frame from
  exported component roots or dedicated exported anchor nodes. It rejects
  missing, duplicated, mismatched or moved nodes and records non-mechanical
  required connections as unevaluated. Every `resolved_from_operation`
  endpoint also requires a unique exported support node with exact identity and
  a real glTF mesh; this proves mesh existence only, not contact, fasteners,
  load transfer or manufacturability.
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
  successful real-Blender, gate, QA and coverage results. Schema `1.4.0` binds
  both `component_proofs.json` and `constraint_evidence.json` for trusted
  AssemblyPlan 1.1; schema `1.2.0` remains the non-assembly component-proof
  path.

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
- Certificate schema 1.4 additionally requires passed, canonical post-export
  constraint evidence whose workflow, plan hash and GLB hash match the certified
  scene. The evidence file is also hash-bound by the build lock; tampering or a
  schema downgrade is fail-closed.
- Requested GeometryProgram maximum dimensions are measured from the program
  envelope before Blender. A deterministic uniform adapter can only correct this
  envelope overflow, records the adjustment and revalidates the full contract.
  The workflow aggregate is capped at 1024 program nodes.

## What is not yet real

- Mesh QA v1 does **not** verify exact per-vertex panel normals or RF propagation.
- AABB broad-phase interference is implemented for primary equipment, but exact
  triangle/BVH collision, self-intersection and engineering clearance are not.
- No full manifold, self-intersection, weld/node or structural load validation.
- Post-export anchor QA does not yet measure contact patches, connector
  insertion/fasteners, triangle clearance, structural load or non-mechanical
  continuity.
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
  real Blender generation subprocess or the product readiness-probe subprocess.
  Fake probe tests replace that explicit boundary; they never weaken the guard
  globally. Older counts are historical and are superseded by the final
  current-tree collection below.
- Collection can be audited without executing Blender or a provider with
  `pytest --collect-only -q`, `pytest --collect-only -q -m blender_runtime` and
  `pytest --collect-only -q -m provider_live`. Tests that stop before Blender,
  including admission, invalid-input and terminal-persistence failure paths,
  remain in the fast gate rather than inheriting a runtime marker.
  The final 2026-08-11 collection contains 712 tests: 660 fast tests, 48
  `blender_runtime` tests and 4 `provider_live` tests; the complete fast gate
  passed in 23.68 seconds. `browser_smoke` is registered but has zero automated
  pytest cases; the browser proof remains a recorded interactive runtime gate.
- `pytest -q -m blender_runtime --durations=30` is the serialized real-Blender
  gate. The 2026-08-10 audit exercised the Blender suite in 14 minutes 43 seconds;
  the two non-Blender failure-path cases discovered during classification now run
  in the fast gate. It must never accept fallback artefacts as proof of a
  successful design.
- `TELECOM_STUDIO_TEST_LIVE_PROVIDERS=1 pytest -m provider_live` is the explicit
  external capability gate. On 2026-08-11 it validated all four configured Groq
  accounts, the bounded asset and planning contracts, and the complete Groq +
  NVIDIA + Blender product flow without fallback (4 tests in 34.69 seconds).
  The result is point-in-time runtime evidence, not a permanent availability
  guarantee.
- The convergence commit `19791be` passed a real API/browser creation gate for
  Canvas/WebGL, GLB loading, SSE progress, RAG evidence and contextual drawers.
  The later current-tree layout smoke is read-only. Document
  upload, edit/version, rollback and degraded-provider branches still require
  exhaustive browser replay. Vitest/jsdom remains a fast contract gate, not
  visual runtime evidence.

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
- The convergence commit `19791be` passed the complete fast gate plus the isolated
  real-Blender assembly/edit/version E2E (`1 passed in 44.39 s`) and the
  connected browser 4G creation scenario with QA 1.0 and an issued certificate.
- The frontend has 180 passing Vitest tests plus green typecheck/build. A
  read-only current-tree layout smoke loaded the certified GLB at 1440 x 1000
  and 1047 x 2748; the connected provider/generation smoke belongs to the
  immediately preceding convergence tree. The real generic multi-project user
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

## CAD conversion benchmark — 2026-09-09

### Result and scope

**No admissible mesh or neutral master was produced. No asset was promoted.**
Three real antenna/radio/support DWGs were converted in a temporary directory.
All default conversions returned exit code 0, but the resulting solid entities
had empty SAT/SAB payloads and ezdxf extracted zero mesh bodies. This is a
content-validation failure, not evidence that the entire source library is unusable.
Original CAD files were only read; rights remain unverified.

### Tools and sample

Host tools: LibreDWG `dwg2dxf` 0.13.3, Python 3.12.7, ezdxf 1.4.4.
ODA Drawings Explorer bundle 27.1.0.0 was inspected separately. FreeCAD and
ODAFileConverter were not found in the installed applications/PATH checked.

Paths below are relative to `assets/library/raw/maj_des_blocs/`:

| Source | SHA-256 |
|---|---|
| `3D/Antenne/Kathrein/739 506/739506.dwg` | `7556068173c425106ad84f33cc62d90e9f1ff02c2eb23e849e153d3501f65bde` |
| `3D/Baie/Ericsson/Outdoor/RRU/2203/Radio_2203.dwg` | `32f30bbb60477cadef0b17171a5d7297f53e70767395f28c1cbe4969a3887379` |
| `3D/Antenne/_Support/Volx/Support RRU/DAL16RRUZ3R3BD.dwg` | `e718eb5743b2ee308d46e89416f8b3b38b01cbd3acdbfb6113fc36d1c97fa840` |

| Sample | Single conversion wall time | DXF bytes | 3DSOLID entities in DXF | Extracted mesh bodies |
|---|---:|---:|---:|---:|
| Kathrein 739506 | 0.03 s | 240418 | 1 | 0 |
| Ericsson Radio 2203 | 0.02 s | 306860 | 11 | 0 |
| Volx DAL16RRUZ3R3BD | 0.01 s | 139454 | 5 | 0 |

Times cover the subprocess only, rounded to hundredths; these are single local
observations, not throughput guarantees. All three DXFs declare millimeters
(`INSUNITS=4`). INSERT/block structure remains present, but solid completeness,
world-space dimensions, hierarchy fidelity and attachment surfaces are unverified.
Every inspected solid has `len(sat)==len(sab)==0`.

A separate Radio 2203 conversion with `--as r2000` also returned 0, but retained
no 3DSOLID entities. Direct `dwgread -O JSON` found 11 solid entities; the first
reported `acis_empty=1` with no decoded ACIS payload. These observations do not
prove the original DWG contains no recoverable geometry in another CAD kernel.

### Reproduction

Run from the repository root; outputs always use a fresh temporary directory.
Repeat the source assignment for the other two paths above.

```sh
cad_probe_dir=$(mktemp -d /tmp/cad-conversion-XXXXXX)
cad_probe_source='assets/library/raw/maj_des_blocs/3D/Baie/Ericsson/Outdoor/RRU/2203/Radio_2203.dwg'
dwg2dxf -o "$cad_probe_dir/default.dxf" "$cad_probe_source"
dwg2dxf --as r2000 -o "$cad_probe_dir/r2000.dxf" "$cad_probe_source"
dwgread -O JSON -o "$cad_probe_dir/probe.json" "$cad_probe_source"
.venv/bin/python - "$cad_probe_dir/default.dxf" <<'PYCODE'
import sys
import ezdxf
from ezdxf.acis import api

doc = ezdxf.readfile(sys.argv[1])
solids = [e for e in doc.entitydb.values() if e.dxftype() == "3DSOLID"]
print("units", doc.units, "solids", len(solids))
for entity in solids:
    print("payload", len(entity.sat), len(entity.sab))
    for body in api.load_dxf(entity):
        print("mesh sizes", [(len(m.vertices), len(m.faces))
                             for m in api.mesh_from_body(body)])
PYCODE
```

Original scratch evidence is local and ephemeral:
`/var/folders/8w/vmnlvcp94ys003dwvn51llp00000gn/T/cad-source-slice-0js2cvz3/benchmark.json`.
Sibling files `0.dxf`, `1.dxf`, `2.dxf`, `radio2000.dxf`, `radio.json` retain
intermediates. This report preserves the material results if scratch is removed.

### Existing DXF alternatives

All 12 source DXFs were parsed. `3D/Pylone/Leclerc/1500/Plateforme.DXF`
(SHA-256 `3fe4264eae977e6d0560531d14c9ac4cb7ee4827ddfc0b2644e1868e20e5222a`)
has 4630 POLYLINE entities with flags 0, six SOLID entities, unspecified units,
and no polyface meshes. A DXF SOLID entity is not proof of an ACIS 3DSOLID.
The folder label does not qualify a solid platform.

Five Camusat TC120 platform sheet drawings (150003A/H/I/J/K) contain 2D
lines/circles/arcs and declare millimeters. They are candidates for a governed
profile reconstruction only after thickness and technical intent are evidenced;
no extrusion thickness was invented. The remaining signage/tree/ladder DXFs
were not promoted as equipment meshes. Full source hashes and entity counts are
in the scratch benchmark inventory.

### Decisions and remaining route

- Reject this tested LibreDWG-to-DXF-to-ezdxf route for exact promotion of these
  three samples: subprocess success did not preserve usable solid payloads.
- Reject R2000 down-conversion as a repair for Radio 2203: solids disappeared.
- Reject inferred extrusion or dimensions as professional source evidence.
- Keep LibreDWG for metadata/probing and raw candidates in quarantine.
- ODA opened Radio 2203 and exposed Export with 3D DWF as its default format.
  UI automation reported a user/app-state change before export; interaction was
  stopped. No ODA export, tessellation quality or neutral conversion was proved.
- A bounded next experiment must obtain a real neutral export or complete a
  controlled ODA mesh export, then compare body counts, units, bounds, block
  placements and visual completeness. Such a mesh would still require rights,
  provenance, anchors and qualification QA before product use.

No purchase, account creation, runtime conversion implementation, qualified
manifest mutation or professional fidelity claim is part of this benchmark.

### Generic exact-source runtime — 2026-09-10

`tests/e2e/test_generic_exact_asset_reuse.py` uses a controlled cognitive planner,
real catalog retrieval, the generic compiler and real Blender. Final execution:
1 passed in 13.95 s. It checks certificate 1.3 issuance, independent GLB world
transforms for the requested +1 m Z placement, every source/export POSITION
vertex within 1e-6 m, PBR equality, exact-import provenance and build-lock pins.
Artifacts: `/tmp/studio-generic-exact-reuse-20260910-final/test_generic_exact_reuse_reach0/`;
log: `/tmp/studio-generic-exact-reuse-20260910-final.log`. The preview was inspected
locally and shows the internal plain panel. This is source-preservation evidence,
not manufacturer geometry, live LLM reliability or professional assembly proof.

Admission tests reject altered source bytes/manifests, missing geometry
qualification or transform permissions, fallback, scale changes, disallowed
rotation, missing placement, excess quantity and exceeded envelopes. The
admission observation explicitly states that Blender has not executed yet.
Frontend visual acceptance for the new free-intent/provenance controls is pending.

Final fast regression: **697 passed, 53 deselected in 23.02 s**
(`/tmp/studio-reuse-fast-clean-20260910.log`). The excluded markers cover external
provider, browser and Blender suites; the exact-source Blender test was executed
separately as above. Frontend: **180 tests passed**, TypeScript check and production
build passed. Ruff and whitespace checks passed on the changed implementation.
The revision regression also verifies retained selected-asset metadata; historical
cognitive plan hashes remain stable when optional placement is absent.

### Mainline recovery and raw discovery — 2026-09-10

Final fast suite: **710 passed, 53 deselected in 23.74 s**, log
`/tmp/studio-mainline-final-fast-20260910.log`; Ruff/whitespace passed. No Blender
geometry or frontend rendering changed in this tranche. Origin tests cover all six
origins on five tables, idempotent legacy migration, product-only recall/projection,
forbidden identity reassignment and provenance fingerprint invalidation. Status
origin is tested through pending/failure persistence. Both host databases passed
SQLite integrity checks after selective deletion, compaction and migration.

Recovery root: `/Users/imad/Desktop/Multi_agentic-AI-3D-recovery/20260910-mainline`.
`snapshot-manifest.json` verifies 2,865 stable files; SQLite ephemeral sidecars
are excluded after the Backup API destinations are closed. `inventory.json`
contains schemas, original counts and exact pytest IDs. `cleanup-result.json`,
`cleanup-applied.py`, `clean-memory-projection.json` and `retired-collections.json`
record applied actions; `RESTORE.md` documents selective recovery.

`library-search-before.json` and `library-search-after.json` compare 13 real
queries across the raw catalog. Confirmed improvements include tree/StreetMacro
false-positive removal, explicit 36m over 35m, Volx support over another maker,
platform metadata and spiral-staircase discovery. The bench query remains empty;
no aggregate semantic-accuracy or geometry-quality score is claimed. Warm queries
complete in roughly 3–33 ms on this host; index initialization is about 120 ms.
An isolated real Uvicorn HTTP smoke verifies four of these queries and public
quarantine/evidence fields (`library-http-smoke.json`), without altering raw CAD.

Static embedding rebuilding failed with HTTP410 for the configured retired model.
The alternative benchmark sent only the existing 25 static documents and six
queries, no raw CAD. Both batch trials timed out after about 90 s total each;
`embedding-benchmark.json` records the failed attempts. One separate single-query
Nemotron 3 response is insufficient to change the configured default. No static
neural index replacement is declared successful.

## Tower access evidence — 2026-09-12

Quand une tour treillis porte un `TowerAccessGeometryProfile` et une demande
d'échelle ou de plateformes, le résultat ne peut être activé sans
`tower_access_evidence.json`. L'inspecteur relit les positions GLB exportées
et vérifie l'identité sémantique et le hash du profil, deux rails, le minimum de
barreaux, leur largeur, leur espacement et leurs bornes, puis chaque plateau
demandé: altitude du dessus, largeur, profondeur, garde-corps, plinthes et
supports. Il teste également les chevauchements AABB de plateau avec les
équipements principaux.

Cette vérification est une mesure de géométrie exportée, non une validation
structurelle ou de sécurité. Les collisions triangle/BVH, les contacts, les
charges, l'antichute, les détails de fixation et la conformité de chantier
restent hors périmètre. Le certificat 1.5, le build lock et l'activation de
version lient cette preuve et la refusent en cas de hash, scène ou relecture
incohérente.
