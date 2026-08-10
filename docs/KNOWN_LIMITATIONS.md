# Known Limitations

Active limitations that must remain visible in the API, reports, and future
frontend.

## Visible during frontend build

- `apps/frontend` has a visually verified historical real-backend product
  baseline and 151 passing M0 Vitest tests plus green typecheck/build. The
  2026-08-04 Docker smoke restored a certified real GLB and two-version design
  without browser console errors. Document-pack generation, rollback and
  relevant degraded/retry paths still need a recorded browser acceptance pass.
- The first technical kernel was rejected as too dashboard-like; permanent
  stage grids, capability counters, raw workflow ids, and raw JSON surfaces must
  not come back.
- The Three.js/React Three Fiber viewer is lazy-loaded and its runtime is split
  into cacheable production chunks. The 2026-07-31 build keeps every JavaScript
  chunk below 371 kB uncompressed, but the complete 3D dependency set remains
  substantial and still benefits from browser caching.
- Old dashboard patterns remain rejected.
- No `/projects` or `/runs` API is added in v1. The frontend maps its "run"
  concept to `workflow_id` and "scene plan" to `scene_spec`.
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
- The shared Groq transport adds bounded transient retries, a configurable
  `Retry-After` sleep cap (30 seconds by default) and a per-capability circuit
  breaker, but no live Qwen call was accepted in M1.
  `configured_unverified` remains different from `operational`; a configured
  key is not health proof.
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
  hash retrieval is allowed only for tests/bootstrap or explicit degraded mode;
  hash is not production quality.
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
  `browser_smoke` gates. The fast gate passed 586 tests in 24.29 seconds on
  2026-08-10. The runtime audit completed the real-Blender cases; its only
  additional failure was a non-Blender domain-routing regression that has since
  been moved back to the fast gate and fixed with positive and negative routing
  coverage. A missing-Blender failure-path test was also returned to the fast
  gate, leaving 52 tests that actually require Blender. The Blender gate is
  intentionally not represented as fast CI.

## Documents

- Document-pack is synchronous, 80 MB max.
- Pack corrections, generated-workflow linkage and reads are serialized by an
  in-process per-pack lock; each JSON file is atomically replaced and fsynced.
  A correction still spans several compatibility files, so a host/process crash
  between replacements can leave a mixed revision. A single revision envelope
  or write-ahead journal remains required for crash-level transactions.
- Document-pack generation requires a foundation compatible with the confirmed
  tower type. If evidence is missing, the pack is blocked until a user
  correction supplies the value; the backend does not invent a concrete pad.
- `/document-packs/capabilities` is honest and reports
  `document_pack_status=limited`.
- OCR is limited and depends on installed Tesseract + languages.
- Docling is import-only / not active by default.
- DXF document-pack extracts text/layers; it is not a solid-CAD importer.
- The local CAD library is fully copied and catalogued, but remains quarantined:
  11,974 files, 11,531 unique contents, 443 duplicate contents and 0
  generation-eligible entry. No global licence file was found in the source.
- LibreDWG `dwgread` provides honest DWG metadata/entity probes. Sample telecom
  models contain `3DSOLID` ACIS/B-Rep entities, so converting them through DXF
  alone is not accepted as mesh proof. A real B-Rep conversion tool and
  post-conversion unit, mesh, semantic-role and visual QA are still required.
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
  `/Applications/Blender 4.5 LTS.app`, but the 2026-08-05
  background/factory-startup smoke exits by `SIGSEGV` in USD
  `Arch_ValidateAssumptions`; eight focused Blender-runner tests therefore fail
  before the worker script executes. Blender 5.1.2 fails the same smoke. The
  Product API now reports Blender unavailable when this runtime smoke fails;
  executable presence is no longer treated as readiness proof. The Docker
  `linux/amd64` Blender runtime is a separate path and must pass its own health
  smoke.
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
  `scene_spec.json`. Schema `1.2.0` is required for `AssemblyPlan 1.1` or
  GeometryProgram component evidence and additionally certifies
  `component_proofs.json`. Historical `1.0.0` results remain legacy evidence.
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
- The curated manifest catalog is intentionally small: all 13 manifests are
  generation-eligible, with 3 GLBs qualified for exact import, 10
  component/tower profiles qualified for controlled parametric generation and
  0 reference-only entry. The 5G panel and RRU
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

## M1 professional asset qualification gate

- Status is `MILESTONE 1 — PARTIEL`. The verified baseline is local commit
  `4829995130a43c09c5fb0c23d4216ed007e2d2c2` and tag
  `cognitive-3d-m1-baseline-20260808` on branch
  `codex/m1-asset-qualification`.
- All 13 current runtime assets fail the stronger professional proof gate.
  They do not collectively provide a neutral master, qualified viewer lineage,
  explicit professional provenance/licence, five passed asset previews,
  typed anchors/connectors and the required qualification QA.
- The public gate is now byte-verified by `ProfessionalAssetVerifier`, not
  copied from the manifest declaration. Missing/out-of-root/tampered
  master/viewer/previews/report files, invalid GLB/PNG data, inconsistent
  dimensions or out-of-bounds anchors fail closed. This verifier does not
  create the missing neutral CAD source, prove licensing rights or validate a
  B-Rep semantically.
- No neutral STEP/B-Rep sample is currently admitted for the requested
  professional structure, antenna, RRU, support, ground cabinet, GPS and
  platform roles. DWG `3DSOLID`/ACIS remains `source_only`; metadata search or
  an LLM decision cannot convert it into exact geometry.
- `QualifiedAssetCandidateRetriever` and `AssetDecisionPacket` improve the
  decision contract, not the underlying fidelity. Telecom persists and
  validates semantic strategies. Generic cognitive retrieval now exposes
  candidates, but the generic compiler cannot yet execute asset
  `reuse`/`adapt`/`compose`, so it publishes no allowed asset strategy.
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
- A green test suite, HTTP scenario or older browser capture does not close the
  remaining browser gate. No global convergence is claimed.

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
- L'Asset Intelligence générique sait désormais rechercher et exposer des
  candidats qualifiés sous forme d'`AssetDecisionPacket`, mais elle n'est pas
  encore opérationnelle jusqu'à Blender. Le compilateur générique ne sait pas
  exécuter `reuse`/`adapt`/`compose`; la route publie donc zéro stratégie asset
  autorisée et reste procédurale à l'exécution.
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
