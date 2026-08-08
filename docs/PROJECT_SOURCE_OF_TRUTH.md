# Project Source Of Truth

Active master document. All other documentation must stay aligned with this
file.

## Product

Local-first, single-user studio to turn a telecom brief or document pack
(PDF, ZIP, DXF, images) into a `SceneSpec`, Blender/GLB artefacts, QA, versions,
and rollback.

The end goal is a chat-first and 3D-first product. A real-backend frontend
rework exists under `apps/frontend`, but it is not an accepted product gate.

## What the project is not

- Not a multi-user SaaS.
- Not a dev dashboard.
- Not an LLM-free-form Blender code generator.
- Not marketing proof where a fallback is presented as a real result.
- Not yet a complete vendor-grade asset library. A large local CAD corpus is
  catalogued, but remains quarantined until rights and geometry are qualified.

## Current backend

- FastAPI exposes design workflow, document-pack, RAG, memory, asset, and
  Product APIs.
- `/designs` and `workflow_id` are the stable product contract for the next
  frontend. Do not add `/projects`, `/runs`, `job_id`, or a new state model
  unless a later architecture decision proves it necessary.
- LangGraph is used for prompt workflows, document-pack generated requirements,
  scene revision generation, and bounded asset adaptation. `SceneEditAgent`
  executes a checkpointed four-node adaptation graph: discover declared
  capabilities, plan, validate, then mutate `SceneSpec`. Version bookkeeping
  remains service-level.
- Runtime traces classify every step as `llm_decision`,
  `deterministic_specialist`, `service`, `quality_gate`, or `external_tool`,
  with explicit decision authority. This is a controlled expert workflow, not
  yet a dynamic swarm/supervisor architecture.
- `compose_design_blueprint` now creates a generic typed planning intent after
  requirement validation. Its typed specialist DAG runs asset composition as a
  fail-closed gate, then executes the independent RF-layout and structural
  specialists and, when an out-of-catalog component is requested, the
  geometry-generation policy specialist through bounded parallel fan-out. Every
  decision records its dependencies and execution wave; unknown domains, cycles,
  handler exceptions, mismatched outputs, and failed gates are rejected before
  dependent work.
  The blueprint records component quantities/asset queries/fidelity/placement,
  persists `design_blueprint.json`, and proves
  `RequirementSpec -> DesignBlueprint -> SceneSpec`. `SceneSpec`, including any
  embedded `GeometryProgram`, remains the sole 3D generation source of truth.
  Routing, contracts and gates are deterministic. GPT-OSS can select only
  supplied planning/asset candidates, or author primitives, polygonal curves,
  instances, materials and transforms inside the bounded GeometryProgram
  contract; it cannot add a specialist, execute Python or call arbitrary Blender
  operations.
- Groq `openai/gpt-oss-120b` is used when a real key is configured; otherwise
  explicit deterministic extraction. Extraction, planning and asset selection
  now share one validated request policy: HTTPS outside localhost, explicit
  `low|medium|high` reasoning effort, bounded completion budgets, strict JSON
  Schema where supported, `stream=false`, no tool use, local Pydantic
  validation, and user-visible deterministic fallback diagnostics.
- `RequirementSpec` carries typed field evidence, candidate values, assumptions,
  conflicts, and confirmation fields. Explicit unresolved contradictions block
  the natural-language graph before RAG, asset selection, `SceneSpec`, and
  Blender; a late value is accepted automatically only when the prompt marks it
  as an explicit correction.
- GPT-OSS is the bounded decision layer for ambiguous extraction, controlled
  RAG candidate arbitration, asset selection, edit interpretation and typed
  out-of-catalog geometry. Geometry authorship is declarative data, never Python:
  local validation owns units, references, transformations, envelope bounds and
  a 1024-node aggregate workflow budget before the deterministic Blender compiler
  executes it. Governance constrains scope, records evidence and preserves
  rollback; invalid geometry fails before Blender.
- Public product responses expose GPT-OSS truth through `extraction_provider`,
  `llm_provider`, `llm_available`, `llm_fallback_used`, and
  `llm_fallback_reason`; the frontend must display fallback/degraded status
  instead of guessing.
- `/viewer-bundle` also exposes bounded GeometryProgram provenance: generator,
  model, structured-output mode, source prompt hash, source description,
  placement context, requested maximum dimensions, deterministic adjustments and
  declared limitations.
