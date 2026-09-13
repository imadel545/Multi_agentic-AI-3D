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

## Mainline and runtime recovery — 2026-09-10

`main` is the active development branch. The 29 local commits through `b5c5674`
were pushed normally after fetch, ancestry and secret review. Remote `main` was
verified at that SHA; the merged local development branch was deleted. A local
`mainline-recovery-20260910` tag preserves this checkpoint.

The host runtime was captured outside the repository at
`/Users/imad/Desktop/Multi_agentic-AI-3D-recovery/20260910-mainline` using SQLite
Backup API plus full output/vector copies and a verified SHA-256 manifest of
2,865 stable files. Raw CAD was neither copied nor modified. Cleanup removed
1,371 proven pytest workflows, 1,371 associated designs, 16,373 error rows,
112 checkpoints, 314 checkpoint writes and one explicitly named test pack.
The 32 unknown-origin workflow directories and remaining pack are preserved.
182 workflow, 164 design, 2,182 error and 128 pack memory rows remain recoverable
in SQLite as `UNKNOWN`, excluded from product recall and vector projection.

New memory writes carry origin and eligibility. Only eligible `PRODUCT` rows
feed product experience; tests run with `TEST`, and evaluation services can use
`EVALUATION`. Existing identities cannot silently change origin; conflicting
memory writes skip without failing geometry generation. SQL origin checks and
writes share one immediate transaction. Workflow status persists its origin.
The active memory projection is rebuilt empty, and six unconsumed historical
collections are removed after backup. Static knowledge and qualified assets stay
intact. Docker volumes were not inspected because its daemon was unavailable.

Static vector rebuilding encountered a real external limitation: the configured
NVIDIA embedding model returned HTTP 410, citing retirement on 2026-08-25.
Two available alternatives timed out on the bounded 25-document benchmark;
Nemotron 3 answered one single-query probe (2,048 dimensions), which is not
retrieval-quality validation. No replacement model or hash-based product index
was silently installed. The static vector rebuild remains pending; explicit local
lexical degradation remains the supported retrieval path when the provider fails.

Raw library search now uses a separate cached lexical ranking module with corpus
IDF, bounded bilingual concepts, exact token/reference signals, unit-token
normalization and content deduplication. It fixes substring false positives and
returns matched-term evidence through the existing endpoint. Search remains
metadata-only and cannot qualify or select raw CAD for Blender automatically.

## Native CAD inspection boundary — 2026-09-10

`python -m scripts.inspect_native_cad source.dwg --output /tmp/new-cad-proof`
now runs a quarantined native-polyface inspection through LibreDWG, a source/DXF
comparison, deterministic extraction, real Blender GLB export/reimport and two
inspection renders. This CLI does not modify the catalog or create a completed
design workflow. `generation_eligible` and `professional_qualified` remain false.

The real `ac3_billo2.dwg` chair source preserves 7,952 source vertices and 12,720
faces across four modelspace meshes. LibreDWG's unsigned hidden-edge face indices
are decoded only after source-handle/index equality. Vertex ordering, declared
units and mesh membership are checked; DWG meshes inside blocks are refused by
this initial source-comparison bridge. Direct DXF extraction separately supports
nested INSERT placement, with source handles and hierarchy retained.

The chair declares millimetres despite a raw height of 0.675 units. Its resulting
0.675 mm height is retained, not silently corrected; physical scale is unqualified.
Overlapping mesh pairs in the source are retained. CAD materials and missing
design parts are not reconstructed. This proves native mesh transport, not a
professional telecom asset or a complete usable chair. No generated catalog asset is
admitted from this path. ACIS telecom conversion, professional assembly and frontend
integration of this inspection remain open.

## Professional STEP candidate evidence — 2026-09-12

The bounded `scripts.qualify_step_asset` command now records a local review for
one real manufacturer source without promoting it into generation. The source
is the official Sierra Wireless/Semtech `6001124` 2-in-1 MIMO panel antenna
STEP. Its manifest is `ANT_SIERRA_6001124_REFERENCE` with
`geometry_status=reference_only`; the STEP, derived GLB and previews remain in
the quarantined workspace outside Git. The manifest preserves their immutable
hashes; `/assets/inventory` and the review drawer expose whether those local
bytes are available, partial or absent on the current installation.

