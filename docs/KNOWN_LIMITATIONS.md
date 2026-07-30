# Known Limitations

Active limitations that must remain visible in the API, reports, and future
frontend.

## Visible during frontend build

- `apps/frontend` has a visually verified real-backend product baseline, but the
  complete frontend gate is still limited: document-pack generation, edit,
  rollback and degraded fallbacks need one recorded end-to-end acceptance pass.
- The first technical kernel was rejected as too dashboard-like; permanent
  stage grids, capability counters, raw workflow ids, and raw JSON surfaces must
  not come back.
- The Three.js/React Three Fiber viewer is already lazy-loaded, but its production
  chunk is about 976 kB minified (267 kB gzip); deeper engine-level splitting is
  still a performance task.
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
- LLM state is visible through `extraction_provider`, `llm_provider`,
  `llm_available`, `llm_fallback_used`, and `llm_fallback_reason`; fallback is
  acceptable only if the frontend displays it.
- Agents are typed deterministic specialists or bounded LLM wrappers; this is
  not a free-form autonomous Blender coding system.
- The main topology is still predominantly fixed. A typed deterministic
  `DesignBlueprint` stage now routes the currently required asset-composition,
  RF and structural specialists, persists composition intent, and proves
  `RequirementSpec -> DesignBlueprint -> SceneSpec`. It is not yet an
  LLM-selected blueprint candidate system or an autonomous supervisor.
  Asset selection is still first-compatible rather than scored across multiple
  qualified candidates; connector intents, conflict aggregation, recalled
  designs as planning candidates, and a bounded post-Blender critique/rebuild
  loop remain missing.
- Prompt workflows, document-pack generated requirements, and scene revisions
  enter the main compiled graph. Edit interpretation now enters a separate
  checkpointed LangGraph adaptation graph; version bookkeeping remains
  service-level.
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

- NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` at 1024 dimensions is the
  product provider. `baai/bge-m3` remains supported as an explicit model choice.
- A configured provider is reported as `configured_unverified` until a real
  operation succeeds. On 2026-07-28, the key authenticated successfully and
  listed `baai/bge-m3`, but that model returned HTTP 500 for both scalar and
  batched embedding calls. The configured Nemotron replacement returned a real
  1024D embedding with the same key.
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
- RAG search accepts logical collection names only. Runtime invalidation removes
  active, obsolete, base and abandoned `__build_` collections and serializes
  searches/writes across the publication boundary.
- The optional Docker service is loopback-only but still pins legacy Qdrant
  server `v1.9.2`. Existing storage needs a tested stepwise migration before an
  upgrade; this server must not be exposed to a LAN or the Internet.
- Reranker product path is NVIDIA API, but it is fail-open. If unavailable,
  vector order is used and `rag_reranker_degraded_reason` must be displayed.
  Local reranker is an explicit developer override, not product default.
- Memory is still limited: workflow recall is predominantly deterministic SQL
  matching. The compact Qdrant projection is operational for explicit semantic
  search and future bounded recall, but it is not yet allowed to mutate
  `RequirementSpec` or `SceneSpec` directly.
- `rag_context_count > 0` does not mean the 3D plan changed. In v1, only
  structured, whitelisted `payload.planning_hints` can affect planning; RAG is
  not used for RequirementSpec extraction. Use `rag_evidence.json` for sources
  and candidate hint proof.

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
- Tool failures, timeouts and non-UTF/invalid JSON probe output are returned as
  controlled quarantine errors; they never qualify a file or expose a raw decode
  exception as a product result.
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
- The audited macOS host now has Blender 4.5.12 LTS arm64 installed at
  `/Applications/Blender 4.5 LTS.app`; its background/factory-startup smoke and
  28 focused Blender/golden/runtime tests pass. The older Blender 5.1.2 bundle
  remains installed and still crashes during Metal detection, so the resolver
  deliberately prefers the pinned LTS path. Executable presence alone remains
  insufficient proof on other hosts.
- Blender fallback is rejected by default, but missing assets can still become
  visible procedural geometry during a real Blender generation.
- Geometry source of truth is `SceneSpec + parametric generator`; GLB is only
  the exported viewer result.
- Mesh QA v1 is `mesh_level_spatial_basic` when semantic transforms and all
  primary-equipment bounds are readable, `mesh_level_transform_basic` when only
  transforms are complete, otherwise `mesh_level_basic`. It computes bounds
  from real GLB `POSITION` bytes, verifies basic HBA/azimuth transforms and
  rejects unexpected AABB overlap among antennas, RRUs, GPS and cabinets.
  Same-sector antenna/RRU contact uses a 0.15 m minimum-axis penetration bound;
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
- New schema `1.1.0` commits also bind persisted QA, geometry-validation and
  GLB-inspection reports and compare `SceneVersion.scene` with the persisted
  `scene_spec.json`. Historical `1.0.0` results remain legacy evidence.
- New Blender builds copy the complete Python worker-source bundle into an
  immutable per-attempt snapshot, execute that copy, then hash it in the lock.
  Historical schema `1.0.0` locks contain only the entry-script hash and remain
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
- The tower validator uses height only as a conservative trigger for aviation-marking
  review. It does not determine whether lighting is legally required; national rules,
  obstacle location and the competent aviation authority remain authoritative.
- Internal/CC-BY assets are not vendor-grade.
- The 5G panel and RRU parametric outputs are multi-part
  `technical_generic` profiles with explicit LOD, but they still do not prove a
  vendor model, exact RF ports, thermal performance, maintenance clearance or
  fabrication fitness.
- The overview preview still lacks a certified sector-equipment close-up. Its
  camera bounds now ignore technical annotations, but role-specific pixel
  visibility/contrast remains future work.
- The curated manifest catalog is intentionally mixed: 4 GLBs are qualified
  for exact import, 6 component/tower profiles are qualified for controlled
  parametric generation, and 2 GLBs are reference-only. The 5G panel and RRU
  companion GLBs have not passed orientation qualification and are therefore
  never imported by the product path.
- Asset qualification proves file identity, basic mesh integrity, declared
  dimensions, pivot and orientation for the authorized use. It does not prove
  vendor identity, RF performance, structural capacity or fabrication fitness.

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