- Primary RAG: NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` at 1024 dimensions.
- Provider configuration is not runtime proof. `/studio/summary` reports
  `configured_unverified` until a real embedding/search succeeds,
  `primary_nvidia_embedding` only after success, and
  `configured_but_last_operation_failed` after an operational failure.
- RAG fallback policy: no automatic local embedding model in the product path.
  Deterministic hash is allowed only for tests/bootstrap or explicit degraded
  mode; it is not product-quality retrieval.
- Reranker: NVIDIA API by default with visible fail-open degraded passthrough.
  No hidden local model is downloaded or loaded by the product runtime.
- RAG evidence is written to `rag_evidence.json` and exposed through
  `/viewer-bundle`; it lists retrieved sources, controlled candidate hints,
  reranker status, and limitations.
- Memory: local SQLite is authoritative. Qdrant is an optional derived
  projection published through a durable SQLite outbox. A canonical mutation
  and its projection intent commit in the same SQLite transaction; failed or
  interrupted projection attempts remain visible, retryable and recoverable at
  startup. Incompatible legacy runtime collections are preserved and new
  vectors are routed to provider/dimension-versioned collections.
- Document-pack: synchronous direct multi-file or ZIP intake with bounded
  archive assembly, limited PDF/OCR/DXF extraction, consolidation, conflicts,
  corrections, and QA. A missing or tower-incompatible foundation blocks
  generation before a workflow is created; the user must confirm a supported
  foundation instead of receiving a predictably failed Blender workflow. The
  summary, QA response, generation gate, and correction UI consume the same
  blocking-field list.
- Blender: real generation when Blender is found; Blender fallback is rejected
  by default for quality (`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0`).
  "Found" means a real background/factory-startup smoke succeeds, not merely
  that an executable path exists. The smoke result is cached against the binary
  identity so the Product API cannot advertise a crashing Blender runtime as
  available.

## Current frontend

- `apps/frontend` is a Vite + React + TypeScript product rework connected to the
  real FastAPI backend with Zod contract validation.
- The rejected dashboard kernel has been removed from the active layout. The
  current baseline is conversation-first, 3D-dominant, and uses contextual
  drawers for agent history, QA, alerts, deliverables, and versions.
- Raw workflow ids, runtime capability counts, permanent stage grids, and raw
  QA/RAG JSON are not part of the primary product surface.
- It consumes `/designs` + `workflow_id`, not `/projects`, `/runs`, `job_id`, or
  a new state model.
- The command field starts empty and never injects demo content. When a verified
  design is restored, the same composer switches to bounded design adaptation;
  the user can explicitly switch back to a new design.
- The viewer loads only backend artifact URLs and must show either a visible GLB
  or an explicit backend preview/error fallback during smoke.
- Technical inspection aids (azimuth arrows, beams, height markers and labels)
  are hidden by default and explicitly toggleable. The viewer separates their
  count from physical component count so diagnostic geometry is not presented
  as telecom equipment.
- Visual/runtime smoke on 2026-07-24 restored `wf_3c86a159cd7b`, loaded its real
  Blender GLB, proved visible rendering and camera fit, exercised the contextual
  agent, QA, issue, artifact, version, and CAD-library drawers against real
  backend responses, exposed no local filesystem path, and produced no browser
  console error. The broader frontend gate still requires one recorded pass for
  every mutation flow listed in `FRONTEND_ACCEPTANCE_CRITERIA.md`.
- A second 2026-07-24 acceptance smoke proved real Groq
  `openai/gpt-oss-120b` extraction, completed Blender/GLB generation,
  checkpointed bounded edit, version creation, rollback, document-pack
  ingestion, explicit foundation blocking/correction, and document-pack
  generation. These mutations were verified at Product API level; the remaining
  frontend limitation is replaying every mutation through browser controls in
  one recorded session.
- The 2026-07-30 audit extended the then-current frontend suite, typecheck,
  production build and npm audit, then restored real workflow
  `wf_a6660b81b929` against the
  current API. Desktop/mobile rendering showed its verified Blender model; a
  separate Chrome headless run without WebGL displayed the real backend preview
  and the explicit WebGL warning. All requested product endpoints returned 200
  and no application console error was observed.
- Old dashboard patterns remain rejected.

## Current assets

- 13 manifests, all generation-eligible in the current qualified catalog.
- 12 GLB files present.
- The procedural-only dual-band panel intentionally has no companion file and
  is not reported as a missing asset file.
- 0 tower without a local GLB.
- Expected `/assets/inventory` status: `qualified_mixed_catalog`.
- 13 manifests are generation-eligible: 3 authorize an exact GLB import and 10
  authorize SceneSpec-driven parametric generation; 0 is `reference_only`.
  The cable-tray family is now qualified through its typed parametric route,
  not through an exact mesh import. The bracket companion GLB is not imported,
  but its typed procedural builder and connector contract are
  generation-qualified.
- Exact import authorization is fail-closed: the manifest pins SHA-256, units,
  dimensions, pivot, orientation and mesh-integrity review. A changed file is
  rejected; it is not silently replaced by procedural geometry.
- The three historically missing towers (monopole, rooftop, small-cell) are now
  internal project generated assets produced with Blender.
- Current assets are internal/CC-BY and not vendor-grade.
- Towers are generated parametrically by default. In the product planning path,
  GLB import happens only when the manifest authorizes and the planner selects
  `imported_glb_exact`.
- The scene planner now stamps the manifest-authorized generation mode and
  reason into `SceneSpec`. A 4G scene can therefore assemble qualified panel and
  GPS GLBs while keeping the tower, RRU and power cabinet parametric. The 5G
  panel and RRU companion GLBs are not imported because their orientation is
  not qualified; this prevents silent non-uniform distortion.
- The generic 5G panel and RRU carry typed, bounded geometry profiles in their
  manifests and resolved `SceneSpec`. `detail_level` is operational:
  high/medium/low select different declared sub-part counts while preserving
  dimensions and placement. Their fidelity is `technical_generic`, never
  `vendor_qualified`.
- The RRU adaptation profile exposes bounded vertical/radial mounting offsets.
  The LLM may select declared values only; the deterministic Blender builder
  owns topology and never executes generated Python.
- Every manifest references an explicit adaptation profile. The versioned
  catalog under `assets/capabilities/adaptation_profiles.json` declares the
  editable parameter, JSON pointer, value type, bounds, effect, and execution
  tool. The LLM cannot add a path or tool outside the resolved scene profile.
- Parametric towers support bounded reconstruction; sector antennas support
  height/azimuth/tilt/beam/cable/label layout; cabinet/GPS accessories support
  verified position, rotation, and positive XYZ scale. Opaque mesh topology
  editing and arbitrary materials are not claimed.
- The local `assets/library` corpus is a lossless copy of `MAJ des Blocs`:
  11,974 files (11,531 unique contents; 443 duplicates by SHA-256), including
  2,834 paths claimed as 3D and 8,514 as 2D. These directory labels are
  provenance only, not geometry proof.
- Catalog, search and DWG probe APIs are operational, but every imported
  library file is currently `quarantined_unverified`: 0 is generation-eligible.
  No global source licence was detected. Raw files and generated indexes remain
  local and ignored by Git.
- Catalog schema `1.1.0` links nearby source preview images by deterministic
  filename provenance: 7 CAD files have 15 preview links. A linked image is a
  retrieval aid only; it is not geometry, scale, licence or conversion proof.
- Real probes show DWG `3DSOLID`/ACIS content. LibreDWG can inventory entities,
  but it is not accepted as a B-Rep tessellator. A controlled ACIS/OpenCascade,
  ODA or vendor-CAD conversion path plus unit/material/geometry QA is required
  before any entry can become a production manifest.
- The targeted 2026-08-06 probe of catalog file
  `lib_590cb8d275d2c900a36c` (`Axians_Nedea_36m.dwg`) found 99 `3DSOLID`,
  440 `INSERT`, millimeter `INSUNITS`, a conflicting display-unit label and no
  mesh-convertible entity. It therefore remains quarantined and requires an
  ACIS B-Rep bridge; retrieval or LLM selection cannot make it Blender-ready.
- ODA Drawings Explorer 27.1 is installed locally and can visually inspect the
  representative DWG, but its application bundle exposes no verified headless
  STL/DAE export route. Its presence therefore does not make conversion active.

## Current 3D and QA

- `SceneSpec`, including its selected manifests, `AssemblyPlan` and optional
  `GeometryProgram` values, is the source of truth for geometry. Fixed
  parametric builders and the deterministic GeometryProgram compiler consume it.
- `AssemblyPlan` schema `1.1.0` is executable rather than descriptive: it binds
  manifest and builder snapshots, allowed parameters, anchors, connectors and
  hashed operations. The isolated Blender worker independently revalidates the
  current manifest catalog, exact asset bytes, builder registry and operations
  before constructing geometry. An exact import without this trusted plan fails
  closed.
- GLB is only the exported viewer result, not the source of truth.
- Blender produces `design.glb`, `preview.png`, `scene_metadata.json`, and
  `component_proofs.json` when trusted assembly or generated geometry requires
  it, and a runner-owned `build.lock.json` schema `1.2.0`. The lock contains the
  isolated attempt/build ID, raw SceneSpec hash, immutable worker-bundle hash,
  Blender runtime identity, artifact hashes and a self-bound `trusted_inputs`
  envelope for manifest/catalog, builder profiles, exact files, assembly
  operations and GeometryPrograms. Blender starts in background factory mode
  and every retry uses a fresh staging directory. The workflow also persists
  `requirement_coverage.json`,
  `completion_certificate.json` and the critical QA reports.
- `component_proofs.json` records each catalog or generated component, its
  semantic strategy (`reuse`, `adapt`, `compose` or `procedural_generate`),
  geometry source, resolved parameters, transform, bounds, geometry
  fingerprint, executed assembly operations and local QA. These are auditable
  construction proofs, not vendor or engineering certification.
- Successful revisions also persist `adaptation_plan.json`,
  `adaptation_capabilities.json`, `scene_patch.json`, and `scene_diff.json`.
  Blender still regenerates from the validated `SceneSpec`; the LLM may author a
  typed GeometryProgram but never emits or executes Python.
- Real QA categories:
  - `glb_parse_structural`
  - `mesh_level_spatial_basic` — readable semantic transforms plus real-vertex
    world-space AABB interference screening for antennas, RRUs, GPS and cabinets
  - `mesh_level_transform_basic` — GLB accessors plus readable role transforms
    and approximate antenna HBA when transforms are available
  - `mesh_level_basic` — real bounding box from GLB accessors
  - `object_name_based_geometry`
  - `metadata_based_height_azimuth`
  - `preview_pixel_framing_basic`
- Mesh QA v1 checks: GLB parse OK, tower height approximation, scene above
  ground, scale realism, antenna count, readable object transforms when present,
  approximate HBA from antenna node transforms when possible, RRU/cable/cabinet/GPS
  presence, concrete pad presence when requested, real label object presence, and
  primary-equipment AABB interference. Same-sector antenna/RRU contact is the only
  declared primary-equipment overlap allowed by this gate; its minimum-axis
  penetration is bounded to 0.20 m and a total overlap is rejected.
- GLB integrity QA reads actual binary buffers, buffer views, `POSITION`
  accessors and optional index accessors. It rejects JSON-only accessor claims,
  non-finite vertex values, out-of-range indices, incomplete primitives, and
  semantic entities that have no valid mesh in their node tree.
- For profiled internal panel/RRU generation, structural QA also requires the
  declared radome/chassis/mount/port and enclosure/heatsink/mount/connector
  sub-parts. A single semantic box can no longer satisfy these profiles.
- Before export, every generated cylindrical member records its requested
  endpoints and is measured from transformed Blender mesh vertices. Generation
  hard-fails above 1 mm endpoint error; this protects lattice legs/braces,
  mounting members, beams, arrows, ladders and similar segment primitives.
- `RequirementCoverageReport` proves the critical `RequirementSpec -> SceneSpec`
  mapping. A planning override is accepted only when an applied, typed decision
  carries matching evidence.
- A workflow may be `completed` only after `certify_completion` issues a
  certificate binding requirement/SceneSpec hashes,
  GLB/preview/metadata/build-lock hashes,
  real-Blender mode, requirement coverage, both quality gates, GLB binary
  integrity, geometry QA and preview QA. The persistence boundary re-verifies
  those hashes before activation.
- Certificate schema `1.2.0` is required when `AssemblyPlan 1.1` or a
  `GeometryProgram` requires component proof. It additionally certifies
  `component_proofs.json` and the `component_proof_verified` check. Legacy
  schema `1.1.0` remains valid only for scenes that do not require this M0
  evidence.
- Persisted completion is also revalidated on active status reads, rollback and
  artifact serving: full certificate schema/check set, RequirementSpec/SceneSpec
  hashes, selected `SceneVersion.scene`, build-lock evidence, every certified
  artifact hash and, for schemas 1.1/1.2, critical report hashes. A historical
  result without this chain becomes `legacy_unverified`; a changed active
  artifact becomes `integrity_failed`. Files remain on disk but are not served.
- Mesh QA v1 does **not** verify exact antenna azimuth from vertices and does
  **not** perform collision/RF/structural wind-load validation.
- Preview QA parses PNG pixels and checks subject occupancy, framing, clipping,
  centering, contrast, and resolution. It is still not semantic visual review.
- Preview camera fitting excludes beams, azimuth arrows, height markers and
  labels so annotations cannot inflate physical subject bounds. A dedicated
  equipment close-up/role-pixel gate is still missing.
- QA does not yet finely validate materials or vendor exact mesh dimensions.
- GeometryProgram contract QA proves its graph, typed primitives, transforms,
  meter units, requested maximum envelope and resource limits. The exported GLB
  still has no semantic judge proving that the model matches the natural-language
  intent; placement context is preserved as provenance but is not interpreted or
  independently validated, and custom roles are not yet included in the
  primary-equipment AABB gate.
- Do not call this QA "advanced geometry".

## Events and runtime

- Events are persisted in JSONL and pushed through an in-memory queue per
  workflow while the local workflow thread is alive.
- `/events/stream` is now `push_sse`: it replays persisted JSONL events first,
  then streams live queue events until `workflow_completed` or
  `workflow_failed`.
- Reconnect cursors seed the already-seen durable prefix. If a slow subscriber's
  bounded in-memory queue drops events, a sequence gap triggers JSONL catch-up
  before the terminal event is emitted.
- Polling recovery can request `/events?after_sequence=N`; the frontend batches
  and deduplicates only the returned delta. SSE tolerates two transient errors
  before the third switches to visible polling, and recovery restores SSE.
- Orchestration nodes emit `node_started`, then `node_completed`,
  `node_failed`, or `node_skipped` with `node`, `phase`, `status`, human label,
  progress message, detail, `duration_ms`, warnings, and errors.
- Product events include `artifact_ready`, `qa_completed` / `qa_failed`, and
  `user_issue_created` when relevant.
- Every public workflow event carries `event_id`, `workflow_id`, `timestamp`,
  `event_source`, and payload fields for `phase`, `node`, `human_label`,
  `progress_message`, `status`, `duration_ms`, warnings, errors, and
  artifact refs.
- `/current-operation` exposes `current_phase`, `current_node`, and
  `event_source`, plus frontend labels, terminal/running flags, last event time,
  and available actions.
- During an edit, the existing root `status.json` persists an
  `active_operation`; a reconnect therefore sees `running` instead of the old
  terminal design status. Failed/rejected edits restore the previous active
  version and status.
- `active_design.json` is the canonical, atomically published active-version
  commit. It is created only for a completed version whose completion
  certificate, persisted `SceneVersion.scene`, schema-required certified
  artifacts and, for schemas 1.1/1.2, critical QA reports revalidate.
  `active_version.json`, root status and terminal/product events are
  compatibility projections; a failure in one of them cannot downgrade the
  canonical commit.
- Startup recovery distinguishes an interrupted initial generation from an
  interrupted revision. Initial generation fails without a valid product
  version; an interrupted revision marks only its candidate version failed,
  restores the last completed active version, clears `active_operation`, and
  emits `edit_patch_rejected`.
- LangGraph checkpoint threads are deleted after terminal workflows and
  terminal adaptation decisions, and bounded
  at startup. SQLite checkpoint pages are compacted only when at least 64 MiB
  and 25% of the file are reclaimable, preventing deleted graph state from
  retaining unbounded disk space without vacuuming every startup.
- Deleting a design purges its workflow/design/error memory, unlinks
  document-pack references, removes its checkpoint threads and invalidates the
  complete derived Qdrant memory projection. SQLite remains canonical; the
  durable projection outbox survives Qdrant failure and startup interruption,
  retries without creating a second authority, and
  `/memory/vector/reindex` rebuilds the remaining projection.
- Qdrant accepts logical search collections only; runtime invalidation also
  removes abandoned build collections and serializes concurrent reads/writes.
  The Docker server is loopback-bound and pinned to `v1.18.0`, matching the
  Python client. Existing non-empty volumes still require a supported, tested
  migration before any future version jump.
- Mutating generation endpoints enforce configurable free-space admission via
  `TELECOM_STUDIO_MIN_FREE_DISK_MB` (256 MB by default) and return HTTP 507
  before creating orphan state when local persistence is unsafe.
- `/timeline-summary` exposes frontend-readable timeline steps with label,
  phase, node, status, started/completed timestamps, duration, warning count,
  error count, progress message, and artifact refs when available.
- Public workflow/edit/version responses expose artifact URLs, not local
  filesystem paths. `asset_imports[].resolved_path` remains internal only.
- HTTP workflow/version identifiers are pattern-validated before path lookup,
  including percent-encoded inputs.
- Frontend "scene plan" maps to the `scene_spec` artifact. `SceneSpec` remains
  the geometry source of truth.

### Docker delivery baseline — 2026-08-04

- `infra/docker-compose.yml` runs five healthy local services: compiled
  frontend/Nginx, FastAPI plus Blender 4.5.12 LTS, Qdrant 1.18.0,
  `sqlite-snapshot`, and Adminer.
- Only ports 5173, 8000, 8080 and 6333 are published, all on `127.0.0.1`.
  Nginx preserves the existing API and artifact URLs and streams design events
  with proxy buffering disabled.
- Fresh named volumes are authoritative for container SQLite, outputs and
  Qdrant. Host databases and outputs are never imported automatically. The raw
  CAD library is mounted read-only.
- Adminer can inspect only integrity-checked SQLite snapshots mounted read-only;
  it has no path to the API's live database. Qdrant collections remain visible
  through the Qdrant dashboard.
- The API image is `linux/amd64` on Apple Silicon because the qualified official
  Blender archive is x86-64. This is functional but materially slower than a
  native arm64 Blender runtime. Docker therefore uses a governed 8-sample EEVEE
  preview profile while preserving real Blender generation and five previews.
- Frontend bundles are emitted under `/static`; the same-origin `/assets` path
  remains reserved for the FastAPI asset-library API.
- The 2026-08-04 Docker acceptance generated a real Blender GLB and five
  previews, passed QA with an issued completion certificate, used Qdrant/Groq,
  created a second version through bounded edit, survived API and full-stack
  restarts, and restored the active GLB in the browser without console errors.
- `/viewer-bundle` exposes viewer-ready artifact URLs for GLB, preview,
  metadata, SceneSpec, QA report, generation report, geometry validation,
  requirement coverage, completion certificate, and technical report, plus a
  compact QA summary for drawers. It also exposes `assembly_plan_url`,
  `geometry_fidelity_summary` and `geometry_program_summary`.
- Public workflow/viewer responses expose `rag_planning_summary` and
  `rag_evidence_url` so the frontend can distinguish retrieved context from
  structured hints that actually influenced SceneSpec planning. RAG is not used
  for RequirementSpec extraction in v1.
- Edit and rollback responses expose frontend action URLs (`viewer-bundle`,
  `timeline-summary`, `user-issues`, `current-operation`) and available actions
  so the UI does not infer post-action state.
- `/assets/adaptation-capabilities` exposes the versioned catalog and
  `/designs/{id}/adaptation-capabilities` resolves only the capabilities of the
  active scene. Generated components add bounded dynamic
  `/geometry_programs/{index}` rebuild capabilities. The frontend capabilities
  drawer consumes these contracts.
- Public workflow/product responses expose `runtime_capabilities` and
  `unsupported_actions`; cancel, pause, resume, same-workflow retry,
  human-in-loop, and WebSocket runtime are explicitly unsupported in v1.
- Streaming is local-process only: no cross-process broker, cancellation, or
  durable resume manager yet.

## SPECIALIST ORCHESTRATION AND GROQ GPT-OSS — delivered scope

- The blueprint specialist collaboration is a deterministic DAG rather than a
  sequential registry loop: `asset_composition` is wave 0;
  `rf_layout`, `structural_support` and conditional `geometry_generation` depend
  on it and run in parallel in wave 1. Output ordering stays reproducible for
  hashes and persistence.
- The router detects duplicate or unknown domains, missing dependencies,
  dependency cycles, handler exceptions, wrong-domain responses, and failed
  gates. It fails closed and does not execute dependent specialists after a
  gate failure.
- Groq extraction, bounded planning arbitration, bounded asset selection and
  GeometryProgram authorship use the configured `openai/gpt-oss-120b` endpoint
  with per-capability timeout, reasoning-effort and output-token settings.
  Geometry generation tries strict JSON Schema, then locally validated JSON and
  at most two bounded model repairs. Structured requests explicitly disable
  streaming and tools because those combinations are not supported by the
  selected Groq Structured Outputs path.
- Asset selection now rejects a returned asset ID unless it belongs to the
  candidate set of that exact role. Provider authentication, rate-limit,
  availability, timeout, transport, and model-output failures are classified
  without exposing the API key.
- A live local provider smoke on 2026-07-31 used the configured
  `openai/gpt-oss-120b`, selected two supplied telecom asset IDs with bounded
  authority, and returned in 933 ms. This proves that operation only; it is not
  a permanent provider-availability guarantee.
- This remains a controlled expert workflow, not an autonomous swarm:
  deterministic code owns routing, dependencies, contracts, transformation
  validation/application, units, QA, persistence and Blender execution.

## FRONTEND REAL-RUNTIME UX HARDENING — 2026-07-31

- Local development now uses a same-origin Vite proxy for the stable FastAPI
  routes. This removed a browser-only cross-origin GLB failure while preserving
  backend artifact URLs as the source of truth.
- A recorded local smoke restored `wf_a6660b81b929`, loaded its real GLB and
  reported 121 named nodes, 23 semantic equipment entities and a visible WebGL
  render. The backend preview remains an explicit retryable degraded state, not
  a successful 3D result.
- The top bar now distinguishes a certified result from its remaining
  limitations. Repeated asset warnings are grouped before display; QA and
  limitations share one `Contrôles` drawer instead of presenting contradictory
  peer statuses.
- Restored document packs stay collapsed until requested. Terminal workflows no
  longer retain an inactive progress card. Runtime/RAG evidence is grouped in
  `Système`, and specialist activity remains available in `Activité`.
- Running workflows expose a live, accessible overlay driven only by real
  operation/timeline/SSE data. No synthetic percentage or fake stage is shown.
- Revision and rollback now clear stale terminal events before streaming the
  new operation. The certified version stays visible while QA runs, but its
  terminal message is not reused as the status of the active revision. Rapid
  duplicate submissions are synchronously blocked and every failure exits the
  busy state.
- The duplicated lower workflow-status card was removed. The left rail owns one
  readable scroll surface, changes its guidance for design versus revision,
  and keeps document intake collapsed under a compact `Documents techniques`
  disclosure. QA limitations and long issue lists are collapsed until opened.
- Fidelity counts now say `modèles sélectionnés`; the viewer separately reports
  instantiated semantic equipment and GLB nodes. These counts measure different
  things and are no longer presented with the same `composants` wording.
- The telecom camera fit includes explicit framing margin for tall assemblies,
  and the viewer offers a retry action when a real GLB load fails.
- Frontend regression proof after the M0 recovery changes: 150 Vitest tests,
  TypeScript typecheck and production build pass. A connected current-tree
  browser smoke on 2026-08-03 exercised real prompt analysis, live progress,
  certified GLB display, bounded edit and version creation against FastAPI and
  Blender 4.5 LTS.
- Frontend proof on 2026-07-31: 125 Vitest tests, TypeScript production build,
  and local browser smoke against FastAPI on port 8000 and Vite on port 5173.
  Rolldown code splitting keeps every production JavaScript chunk below 371 kB
  uncompressed while preserving lazy loading of the viewer.
- A prior recorded browser smoke restored active version `v86dc95d0` with a
  real 217-node GLB, 25 semantic equipment instances, QA score 1.0, issued
  completion certificate and seven visible limitations. No terminal progress
  overlay or duplicate workflow card remained on screen.

## Current verdict

`ASSET_DRIVEN_TELECOM_ASSEMBLY_V1_ACCEPTED_LOCAL`

The implementation contains the trusted assembly, component-proof, build-lock,
completion-proof, SQLite/Qdrant recovery and frontend recovery contracts
described below. The required asset-driven telecom generation/edit/version
scenario is confirmed from the current frontend through the real API and
Blender runtime. This is a local milestone acceptance, not a global convergence,
vendor-grade engineering certification, or acceptance of every generic 3D
scenario.

## ASSET-DRIVEN TELECOM ASSEMBLY V1 — delivered scope

- The qualified milestone sample is intentionally small: `TOWER_LATTICE_30M`,
  `ANT_PANEL_5G_001`, `RRU_SMALL_001`, `MOUNTING_BRACKET_001`,
  `POWER_CABINET_001`, and `GPS_ANTENNA_001`. It does not scan, convert or
  claim qualification for the rest of the local library.
- Manifests now carry meter-based dimensions, typed anchors, connector roles,
  allowed adaptation parameters, builder-profile IDs and capability tags for
  the selected families. The bracket is qualified for bounded parametric
  generation; its companion GLB remains reference-only.
- `AssetAssemblyPlanner` ranks every generation-eligible candidate with
  reproducible compatibility, generation-permission and dimensional scores.
  Groq receives only the supplied candidates plus their scores, dimensions,
  compatibility, allowed strategies, parameter IDs and limitations. It chooses
  a candidate/strategy pair governed by `bounded_asset_selection@1.1.0`; an
  unknown ID or strategy is rejected. If unavailable or rejected,
  deterministic top ranking is used and recorded as `deterministic_fallback`.
- `AssemblyPlan` is persisted as `assembly_plan.json`, embedded in `SceneSpec`,
  linked to the blueprint, exposed in `/viewer-bundle`, and listed by the
  frontend artifact drawer. It records component candidates, selection reason,
  allowed parameters, selected builder profile, connectors and fallback truth.
- Blender remains fully deterministic: it consumes `SceneSpec`, records the
  selected parametric bracket per sector and builds the cable route through its
  qualified typed parametric handler. A genuinely absent requested component
  may be supplied by a bounded LLM-authored GeometryProgram, but no
  LLM-generated Blender code is accepted or executed.
- Builder dispatch is profile-driven. `geometry_family` is signed inside the
  builder snapshot (`panel` or `microwave_dish`) and revalidated by the worker;
  asset IDs and network names no longer select worker geometry. Historical
  snapshots that genuinely predate this field retain a narrowly checked legacy
  hash path. Manifest parameters, types, enums, finite values and bounds are
  revalidated by the contract, compiler and worker.
- `POWER_CABINET_001` is now qualified through the bounded
  `ground_cabinet_v1` profile instead of importing its former minimal reference
  GLB. The deterministic builder derives a 17-object enclosure tree from typed
  manifest dimensions (plinth, enclosure, weather roof, doors, handles, vents,
  cable glands and warning placard). Revision dependency rebinding now records
  the same generation strategy and geometry source in `SceneSpec`, metadata and
  provenance.
- The isolated M0 acceptance test covers a 4G/5G site with a dynamically chosen
  exact asset, an adapted component, connector-driven assembly, a typed
  GeometryProgram fallback, bounded Groq selection, real Blender 4.5.12 LTS,
  GLB/previews, component proofs, QA, certification, edit and new version. Its
  final rerun passed on 2026-08-01 with Blender 4.5 LTS (`1 passed`).
- The real HTTP acceptance workflow `wf_42ccbfbb6318` selected seven catalog
  roles through bounded Groq, reused exact `ANT_PANEL_4G_001` and
  `GPS_ANTENNA_001` GLBs, generated the other qualified components and authored
  two bounded GeometryPrograms for a staircase and slab. Blender produced a
  1.58 MB GLB and 1920×1080 preview; component/operation proofs, QA 1.0 and the
  completion certificate passed without public local-path leakage. A bounded
  Groq edit changed only the S1 RRU vertical offset to 1.45 m, regenerated with
  Blender, reported `sectors_changed=true`, and created active version
  `v4fc11460` from `v4bdb73cf`.
- The same live request exposed and drove fixes for an azimuth parser spillover
  into the token `4G`, French `armoire d'énergie` recognition, nested sector
  diff reporting, repeated per-sector warnings and recovery from invalid legacy
  memory rows. Invalid persisted rows are preserved and counted as skipped;
  they no longer terminate the vector reconciliation worker.