The source declares millimetres in its STEP header. OCP XDE preserved one
top-level assembly, 20 occurrences and 18 mesh leaves with stable definition
entries. The complete extracted extents are 0.468118 × 0.093021 × 0.044536 m
because the two cable runs are included; the housing leaf measures about
150 × 49 × 45 mm and is kept distinct from the assembly extents. Real Blender
4.5.12 LTS, verified before qualification against the shared runtime contract,
produced and re-imported a GLB with 18 meshes and 49,478 triangles;
the independent post-Blender measurement found 126,238 vertices, 18 component
identities and a 0.0 m maximum roundtrip vertex error. Perspective, front, side,
top and housing close-up PNGs passed the bounded framing/contrast evidence gate.

The record captures the product role, source hash, hierarchy, dimensions,
datasheet connector/mount summaries, and explicit adaptation limits. Two SMA
plugs, two RG174 cable runs and the bolt mount are source/datasheet observations;
their mating anchors, orientation and installation fit remain unverified. The
candidate is visible in the studio asset drawer for provenance review, but it
cannot be selected by the cognitive compiler or sent to Blender until rights,
anchors and engineering qualification are completed.

## Exact catalog reuse checkpoint — 2026-09-10

The generic cognitive compiler now executes a bounded `reuse` decision through
one compiler-authored `exact_asset` node per independent component. The initial
opted-in source is `ANT_PANEL_4G_001`, an internal project-generated panel; this
is not a manufacturer-qualified asset. Each source has explicit rigid placement,
quantity one, unchanged scale/materials and pinned manifest/GLB hashes. Parameter
adaptation and procedural rebuilding of imported sources are rejected. The rigid
composition checkpoint below extends the original independent-reuse boundary.

Admission executes catalog/file validation and explicitly reports
`blender_executed: false`. Actual completion still requires Blender, exported
mesh QA and certificate 1.3. The real runtime test passed in 13.95 s: source
vertices and PBR materials are preserved, exported world transforms include the
requested one-metre placement, source hashes enter the build lock, and the
completion certificate is issued. Planning uses a controlled test client;
this does not establish live-provider reliability.

The existing chat adds an “Intention libre” entry, with backend routing and
experimental wording. Component proofs distinguish catalog reuse from generated
geometry. Frontend automated checks cover these changes; their visual acceptance
is pending. No additional browser session was used in this slice.

## Rigid catalog composition checkpoint — 2026-09-10

`compose` now executes a bounded required `aligned_with` relationship between
singleton exact catalog components. Each driven component has one target and an
explicit `offset_world_m` vector. The compiler derives its position and copies
target orientation; an explicitly placed `reuse` component roots the acyclic
chain. Unsupported relations, ports, parents, cycles, multiple drivers, manual
placement of driven components and unauthorized transforms are refused.

The persisted SceneSpec carries `rigid_component_relations`, and exported GLB QA
measures relative position and orientation while checking that component meshes
remain descendants of their placement nodes. This is a required mesh QA check,
not just planning metadata. Component proofs distinguish `compose` from `reuse`.
Source geometry/materials remain unchanged; contact, fastening and collision
are not inferred from aligned origins.

The real Blender regression generated two internal panels at 0.80 m and 1.20 m
relative X offsets in two separate runs. Both received completion certificates;
the fixed component and source-local vertices remained unchanged. Deliberately
displacing the exported driven node by 0.05 m fails mesh QA. The two runs use a
controlled planner, not a live-provider or frontend edit/version acceptance.
This does not add professional assets or generic parameter adaptation.

## Sector subassembly evidence and usable 3D focus — 2026-09-11

The first user-facing telecom-quality correction is bounded to a real, certified
three-sector assembly. Its `ANT_PANEL_4G_001` panel is an internal project
asset imported exactly with a manifest/file hash; its mounts and RRUs are
contract-generated. It is not a manufacturer-qualified installation assembly.
The reference-only Sierra/Semtech STEP candidate remains excluded from planning
and generation.

