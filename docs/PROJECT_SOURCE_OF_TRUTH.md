# Project Source Of Truth

Active master document. Other active documentation must remain aligned with this
file. Historical delivery narratives belong to Git history, not to the current
capability description.

## Product boundary

The project is a local-first, single-owner studio that turns a telecom brief or
a document pack into a validated `RequirementSpec`, `DesignBlueprint`,
`SceneSpec`, Blender/GLB artifacts, QA evidence, versions, and rollback. The
product direction is chat-first and 3D-first.

It is not a multi-user SaaS, a developer dashboard, an unrestricted Blender code
generator, an engineering certification service, or a complete vendor-grade
asset library. A fallback, preview, catalog hit, or configured provider is never
presented as a verified generated design.

## Verified runtime evidence — 2026-09-14

This is the sole active documentation record of the requested point-in-time
runtime proof:

- Docker workflow `wf_41f68442a558` used Groq
  `openai/gpt-oss-120b` extraction without deterministic fallback, executed real
  Blender, completed on its first Blender attempt as version `v3b665901`, and
  issued a completion certificate. Independent exported-geometry checks passed
  for the requested antenna anchors and platform supports, and the frontend
  loaded the resulting GLB. The panels and RRUs remained technical generic
  profiles; this did not prove vendor or engineering fidelity.
- The Docker API embedded the 25 controlled static documents with NVIDIA
  `nvidia/nemotron-3-embed-1b` at 2048 dimensions and completed one French vector
  search. `/studio/summary` reported the NVIDIA embedding path operational,
  without retrieval degradation, and explicit `passthrough_no_rerank`. This
  proves bounded transport, indexing, and search only; it is not a representative
  telecom retrieval-quality evaluation.
- The Groq result proves one successful configured request path at that time. It
  does not prove permanent service availability, every configured credential,
  or all model outputs.

After an external backup, the owner reset the local runtime database, runtime
indexes, generated outputs, sessions, and owner registration on 2026-09-14.
Static knowledge and catalog inputs remain. The workflow identifiers above are
therefore prior-to-reset historical evidence retained with the external backup,
not queryable records in the empty runtime. Git commits preserve source history;
they do not preserve ignored runtime databases, provider responses, generated
outputs, or external availability.

## Current backend

- FastAPI exposes design workflows, document packs, RAG, memory, assets, and
  frontend-safe Product APIs.
- `/designs` and `workflow_id` are authoritative for execution, artifacts, QA,
  and versions. `/workspace` organizes local projects, conversations, drafts,
  and optional links without introducing a second run state model.
- Prompt creation, document-enriched creation, and scene revision pass through
  validated LangGraph workflows. Edit adaptation discovers declared
  capabilities, plans, validates, and only then mutates `SceneSpec`; version
  bookkeeping remains service-level.
- `RequirementSpec` preserves typed evidence, candidate values, assumptions,
  conflicts, and confirmations. Unresolved explicit contradictions block before
  RAG, planning, `SceneSpec`, and Blender.
- The deterministic specialist DAG writes `DesignBlueprint`, then compiles
  `SceneSpec`. Asset composition is a fail-closed gate; RF, structural, and
  conditional geometry-policy specialists run through bounded declared routes.
  Dependencies, execution waves, provider authority, and fallback reasons are
  persisted.
- GPT-OSS may choose only supplied planning or asset candidates and may author a
  bounded declarative `GeometryProgram`. It cannot add specialists, execute
  Python, access paths or URLs, or call arbitrary Blender operations.
- `SceneSpec`, including selected manifests, trusted `AssemblyPlan`, and any
  `GeometryProgram`, remains the only geometry source of truth.
- Public responses expose provider, model, availability, fallback, degradation,
  and GeometryProgram provenance. Technical failures are mapped to user-facing
  messages while durable internal journals retain diagnostic detail.
- A document pack is synchronous bounded context for a non-empty prompt. It can
  ingest direct files or ZIP, perform limited PDF/OCR/DXF extraction, consolidate
  sourced facts and conflicts, accept corrections, and bind its input hashes in
  an analysis receipt. It cannot create a workflow by itself.

