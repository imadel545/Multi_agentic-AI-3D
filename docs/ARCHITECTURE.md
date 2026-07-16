# Architecture

Pipeline local-first mono-utilisateur. Les contrats Pydantic et validations déterministes
sont la base; les couches agentiques et RAG restent contrôlées.

## Flow

```text
FastAPI
  -> requirements text or document pack
  -> RequirementSpec / ProjectDesignSpec
  -> LangGraph-orchestrated generation pipeline
  -> Groq extraction or deterministic fallback
  -> NVIDIA API BGE-M3 query/passage retrieval + NVIDIA reranker evidence
  -> bounded GPT-OSS planning decision over validated RAG candidates
  -> SQLite memory recall
  -> asset registry + inventory
  -> SceneSpec planner
  -> SceneSpec validation + quality gates
  -> Blender runner
  -> GLB/preview/metadata artifacts
  -> structural/proxy geometry/preview QA
  -> memory writeback
  -> Product API summaries
```

## Modules

- `apps/api`: FastAPI gateway, Product API, workflow lifecycle.
- `apps/blender_worker`: SceneSpec-driven Blender script.
- `core/contracts`: strict contracts.
- `core/document_pack`: ZIP/PDF/OCR/DXF extraction and `ProjectDesignSpec`.
- `core/orchestration`: LangGraph workflow and route logic.
- `core/agents`: deterministic/LLM wrappers for extraction, planning, editing, RF/tower checks.
- `core/rag`: Qdrant, NVIDIA API BGE-M3 embeddings, NVIDIA reranker with visible
  degraded passthrough, deterministic test/bootstrap mode, explicit local override.
- `core/memory`: SQLite workflow/document-pack memory.
- `core/services`: assets, events, versioning, Blender runner, cleanup.
- `core/qa`: GLB structural parse, mesh/accessor/transform basic QA, proxy
  geometry, preview pixel/framing QA.

## Runtime truths

- `outputs/temp` contains ignored workflow artifacts.
- `data/sqlite` and `data/qdrant` are local ignored runtime stores.
- Workflow mutations check free local storage before persistence. Startup
  recovery restores the last valid active version after an interrupted edit,
  while an interrupted initial generation remains failed.
- `.env` contains real secrets and must never be committed.
- `.env.example` contains placeholders only.
- `apps/frontend` is a real-backend product rework, not an accepted final gate.

## Known weak points

- Edit patch creation, artifact copying, and version bookkeeping are service-level concerns
  outside the graph; generation paths enter the compiled LangGraph graph.
- Revision preparation rebinds tower/equipment assets and recalculates derived
  GPS/cabinet placements before validation and Blender generation.
- Events are frontend-readable and `/events/stream` is `push_sse` local-process, but there is
  no broker, cancellation manager, or durable resume yet.
- Asset import fallback can still create procedural geometry if an import fails, but the active
  inventory has 12 manifests, 12 GLB files, and 0 missing files.
- Geometry QA is mesh/accessor/role-transform basic plus object/name/count/metadata
  checks; it is not collision/RF/vendor-grade QA.
- RAG is not used for extraction in v1; only structured, whitelisted
  `payload.planning_hints` can influence planning, and `rag_planning_summary`
  plus `rag_evidence.json` expose whether that happened.