After Blender exports the actual `design.glb`, the worker renders one close-up
for each sector and writes render-byte metadata. An independent process then
checks the exported GLB semantic extras, stable sector roots, expected roles,
PNG hash, resolution, subject coverage, contrast, centring and clipping. The
versioned build lock binds this `sector_preview_evidence.json`; it is rechecked
before the corresponding product URL can serve an image. The 2026-09-11 native
Blender 4.5.12 LTS run generated and revalidated all three sector images.

The inspection image frames the mechanical panel/support/radio group. Where a
cable route exists, it is required in the exported GLB but not framed because
its real descent to the tower base would make the close-up unreadable. This
makes no claim about cable termination, RF continuity, fastening, load or
manufacturer fidelity.

The Studio viewer retains the exact selected semantic root for picking and
editing, but derives camera focus only from the published `component_proofs`
sharing its stable `instance_id`. It includes proven antenna, mount and radio
roots and excludes a full-height cable route. Thus selecting a cable now frames
the sector it belongs to rather than shrinking the antenna to fit the complete
tower. The toolbar returns to the complete design by clearing selection. No
name parsing, synthetic sector or universal constraint solver is introduced;
legacy workflows retain their existing single-root/global focus behaviour.

The exported overall preview remains a technical view and is not yet a
professional presentation. On 2026-09-12, an isolated Chrome/WebGL smoke loaded
the certified design, picked an antenna from the real GLB, framed its proven
antenna/mount/radio group and opened the matching sector inspection. The product
surface used the readable label `antenne du secteur S3`; the backend semantic
root remained internal. This closes the bounded picking/focus proof, not the
professional visual-quality gate. No vendor-grade asset or installation quality
is claimed by this checkpoint.

## Targeted editing checkpoint — 2026-09-09

The local `codex/asset-assembly-convergence` slice connects certified component
selection to bounded conversational editing. The backend verifies the selected
version and component-proof hash, filters planner capabilities, then independently
restricts the resulting patch. Antenna poses and RRU offsets are supported;
single-quantity generated groups are supported by the API. Unsupported or stale
selections are rejected. Whole-scene regeneration still runs through Blender/QA;
this is not an incremental mesh editor.

The real Blender M0 regression now builds a third version changing sector S2
from 120 to 80 degrees, verifies unchanged S1/S3 exported world transforms,
checks the new certificate and rejects a stale selection. It passed in 47.16 s
on native Blender 4.5.12. Planning transports in this test are controlled;
the targeted edit uses the explicit deterministic fallback, not a live LLM.
This exposed and fixed inconsistent normalization in the assembly evidence
angle recalculation without changing QA tolerances.

The frontend supports picking known component identities and framing all meshes
of a selected assembly. The isolated browser workflow `wf_6baad6cdb0df` selected
the S2 antenna, submitted a 130-degree azimuth edit, produced certified Blender
version `v04a88085`, and recorded the user request and outcome in the durable
conversation. The provider edit call failed and the explicit deterministic
fallback applied the user's exact numeric value; this is not recorded as a live
LLM success. Two later vague edits were refused without producing versions, and
an explicit rollback restored `v519150d5` while preserving `v04a88085` in
history. A subsequent Chrome reload restored the conversation and active GLB,
then picked S3 with the readable product label and verified sector close-up,
with no console, network or HTTP error observed.