- A live revision on 2026-07-31 asked GPT-OSS 120B to move the power cabinet to
  `[5.6, 0.0, 0.0]`. The LLM selected only the declared
  `/accessory_assets/0/position` capability; deterministic validation,
  Blender generation and QA produced active version `v86dc95d0` with
  `real_blender`, score 1.0 and no procedural fallback.
- A separate real out-of-catalog proof on 2026-07-31 completed workflow
  `wf_ead2456914b2`, then regenerated its generated component as version
  `v2e0a4faf`. Both passes used `real_blender`, produced GLB and preview, scored
  QA 1.0 and issued a completion certificate. Source description, placement
  context and requested maximum dimensions are now persisted by the contract
  and covered by revision tests. The recorded initial workflow predates those
  two provenance fields, so its revision cannot prove recovery of values that
  were not persisted originally.
- Current-tree acceptance on 2026-08-03 used the full French 5G brief through
  the browser. GPT-OSS preserved the explicit 45 m tower, 40 m HBA and
  0/120/240 degree azimuths, and reconciled the 4 m gate into one bounded
  14 x 14 x 2.4 m perimeter-fence request instead of generating a disconnected
  duplicate. Workflow `wf_3f66e833e1c0` completed with `real_blender`, a
  2,032,248-byte GLB, five 1920 x 1080 previews, mesh QA passed, QA score 1.0,
  full requirement coverage and completion certificate issued. Active initial
  version was `v02af93b0`.
