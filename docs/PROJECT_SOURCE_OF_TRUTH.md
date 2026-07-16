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
- Not yet a complete vendor-grade asset library.

## Current backend

- FastAPI exposes design workflow, document-pack, RAG, memory, asset, and
  Product APIs.
- `/designs` and `workflow_id` are the stable product contract for the next
  frontend. Do not add `/projects`, `/runs`, `job_id`, or a new state model
  unless a later architecture decision proves it necessary.
- LangGraph is used for prompt workflows, document-pack generated requirements,
  and scene revision generation. Edit patch creation and version bookkeeping
  remain service-level logic outside the graph.
- Groq `openai/gpt-oss-120b` is used when a real key is configured; otherwise
  explicit deterministic extraction.
- GPT-OSS is the bounded decision layer for ambiguous extraction, controlled
  RAG candidate arbitration, and edit-patch interpretation. It may revise a
  typed proposal, but it cannot bypass `RequirementSpec`, `SceneSpec`, telecom
  rules, Blender's parametric generator, or QA. Governance constrains scope,
  records evidence, and preserves rollback; it does not invent geometry.
- Public product responses expose GPT-OSS truth through `extraction_provider`,
  `llm_provider`, `llm_available`, `llm_fallback_used`, and
  `llm_fallback_reason`; the frontend must display fallback/degraded status
  instead of guessing.
- Primary RAG: NVIDIA API `baai/bge-m3`.
- RAG fallback policy: no automatic local embedding model in the product path.
  Deterministic hash is allowed only for tests/bootstrap or explicit degraded
  mode; it is not product-quality retrieval.
- Reranker: NVIDIA API by default with visible fail-open degraded passthrough.
  Local `BAAI/bge-reranker-v2-m3` remains an explicit developer override only.
- RAG evidence is written to `rag_evidence.json` and exposed through
  `/viewer-bundle`; it lists retrieved sources, controlled candidate hints,
  reranker status, and limitations.
- Memory: local SQLite with writeback; optional Qdrant for some summaries.
- Document-pack: synchronous ZIP, limited PDF/OCR/DXF extraction, consolidation,
  conflicts, corrections, QA.
- Blender: real generation when Blender is found; Blender fallback is rejected
  by default for quality (`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0`).

## Current frontend

- `apps/frontend` is a Vite + React + TypeScript work-in-progress connected to
  the real FastAPI backend with Zod contract validation.
- The first technical kernel was rejected as too dashboard-like. It must not be
  treated as an accepted product gate.
- The current frontend direction is a product studio rework: conversation-first
  command, dominant 3D viewer, contextual drawers, narrative agent progress,
  document-pack intake, visible QA/RAG/issues, and no raw JSON as the primary
  surface.
- It consumes `/designs` + `workflow_id`, not `/projects`, `/runs`, `job_id`, or
  a new state model.
- The command field starts empty; example prompts are user-selected helpers, not
  hidden demo state.
- The viewer loads only backend artifact URLs and must show either a visible GLB
  or an explicit backend preview/error fallback during smoke.
- This frontend is not accepted as final until a real smoke proves: prompt or
  document pack -> backend workflow -> streamed progress -> visible GLB or honest
  fallback -> QA/RAG/issues/artifacts in user language.
- Old dashboard patterns remain rejected.

## Current assets

- 12 manifests.
- 12 GLB files present.
- 0 tower without a local GLB.
- Expected `/assets/inventory` status: `ready_for_import`.
- The three historically missing towers (monopole, rooftop, small-cell) are now
  internal project generated assets produced with Blender.
- Current assets are internal/CC-BY and not vendor-grade.
- Towers are generated parametrically by default. GLB import happens only when
  the resolver explicitly selects `imported_glb_exact` or
  `internal_project_generated`.

## Current 3D and QA

- `SceneSpec + parametric generator` is the source of truth for geometry.
- GLB is only the exported viewer result, not the source of truth.
- Blender produces `design.glb`, `preview.png`, `scene_metadata.json`, and
  reports.
