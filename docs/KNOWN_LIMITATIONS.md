# Known Limitations

Active limitations that must remain visible in the API, reports, and future
frontend.

- The product has no user account, JWT or server session. Its supported threat
  model is one user on loopback. Trusted hosts, bounded CORS, security headers
  and a pre-service foreign-Origin rejection protect browser mutations, but do
  not authenticate another local process. LAN/remote access requires TLS and a
  separately designed owner/session model; a token in `localStorage` is not an
  accepted shortcut.
- Nginx security headers and the host/origin boundary pass deterministic tests.
  Compose configuration was revalidated on 2026-09-11, including its fixed
  loopback ports and container Blender path, but this checkpoint did not start
  or build the complete stack. Container and browser runtime smoke remain open.

## Runtime recovery checkpoint — 2026-09-10

- Native CAD inspection is a separate quarantined CLI, not a product admission
  route. Its real chair proof has implausible declared millimetre units and
  overlapping source meshes, all preserved. No telecom source is generation-
  qualified; the Sierra candidate remains reference-only.
  DWG source/DXF comparison currently accepts modelspace polyfaces only; the
  independent DXF extractor supports nested blocks but refuses ACIS, clipping,
  external/multiple inserts, subdivision and malformed faces. Wires/annotations
  are counted and omitted; materials are not reconstructed. GLB roundtrip checks
  do not establish manifoldness, manufacturer fidelity or engineering fitness.
- Raw probe mesh detection no longer counts a `POLYLINE_3D` wire as mesh geometry;
  it now recognizes `POLYLINE_MESH`. A mixed mesh/ACIS file still requires a solid
  tessellation route and cannot become generation-eligible from probe results.
- A real Sierra Wireless/Semtech 6001124 MIMO panel STEP now has a local
  qualification report with explicit millimetre evidence, 18 preserved mesh
  leaves, real Blender/GLB roundtrip, independent post-Blender measurement and
  five structural preview checks. Its manifest is intentionally
  `reference_only`: the restricted source terms, stable anchors, mating fit,
  orientation, and engineering approval are still unverified, so retrieval
  and Blender generation cannot use it.

- The configured NVIDIA text embedding endpoint returns HTTP 410 (retired model).
  Replacement retrieval quality and full static reindex are not validated;
  local lexical fallback remains explicit. A successful single-vector response
  from Nemotron 3 is not a benchmark result.
- Unknown historical memory remains preserved but ineligible; existing designs
  remain visible. Reusing their identity skips new memory writeback rather than
  relabeling historical records as product experience.
- Host runtime cleanup does not cover stopped Docker volumes. No global clean
  Docker baseline is claimed.
- Raw CAD search improves metadata discovery and publishes match evidence, but
  has no semantic guarantee, geometry qualification or automatic compiler path.

## Sector inspection and viewer focus — 2026-09-11

- A required telecom `AssemblyPlan 1.1` now produces one actual Blender close-up
  per sector after `design.glb` export. The image is accepted only when an
  independent inspector re-reads exported semantic roots, checks the renderer
  bytes and measures PNG framing, contrast and subject presence. The viewer
  serves it only from a verified active version.
- This is inspection evidence for the local panel/support/radio subassembly.
  The cable route is verified in the GLB but intentionally excluded from the
  close-up because its descent to the tower base destroys useful scale. It does
  not certify connector mating, RF continuity, fixing, structural load or
  manufacturer fidelity.
- The current viewer derives a local camera subject from published
  `component_proofs` and their stable `instance_id`. Clicking a panel or its
  cable route frames the proven panel/support/radio group; the raw selected root
  remains available for outline and targeted edit. Legacy or unproven scenes
  receive no inferred sector focus. A full overview remains visually weaker than
  a professional presentation and needs a qualified production asset set plus a
  recorded end-user visual acceptance pass.

## Visible during frontend build

- The document-pack action is intentionally user initiated. A retained pack is
  represented by a compact attachment chip in the composer. Extraction fields,
  QA diagnostics and provider internals are not exposed in the product UI. The
  composer and conversation tray show workflow events and phases,
  not provider tokens or a fabricated assistant transcript.
- The main inspector no longer exposes developer-only Progression or Détails
  avancés panels. Their underlying evidence remains available through the
  product endpoints and the focused QA/assets/versions/composition drawers.
  This surface change does not improve the current technical generic
  geometry or qualify the reference-only manufacturer asset.

- A loaded document pack can be deleted with the attachment `×`. Deletion is
  local, guarded by chat references, and also removes its canonical document
  memory. Derived vector projection is refreshed asynchronously through the
  existing outbox; a transient projection delay can therefore remain visible.

- Telecom confirmation requires at least one explicit, non-default site
  identity/layout field in extraction provenance. An image question with an
  all-default site returns `TELECOM_BRIEF_REQUIRED`, no requirements/hash/receipt,
  and cannot be replayed through the confirmed-design endpoint. This is a bounded
  admission rule for telecom confirmation, not a conversational intent classifier
  or image analysis. Free-intention keeps its own admission contract; a
  document pack can only enrich a non-empty prompt and cannot start generation
  by itself.
