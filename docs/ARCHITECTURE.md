# Architecture

Local-first, single-user generation pipeline. The deterministic core is the safety net; agentic layers are added around it.

## High-level flow

```text
FastAPI Local Gateway
  -> Document Pack Intelligence (optional entry)
  -> ProjectDesignSpec / RequirementSpec mapping
  -> LangGraph Orchestrator
  -> RAG Retrieval (advisory)
  -> Groq Structured Extraction or Deterministic Parser
  -> SQLite Memory Recall
  -> Asset Registry
  -> Rule Engine
  -> Scene Planner
  -> SceneSpec Validator
  -> Pre-Blender Quality Gate
  -> Blender Runner
  -> Asset GLB Import or Explicit Procedural Fallback
  -> GLB Structural Inspector
  -> GLB Geometry Validator
  -> Preview Inspector
  -> Generation QA
  -> Post-Blender Quality Gate
  -> SQLite Memory Writeback
  -> Artifact Writer
```

## Key modules

- `core/contracts`: strict Pydantic contracts.
- `core/document_pack`: ZIP ingestion, classification, extraction, consolidation, QA.
- `core/services`: asset registry, inventory, versioning, events, Blender runner.
- `core/llm`: Groq structured extraction client.
- `core/agents`: extraction, planning, edit, tower/RF validation (mostly deterministic wrappers).
- `core/orchestration`: LangGraph workflow.
- `core/memory`: SQLite workflow memory.
- `core/rules`: business rule validation.
- `core/validation`: SceneSpec validator and quality gates.
- `core/qa`: GLB/geometry/preview QA.
- `core/rag`: Qdrant indexing/search.
- `apps/api`: FastAPI gateway.
- `apps/blender_worker`: SceneSpec-driven Blender entrypoint.

## Important architectural facts

- `DesignOrchestrator.run_requirements` and `run_scene_revision` currently bypass the compiled LangGraph graph and execute the same sequence imperatively. The checkpoint saver is therefore unused for these paths.
- RAG and memory provide context only; they do not override deterministic rules or validation.
- Default RAG embedding is deterministic hashing, not semantic. FastEmbed is optional.
- Memory recall uses exact matching on network_type, tower_type, sector_count.
- Without Blender, the runner produces explicit fallback artifacts. The current QA may incorrectly pass these artifacts; this is a known limitation.

## Local runtime

- SQLite under `data/sqlite`.
- Qdrant local under `data/qdrant` or remote via `TELECOM_STUDIO_QDRANT_URL`.
- Workflow artifacts under `outputs/temp`.

## Future

- Make Blender output mandatory for `completed` status.
- Use real semantic embeddings by default.
- Make memory recall similarity-based.
- Run all orchestration through the compiled LangGraph graph.
- Rebuild the frontend as chat-first / 3D-first.