## Providers, RAG, and memory

- Groq `openai/gpt-oss-120b` is the configured decision model. When extraction
  can degrade safely, deterministic extraction is explicit and recorded. Missing
  geometry generation fails closed rather than fabricating a component.
- Provider requests use HTTPS outside loopback, bounded timeouts and completion
  budgets, structured output where supported, local schema validation, no tool
  use, and visible fallback diagnostics. Multiple credentials are isolated by
  capability and cooldown; configuration is not health proof.
- NVIDIA `nvidia/nemotron-3-embed-1b` is the product embedding model. Static
  documents use the passage input profile in bounded batches; queries use the
  query profile. Collections are isolated by provider, model, input profile, and
  vector dimension.
- Provider state is `configured_unverified` until a real operation succeeds. A
  failed operational call is reported as degraded or failed, never silently as
  primary neural retrieval.
- If NVIDIA indexing or query embedding fails, the service ranks the real local
  corpus lexically and exposes `degraded_local_lexical` with its reason.
  Deterministic hash embeddings are restricted to tests/bootstrap.
- Reranking is explicit passthrough because the checked hosted NVIDIA text
  rerankers were unavailable. Its provider is `passthrough`, its model is null,
  and no local neural reranker is implied.
- `rag_evidence.json` records retrieved sources, controlled planning hints,
  provider state, reranker state, and limits. Retrieved context does not prove it
  changed the plan.
- SQLite is canonical memory. Qdrant is a derived projection published through a
  durable SQLite outbox. Projection failure cannot roll back or replace the
  canonical mutation. New collections are versioned by embedding identity;
  incompatible legacy collections are not mixed into them.

See [RAG_STRATEGY.md](RAG_STRATEGY.md) for the operational retrieval contract and
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for quality limits.

## Current frontend

- `apps/frontend` is a Vite, React, and TypeScript rework connected to the real
  FastAPI API with runtime schema validation.
- The active layout is conversation-first and 3D-dominant. QA, alerts, assets,
  composition, deliverables, and versions are contextual drawers. Raw workflow
  IDs, capability counts, stage grids, provider tokens, and QA/RAG JSON are not
  primary product UI.
- Projects own visible conversation branches. Drafts, exact workflow restoration,
  navigation blocking during mutations, compact conversation history, and
  contextual destructive menus are persisted through `/workspace`.
- The composer starts empty. It supports a compact attachment chip with real
  filenames, document count, and guarded removal. Successful removal, refusal,
  and storage failure are explicit states rather than inferred from message copy.
- The viewer loads backend artifact URLs only and must display a real GLB or an
  explicit backend preview/error fallback. Diagnostic labels, beams, arrows, and
  markers are hidden by default and excluded from physical component counts.
- SSE supplies event-level progress, with polling recovery. The UI does not claim
  token streaming or expose chain-of-thought.
- Local owner authentication uses the configured API base URL, credentialed
  requests, and credentialed cross-origin SSE when a development override is
  used. Docker and native runtimes use distinct configurable cookie names to
  avoid overwriting each other's sessions on localhost.
- Remaining browser acceptance items are tracked only in
  [FRONTEND_ACCEPTANCE_CRITERIA.md](FRONTEND_ACCEPTANCE_CRITERIA.md).

## Current assets and CAD boundary

- The catalog has 14 manifests: 13 generation-eligible internal/technical assets
  and one manufacturer candidate retained as `reference_only`. Twelve local GLB
  files are present; the procedural-only panel intentionally has no companion
  file. Inventory status is `qualified_mixed_catalog`, not vendor-grade.
- Exact imports pin source hash, units, dimensions, pivot, orientation, and mesh
  review and fail closed if bytes change. Parametric builders operate only through
  declared profiles and bounded parameters.
- Internal panel, RRU, tower, cable, accessory, ladder, and platform profiles are
  technical geometry. They do not establish manufacturer identity, structural
  capacity, mounting fit, or regulatory compliance.
- The Sierra Wireless/Semtech STEP candidate is visible for provenance review but
  remains excluded from planning and generation until rights, anchors, orientation,
  installation fit, and engineering qualification are complete.
