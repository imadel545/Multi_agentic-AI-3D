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
  -> NVIDIA API Nemotron query/passage retrieval + NVIDIA reranker evidence
  -> bounded GPT-OSS planning decision over validated RAG candidates
  -> SQLite memory recall
  -> asset registry + inventory
  -> qualified asset-library retrieval only (raw CAD stays quarantined)
  -> SceneSpec planner
  -> SceneSpec validation + quality gates
  -> Blender runner
  -> GLB/preview/metadata artifacts
  -> structural/proxy geometry/preview QA
  -> memory writeback
  -> Product API summaries
```

Une révision par prompt suit d'abord un graphe spécialisé:

```text
active SceneSpec + prompt
  -> resolve manifest capability profiles
  -> bounded Groq JSON-Schema plan or visible deterministic fallback
  -> capability/path/tool/value/grounding validation
  -> SceneSpec mutation
  -> main revision graph -> Blender -> QA -> certified version activation
```

## Modules

- `apps/api`: FastAPI gateway, Product API, workflow lifecycle.
- `apps/blender_worker`: SceneSpec-driven Blender script.
- `core/contracts`: strict contracts.
- `core/document_pack`: bounded direct-file/ZIP intake, PDF/OCR/DXF extraction,
  and `ProjectDesignSpec`.
- `core/orchestration`: LangGraph workflow and route logic.
- `core/agents`: deterministic/LLM wrappers for extraction, planning, editing, RF/tower checks.
- `core/rag`: Qdrant, NVIDIA API multilingual embeddings, NVIDIA reranker with visible
  degraded passthrough, deterministic test/bootstrap mode, explicit local override.
- `core/memory`: SQLite workflow/document-pack memory.
- `core/services`: assets, events, versioning, Blender runner, cleanup.
- `core/services/asset_library.py`: immutable-source catalog, SHA-256
  deduplication, metadata search, deterministic CAD-to-source-preview links and
  isolated LibreDWG probes. Preview links are retrieval evidence only. The
  service does not promote or tessellate a raw CAD asset.
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

- Artifact copying and version bookkeeping remain service-level. Edit planning,
  validation and SceneSpec mutation now run inside a dedicated checkpointed
  LangGraph graph before the main revision graph.
- Revision preparation rebinds tower/equipment assets and recalculates derived
  GPS/cabinet placements before validation and Blender generation. Existing
  accessory rotation/scale are preserved; explicitly moved positions are marked
  `user_defined`, while derived positions continue to follow tower geometry.
- Events are frontend-readable and `/events/stream` is `push_sse` local-process, but there is
  no broker, cancellation manager, or durable resume yet.
- Asset import fallback can still create procedural geometry if an import fails, but the active
  inventory has 12 manifests and 12 GLB files: 10 manifests are
  generation-eligible, 4 authorize exact hash-pinned GLB import, and 2 remain
  reference-only.
- The separate 11,974-file CAD library is not part of that active inventory.
  Its 11,531 unique contents remain quarantined until licence, units, B-Rep
  conversion and geometry QA produce a validated manifest. Only validated,
  generation-eligible catalog rows may enter the asset RAG collection.
- Geometry QA combines binary accessor checks, semantic role transforms and a
  real-vertex AABB interference screen for primary equipment. It is not exact
  triangle/BVH collision, RF, structural or vendor-grade QA.
- RAG is not used for extraction in v1; only structured, whitelisted
  `payload.planning_hints` can influence planning, and `rag_planning_summary`
  plus `rag_evidence.json` expose whether that happened.