- The same browser session requested only a tower-height change to 48 m. The
  Groq `openai/gpt-oss-120b` adaptation specialist selected the declared
  `/tower/height_m` capability and `parametric_rebuild`; deterministic contract
  validation and Blender produced certified active version `v74e009a3` with QA
  score 1.0 while preserving sector, accessory and generated-fence geometry.
  A final 47 m revision produced active version `vec35e56d` with the same real
  Blender/QA proof and confirmed that product history preserves the user's
  French instruction while the normalized LLM decision stays in provenance.
  Failed historical workflows now expose no artifact, download or trace URL;
  quarantined candidate files cannot be advertised as product deliverables.
- The corresponding current-tree regression proof is 150/150 frontend tests,
  frontend typecheck and production build, 33 targeted Product/API tests and 46
  extraction/Groq/GeometryProgram tests. The latter set includes real Blender
  compilation of transformed Boolean operands and ground-aligned generated
  geometry.

### ASSET-DRIVEN TELECOM ASSEMBLY V1 backlog

- The 5G panel role now offers one existing internal reference profile and one
  explicitly procedural generic dual-band profile. RRU, bracket, cabinet and
  GPS still have one qualified candidate each; the cabinet is technical generic,
  not vendor-specific. Additional real candidates
  require independent qualification, not copied manifests.
