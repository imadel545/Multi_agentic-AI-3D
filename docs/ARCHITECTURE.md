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
  -> NVIDIA API BGE-M3 RAG context (advisory, structured hints only)
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
- `core/rag`: Qdrant, NVIDIA API BGE-M3 embeddings, deterministic test/bootstrap mode,
  passthrough reranker by default with explicit local override.
- `core/memory`: SQLite workflow/document-pack memory.
- `core/services`: assets, events, versioning, Blender runner, cleanup.
- `core/qa`: GLB structural parse, proxy geometry, preview luminance QA.

## Runtime truths

- `outputs/temp` contains ignored workflow artifacts.
- `data/sqlite` and `data/qdrant` are local ignored runtime stores.
- `.env` contains real secrets and must never be committed.
- `.env.example` contains placeholders only.
- `apps/frontend` is not an operational app.

## Known weak points

- Edit patch creation, artifact copying, and version bookkeeping are service-level concerns
  outside the graph; generation paths enter the compiled LangGraph graph.
- Events are frontend-readable and `/events/stream` is `push_sse` local-process, but there is
  no broker, cancellation manager, or durable resume yet.
- Asset import fallback can still create procedural geometry if an import fails, but the active
  inventory has 12 manifests, 12 GLB files, and 0 missing files.
- Geometry QA is object/name/count/metadata based, not mesh-transform exact.
- RAG is not used for extraction in v1; only structured `payload.planning_hints`
  can influence planning, and `rag_planning_summary` exposes whether that
  happened.