The three-source [CAD benchmark](QA_STRATEGY.md#cad-conversion-benchmark--2026-09-09)
produced no admissible mesh. No professional asset was promoted. Library-first
professional assembly remains open; this slice improves verified editability,
not manufacturer fidelity, physical fastening or collision certification.

## Previous delivery checkpoint — 2026-08-11

`MILESTONE 1 — PARTIEL`

- The recovered M1 and convergence work is now local on `main`. The verified
  pre-M1 baseline remains commit `4829995130a43c09c5fb0c23d4216ed007e2d2c2`,
  tagged locally as `cognitive-3d-m1-baseline-20260808`; those commits were subsequently pushed during the 2026-09-10 mainline consolidation.
- The existing Groq callers now share a governed transport and versioned
  capability profiles. `openai/gpt-oss-120b` remains the strict structured
  text-decision model. `qwen/qwen3.6-27b` is a separate opt-in advisory
  capability for multimodal interpretation and asset-preview review. Project
  consent is disabled by default, persisted with the workflow and exposed by
  the public API. Configuration alone never reports the capability as
  operational.
- The shared Groq transport accepts an ordered pool while preserving the legacy
  scalar key. Selection is atomic least-in-flight with round-robin ties and a
  bounded per-credential concurrency. HTTP 401 quarantines one credential,
  HTTP 403 restricts only the rejected capability, and HTTP 429 cools one
  credential while another is tried immediately. If all credentials are rate
  limited the call fails fast without sleeping a workflow thread. Ambiguous
  read/write/protocol failures are not replayed on another account. Aggregate
  pool health exposes counts only, never key identity or secret material.
- A controlled live gate on 2026-08-11 resolved four distinct credentials from
  separate accounts and completed one locally validated strict JSON response
  through every configured pool slot. This proves all four configured accounts
  for that point-in-time text request only; it is not a permanent Groq
  availability guarantee and does not qualify the inaccessible Qwen path.
- The live provider gate covers every Groq pool slot, a bounded asset-selection
  contract, a bounded planning contract, and a Groq/NVIDIA/real-Blender product
  workflow with `llm_bounded` asset selection. Its final result and duration are
  recorded in the gate section below. Asset and planning decisions expose
  closed request-specific schemas whose atomic choices map only to locally
  authorized candidates; planning cannot combine a keep action with a candidate
  ID. Deterministic validation remains the final authority. An earlier
  run exposed Groq's account-specific HTTP 413
  `rate_limit_exceeded` response for the larger asset-selection payload; the
  transport now treats that machine code as credential rate limiting and
  fails over instead of misclassifying it as invalid model output.
- The vision contract records only bounded observations, input hashes, source
  regions, confidence, limitations and invocation provenance. Vision-only
  requirement evidence is inferred and requires confirmation; it cannot create
  an exact dimension or override deterministic QA. No live Qwen proof,
  automatic document-workflow invocation, PDF rasterization route, or versioned
  8+8+8 vision evaluation has passed in this milestone.
- `QualifiedAssetCandidateRetriever` and typed `AssetDecisionPacket` contracts
  now unify candidate exposure. The telecom assembly route persists the
  semantic strategy chosen from its authorized candidates and validates it
  deterministically. The generic cognitive route can expose qualified
  candidates. This earlier compiler limitation was superseded on 2026-09-10
  for opted-in exact `reuse` and bounded rigid `compose`; `adapt` remains open.
- The current runtime catalog contains 14 manifests: 13 usable
  internal/technical manifests and one real professional candidate kept as
  `reference_only`. **0 of 14 passes the new professional M1 proof gate**.
  Generation eligibility is now an effective runtime decision rather than the
  qualification declaration alone: any manifest claiming a vendor source,
  vendor-qualified fidelity, manufacturer or reference must pass
  `ProfessionalAssetVerifier`. Its `professional_asset_qa.v1` report must bind
  the asset ID, qualification version, master hash, viewer hash and passed mesh,
  dimensions, pivot and orientation checks. The published source hash must
  match the master representation. Registry selection and snapshots, decision
  packets, cognitive reuse, exact-asset execution and trusted assembly all fail
  closed when this admission fails. A professional identity is admitted only
  through its exact qualified viewer import; a generic parametric builder cannot
  inherit manufacturer identity from an unrelated proof bundle. The configured
  manifest directory must resolve to `<project_root>/assets/manifests`, keeping
  API selection, snapshots, trusted-input hashing and Blender on one catalog.
- This closes a declaration-only bypass; it does not admit a new professional
  asset. Structured rights status is now part of the manifest and admission
  gate; Sierra is explicitly `review_only`, with project, derivative and
  redistribution authorization all false. No catalog publication transaction
  or project authorization has been completed.
  Sierra Wireless/Semtech `6001124` remains `reference_only`, and raw DWG ACIS
  remains `source_only`.
- Consequently, no current-tree professional Blender/browser end-to-end run
  proves the required seven real assets, asset previews, reuse/adapt/compose,
  procedural complement, GLB, QA, provenance and targeted new version. The
  older local technical-generic asset-driven acceptance below remains valid for
  its stated scope only; it does not close this professional qualification gate.
- This milestone does not change Nemotron retrieval, SQLite authority, Docker
  topology, or the ban on PostgreSQL/BGE-M3 work and free-form Blender code.

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
- Groq `openai/gpt-oss-120b` is used when at least one real key is configured; otherwise
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
  Deterministic hash is allowed only for tests/bootstrap. Static product
  documents are embedded by one cross-collection operation, sent to NVIDIA in
  bounded batches of at most 32 passages with no automatic SDK retry on the
  synchronous path. If NVIDIA indexing or query embedding fails,
  the service ranks the real local corpus lexically, publishes
  `rag_retrieval_status=degraded_local_lexical` and retains the failure reason;
  it never presents that fallback as vector retrieval.
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
- The current camera fit keeps a real tall tower readable when a wide civil
  foundation would otherwise dominate a portrait viewport. Only the fit box is
  narrowed under a measured disproportion: no GLB node is hidden or removed.
  The previous fixed-distance fog was removed because it could obscure tall or
  extended certified scenes. Desktop page scroll is contained while the
  conversation feed remains independently scrollable; mobile restores natural
  page scroll.
- A 2026-08-11 read-only current-tree browser smoke loaded the existing
  certified `wf_0843599873e7` GLB at 1440 x 1000 and 1047 x 2748. It confirms
  visible framing and scroll ownership only. Providers were disabled and no
  design was generated, so this is not Groq/NVIDIA, conversion or CAD-fidelity
  evidence.
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
- The 2026-08-10 current-tree smoke restored certified workflow
  `wf_e465a9cd4414`, loaded its real GLB, called `/assets/inventory` during
  bootstrap and opened Composition against the real API. It displayed seven
  technical assets as professional-proof incomplete, zero professional preview,
  zero raw `qualified_for_generation` label and no browser console error. This
  proves truthful display for the restored technical scene, not the missing
  professional M1 asset chain.
- Old dashboard patterns remain rejected.

## Current assets

- 14 manifests: 13 generation-eligible internal/technical assets and one
  manufacturer candidate kept as `reference_only`.
- 12 GLB files present.
- The procedural-only dual-band panel intentionally has no companion file and
  is not reported as a missing asset file.
- 0 tower without a local GLB.
- Expected `/assets/inventory` status: `qualified_mixed_catalog`.
- 13 manifests are generation-eligible: 3 authorize an exact GLB import and 10
  authorize SceneSpec-driven parametric generation; one real STEP candidate is
  `reference_only`.
  The cable-tray family is now qualified through its typed parametric route,
  not through an exact mesh import. The bracket companion GLB is not imported,
  but its typed procedural builder and connector contract are
  generation-qualified.
- Exact import authorization is fail-closed: the manifest pins SHA-256, units,
  dimensions, pivot, orientation and mesh-integrity review. A changed file is
  rejected; it is not silently replaced by procedural geometry.
- The three historically missing towers (monopole, rooftop, small-cell) are now
  internal project generated assets produced with Blender.
- The generation catalog remains internal/CC-BY and not vendor-grade. The
  Sierra Wireless/Semtech candidate is visible for provenance review, but is
  not part of the generation catalog.
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
- The bounded professional subassembly candidate is now
  `3D/Antenne/RFS/Fixation/APM40/APM40_Fixation.dwg` from the local corpus
  (catalog `lib_44c738f8639aff42ee3b`). Its source hash, DWG header, units and
  four ACIS solids are observable through the library probe. It is not a
  manufacturer-qualified or Blender-ready asset: the source has no native mesh,
  the block hierarchy/axes/extents have not crossed a B-Rep bridge, and no
  anchors or installation fit have been verified. Owner authorization allows
  the qualification work, but does not turn those missing proofs into facts.
- The installed ODA Drawings Explorer 27.1.0.0 remains an interactive inspector,
  not a governed conversion service. No supported local batch exporter for
  SAT, STEP or a mesh is present, so its internal B-Rep libraries are never
  called directly. The next legitimate admission test needs a documented export
  capability and a one-source quarantine benchmark before any RFS geometry can
  enter Blender.
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
  it. `AssemblyPlan 1.1` additionally requires `constraint_evidence.json`,
  generated by re-reading the exported GLB before promotion. A runner-owned
  `build.lock.json` schema `1.2.0` binds these artefacts. The lock contains the
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
- `constraint_evidence.json` reconstructs glTF world matrices and measures every
  required mechanical connection from exported component roots or dedicated
  exported anchor nodes. Position tolerance comes from connector snapshots;
  normal opposition and `up` alignment use the evidence-v1 angular tolerance.
  Missing, duplicated, mismatched or moved anchor nodes fail closed. Every
  `resolved_from_operation` endpoint also requires exactly one exported support
  node with the declared identity and a real glTF mesh; the public summary
  exposes `resolved_support_count`. This proves the support mesh exists, not
  surface contact, fastener engagement, load transfer or manufacturability.
  Required non-mechanical connections are listed but not evaluated, and the report does
  not claim contact, collision, fasteners, load capacity or electrical/RF
  continuity.
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
  - `assembly_constraint_post_export_v1` — exported anchor-frame position and
    orientation only
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
- Certificate schema `1.4.0` is required for `AssemblyPlan 1.1`. It certifies
  `component_proofs.json`, `constraint_evidence.json`, their checks, the final
  GLB hash and the canonical plan hash. Schema `1.2.0` remains the component-
  proof certificate for non-assembly GeometryPrograms; schema `1.3.0` remains
  the bounded cognitive-plan certificate. Legacy schema `1.1.0` remains valid
  only for scenes that require none of those stronger proofs.
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
- The local API now allowlists `Host`, uses an explicit no-credentials CORS
  surface, and rejects every state-changing browser request whose present
  `Origin` is not an allowed local frontend before calling the service. API and
  Nginx responses carry framing, MIME, referrer, permissions and CSP headers;
  HSTS is intentionally absent on HTTP loopback. This protects the local
  browser boundary but is not user authentication: there is no account, JWT or
  remote-access contract.
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
  `constraint_evidence_url`, `assembly_constraint_summary`,
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
- A current-tree live probe on 2026-08-11 exposed a Groq
  `json_validate_failed` response for the former per-role object containing a
  bounded choice plus free-form reason. This was a model-output contract
  rejection, not quota, rate limit or timeout. The provider schema is now the
  minimal closed mapping `role_id -> choice_id enum`; the local table still
  reconstructs and validates the indivisible asset/generation/semantic tuple.
  The corrected live probe passed without Blender. Model-authored selection
  prose was removed because it had no execution authority.
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
- Current-tree browser proof on 2026-08-11 created `wf_0843599873e7` from the
  chat-first flow against the real FastAPI runtime, four-account Groq pool,
  NVIDIA retrieval/reranking and Blender 4.5.12 LTS. It completed in 23.348 s
  (RAG 1.620 s; Blender 19.112 s), published certified version `v8995acb1`,
  rendered a 122-node/114-mesh GLB, loaded RAG evidence and exposed the
  Bibliothèque/Intelligence drawers with no browser console warning/error.
  Retrieval was `primary_vector`, reranking `primary_nvidia_reranker`, and asset
  selection `llm_bounded` without fallback. The evidence measured 3/3 required
  mechanical instances and one resolved support mesh; the required RF route is
  real GLB geometry but remains explicitly unevaluated post-export.

## Current verdict

`ASSET_DRIVEN_TELECOM_ASSEMBLY_V1_ACCEPTED_LOCAL`

The implementation contains the trusted assembly, component-proof, build-lock,
completion-proof, SQLite/Qdrant recovery and frontend recovery contracts
described below. Current-tree creation is confirmed from the real frontend
through FastAPI and Blender. The bounded edit/version path is confirmed by the
focused API/Blender E2E, not by the final browser replay. This is a local
milestone acceptance, not a global convergence, vendor-grade engineering
certification, or acceptance of every generic 3D scenario.

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
  a candidate/strategy pair governed by `bounded_asset_selection@1.2.0`; an
  unknown ID or strategy is rejected. A `model_output_rejected` response permits
  exactly one immediate second model call; auth, rate-limit, timeout and
  transport failures are not replayed by this client. If unavailable or rejected twice,
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
- The corresponding current-tree deterministic proof is 180/180 frontend tests,
  frontend typecheck and production build, and 764 default backend tests in 30.46 s.
  The immediately preceding convergence tree also passed the focused real-Blender
  qualified 4G assembly/edit/version test (1/1 in 44.39 s) and complete provider
  gate (4/4 in 34.69 s); these runtime results were not rerun after the later
  viewer-layout and tower-less generic-adaptation changes. That Blender test
  certifies 9/9 mechanical instances before and
  after the bounded RRU offset edit.
  This bounded run is not a claim that the entire Python or browser acceptance
  matrix passed.

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
frontend now has a verified chat-first/3D-first product baseline and 209 passing
component/contract tests. Current-tree connected creation, real GLB picking,
targeted edit/version, durable conversation restoration and explicit rollback
have each passed in the isolated product path. The 2026-09-12 current-tree smoke
also removed backend semantic roots and RAG/SceneSpec/Blender jargon from the
normal selection, conversation, progress and source-decision surfaces. Every
degraded, document-pack and interruption branch still remains a broader product
release gate outside this milestone.

The frontend must keep these limitations visible: `mesh_level_spatial_basic`,
`mesh_level_transform_basic` or `mesh_level_basic` QA, local-process `push_sse`, limited document-pack
intelligence, fail-open reranking, non-vendor-grade assets, and no durable
broker/cancellation.

The primary current assembly/edit/version proof is
`tests/e2e/test_m0_trusted_assembly_recovery.py`; the older
`tests/e2e/test_telecom_generation_proof.py` remains complementary. Product API,
RAG, LangGraph, Blender and QA tests provide the narrower contract proofs.
Frontend acceptance requires the checks and smoke described in
`apps/frontend/FRONTEND_KERNEL_README.md`.

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
- Le frontend reconstruit le contexte actif depuis le prompt/exigences et les
  demandes effectivement enregistrées du workflow, expose la scène, les
  stratégies, la provenance, les composants sélectionnables dans le viewer et
  la galerie des previews réelles. Les créations enregistrent leur texte
  utilisateur ou, pour un dossier documentaire, une origine système explicite;
  les éditions nouvellement reçues sont enregistrées dans le journal durable
  avant exécution. Leurs issues sont des notifications système fondées sur le
  résultat réel, jamais des réponses assistant inventées. Les workflows
  historiques restent explicitement partiels et il n’existe ni transcript
  assistant complet, ni sélecteur de sessions. Il ne présente plus une erreur
  globale de synchronisation lorsque le bundle certifié principal est déjà
  disponible.

Ce statut n'est pas `IMPLEMENTED`: le parcours télécom GPT-OSS réel du
2026-08-03 passe après correction des contrats JSON, des bounds de sweep, des
transformations booléennes et de l'ancrage au sol, mais les trois scénarios
génériques réels ne sont pas tous passés. La limitation initiale de réutilisation
a été dépassée le 2026-09-10 pour les sources explicitement activées : `reuse`
exact et `compose` par alignement rigide sont exécutables. `adapt`, assemblage
arbitraire et qualification professionnelle restent ouverts. Aucune convergence
globale n'est déclarée.

## Accès de maintenance du pylône — 2026-09-12

Une demande télécom explicite peut maintenant décrire une échelle d'accès et des
niveaux de plateformes de maintenance. Pour une tour treillis dotée du profil
manifesté `TOWER_LATTICE_30M`, le `SceneSpec` porte ce profil et les niveaux
demandés; le worker Blender 4.5 LTS produit des rails, barreaux, plateformes
latérales, garde-corps, plinthes et supports sous une identité sémantique stable
`tower_access_<asset_id>`.

Cette capacité concerne uniquement une géométrie procédurale technique interne.
Elle n'est ni une géométrie de fabricant, ni une qualification professionnelle,
ni une preuve de résistance, d'antichute, de fixation, de conformité ou
d'approbation de chantier. Le manifest reste `technical_generic`.

Après export, `tower_access_evidence.json` relit le GLB et vérifie l'identité
du profil, deux rails et les barreaux de l'échelle, la hauteur de chaque plateau,
ses dimensions, les garde-corps/plinthes/supports et l'absence de
chevauchement AABB avec les équipements principaux. La preuve est hashée,
incluse dans le build lock, obligatoire au certificat 1.5 et recontrôlée avant
activation, lecture, rollback ou service d'artefact.

Le workflow d'évaluation isolé du 2026-09-12 a exécuté GPT-OSS pour analyser le
brief, puis Blender 4.5.12 LTS pour le GLB. Il a matérialisé 97 barreaux et deux
plateformes demandées à 18 m et 26 m, sans chevauchement AABB des plateaux avec
les équipements principaux. La réponse `viewer-bundle` expose seulement un
résumé d'inspection et l'artefact de preuve; la sélection de cet ensemble dans
le Studio est volontairement `inspection_only`, sans édition ciblée.

Le résultat améliore la lisibilité d'un pylône technique, mais ne transforme
pas le site entier en conception télécom professionnelle. Les assets
constructeur, les détails de fixation, les collisions fines et la validation
d'installation restent ouverts.

## Revue produit des candidats professionnels — 2026-09-12

La bibliothèque du Studio expose maintenant le dossier du candidat constructeur
Sierra Wireless/Semtech `6001124` depuis l'inventaire réel et l'endpoint de
provenance. L'utilisateur voit l'identité, la source STEP, les dimensions
publiées, l'état du contrôle géométrique et les preuves encore manquantes. La
recherche par fabricant ou référence filtre les composants sans rapport.
Les aperçus locaux sont résolus sur l'origine réelle de l'API et ne dépendent
plus du proxy Vite. Le dossier reste accessible après une future admission et
publie la décision de droits ainsi que la disponibilité locale des preuves.
Aucun bouton d'ajout ou d'utilisation n'est proposé tant que
`generation_eligible=false`.

Cette revue ne promeut pas l'asset. Le candidat reste `reference_only` : son
repère d'installation, ses ancres, ses connecteurs, sa compatibilité mécanique,
les droits du projet et la QA professionnelle ne sont pas validés. Les preuves
techniques détaillées restent consultables sans devenir le texte principal de
l'interface.

La sonde DWG accepte aussi le dialecte JSON réel observé sur `Radio_2260.dwg`,
où LibreDWG émet une valeur décimale avec point final en plus de valeurs non
finies. La normalisation est bornée, tracée par `parser_mode` et ne rend pas le
fichier exploitable : la sonde confirme trois solides ACIS, 34 régions, les
unités millimètres, aucun maillage natif et aucune admission à la génération.


### Vérification de la revue — 2026-09-13

La qualification publiée réutilise le verdict effectif d'admission dans le
registre, le retriever et les documents RAG. Les droits de projet sont
explicites ; leur enregistrement ne constitue pas une expertise juridique.
Une preuve QA contradictoire ne permet plus de présenter géométrie, pivot ou
orientation comme vérifiés. Un aperçu exige son hash, une structure PNG valide
et les dimensions déclarées ; son endpoint refuse les données incohérentes et
sert les images valides en affichage inline. Les tests de contrat ne supposent
plus la présence du cache Sierra ignoré par Git.

Validation : 819 tests backend passent, 1 est ignoré et 55 sont désélectionnés
hors gates Blender/provider ; 212 tests frontend passent, ainsi que TypeScript,
bundle et Ruff. Après le changement inline, les 7 tests du contrat public ont
été rejoués avec succès. Sur API isolée 8023 et frontend 5183, health, dossier
et cinq PNG répondent HTTP 200. Le parcours navigateur bibliothèque → examiner
Sierra a exposé le dossier réel, ses limites et ses cinq liens vers l'API.
L'ouverture directe de l'image a été bloquée par le client navigateur : cette
étape visuelle n'est donc pas déclarée acceptée. Aucune nouvelle génération
LLM, composition professionnelle ou édition de ce candidat n'est prouvée par
ce contrôle de consultation. Le candidat reste reference_only.