- Preview generation est scene-level et publie désormais cinq vues Blender.
  Les previews par asset et la QA visuelle sémantique du close-up restent à faire.
- Connector roles prove composition contracts and route intent; they are not an
  electrical, RF, load, clearance or vendor-installation certification.

`FRONTEND_PRODUCT_BASELINE_VERIFIED_LIMITED`

The backend contract is consolidated around `/designs` + `workflow_id`. The
frontend now has a verified chat-first/3D-first product baseline and 150 passing
component/contract tests. The required current-tree connected creation and
edit/version path has passed. Exhaustive browser replay of every degraded,
document-pack, rollback and recovery branch remains a broader product release
gate, outside this milestone.

The frontend must keep these limitations visible: `mesh_level_spatial_basic`,
`mesh_level_transform_basic` or `mesh_level_basic` QA, local-process `push_sse`, limited document-pack
intelligence, fail-open reranking, non-vendor-grade assets, and no durable
broker/cancellation.

Backend proof remains `tests/e2e/test_telecom_generation_proof.py` plus targeted
Product API, RAG, LangGraph, Blender, and QA tests. Frontend acceptance requires
the checks and smoke described in `apps/frontend/FRONTEND_KERNEL_README.md`.

## GENERIC COGNITIVE 3D CORE V1 — livraison 2026-08-02