- Real QA categories:
  - `glb_parse_structural`
  - `mesh_level_transform_basic` — GLB accessors plus readable role transforms
    and approximate antenna HBA when transforms are available
  - `mesh_level_basic` — real bounding box from GLB accessors
  - `object_name_based_geometry`
  - `metadata_based_height_azimuth`
  - `preview_pixel_framing_basic`
- Mesh QA v1 checks: GLB parse OK, tower height approximation, scene above
  ground, scale realism, antenna count, readable object transforms when present,
  approximate HBA from antenna node transforms when possible, RRU/cable/cabinet/GPS
  presence, concrete pad presence when requested, and real label object presence.
- Mesh QA v1 does **not** verify exact antenna azimuth from vertices and does
  **not** perform collision/RF/structural wind-load validation.
- Preview QA parses PNG pixels and checks subject occupancy, framing, clipping,
  centering, contrast, and resolution. It is still not semantic visual review.
- QA does not yet finely validate materials or vendor exact mesh dimensions.
- Do not call this QA "advanced geometry".

## Events and runtime

- Events are persisted in JSONL and pushed through an in-memory queue per
  workflow while the local workflow thread is alive.
- `/events/stream` is now `push_sse`: it replays persisted JSONL events first,
  then streams live queue events until `workflow_completed` or
  `workflow_failed`.
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
- Startup recovery distinguishes an interrupted initial generation from an
  interrupted revision. Initial generation fails without a valid product
  version; an interrupted revision marks only its candidate version failed,
  restores the last completed active version, clears `active_operation`, and
  emits `edit_patch_rejected`.
- Mutating generation endpoints enforce configurable free-space admission via
  `TELECOM_STUDIO_MIN_FREE_DISK_MB` (256 MB by default) and return HTTP 507
  before creating orphan state when local persistence is unsafe.
- `/timeline-summary` exposes frontend-readable timeline steps with label,
  phase, node, status, started/completed timestamps, duration, warning count,
  error count, progress message, and artifact refs when available.
- Public workflow/edit/version responses expose artifact URLs, not local
  filesystem paths. `asset_imports[].resolved_path` remains internal only.
- Frontend "scene plan" maps to the `scene_spec` artifact. `SceneSpec` remains
  the geometry source of truth.
- `/viewer-bundle` exposes viewer-ready artifact URLs for GLB, preview,
  metadata, SceneSpec, QA report, generation report, geometry validation, and
  technical report, plus a compact QA summary for drawers.
- Public workflow/viewer responses expose `rag_planning_summary` and
  `rag_evidence_url` so the frontend can distinguish retrieved context from
  structured hints that actually influenced SceneSpec planning. RAG is not used
  for RequirementSpec extraction in v1.
- Edit and rollback responses expose frontend action URLs (`viewer-bundle`,
  `timeline-summary`, `user-issues`, `current-operation`) and available actions
  so the UI does not infer post-action state.
- Public workflow/product responses expose `runtime_capabilities` and
  `unsupported_actions`; cancel, pause, resume, same-workflow retry,
  human-in-loop, and WebSocket runtime are explicitly unsupported in v1.
- Streaming is local-process only: no cross-process broker, cancellation, or
  durable resume manager yet.

## Current verdict

`FRONTEND_PRODUCT_REWORK_IN_PROGRESS`

The backend contract is consolidated around `/designs` + `workflow_id`. The
frontend now has reusable real-backend pieces, but the previous dashboard-like
kernel is not accepted as product UX. The active frontend work must prove a
studio experience, not only a connected technical shell.

The frontend must keep these limitations visible: `mesh_level_transform_basic`
or `mesh_level_basic` QA, local-process `push_sse`, limited document-pack
intelligence, fail-open reranking, non-vendor-grade assets, and no durable
broker/cancellation.

Backend proof remains `tests/e2e/test_telecom_generation_proof.py` plus targeted
Product API, RAG, LangGraph, Blender, and QA tests. Frontend acceptance requires
the checks and smoke described in `apps/frontend/FRONTEND_KERNEL_README.md`.
