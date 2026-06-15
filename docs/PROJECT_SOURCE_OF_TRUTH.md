# Project Source Of Truth

Active master document. All other documentation must stay aligned with this
file.

## Product

Local-first, single-user studio to turn a telecom brief or document pack
(PDF, ZIP, DXF, images) into a `SceneSpec`, Blender/GLB artefacts, QA, versions,
and rollback.

The end goal is a chat-first and 3D-first product, but that UI does not exist
yet.

## What the project is not

- Not a multi-user SaaS.
- Not a dev dashboard.
- Not an LLM-free-form Blender code generator.
- Not marketing proof where a fallback is presented as a real result.
- Not yet a complete vendor-grade asset library.

## Current backend

- FastAPI exposes design workflow, document-pack, RAG, memory, asset, and
  Product APIs.
- LangGraph is used for prompt workflows, document-pack generated requirements,
  and scene revision generation. Edit patch creation and version bookkeeping
  remain service-level logic outside the graph.
- Groq `openai/gpt-oss-120b` is used when a real key is configured; otherwise
  explicit deterministic extraction.
- Primary RAG: NVIDIA API `baai/bge-m3`.
- RAG fallback: local `sentence-transformers`, then deterministic hash as last
  resort.
- Reranker: local `BAAI/bge-reranker-v2-m3` best-effort; passthrough if
  unavailable.
- Memory: local SQLite with writeback; optional Qdrant for some summaries.
- Document-pack: synchronous ZIP, limited PDF/OCR/DXF extraction, consolidation,
  conflicts, corrections, QA.
- Blender: real generation when Blender is found; Blender fallback is rejected
  by default for quality (`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0`).

## Current frontend

- No operational frontend.
- Old React/Vite dashboard is rejected.
- `apps/frontend` may exist as an empty local folder, but it contains no
  application.
- Do not rebuild the frontend until product APIs, timeline, asset fallback, and
  QA are reliable.

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
  - `mesh_level_basic` — real bounding box from GLB accessors
  - `object_name_based_geometry`
  - `metadata_based_height_azimuth`
  - `preview_luminance_only`
- Mesh QA v1 checks: GLB parse OK, tower height approximation, scene above
  ground, scale realism, antenna count.
- Mesh QA v1 does **not** verify individual antenna HBA/azimuth from vertices
  and does **not** perform collision detection.
- QA does not yet finely validate transforms, materials, or exact mesh
  dimensions.
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
- `/timeline-summary` exposes frontend-readable timeline steps with label,
  phase, node, status, started/completed timestamps, duration, warning count,
  error count, progress message, and artifact refs when available.
- Public workflow/edit/version responses expose artifact URLs, not local
  filesystem paths. `asset_imports[].resolved_path` remains internal only.
- `/viewer-bundle` exposes viewer-ready artifact URLs for GLB, preview,
  metadata, SceneSpec, QA report, generation report, geometry validation, and
  technical report, plus a compact QA summary for drawers.
- Edit and rollback responses expose frontend action URLs (`viewer-bundle`,
  `timeline-summary`, `user-issues`, `current-operation`) and available actions
  so the UI does not infer post-action state.
- Streaming is local-process only: no cross-process broker, cancellation, or
  durable resume manager yet.

## Current verdict

`BACKEND_PRODUCT_READY_FOR_FRONTEND_BUILD`

The backend can generate tested local 3D workflows and exposes frontend-safe
product surfaces for status, live progression, viewer bundle, edit, versions,
timeline, current operation, document-pack capabilities, and user issues. The
frontend still does not exist; the next step is to build it against this
backend product contract, while keeping the documented limitations visible.