- The local `MAJ des Blocs` CAD corpus remains quarantined and ignored by Git.
  Catalog and metadata search aid discovery; directory labels, nearby images,
  DWG entity counts, and RAG scores do not qualify geometry.
- Representative telecom DWGs contain `3DSOLID` ACIS/B-Rep data without an
  accepted native mesh. LibreDWG inventory and DXF conversion are not a B-Rep
  tessellation path. The installed ODA viewer is an interactive inspector, not a
  governed batch converter.
- A source enters the generation catalog only after a documented conversion path
  and source, rights, units, hierarchy, geometry, semantic-role, visual, anchor,
  and Blender roundtrip evidence pass. No LLM or retrieval decision can bypass
  that admission gate.

## Current 3D and QA

- Real completion requires a qualified Blender runtime. Merely locating an
  executable is insufficient; readiness is checked with the governed background
  factory-startup profile. Blender fallback is rejected by default.
- Trusted `AssemblyPlan` binds catalog and builder snapshots, exact source bytes,
  allowed parameters, anchors, connectors, and operations. The isolated Blender
  worker revalidates them before construction.
- Blender writes the GLB, preview, scene metadata, component proofs, and any
  required constraint or tower-access evidence. A runner-owned build lock binds
  the raw SceneSpec, worker bundle, runtime identity, trusted inputs, and artifact
  hashes.
- GLB QA reads actual buffers and vertex/index accessors. Mesh QA measures real
  bounds, scale, ground, approximate tower/antenna transforms, semantic coverage,
  and bounded broad-phase interference. Assembly QA reconstructs exported glTF
  transforms and measures declared mechanical frames and generated support nodes.
- Completion certificates bind requirement and SceneSpec hashes, build lock,
  artifacts, coverage, gates, and schema-required evidence. Active reads,
  rollback, and artifact serving revalidate the persisted chain. Changed artifacts
  become integrity failures; incomplete legacy records are not promoted.
- These checks prove bounded construction and artifact integrity. They do not
  certify structural, RF, electrical, material, vendor, installation, safety, or
  fabrication fitness. Full limits and gate commands are in
  [QA_STRATEGY.md](QA_STRATEGY.md).

## Runtime, storage, and security

- Workflow events are persisted in JSONL and streamed from an in-memory queue
  while the local process lives. SSE replays the durable prefix, detects gaps,
  and falls back to bounded polling. It is not a cross-process broker or a
  pause/resume/cancellation system.
- `active_design.json` is the atomic active-version commit. Interrupted revisions
  preserve the last verified active version; failed candidates remain failed.
- Terminal checkpoint threads are removed. Local free-space admission rejects new
  mutations before orphan state is created. Retention still requires explicit
  maintenance.
- Deleting a design removes its canonical workflow/design/error memory, document
  links, checkpoints, and derived vector projection. Deleting a document pack is
  guarded by chat references and restores the link if storage deletion fails.
- The API allowlists local hosts and origins, rejects malformed or unauthorized
  mutation origins, and emits browser security headers. All data, artifact, SSE,
  and mutation routes require the local owner session; only health and bounded
  authentication bootstrap/status/login/logout are public.
- The owner password is selected on first loopback launch and stored as a scrypt
  hash. Only hashes of opaque expiring session tokens are persisted. The browser
  cookie is `HttpOnly` and `SameSite=Strict`. There is no remote administration,
  password recovery, TLS termination, or multi-user authorization contract.
- Docker publishes services on loopback, uses independent named volumes, pins
  Qdrant server/client compatibility, and exposes Adminer only through
  integrity-checked SQLite snapshots. Its Linux x64 Blender runs under emulation
  on Apple Silicon and is materially slower than the native ARM runtime.

## Current verdict

The repository implements a real local pipeline with bounded model decisions,
fail-closed geometry generation, real Blender artifacts, layered QA, version
integrity, and an attached chat-first/3D-first frontend. Its strongest evidence
covers controlled technical telecom scenarios. Professional vendor assets,
representative retrieval quality, complete browser replay of every mutation,
and engineering validation remain open and must stay visible.
