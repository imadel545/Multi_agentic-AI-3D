# Architecture Audit

Audit date: 2026-06-05.

Commands run:

```bash
pwd
find . -maxdepth 6 -type f | sort
rg "<code-smell audit patterns>" core apps tests docs assets data/knowledge
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Initial result:

- Tests passed: 61 passed.
- Ruff check passed.
- Ruff format check failed on existing files; formatting was applied.
- Runtime artifacts exist under ignored paths: `outputs/temp`, `data/qdrant`, and `data/sqlite`.
- Fallback paths are visible in code/docs, not hidden, but needed stronger 3D geometry checks.

Updated audit on 2026-06-08:

- Tests before this hardening pass: `114 passed`.
- `ruff check .` passed.
- `ruff format --check .` initially failed on four files.
- Confirmed issues: `/assets/inventory` route shadowing, exception handler re-raising,
  semi-integrated edit regeneration, RAG text heuristics in planner, dead `error_memory` lookup,
  and GPS/power cabinet enabled by default.

| finding | risk_level | module | why_it_matters | action_taken | remaining_risk |
|---|---|---|---|---|---|
| Geometry QA stopped at structural object presence and metadata fallback. | high | `core/qa`, `core/validation`, `apps/api` | A generated GLB could contain expected names but still miss technical geometry expectations. | Added `GeometryValidationReport`, `GLBGeometryValidator`, API artifact/status integration, quality gate check, trace/metrics integration, and tests. | Bounding box remains metadata/proxy based until GLB transform parsing is added. |
| Real Blender outputs were not explicitly required to parse as GLB at the post gate. | high | `core/validation/quality_gates.py` | A broken real Blender artifact could pass weaker artifact checks. | Added `real_blender_glb_parse_required` to post-Blender quality gate. | Fallback mode still uses explicit metadata fallback by design. |
| `include_cables=false` scenes failed validator assumptions. | medium | `core/rules`, `core/validation` | A valid no-cable option was treated as invalid, blocking legitimate telecom requirements. | Replaced mandatory cable presence checks with option consistency checks. | Mixed per-sector cable policies are still not modeled. |
| LangGraph runtime tests covered routes, but not all required named agentic cases. | medium | `tests/unit` | Route regressions could silently bypass repair, memory, or quality gates. | Added explicit tests for repair success, unrepairable failure, memory order/writeback, route history, and no Blender before gate. | Orchestrator remains one large module; future split should be careful and test-preserving. |
| RAG seed did not state the microwave/RRU exception. | medium | `data/knowledge`, `tests/rag_eval` | Retrieval could imply RRU is always mandatory even for MW dish cases. | Added explicit telecom rule and RAG eval tests for 5G lattice, microwave dish, and small-cell pole queries. | Deterministic embedding remains a local fallback, not semantic-grade retrieval. |
| Output cleanup existed only as manual hygiene. | medium | `core/services`, `outputs/temp` | Local-first workflows can accumulate artifacts and stale workflow folders. | Added `CleanupService` with TTL deletion for managed `wf_<12 hex>` folders and safe deletion tests. | Not wired into API startup or scheduled execution yet. |
| API exposed an unused variant-generation option although variants are not implemented. | medium | `apps/api` | Silent no-op options create false expectations and create scope creep. | Removed the unused option from `DesignOptions` and tests. | Future variant generation should add a real contract and tests before reintroducing an option. |
| Groq provider wiring lacked API-level proof that `use_llm` controls provider usage. | medium | `apps/api`, `core/agents`, `core/llm` | The project depends on LLM-assisted extraction, but fallback must remain explicit and controlled. | Added unit tests for Groq payload/model/schema and API workflow tests for `use_llm=true` and `use_llm=false`. | Real Groq availability still depends on a valid local key and network. |
| Qdrant local client was left to Python object destruction at API shutdown. | low | `apps/api`, `core/rag` | Local shutdown could print noisy destructor errors and mask real shutdown issues. | Added `RagService.close()` and FastAPI lifespan shutdown cleanup. | Server-mode Qdrant still depends on external service availability. |
| Pylon extraction only captured type and height. | high | `core/contracts`, `core/services`, `core/llm`, `apps/blender_worker` | Advanced 3D generation needs structural characteristics, not just a generic tower label. | Added typed `TowerCharacteristics`, deterministic and Groq schema extraction, SceneSpec propagation, metadata/QA checks, API summary, and tests. | Real vendor GLB imports still need an inventory validator and asset files. |
| Docs over-described future asset imports relative to current files. | medium | `docs`, `assets` | The project must not imply real vendor GLB assets exist when only manifests exist. | Added asset strategy doc and updated QA/Blender/performance/roadmap truth state. | Need real GLB inventory before claiming imported asset quality. |
| API layer stayed mostly thin but writes artifact/status packaging. | low | `apps/api` | API should not absorb orchestration/QA logic. | Kept geometry summary and artifact writing in API; QA remains in core. | Archive/status writer may deserve extraction if it grows. |
| Contracts are centralized and reusable. | low | `core/contracts` | Typed state keeps agents/services decoupled. | Added geometry contract instead of ad hoc dicts. | More report schemas may be needed for asset quality and cleanup results. |
| Blender worker is controlled and does not execute LLM Python. | low | `apps/blender_worker` | Prevents unsafe arbitrary code execution. | Preserved SceneSpec-only worker contract and added tower height metadata. | Procedural primitives still stand in for real imported assets. |
| Prompt edits created versions but only relaunched Blender in the root workflow folder. | high | `apps/api`, `core/orchestration`, `core/services` | A frontend could display a v2 GLB with stale v1 QA/status/report artifacts. | Added controlled `run_scene_revision`, per-version artifact directories, patch/diff/status files, QA rerun, quality gates, active version switching only after success, and tests. | Edit is synchronous for now; a future preview/apply flow may need async job state. |
| `/assets/inventory` was shadowed by `/assets/{asset_id}`. | high | `apps/api` | Frontend asset readiness checks returned asset lookup behavior instead of inventory. | Moved the static inventory route before the dynamic asset route and added API test coverage. | None known. |
| Global exception handler raised `HTTPException` inside the exception handler. | medium | `apps/api` | Internal failures could bubble through TestClient/server handling instead of returning clean JSON. | Replaced with `JSONResponse` including `request_id` and added test coverage. | App-specific error envelopes can still be refined. |
| SSE event stream could loop forever for unknown workflows. | medium | `apps/api`, `core/services` | Frontend timeline could hang silently. | Unknown workflows now return `404`; event stream has an idle timeout. | Long-running workflows over five minutes need a heartbeat/timeout policy adjustment. |
| RAG and memory planner logic used untyped text heuristics and a dead memory key. | high | `core/agents/scene_planner.py` | Retrieved noisy text could silently mutate dimensions/accessories; memory error patterns were ignored. | Planner now accepts only structured `payload.planning_hints`, uses `error_patterns`, and tests reject unstructured decorative hints. | Need richer typed planning-hint contracts before expanding RAG influence. |
| GPS antenna and power cabinet were enabled by default. | high | `core/contracts`, `apps/blender_worker` | The generator added objects the user did not request, creating decorative/fake output. | Defaults are now false; Blender worker uses false defaults; tests prove normal generation does not add them. | Dedicated real assets and accessory geometry QA remain future work. |
| Workflow deletion used direct `shutil.rmtree`. | medium | `apps/api`, `core/services` | Unsafe deletion logic can grow risky as local outputs expand. | API deletion now uses `CleanupService.delete_workflow()` with managed `wf_<12 hex>` confinement. | Cleanup TTL is still not scheduled automatically. |
