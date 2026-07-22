# Known Limitations

Active limitations that must remain visible in the API, reports, and future
frontend.

## Visible during frontend build

- `apps/frontend` is a real-backend product rework in progress, not an accepted
  frontend gate.
- The first technical kernel was rejected as too dashboard-like; fixed topbar
  badges, permanent tab grids, and raw JSON surfaces must not come back.
- Old dashboard patterns remain rejected.
- No `/projects` or `/runs` API is added in v1. The frontend maps its "run"
  concept to `workflow_id` and "scene plan" to `scene_spec`.
- `events/stream` is `push_sse` inside the local FastAPI process, with JSONL
  replay and queue live events. It is not a cross-process broker.
- Runtime timeline depends on node events + trace file; robust cancellation,
  retry, and durable resume are not yet implemented.
- `runtime_capabilities` and `unsupported_actions` expose these missing
  runtime actions explicitly: cancel, pause, resume, same-workflow retry,
  human-in-loop checkpoints, and WebSocket runtime.
- The local thread executor has bounded admission but is not a durable job
  broker. Process shutdown and test harnesses must close the service lifespan;
  there is no cross-process ownership or recovery.
- Local storage admission requires at least 256 MB free by default
  (`TELECOM_STUDIO_MIN_FREE_DISK_MB`). Ignored workflow artifacts still need
  periodic cleanup; the guard prevents a new mutation but is not a retention
  scheduler.

## Backend and agents

- Deterministic extraction is fragile on complex requirements.
- Groq improves extraction only when a real key is configured.
- LLM state is visible through `extraction_provider`, `llm_provider`,
  `llm_available`, `llm_fallback_used`, and `llm_fallback_reason`; fallback is
  acceptable only if the frontend displays it.
- Agents are mostly deterministic functions or LLM wrappers.
- Prompt workflows, document-pack generated requirements, and scene revisions enter the
  compiled LangGraph graph; edit patch creation and version bookkeeping remain service-level.
- No robust cancellation/retry manager; async execution uses local threads.

## RAG and memory

- NVIDIA API `baai/bge-m3` is the product provider.
- The product path does not silently load a local embedding model. Deterministic
  hash retrieval is allowed only for tests/bootstrap or explicit degraded mode;
  hash is not production quality.
- Static RAG docs/manifests are checked against a persisted index identity and
  reindexed automatically when they change. Runtime memory collections remain
  local-first and can still require operational cleanup if Qdrant storage is
  corrupted or locked by another process.
- Reranker product path is NVIDIA API, but it is fail-open. If unavailable,
  vector order is used and `rag_reranker_degraded_reason` must be displayed.
  Local reranker is an explicit developer override, not product default.
- Memory is still limited, with incomplete semantic recall.
- `rag_context_count > 0` does not mean the 3D plan changed. In v1, only
  structured, whitelisted `payload.planning_hints` can affect planning; RAG is
  not used for RequirementSpec extraction. Use `rag_evidence.json` for sources
  and candidate hint proof.

## Documents

- Document-pack is synchronous, 80 MB max.
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
- Blender fallback is rejected by default, but missing assets can still become
  visible procedural geometry during a real Blender generation.
- Geometry source of truth is `SceneSpec + parametric generator`; GLB is only
  the exported viewer result.
- Mesh QA v1 is `mesh_level_transform_basic` when transforms are readable,
  otherwise `mesh_level_basic`. It computes real bounding boxes from GLB
  accessors and approximate HBA from node transforms when possible, but does
  **not** verify exact antenna azimuth from vertices and does **not** perform
  collision detection.
- No material, RF, structural wind-load, or vendor-grade mesh dimension validation yet.
- The tower validator uses height only as a conservative trigger for aviation-marking
  review. It does not determine whether lighting is legally required; national rules,
  obstacle location and the competent aviation authority remain authoritative.
- Internal/CC-BY assets are not vendor-grade.

## Can wait

- WebSocket.
- Queue/job manager.
- Full LangGraph redesign.
- Advanced mesh-level QA.
- Production Docling.
- Final polished frontend beyond the current product rework.
