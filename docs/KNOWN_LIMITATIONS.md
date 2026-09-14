# Known Limitations

These are active product limits. Point-in-time runtime proof is recorded once in
[PROJECT_SOURCE_OF_TRUTH.md](PROJECT_SOURCE_OF_TRUTH.md); old suite totals and
workflow checkpoints are not current capability claims.

## Local owner and runtime state

- The product supports one local owner. The runtime stores were intentionally
  reset on 2026-09-14 after an external backup: projects, conversations,
  workflows, generated outputs, document packs, checkpoints, runtime memory,
  sessions, and owner registration are empty. Static knowledge and catalog inputs
  remain. The next launch requires owner registration.
- Git retains source and documentation history. It does not restore ignored
  databases, Qdrant runtime collections, generated outputs, provider responses,
  credentials, or deleted local sessions.
- Authentication is a loopback contract. Password hashes use `scrypt`; only
  hashes of opaque expiring session tokens are stored. There is no password
  recovery, multi-user authorization, remote administration, or TLS termination.
  LAN or Internet exposure requires a separate deployment and recovery design.
- Native and Docker runtimes have independent storage and distinct cookie names.
  A login, project, or design in one is not automatically present in the other.

## Frontend and workflow runtime

- The frontend is connected to the real Product API, but not every mutation in
  [FRONTEND_ACCEPTANCE_CRITERIA.md](FRONTEND_ACCEPTANCE_CRITERIA.md) has one
  complete recorded browser replay. Unit tests, typecheck, build, HTTP smoke, and
  a restored GLB prove different boundaries.
- A document pack enriches only a non-empty command. Upload or restoration does
  not start design generation. The current edit endpoint does not consume a newly
  attached pack.
- The workspace filesystem and its SQLite link cannot commit atomically across a
  process crash. Workflows remain independently recoverable, but a crash can
  leave organization links to reconcile.
- SSE is an in-process event stream with JSONL replay and polling recovery. It is
  not token streaming, a distributed broker, or a durable job system.
- Cancel, pause, resume, same-workflow retry, human-in-loop checkpoints, and
  WebSocket runtime are unsupported. The local thread executor has bounded
  admission but no cross-process ownership or recovery.
- Large checkpoint churn is compacted only above configured thresholds. The disk
  admission guard prevents unsafe new writes; it is not a retention scheduler.
- The previous dashboard layout remains rejected. Raw workflow IDs, provider
  internals, stage grids, and QA/RAG JSON must not return as primary UI.

## Models and agents

- Deterministic extraction covers bounded French and English telecom patterns,
  evidence, contradictions, and explicit corrections. It cannot understand every
  free-form brief.
- Groq improves bounded extraction, planning, asset choice, editing, and
  `GeometryProgram` authorship only while a configured request succeeds. A key or
  successful historical request is not permanent availability proof.
- Multiple Groq credentials have isolated concurrency, cooldown, and capability
  state, but accounts may have different TPM/RPM limits. HTTP 413 and 429 can
  exhaust the ready pool. Per-attempt timeouts do not yet form one workflow-wide
  token/call/deadline budget.
- Missing or invalid out-of-catalog geometry fails closed. There is no
  deterministic component generator that pretends to replace the geometry
  specialist.
- The specialist graph is typed and bounded, but predominantly fixed. The generic
  supervisor route is persisted provenance; it does not dynamically invent or
  replace specialists. There is no autonomous conflict aggregator, recalled-
  design authority, or post-Blender critique/rebuild loop.
- `GeometryProgram` supports governed primitives, polygonal curves, profiles,
  extrusion, revolution, sweep, arrays, exact booleans, instances, materials,
  transforms, and a bounded modifier set. It is not a B-Rep modeler, arbitrary
  topology editor, imported-mesh editor, or general Geometry Nodes graph.
- Workflows cap geometry intents, components, and aggregate program nodes. Asset
  and generated-component decisions can still fan out without a global LLM call
  budget or sibling cancellation after the first failure.
- Optional remote vision remains consented and advisory. The document-pack path
  does not automatically rasterize PDFs or invoke image understanding, and vision
  does not participate in certification.
- Python dependencies use bounded minimum versions rather than a fully locked
  release environment. A fresh resolution still requires security and runtime
  verification.

## RAG and memory

- NVIDIA `nvidia/nemotron-3-embed-1b` at 2048 dimensions is configured for
  product embeddings. The bounded 25-document proof does not establish broad
  telecom retrieval quality.
- Provider configuration starts as `configured_unverified`. A real success or
  failure changes the public state; the API must not infer health from a key.
- NVIDIA passage and query inputs are distinct. Collections are isolated by
  provider, model, input profile, and dimension so incompatible vectors are not
  mixed.