- The workspace shell passes automated component/API checks and a
  same-origin HTTP project/chat/draft lifecycle. A bounded browser check covered
  the project/chat tree, contextual menus, inspector and expanded empty viewer.
  This is not a WebGL or professional-design acceptance. Uploads support initial design input;
  the current edit endpoint does not consume a newly attached document pack.
- Runtime history was reset by explicit user request on 2026-09-13. Old outputs,
  projects, conversations, document packs, checkpoints and indexes were
  permanently deleted together with the temporary recovery archive. Static
  knowledge sources and catalog assets remain, but no historical runtime index
  is an active neural retrieval proof. Resetting history does not improve source
  geometry quality.

- `apps/frontend` has a visually verified historical real-backend product
  baseline and 151 passing M0 Vitest tests plus green typecheck/build. The
  2026-08-04 Docker smoke restored a certified real GLB and two-version design
  without browser console errors. Document-context generation, rollback and
  relevant degraded/retry paths still need a recorded browser acceptance pass.
- The 2026-09-14 current-tree frontend suite passes 225 Vitest tests, typecheck
  and production build. The attachment HTTP smoke proves upload, chat binding,
  bounded context hashing, absence of import-only workflow creation and guarded
  deletion. A fresh Chrome tab loaded the current GLB with no console warning or
  error. This did not trigger or certify a new Blender generation.
- The first technical kernel was rejected as too dashboard-like; permanent
  stage grids, capability counters, raw workflow ids, and raw JSON surfaces must
  not come back.
- The Three.js/React Three Fiber viewer is lazy-loaded and its runtime is split
  into cacheable production chunks. The 2026-07-31 build keeps every JavaScript
  chunk below 371 kB uncompressed, but the complete 3D dependency set remains
  substantial and still benefits from browser caching.
- Old dashboard patterns remain rejected.
- `/workspace` now provides local projects, conversations and draft recovery.
  It remains an organization layer over `/designs`; there is no `/runs`,
  `job_id`, account or multi-user ownership model. SQLite serializes normal
  creation and linking, but workflow files and the workspace link cannot form
  one ACID transaction across a process crash at their filesystem/database
  boundary. The workflow remains independently recoverable in that edge case.
- `events/stream` is `push_sse` inside the local FastAPI process, with JSONL
  replay and queue live events. It is not a cross-process broker.
- Runtime timeline depends on node events + trace file; robust cancellation,
  retry, and durable resume are not yet implemented.
- Streaming is event-level, not token/delta reasoning streaming. Checkpoints
  support graph persistence during an invocation, not pause/resume/HITL.
- `runtime_capabilities` and `unsupported_actions` expose these missing
  runtime actions explicitly: cancel, pause, resume, same-workflow retry,
  human-in-loop checkpoints, and WebSocket runtime.
- The local thread executor has bounded admission but is not a durable job
  broker. Process shutdown and test harnesses must close the service lifespan;
  there is no cross-process ownership or recovery.
- LangGraph checkpoint rows are bounded and terminal threads are removed.
  Terminal adaptation threads are also removed, and design deletion removes
  every checkpoint thread with that workflow prefix.
  Reclaimed SQLite pages are compacted only after significant churn (64 MiB and
  25% free by default), so startup may briefly perform local maintenance after a
  large development/test history.
- Local storage admission requires at least 256 MB free by default
  (`TELECOM_STUDIO_MIN_FREE_DISK_MB`). Ignored workflow artifacts still need
  periodic cleanup; the guard prevents a new mutation but is not a retention
  scheduler.

## Backend and agents

- Deterministic extraction now preserves typed evidence for every field and
  handles numeric/word sector lists in French and English, contradictions, and
  explicit late corrections. It remains rule-based and cannot understand every
  free-form telecom brief.
- Unresolved explicit contradictions block generation and require the user to
  correct the prompt; GPT-OSS may propose a candidate but cannot silently become
  the authority over conflicting source evidence.
- Groq improves extraction only when a real key is configured.
- The shared Groq transport supports multiple independent-account credentials,
  atomic least-in-flight/round-robin selection, bounded per-credential
  concurrency, credential/capability isolation and a per-capability circuit
  breaker. `Retry-After` cools only the affected credential and never sleeps a
  workflow thread; when every credential is cooling the call fails fast with a
  visible provider fallback or fail-closed result. No live Qwen call was
  accepted in M1.
- Groq may express a per-account TPM limit as HTTP 413 with the sanitized code
  `rate_limit_exceeded`, not only as HTTP 429. The transport recognizes both,
  applies the credential cooldown and immediately tries another ready account.
  Different accounts may still have materially different TPM/RPM envelopes;
  the pool does not pretend they are equal-capacity replicas.
  `configured_unverified` remains different from `operational`; a configured
  key is not health proof.
