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
  requirement validation. It routes the required deterministic specialist
  domains, records component quantities/asset queries/fidelity/placement,
  persists `design_blueprint.json`, and proves
  `RequirementSpec -> DesignBlueprint -> SceneSpec`. `SceneSpec` remains the
  sole 3D generation source of truth. The current blueprint is deterministic,
  has no operational connector catalog, and is not yet selected by an LLM from
  competing candidates.
- Groq `openai/gpt-oss-120b` is used when a real key is configured; otherwise
  explicit deterministic extraction.
- `RequirementSpec` carries typed field evidence, candidate values, assumptions,
  conflicts, and confirmation fields. Explicit unresolved contradictions block
  the natural-language graph before RAG, asset selection, `SceneSpec`, and
  Blender; a late value is accepted automatically only when the prompt marks it
  as an explicit correction.
- GPT-OSS is the bounded decision layer for ambiguous extraction, controlled
  RAG candidate arbitration, and edit-patch interpretation. It may revise a
  typed proposal, but it cannot bypass `RequirementSpec`, `SceneSpec`, telecom
  rules, Blender's parametric generator, or QA. Governance constrains scope,
  records evidence, and preserves rollback; it does not invent geometry.
- Public product responses expose GPT-OSS truth through `extraction_provider`,
  `llm_provider`, `llm_available`, `llm_fallback_used`, and
  `llm_fallback_reason`; the frontend must display fallback/degraded status
  instead of guessing.