- When NVIDIA indexing or query embedding fails, the real corpus is ranked
  lexically and `degraded_local_lexical` is exposed. This continuity path is not
  equivalent to semantic vector retrieval. Deterministic hash embeddings are for
  tests/bootstrap only.
- Hosted NVIDIA text rerankers checked for this delivery were unavailable.
  Runtime reranking is explicit passthrough with no model name; no hidden local
  neural reranker is loaded.
- The static corpus and evaluation set are small. `rag_context_count > 0` does
  not mean the plan changed; only whitelisted structured planning hints can do so,
  and `rag_evidence.json` is the evidence boundary.
- SQLite is canonical. Qdrant is a derived projection published through a local
  durable outbox. Publication is recoverable but not distributed; pending or
  failed projection state means semantic memory is degraded.
- Runtime memory has no age-based retention policy. Invalid legacy `SceneSpec`
  rows remain canonical but are skipped from the current projection until an
  explicit migration. Recall cannot mutate requirements or scenes directly.
- Non-empty Qdrant upgrades require a supported migration. Qdrant must remain
  loopback-bound.

## Documents and CAD

- Document packs are synchronous and bounded to 80 MB. Multi-file corrections
  atomically replace individual compatibility files, but the whole correction is
  not yet one crash-safe revision envelope.
- OCR depends on installed Tesseract languages. Docling is import-only and not
  active by default. DXF intake extracts bounded text/layers; it is not a solid
  CAD importer. Missing foundation or vendor facts remain unknown or generic
  with visible warnings.
- The local `MAJ des Blocs` library is a quarantined discovery corpus. Directory
  labels, metadata matches, source images, and RAG scores do not prove licence,
  geometry, scale, hierarchy, or generation fitness. No raw entry is admitted
  automatically.
- Representative telecom DWGs contain ACIS/B-Rep `3DSOLID` entities. LibreDWG
  probes inventory them but do not tessellate them. A converter exit code or DXF
  down-conversion is insufficient when the solid payload or mesh is absent.
- The installed ODA Drawings Explorer is an interactive inspector, not a verified
  headless SAT/STEP/mesh export service. A legitimate B-Rep bridge plus unit,
  hierarchy, mesh, semantic, visual, rights, anchor, and Blender-roundtrip QA is
  required before admission.
- The Sierra Wireless/Semtech STEP candidate remains `reference_only`. Preserved
  hierarchy and Blender roundtrip do not resolve source rights, anchors, mating
  fit, orientation, engineering approval, or permission for generation.
- Native polyface/DXF inspection is a quarantined CLI route. It does not create a
  completed product design or establish manifoldness, physical scale, source
  material fidelity, or professional telecom suitability.

## Blender, geometry, and QA

- A real GLB requires the qualified Blender runtime and a successful background
  readiness probe. A different installed Blender version or a fallback artifact
  cannot silently satisfy completion.
- Docker uses the qualified Linux x64 Blender under Apple Silicon emulation. It
  is materially slower than the native ARM runtime and uses a bounded technical
  render profile, not photorealistic certification.
- Missing assets may use procedural geometry only when the manifest explicitly
  permits and reports it. Exact imports fail closed on missing or changed bytes.
- `SceneSpec` is the geometry source of truth. The exported GLB is a viewer
  artifact; an LLM never edits Blender code directly.
- Mesh QA reads real GLB vertices and indices, but its collision check is
  broad-phase AABB screening with a bounded same-sector antenna/RRU contact rule.
  It is not triangle/BVH collision, self-intersection, connector-zone, clearance,
  manifold, weld, or structural validation.
- Anchor and support evidence measures exported transforms and mesh presence. It
  does not prove contact, fastening, load transfer, RF/electrical continuity,
  fall protection, or manufacturability.
- The completion certificate is a deterministic integrity record, not a signed
  third-party engineering approval. It binds only the declared checks and
  artifacts.
- Preview QA measures pixels, framing, contrast, occupancy, and clipping. It is
  not a semantic or professional visual review. Full-scene framing can still be
  weaker than a dedicated equipment inspection.
- Internal panels, RRUs, towers, mounts, ladders, platforms, cabinets, and GPS
  are technical generic profiles unless their manifest says otherwise. Their
  dimensions and semantic parts do not establish vendor fidelity, material,
  wind load, installation fit, or regulatory compliance.
- `GeometryProgram` validates bounded construction and envelope constraints, but
  there is no general judge for natural-language semantic correctness. Placement
  prose is provenance, and custom roles are not all included in primary-equipment
  interference checks.

## Release gates still open

- No manufacturer asset has completed the full professional admission chain into
  product generation.
- No representative telecom retrieval evaluation establishes NVIDIA embedding
  quality or a remote reranker benefit.
- No single recorded browser session covers every remaining mutation and
  degraded/error branch.
- No engineering authority has validated structural, RF, electrical,
  installation, safety, or fabrication fitness.