- HTTP timeouts remain configured per network attempt rather than as one
  monotonic deadline shared by every structured-output fallback and repair.
  Ambiguous read/write/protocol failures are no longer replayed, but connect/5xx
  retries and application-level repairs can still accumulate latency. A future
  workflow-level invocation context must govern total calls, requested tokens
  and deadline without reducing the contractually required design quality.
- Qwen multimodal interpretation and asset-preview review are advisory and
  opt-in per project. Consent is disabled by default and persisted, but the
  document-pack route currently records `remote_vision_analysis=not_executed`:
  there is no automatic image/PDF workflow invocation or PDF rasterization.
  The planned 8 plan/OCR + 8 asset-preview + 8 negative/ambiguous evaluation
  has not been executed, so vision cannot participate in certification.
- LLM state is visible through `extraction_provider`, `llm_provider`,
  `llm_available`, `llm_fallback_used`, and `llm_fallback_reason`; fallback is
  acceptable only if the frontend displays it.
- Agents are typed deterministic specialists or bounded LLM wrappers; this is
  not a free-form autonomous Blender coding system.
- The main topology is still predominantly fixed. A typed deterministic
  `DesignBlueprint` stage routes asset-composition, RF, structural and
  conditional geometry-generation policy specialists, persists composition
  intent, and proves `RequirementSpec -> DesignBlueprint -> SceneSpec`. Asset
  candidates are scored and connector intents are operational, but candidate
  diversity is still small. There is no autonomous supervisor, conflict
  aggregator, recalled-design candidate authority or bounded post-Blender
  critique/rebuild loop.
- The generic cognitive supervisor currently validates and persists a bounded
  specialist route, but the actual generic execution still follows the fixed
  registered dependency chain. The route is provenance, not an operational
  choice of specialists. Likewise, selected capability IDs prove existence but
  do not yet constrain every GeometryProgram operation actually used.
- GPT-OSS may now author an out-of-catalog `GeometryProgram`, but this is not an
  unrestricted arbitrary-design system. GeometryProgram V2 supports governed
  primitives, polygonal curves, instances, profiles, extrusion, revolution,
  sweep, arrays, exact booleans and a bounded modifier set. It still has no
  B-Rep surface modeler, arbitrary topology editor, imported-mesh editing or
  generalized Geometry Nodes graph.
- Geometry generation is fail-closed and requires the configured Groq
  specialist. There is no deterministic substitute that fabricates the missing
  component. When deterministic requirement extraction is used, it cannot
  reliably discover every free-form out-of-catalog component.
- A request can contain at most 8 geometry intents, each program at most 512
  nodes, and the workflow at most 1024 GeometryProgram nodes in aggregate. These
  are safety bounds, not a proof that every accepted workload has optimal Blender
  performance.
- Generic decomposition is now consistently capped at 24 components in both
  the provider schema and the runtime contract. Asset decisions still fan out
  per component and GeometryPrograms are still planned per generated component;
  there is no workflow-global LLM call/token budget or cancellation of sibling
  futures after the first fail-closed error.
- Requested `maximum_dimensions_m` is compared deterministically with the
  program envelope. A uniform bounded adapter can correct only an envelope
  overflow; it cannot repair semantic design mistakes. New workflows preserve
  `source_description` and `placement_context` through revision. Historical
  programs that predate these fields remain explicitly `legacy_unavailable`;
  placement text is not interpreted or independently validated.
- Prompt workflows, document-pack generated requirements, and scene revisions
  enter the main compiled graph. Edit interpretation now enters a separate
  checkpointed LangGraph adaptation graph for standard capabilities. Generated
  component rebuild uses a bounded specialized branch before the main revision
  graph; version bookkeeping remains service-level.
- No robust cancellation/retry manager; async execution uses local threads.
- HTTP workflow/version identifiers are fail-closed (`wf_` + 12 lowercase hex
  characters, `v` + 8 lowercase hex characters), including percent-encoded
  path segments. Internal service APIs still assume application-generated IDs.
- The frontend lock currently audits clean. Python requirements remain
  lower-bounded ranges without `uv.lock`. Security floors cover the dependency
  advisories validated during this audit (`langsmith>=0.8.18`,
  `pydantic-settings>=2.14.2`, `pillow>=12.3.0`, `torch>=2.13.0` and
  `setuptools>=83.0.0`); the document-layout extra also constrains the matching
  `torchvision>=0.28.0` family. A clean install is still not release-grade
  reproducible and must be scanned after resolution.

## RAG and memory

- The controlled static knowledge corpus and its evaluation set are still small;
  current retrieval is real but not evidence of broad telecom-domain coverage.
- Memory has no TTL/retention-by-age policy yet. Design deletion now purges its
  canonical SQLite rows and invalidates the derived Qdrant projection, which
  must then be rebuilt by the supported reindex flow.
- Qdrant publication is now recoverable through a durable SQLite outbox, but
  its retry worker is local-process and not a distributed delivery service.
  `pending`, `attempt` or `failed` means the projection is degraded while the
  committed SQLite state remains authoritative.

- NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` at 1024 dimensions is the
  product provider. A 2026-08-06 live probe returned 200 and a 1024D vector for
  both query and passage profiles; this availability probe is not a telecom
  retrieval-quality benchmark.
- A configured provider is reported as `configured_unverified` until a real
  operation succeeds.
- The product path does not silently load a local embedding model. Deterministic
  hash retrieval is allowed only for tests/bootstrap. Static documents are
  embedded by one cross-collection operation, sent in bounded batches of at
  most 32 passages with no synchronous SDK retry. If
  NVIDIA indexing/query embedding fails, the real local corpus is ranked
  lexically and the API/UI expose `degraded_local_lexical`; this is useful
  continuity, not equivalent semantic quality.
- Static RAG docs/manifests are checked against a persisted index identity and
  reindexed automatically when they change. Runtime memory uses SQLite as its
  canonical store. `POST /memory/vector/reindex` rebuilds a compact Qdrant
  projection atomically, keyed by provider, model, input profile and dimension;
  legacy collections are preserved. Repeated validated designs and issue rows
  are compacted into technical signatures/patterns before embedding. A failed
  rebuild leaves the previously published vector index active, and
  `/studio/summary` exposes migration/degradation state.
- Persisted design rows that no longer satisfy the current `SceneSpec` contract
  remain in canonical SQLite but are skipped from the derived vector projection
  and counted in `skipped_source_counts`. They require an explicit migration if
  they must become searchable again; they are not silently rewritten.
- RAG search accepts logical collection names only. Runtime invalidation removes
  active, obsolete, base and abandoned `__build_` collections and serializes
  searches/writes across the publication boundary.
- Docker pins Qdrant server and Python client to `v1.18.0`. A future upgrade of
  a non-empty volume still requires a tested supported migration; the server
  must not be exposed to a LAN or the Internet.
- Reranker product path is NVIDIA API, but it is fail-open. If unavailable,
  vector order is used and `rag_reranker_degraded_reason` must be displayed.
  No local neural reranker is loaded by the product runtime.
- Memory is still limited: workflow recall is predominantly deterministic SQL
  matching. The compact Qdrant projection is operational for explicit semantic
  search and future bounded recall, but it is not yet allowed to mutate
  `RequirementSpec` or `SceneSpec` directly.
- `rag_context_count > 0` does not mean the 3D plan changed. In v1, only
  structured, whitelisted `payload.planning_hints` can affect planning; RAG is
  not used for RequirementSpec extraction. Use `rag_evidence.json` for sources
  and candidate hint proof.

## Docker runtime

- On Apple Silicon the API and Blender run as `linux/amd64`. Rendering is
  materially slower under Docker Desktop emulation, so the stack permits one
  running workflow, two queued requests and a 600-second Blender timeout.
- Docker uses a governed 8-sample EEVEE preview profile. It is suitable for the
  technical GLB/preview workflow and QA gates, but it is less polished than a
  higher-sample native render and is not a photorealistic certification.
- Adminer reads integrity-checked SQLite backups, never live database files.
  Its view may trail the API by up to the five-second snapshot interval.
- The four Docker named volumes are independent of host `data/` and `outputs/`.
  There is no automatic import or migration in either direction.
- SQLite remains canonical and local-first. PostgreSQL would require replacing
  repository, checkpoint, transaction/outbox and recovery contracts; it is not
  part of this delivery and would not improve the current single-user runtime.
- Docker health proves process and dependency availability, not that external
  Groq/NVIDIA calls will succeed. Provider status becomes operational only after
  a real successful request and remains visibly degraded otherwise.
- The historical native suite mixed real Blender scenarios with unit tests and
  could take tens of minutes depending on the host PATH. The small-cell and
  certificate/version fixture regressions are fixed. Tests are now split into a
  default fast gate and explicit `blender_runtime`, `provider_live`, and
  `browser_smoke` gates. The final 2026-08-11 collection contains 712 tests:
  660 fast, 48 real-Blender and 4 live-provider tests; the fast gate passed in
  23.68 seconds. `browser_smoke` has zero automated pytest cases, so the current
  visual proof is an interactive runtime smoke. Admission pressure, invalid input and terminal-persistence
  failure paths run in the fast gate because they never cross a Blender
  subprocess boundary. The harness rejects both an unmarked Blender generation
  and an unmarked Blender readiness probe. The Blender gate is intentionally not
  represented as fast CI.

## Documents

- Document-pack is synchronous, 80 MB max.
- Pack corrections, generated-workflow linkage and reads are serialized by an
  in-process per-pack lock; each JSON file is atomically replaced and fsynced.
  A correction still spans several compatibility files, so a host/process crash
  between replacements can leave a mixed revision. A single revision envelope
  or write-ahead journal remains required for crash-level transactions.
- A document pack cannot generate a design alone. Confirmed supported facts are
  combined with a non-empty user prompt during analysis and generation. Missing
  facts still use the explicitly reported deterministic fallback rules; no
  foundation or technical value is invented from unsupported document prose.
- `/document-packs/capabilities` is honest and reports
  `document_pack_status=limited`.
- OCR is limited and depends on installed Tesseract + languages.
- Docling is import-only / not active by default.
- DXF document-pack extracts text/layers; it is not a solid-CAD importer.
- The local CAD library is fully copied and catalogued, but remains quarantined:
  11,974 files, 11,531 unique contents, 443 duplicate contents and 0
  generation-eligible entry. No global licence file was found in the source.
- The [2026-09-09 bounded CAD conversion benchmark](QA_STRATEGY.md#cad-conversion-benchmark--2026-09-09)
  produced no admissible mesh from three real antenna/radio/support DWGs.
  LibreDWG conversions returned exit code 0 while resulting SAT/SAB payloads
  were empty; down-converting the radio to R2000 removed its solid entities.
  Exit code alone cannot qualify conversion. ODA export remained unverified
  after an interrupted UI experiment; no source or licence was promoted.
- LibreDWG `dwgread` provides honest DWG metadata/entity probes. Sample telecom
  models contain `3DSOLID` ACIS/B-Rep entities, so converting them through DXF
  alone is not accepted as mesh proof. A real B-Rep conversion tool and
  post-conversion unit, mesh, semantic-role and visual QA are still required.
- The focused 2026-09-11 candidate `APM40_Fixation.dwg` from the local
  `MAJ des Blocs` corpus is a real ACIS source candidate, not an admitted
  component: its catalog hash is
  `3c4b69804d39b6bd793594c16cefde7b5bd272f437cb54120e5323f1771ce262`, its
  DWG header is `AC1018`, and the local probe finds four `3DSOLID`, five
  blocks and three inserts with millimetre `INSUNITS`, but no native mesh.
  The project-owner authorization permits local derivative qualification work;
  it does not establish manufacturer identity, engineering fit, scale, anchors
  or a faithful tessellation. The source remains quarantined until all of those
  checks are recorded.
- ODA Drawings Explorer 27.1.0.0 is installed locally, but this installation
  exposes only its interactive viewer executable. It does not include
  `ODAFileConverter`, a supported batch exporter, or a documented SAT/STEP/mesh
  conversion command. Bundled B-Rep libraries are not treated as a callable
  conversion API. A product bridge requires a tool and licence that explicitly
  export a neutral B-Rep or controlled tessellation for a bounded benchmark.
- A focused probe of `Axians_Nedea_36m.dwg` found 99 `3DSOLID`, 440 block
  inserts and no mesh-convertible entity. `INSUNITS` says millimeters while the
  display-unit label conflicts. The candidate is not Blender-ready and cannot
  be promoted by metadata retrieval, RAG or an LLM decision.
- Tool failures, timeouts and invalid probe output are returned as controlled
  quarantine errors. The observed LibreDWG Latin-1 and bare non-finite-number
  dialect is normalized narrowly, with parser mode and replacement count in the
  response; it never qualifies a file by itself.
- The catalog links 15 nearby source images to 7 CAD files for retrieval and
  human comparison. These links do not prove that an image matches the complete
  CAD geometry. No local preview is sent to a remote vision model by default.
- A user-provided render from this corpus is a valid fidelity target, but an
  image alone does not identify the exact DWG, prove rights, units, topology,
  editable subcomponents or a deterministic conversion. It cannot bypass the
  qualification gate.
- Detecting `ODAFileConverter`, FreeCAD or `dwg2dxf` only reports
  `installed_import_only`; document-pack processing does not execute a silent
  DWG conversion. The installed ODA Drawings Explorer is an inspector, not an
  accepted headless production converter.
- Missing foundation evidence remains `unknown`; no concrete pad is invented.
- Missing antenna model evidence selects a generic network family with a visible
  warning, never a vendor-exact claim.

## 3D and QA

- Real Blender is required for a real GLB.
- The macOS host has Blender 4.5.12 LTS arm64 at
  `/Applications/Blender 4.5 LTS.app`. On 2026-09-11, its
  `--background --factory-startup` path and a real BlenderRunner generation
  passed. A certified current build lock accepts only the exact 4.5.12 LTS
  runtime metadata, not merely an executable that starts. Blender 5.1.2 is also
  installed locally but is rejected as unqualified by the Product API and build
  lock validation; it cannot silently generate a certifiable version. Compose
  fixes both Blender environment variables to `/opt/blender/blender`, preventing
  a host path from overriding the container worker. The Docker `linux/amd64`
  runtime remains a separate path whose image build and health smoke are still
  open.
- Blender fallback is rejected by default, but missing assets can still become
  visible procedural geometry during a real Blender generation.
- Geometry source of truth is `SceneSpec`, including selected manifests,
  `AssemblyPlan` and optional `GeometryProgram` values. Fixed parametric builders
  and the deterministic program compiler consume it; GLB is only the exported
  viewer result.
- Mesh QA v1 is `mesh_level_spatial_basic` when semantic transforms and all
  primary-equipment bounds are readable, `mesh_level_transform_basic` when only
  transforms are complete, otherwise `mesh_level_basic`. It computes bounds
  from real GLB `POSITION` bytes, verifies basic HBA/azimuth transforms and
  rejects unexpected AABB overlap among antennas, RRUs, GPS and cabinets.
  Same-sector antenna/RRU contact uses a 0.20 m minimum-axis penetration bound;
  this is still a coarse AABB rule, not a connector-zone or triangle test.
  This is conservative broad-phase screening, not triangle-level BVH collision,
  self-intersection, minimum-clearance engineering or exact panel-normal proof.
- GLB integrity now validates actual binary accessor/index ranges and semantic
  mesh coverage, but it does not yet prove manifold topology, self-intersection,
  minimum steel clearance, weld/node engineering, or structural connectivity
  beyond generated cylindrical endpoint alignment.
- The completion certificate is a deterministic local integrity record with
  SHA-256 hashes and full persisted revalidation, not a signed third-party
  engineering approval.
- Schema `1.1.0` commits bind persisted QA, geometry-validation and
  GLB-inspection reports and compare `SceneVersion.scene` with the persisted
  `scene_spec.json`. Schema `1.4.0` is required for `AssemblyPlan 1.1` and
  certifies `component_proofs.json` plus `constraint_evidence.json`; schema
  `1.2.0` remains the component-proof schema for GeometryPrograms without a
  trusted assembly plan. Historical `1.0.0` results remain legacy evidence.
- New Blender builds copy the complete Python worker-source bundle into an
  immutable per-attempt snapshot, execute that copy, then hash it in the lock.
  Build lock `1.2.0` also binds current manifests/catalog, builder profiles,
  exact asset bytes, assembly operations and GeometryPrograms. Historical
  schema `1.0.0` locks contain only the entry-script hash and remain
  recognizable as legacy evidence.
- Blender builds are reproducible at the recorded
  SceneSpec/worker-bundle/runtime identity level, but cross-version bit-for-bit
  GLB reproducibility is not claimed.
- `SceneSpec` rejects non-identity tower transforms and `.gltf` export because
  those paths are not operational. Accessory transforms, per-sector labels,
  height markers and preview camera modes are operational.
- Parametric tower rebuild, sector layout, scene composition, and declared
  accessory transforms are operational. Imported opaque GLBs cannot yet be
  retopologized, have arbitrary parts recolored, or expose Geometry Nodes
  sockets unless a future verified capability profile declares and implements
  those operations.
- No material, RF, structural wind-load, or vendor-grade mesh dimension validation yet.
- GeometryProgram validation proves schema, references, units, graph acyclicity,
  envelope and resource bounds. It does not prove that generated geometry
  semantically satisfies the natural-language request, that placement text was
  followed, or that the component is collision-free. Custom generated roles are
  not yet part of the primary-equipment AABB gate.
- The tower validator uses height only as a conservative trigger for aviation-marking
  review. It does not determine whether lighting is legally required; national rules,
  obstacle location and the competent aviation authority remain authoritative.
- Internal/CC-BY assets are not vendor-grade.
- The 5G panel and RRU parametric outputs are multi-part
  `technical_generic` profiles with explicit LOD, but they still do not prove a
  vendor model, exact RF ports, thermal performance, maintenance clearance or
  fabrication fitness.
- Five scene-level Blender views now include a close-up. Only the primary view
  has the current framing gate; role-specific close-up visibility/contrast and
  per-asset previews remain future work.
- The curated manifest catalog is intentionally small: it contains 14 manifests,
  of which 13 are generation-eligible, with 3 GLBs qualified for exact import,
  10 component/tower profiles qualified for controlled parametric generation and
  one real STEP candidate kept `reference_only`. The 5G panel and RRU
  companion GLBs have not passed orientation qualification and are therefore
  never imported by the product path.
- Asset qualification proves file identity, basic mesh integrity, declared
  dimensions, pivot and orientation for the authorized use. It does not prove
  vendor identity, RF performance, structural capacity or fabrication fitness.
- `component_proofs.json` records strategy, source, transform, bounds,
  fingerprint and executed operations. It does not prove that two meshes are
  semantically equivalent, that a component is manufacturer-authentic, or that
  connector intent satisfies electrical, RF, grounding, load, maintenance or
  regulatory rules.
- `constraint_evidence.json` measures exported semantic anchor frames, not
  triangle-level contact surfaces. It proves bounded position/orientation of
  required mechanical endpoints after export; it does not prove physical
  contact, collision clearance, fastener engagement, deformation, load
  capacity, manufacturability or RF/electrical/routing continuity. Required
  non-mechanical connections are listed as unevaluated. For a resolved endpoint,
  the inspector additionally proves one identified support mesh exists in the
  GLB; it does not prove surface contact, fixation or transfer of load.

## M1 professional asset qualification gate

- Status is `MILESTONE 1 — PARTIEL`. The verified baseline is local commit
  `4829995130a43c09c5fb0c23d4216ed007e2d2c2` and tag
  `cognitive-3d-m1-baseline-20260808`; current convergence continues directly
  on the sole local branch `main`.
- All 14 current runtime manifests fail the professional proof gate. The 13
  internal/technical assets retain their existing generation contract; Sierra
  Wireless/Semtech `6001124` remains `reference_only`.
- A manifest claiming a vendor source, vendor-qualified fidelity, manufacturer
  or reference is no longer executable from declaration alone. The registry,
  snapshots, decision packets, cognitive reuse, exact-asset worker and trusted
  assembly require the effective professional admission result. Professional
  identity is limited to exact import of the qualified viewer; current generic
  parametric builders cannot carry a manufacturer identity.
- `ProfessionalAssetVerifier` re-hashes the master, viewer, previews and report,
  validates GLB/PNG structure, paths, lineage, dimensions and anchor bounds, and
  requires a `professional_asset_qa.v1` report bound to the asset ID,
  qualification version and master/viewer hashes with passed mesh, dimensions,
  pivot and orientation checks. The source hash must equal the master hash.
- This gate requires an explicit, evidenced project-authorization record; it
  does not independently establish the legal validity of that record, semantic
  B-Rep identity, connector mating, mount fitness or engineering validity, and it does not publish a
  catalog bundle transactionally. No professional source is currently admitted
  for generation; DWG `3DSOLID`/ACIS remains `source_only`.
- Blender revalidates the professional boundary with a pure-standard-library
  module copied and hashed into each immutable worker bundle. The application
  adds typed and deeper GLB checks before planning; neither boundary promotes a
  quarantined source.
- Exact-import assets, including technical internal assets, must also have their
  runtime GLB present, hash-matched and structurally valid before registry
  selection or RAG indexing. Missing or altered bytes no longer remain planning
  candidates.
- A manifest catalog outside `<project_root>/assets/manifests` is rejected at
  configuration time. External catalog roots are not propagated through the
  current SceneSpec, trusted-input hashing and worker boundary.
- `QualifiedAssetCandidateRetriever` and `AssetDecisionPacket` improve the
  decision contract, not the underlying fidelity. Telecom persists and
  validates semantic strategies. Generic cognitive retrieval now exposes
  candidates. The 2026-09-10 compiler supports opted-in exact `reuse` and bounded
  rigid `compose`; parameter adaptation and arbitrary assembly remain unsupported.
- No professional M1 Blender/browser E2E has passed with seven qualified real
  assets, five scene previews plus per-asset previews, reuse/adapt/compose,
  procedural complement, deterministic QA, provenance and targeted versioned
  edit. Older technical-generic E2E evidence must not be relabelled as this
  gate.
- A 2026-08-10 technical-generic smoke did pass with the real API, a restored
  certified GLB and the Composition drawer: 0 professional proof, 0 qualified
  per-asset preview, seven explicit incomplete-proof cards and no console
  error. It validates truthful degradation only.
- No BGE-M3, PostgreSQL, new Docker architecture or mass CAD conversion is part
  of this remediation. Nemotron, SQLite, Qdrant projection and the existing
  Compose topology remain unchanged.

## M0 release gate

- Trusted assembly/recovery remains
  `M0_TRUSTED_ASSEMBLY_AND_RECOVERY_PARTIAL`. The isolated real-Blender E2E and
  a real HTTP 4G generation/edit/version run passed. A connected smoke on the
  2026-08-04 Docker tree restored the certified active version and real GLB in
  the viewer with no browser console error or warning; degraded/document-pack,
  rollback and recovery branches are not exhaustively replayed in-browser.
- The current output is technical generic/schematic: the accepted live scene
  has zero vendor-qualified components, a compact simplified staircase and
  crowded summit annotations. Two GeometryPrograms used visible
  `json_object_repaired` mode. QA 1.0 certifies the implemented bounded checks,
  not manufacturer authenticity or semantic visual quality.
- The 2026-08-11 browser smoke on convergence commit `19791be` covers one real creation flow,
  streaming, GLB display and the post-export assembly drawer without console
  errors. It does not close rollback, document-pack, upload, degraded-provider,
  interruption or every edit/recovery branch. No global convergence is claimed.
- The 2026-09-12 isolated Chrome smoke additionally covers a real WebGL pick,
  grouped sector focus, a targeted azimuth edit that produced a second certified
  Blender version, durable conversation restoration and an explicit rollback.
  The edit used the controlled deterministic fallback after the provider call
  failed, so it is not evidence of successful live LLM editing. Document-pack,
  provider-degraded and process-interruption branches are not all browser-accepted.

## Can wait

- WebSocket.
- Queue/job manager.
- Merging version bookkeeping into the adaptation graph.
- Advanced mesh-level QA.
- Production Docling.
- Full frontend mutation-flow acceptance and deeper 3D bundle optimization.
- A journaled, idempotent multi-store delete. Today SQLite memory is purged
  before checkpoints and workflow files; a later failure aborts deletion but
  does not restore already-purged memory rows.

## Generic Cognitive 3D Core V1 — limites bloquantes de livraison

- Le chemin GPT-OSS `openai/gpt-oss-120b` a produit au moins une décomposition
  de composants génériques plausible, mais le scénario complet reste instable:
  Groq retourne encore des HTTP 400 de validation JSON ou des objets incomplets
  malgré les appels découpés, retries et réparations bornées. Aucun fallback
  déterministe ne doit être présenté comme une décision LLM réussie.
- Les scénarios réels obligatoires escalier, jardin aménagé et objet simple
  n'ont pas tous été générés, révisés et certifiés de bout en bout avec le
  provider réel. Les tests d'intégration utilisent un client LLM contrôlé et
  Blender réel; ils prouvent le déterministe, pas la fiabilité externe.
- La réutilisation générique atteint désormais Blender pour un asset explicitement
  autorisé par composant indépendant, quantité un, placement rigide explicite,
  sans déformation. Seul ANT_PANEL_4G_001 est activé dans cette tranche : source
  interne, aucune qualification constructeur. `compose` exécute désormais un
  alignement rigide requis par composant, avec orientation copiée et décalage
  mondial explicite. La QA du GLB mesure cette relation. `adapt`, modification
  de la source, contact, fixation, collision et relations arbitraires restent
  bloqués. Le test avant/après utilise deux générations et un planner contrôlé;
  il ne prouve pas une édition frontend ni la fiabilité du provider réel.
  Les manifests non activés ne publient toujours aucune stratégie générique.
- Le compilateur génère chaque composant déclaré, mais il n'existe pas encore de
  solveur générique de placement/relations qui prouve la cohérence spatiale d'un
  assemblage arbitraire à partir d'ancres et connecteurs.
- La QA générique ne contient ni critique visuelle multimodale ni boucle bornée
  critique-réparation-régénération. Les previews front/side/top/closeup sont
  vérifiées pour intégrité/provenance; seule la preview principale alimente la
  gate de cadrage actuelle.
- Le frontend expose les preuves cognitives réelles disponibles, mais le
  scénario utilisateur créant, sélectionnant et modifiant trois projets
  génériques réels n'est pas encore une acceptance validée.
- La surface conversationnelle restaure désormais les demandes de création et
  d’édition enregistrées dans le journal durable, ou une origine documentaire
  explicitement système, ainsi que des notifications issues des résultats réels.
  Les anciens workflows restent partiels, car ils ne contiennent pas
  rétroactivement leur prompt initial. Il n’existe
  toujours ni transcript complet de tours assistant, ni modèle de sessions ou
  de projets explicitement sélectionnables.

## Accès de maintenance généré — 2026-09-12

Les échelles et plateformes des tours treillis sont une géométrie procédurale
interne issue d'un profil manifesté. Elles améliorent l'inspection technique,
mais ne constituent pas un équipement constructeur, une conception de
protection contre les chutes, une justification de charges, une preuve de
fixation, une validation de dégagement fin ou une autorisation d'installation.

La preuve post-Blender contrôle les rails/barreaux, les dimensions et niveaux
des plateformes et un dégagement AABB contre les équipements principaux. Elle
ne remplace pas une collision triangle/BVH, la vérification des contacts ou une
analyse structurelle. Le viewer expose donc cet ensemble en inspection seule;
son édition ciblée reste indisponible.

## Revue de bibliothèque professionnelle — 2026-09-12

- Le Studio permet d'examiner le dossier du candidat Sierra
  Wireless/Semtech `6001124` et le maintient explicitement hors génération.
- La hiérarchie STEP et le passage du maillage dans Blender ont été observés,
  mais cela ne qualifie ni le repère d'installation, ni les interfaces
  mécaniques, ni les droits d'utilisation du projet.
- Les fichiers RRU Ericsson/Huawei et le support RFS sondés restent des sources
  DWG ACIS sans conversion qualifiée. Ils ne doivent pas être assemblés au
  candidat Sierra sur la seule base de leurs noms ou de leur proximité dans le
  corpus.
- Le STEP, le GLB, le rapport et les cinq vues restent dans une quarantaine
  locale ignorée par Git. Le Studio expose `available`, `partial` ou
  `unavailable`; un clone propre reste fermé et ne propose que la source
  constructeur. Les hashes du manifest sont portables, pas les octets soumis
  aux conditions du fournisseur.
- La qualification refuse explicitement Blender 5.1.2 présent sur le même
  poste; seul Blender 4.5.12 LTS satisfait ce contrat de preuve.
- La prise en charge du nombre décimal LibreDWG `123.` corrige la lecture du
  diagnostic de `Radio_2260.dwg`; elle ne convertit aucun solide et ne change
  aucune décision d'admission.