- Primary RAG: NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` at 1024 dimensions.
- Provider configuration is not runtime proof. `/studio/summary` reports
  `configured_unverified` until a real embedding/search succeeds,
  `primary_nvidia_embedding` only after success, and
  `configured_but_last_operation_failed` after an operational failure.
- RAG fallback policy: no automatic local embedding model in the product path.
  Deterministic hash is allowed only for tests/bootstrap or explicit degraded
  mode; it is not product-quality retrieval.
- Reranker: NVIDIA API by default with visible fail-open degraded passthrough.
  Local `BAAI/bge-reranker-v2-m3` remains an explicit developer override only.
- RAG evidence is written to `rag_evidence.json` and exposed through
  `/viewer-bundle`; it lists retrieved sources, controlled candidate hints,
  reranker status, and limitations.
- Memory: local SQLite with writeback; optional Qdrant for some summaries.
  Incompatible legacy runtime collections are preserved and new vectors are
  routed to provider/dimension-versioned collections.
- Document-pack: synchronous direct multi-file or ZIP intake with bounded
  archive assembly, limited PDF/OCR/DXF extraction, consolidation, conflicts,
  corrections, and QA. A missing or tower-incompatible foundation blocks
  generation before a workflow is created; the user must confirm a supported
  foundation instead of receiving a predictably failed Blender workflow. The
  summary, QA response, generation gate, and correction UI consume the same
  blocking-field list.
- Blender: real generation when Blender is found; Blender fallback is rejected
  by default for quality (`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0`).

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
- The 2026-07-30 audit extended the frontend baseline to 117 tests, typecheck,
  production build and npm audit, then restored real workflow
  `wf_a6660b81b929` against the
  current API. Desktop/mobile rendering showed its verified Blender model; a
  separate Chrome headless run without WebGL displayed the real backend preview
  and the explicit WebGL warning. All requested product endpoints returned 200
  and no application console error was observed.
- Old dashboard patterns remain rejected.

## Current assets

- 12 manifests.
- 12 GLB files present.
- 0 tower without a local GLB.
- Expected `/assets/inventory` status: `qualified_mixed_catalog`.
- 10 manifests are generation-eligible: 4 authorize an exact GLB import and 6
  authorize SceneSpec-driven parametric generation. The bracket and cable-tray
  GLBs remain `reference_only` until typed connector/route contracts exist.
- Exact import authorization is fail-closed: the manifest pins SHA-256, units,
  dimensions, pivot, orientation and mesh-integrity review. A changed file is
  rejected and the controlled fallback is reported.
- The three historically missing towers (monopole, rooftop, small-cell) are now
  internal project generated assets produced with Blender.
- Current assets are internal/CC-BY and not vendor-grade.
- Towers are generated parametrically by default. In the product planning path,
  GLB import happens only when the manifest authorizes and the planner selects
  `imported_glb_exact`.
- The scene planner now stamps the manifest-authorized generation mode and
  reason into `SceneSpec`. A 4G scene can therefore assemble qualified panel,
  GPS and power-cabinet GLBs while keeping the tower and RRU parametric. The 5G
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
- ODA Drawings Explorer 27.1 is installed locally and can visually inspect the
  representative DWG, but its application bundle exposes no verified headless
  STL/DAE export route. Its presence therefore does not make conversion active.

## Current 3D and QA

- `SceneSpec + parametric generator` is the source of truth for geometry.
- GLB is only the exported viewer result, not the source of truth.
- Blender produces `design.glb`, `preview.png`, `scene_metadata.json`, and
  a runner-owned `build.lock.json` containing the isolated attempt/build ID,
  the raw SceneSpec hash, a canonical bundle hash for the immutable copy of
  every Python source under `apps/blender_worker` that Blender actually
  executes, Blender runtime identity and artifact hashes. Blender starts in
  background factory mode and every retry uses a fresh staging directory. The
  workflow also persists `requirement_coverage.json`,
  `completion_certificate.json` and the critical QA reports.
- Successful revisions also persist `adaptation_plan.json`,
  `adaptation_capabilities.json`, `scene_patch.json`, and `scene_diff.json`.
  Blender still regenerates from the validated `SceneSpec`; the LLM never
  emits or executes Python.
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
  penetration is bounded to 0.15 m and a total overlap is rejected.
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
- Persisted completion is also revalidated on active status reads, rollback and
  artifact serving: full certificate schema/check set, RequirementSpec/SceneSpec
  hashes, selected `SceneVersion.scene`, build-lock evidence, every certified
  artifact hash and, for schema 1.1, critical report hashes. A historical
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
  certificate, persisted `SceneVersion.scene`, four certified artifacts and,
  for schema 1.1, critical QA reports revalidate. `active_version.json`, root
  status and terminal/product events are compatibility projections; a failure
  in one of them cannot downgrade the canonical commit.
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
  complete derived Qdrant memory projection. SQLite remains canonical and
  `/memory/vector/reindex` rebuilds the remaining projection.
- Qdrant accepts logical search collections only; runtime invalidation also
  removes abandoned build collections and serializes concurrent reads/writes.
  The optional Docker server is loopback-bound but remains pinned to legacy
  `v1.9.2` pending a tested stepwise volume migration.
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
- `/viewer-bundle` exposes viewer-ready artifact URLs for GLB, preview,
  metadata, SceneSpec, QA report, generation report, geometry validation,
  requirement coverage, completion certificate, and technical report, plus a
  compact QA summary for drawers.
- Public workflow/viewer responses expose `rag_planning_summary` and
  `rag_evidence_url` so the frontend can distinguish retrieved context from
  structured hints that actually influenced SceneSpec planning. RAG is not used
  for RequirementSpec extraction in v1.
- Edit and rollback responses expose frontend action URLs (`viewer-bundle`,
  `timeline-summary`, `user-issues`, `current-operation`) and available actions
  so the UI does not infer post-action state.
- `/assets/adaptation-capabilities` exposes the versioned catalog and
  `/designs/{id}/adaptation-capabilities` resolves only the capabilities of the
  active scene. The frontend capabilities drawer consumes these contracts.
- Public workflow/product responses expose `runtime_capabilities` and
  `unsupported_actions`; cancel, pause, resume, same-workflow retry,
  human-in-loop, and WebSocket runtime are explicitly unsupported in v1.
- Streaming is local-process only: no cross-process broker, cancellation, or
  durable resume manager yet.

## Current verdict

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
  When Groq is configured, its bounded selector may choose only a supplied
  candidate ID for each role. If unavailable or rejected, deterministic top
  ranking is used and recorded as `deterministic_fallback`.
- `AssemblyPlan` is persisted as `assembly_plan.json`, embedded in `SceneSpec`,
  linked to the blueprint, exposed in `/viewer-bundle`, and listed by the
  frontend artifact drawer. It records component candidates, selection reason,
  allowed parameters, selected builder profile, connectors and fallback truth.
- Blender remains fully deterministic: it consumes `SceneSpec`, records the
  selected parametric bracket per sector, and records the missing cable tray as
  a visible `PROCEDURAL_CABLE_ROUTE` fallback. No LLM-generated Blender code is
  accepted or executed.
- The end-to-end acceptance test creates a 5G site with tower, panel antenna,
  RRU, bracket, cable fallback, cabinet and GPS; produces GLB and preview;
  passes real-Blender QA; exposes provenance; then edits the design and creates
  a new active version.

### ASSET-DRIVEN TELECOM ASSEMBLY V1 backlog

- The current qualified sample has only one eligible 5G panel, RRU, bracket,
  cabinet and GPS candidate. Scoring is operational, but meaningful
  multi-candidate choice is currently strongest for the tower family; additional
  candidates require independent qualification, not copied manifests.
- Preview generation is scene-level. Per-asset preview images and a close-up
  visual QA gate remain future work.
- Connector roles prove composition contracts and route intent; they are not an
  electrical, RF, load, clearance or vendor-installation certification.

`FRONTEND_PRODUCT_BASELINE_VERIFIED_LIMITED`

The backend contract is consolidated around `/designs` + `workflow_id`. The
frontend now has a verified chat-first/3D-first product baseline. It is not yet
the final product gate because document-pack mutation, rollback, and every
degraded path have not been replayed in one recorded acceptance session.

The frontend must keep these limitations visible: `mesh_level_spatial_basic`,
`mesh_level_transform_basic` or `mesh_level_basic` QA, local-process `push_sse`, limited document-pack
intelligence, fail-open reranking, non-vendor-grade assets, and no durable
broker/cancellation.

Backend proof remains `tests/e2e/test_telecom_generation_proof.py` plus targeted
Product API, RAG, LangGraph, Blender, and QA tests. Frontend acceptance requires
the checks and smoke described in `apps/frontend/FRONTEND_KERNEL_README.md`.
