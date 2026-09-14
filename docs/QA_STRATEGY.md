# QA Strategy

QA states exactly which layer was measured. Current point-in-time runtime
evidence lives in [PROJECT_SOURCE_OF_TRUTH.md](PROJECT_SOURCE_OF_TRUTH.md); this
document defines durable gates and avoids frozen test counts.

## Gate levels

- **Contract and requirements:** Pydantic validation, field evidence,
  contradictions, bounds, and `RequirementSpec -> DesignBlueprint -> SceneSpec`
  coverage.
- **Planning and generation:** catalog admission, trusted `AssemblyPlan`, bounded
  `GeometryProgram`, pre-Blender quality gates, and explicit provider/fallback
  provenance.
- **Exported geometry:** GLB binary parsing, real vertex bounds, semantic mesh
  coverage, transforms, basic AABB interference, and exported anchor evidence.
- **Presentation:** PNG pixel/framing checks and frontend contract tests.
- **Completion:** certificate and build-lock hashes are revalidated before
  activation, rollback, active reads, and artifact serving.

Passing a lower level never implies a higher one. Contract tests do not prove a
provider is reachable, a Blender test does not prove browser UX, and a pixel
check does not certify engineering fitness.

## What the automated QA measures

- GLB integrity reads container chunks, buffers, buffer views, `POSITION` data,
  optional indices, finite values, ranges, primitive completeness, and semantic
  entity mesh coverage. JSON declarations without backing bytes fail.
- Mesh QA computes real world-space bounds and checks ground, scale, tower
  height approximation, object counts, readable role transforms, approximate
  antenna height/azimuth, and broad-phase AABB interference for primary
  equipment. Same-sector antenna/RRU contact has one declared bounded exception.
- Trusted assembly QA binds manifest/catalog and builder snapshots, exact asset
  hashes, parameters, anchors, connectors, operations, and isolated-worker
  revalidation. Post-export QA reconstructs glTF transforms and measures required
  mechanical frames or explicit generated support nodes.
- Profile QA requires declared panel/RRU subparts. Segment QA measures generated
  cylindrical endpoints from Blender vertices and fails above the configured
  tolerance.
- `GeometryProgram` QA enforces graph integrity, references, metre units, typed
  primitives and transforms, envelopes, operation allowlists, and resource
  budgets. Model output cannot execute Python, paths, URLs, expressions, or
  arbitrary Blender operations.
- Preview QA measures resolution, luminance, contrast, occupancy, framing,
  clipping, centring, and margins. Camera fitting excludes annotations from the
  physical subject bounds.
- Document-pack QA checks source evidence, conflicts, blocking fields,
  plausibility, archive limits, and the explicit OCR/CAD capability boundary.
- Completion certificates bind requirements, `SceneSpec`, generated artifacts,
  QA reports, build lock, component proofs and, when required, constraint or
  tower-access evidence.

## What the QA does not prove

- No structural, RF, wind-load, foundation, fastener, safety, fabrication, or
  regulatory approval.
- No exact vendor identity, material validation, connector mating, electrical
  continuity, manifoldness, self-intersection, or triangle-level clearance.
- No general semantic judge that the exported model matches arbitrary natural
  language. Custom roles are not all covered by the primary-equipment collision
  set.
- Preview checks are pixel and framing checks, not multimodal semantic review or
  professional visual acceptance.
- Native CAD metadata, a successful converter exit code, and a GLB roundtrip do
  not qualify ACIS/B-Rep geometry. Admission still requires source, units,
  hierarchy, geometry, visual, rights, anchor, and integration evidence.

These limits are maintained in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Fallback rules

- Missing or failed Blender produces explicit non-accepted fallback artifacts;
  the quality policy rejects them by default.
- Missing exact-import bytes or a hash mismatch fails closed. A manifest may
  allow an explicitly reported procedural fallback only for that asset.
- LLM and retrieval degradation remains visible in status, reports, Product API,
  and frontend. `json_object_repaired` is recorded as a model-output repair, not
  as Blender proof.
- `completed` requires an issued certificate and successful persisted
  revalidation. Tampered or incomplete historical results are not served as
  verified designs.

## Test gates

Run the fast deterministic gate:

```bash
.venv/bin/python -m pytest -q
```

The harness disables resolved external credentials and prevents unmarked tests
from starting real Blender or its readiness probe. Unit tests use deterministic
embeddings and passthrough reranking.

Run external gates explicitly:

```bash
.venv/bin/python -m pytest -q -m blender_runtime
TELECOM_STUDIO_TEST_LIVE_PROVIDERS=1 .venv/bin/python -m pytest -q -m provider_live
```

`browser_smoke` remains a separate recorded interactive gate. Frontend checks
are:

```bash
npm --prefix apps/frontend run test -- --run
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend run build
```

Collection size and execution time vary with the current tree and host. Audit
markers with `pytest --collect-only`; never reuse an old total as proof.

## Required regression behavior

- Invalid requirements and explicit contradictions fail before RAG, planning,
  `SceneSpec`, and Blender.
- Anti-golden GLBs with missing bytes, bad indices, missing semantic meshes, or
  changed certified artifacts fail.
- Exact assets, manifests, build locks, component proofs, constraint evidence,
  certificates, revisions, and stale edit selections fail closed when altered.
- A successful real-Blender path must export a usable GLB, pass required QA and
  issue a certificate. Fallback artifacts cannot satisfy the same assertion.
- Qdrant failure must not lose the canonical SQLite mutation; projection state
  remains explicit and recoverable.
- Viewer bundles expose artifact URLs and user-readable states without local
  filesystem paths.
- Browser acceptance must exercise the real API, visible GLB or explicit
  preview/error fallback, navigation restoration, attachments, relevant edit and
  rollback actions, and console/network failure states.

## Tower access evidence

For a lattice tower with a `TowerAccessGeometryProfile` and requested ladder or
platforms, activation requires `tower_access_evidence.json`. The inspector
re-reads exported GLB positions and verifies profile identity and hash, rails,
rungs, platform elevations and dimensions, guardrails, toe boards, supports,
and broad-phase overlap with primary equipment. The certificate and build lock
bind that report.

This evidence confirms exported geometry only. It does not validate structural
loads, fall protection, fixings, construction safety, or site compliance.