Statut autoritaire: `IMPLEMENTED_PARTIAL`.

- Le runtime générique étend l'orchestrateur et le `SceneSpec` existants; il ne
  crée ni second moteur de génération, ni second store. Un superviseur borné
  décompose la demande en intention, composants et relations, route les
  spécialistes déclarés, puis compile un `SceneSpec` V2.
- Le registre de capacités gouverne schémas d'entrée/sortie, permissions,
  budgets et observations d'exécution. GPT-OSS ne produit jamais de Python
  Blender: il choisit des stratégies autorisées et peut écrire un
  `GeometryProgram` déclaratif validé.
- `GeometryProgram` V2 supporte profils, extrusion, révolution, sweep, arrays,
  booléens exacts, modificateurs bornés, terrain, hiérarchie, ancres,
  connecteurs et groupes. Le worker Blender compile ces opérations de manière
  déterministe et enregistre les programmes réellement exécutés.
- La route générique produit GLB, cinq previews Blender, QA géométrique
  générique, provenance et certificat cognitif local. La révision d'un
  `SceneSpec` V2 repasse par validation de plan/capacités, Blender, QA,
  certification et versioning existant.
- Le frontend reconstruit une conversation persistée, expose la scène, les
  stratégies, la provenance, les composants sélectionnables dans le viewer et
  la galerie des previews réelles. Il ne présente plus une erreur globale de
  synchronisation lorsque le bundle certifié principal est déjà disponible.

Ce statut n'est pas `IMPLEMENTED`: le parcours télécom GPT-OSS réel du
2026-08-03 passe après correction des contrats JSON, des bounds de sweep, des
transformations booléennes et de l'ancrage au sol, mais les trois scénarios
génériques réels ne sont pas tous passés et la sélection/réutilisation d'assets
génériques hors domaine télécom reste `procedural_only`. Aucune convergence
globale n'est déclarée.
