# Architecture

The project is a local-first mono-user generation pipeline. The deterministic core remains
the safety net, while agentic integrations are layered around it.

```text
FastAPI Local Gateway
  -> LangGraph Orchestrator
  -> RAG Retrieval
  -> Groq Structured Extraction or Deterministic Parser
  -> SQLite Memory Recall
  -> Asset Registry
  -> Rule Engine
  -> Scene Planner
  -> SceneSpec Validator
  -> Pre-Blender Quality Gate
  -> Blender Runner
  -> GLB Structural Inspector
  -> GLB Geometry Validator
  -> Preview Inspector
  -> Generation QA
  -> Post-Blender Quality Gate
  -> SQLite Memory Writeback
  -> Artifact Writer
```

## Implemented

- `core/contracts`: strict Pydantic contracts.
- `core/services/asset_registry.py`: manifest loading and compatibility selection.
- `core/services/requirement_parser.py`: deterministic baseline extraction.
- `core/llm/groq.py`: Groq strict JSON Schema extraction client.
- `core/agents/requirement_extractor.py`: Groq/deterministic extraction router.
- `core/orchestration`: LangGraph workflow nodes and state.
- `core/memory`: SQLite workflow memory, recall, and writeback.
- `core/performance`: local cache helpers and canonical runtime hashes.
- `core/rules/engine.py`: business rule validation before planning.
- `core/agents/scene_planner.py`: controlled SceneSpec construction.
- `core/validation/quality_gates.py`: centralized pre/post Blender gate checks.
- `core/qa/glb_geometry_validator.py`: sector/object/metadata geometry QA.
- `apps/api`: local FastAPI gateway.
- `core/rag`: Qdrant indexing/search over rules, docs, templates, and manifests.
- `core/services/blender_runner.py`: Blender availability detection, execution, timeout, fallback.
- `apps/blender_worker`: controlled SceneSpec-driven Blender entrypoint.
- `core/qa`: generation artifact QA, GLB structural inspection, GLB geometry validation, and
  preview inspection.

## Runtime Reliability

Implemented:

- Quality gate reports are included in workflow trace and API status.
- GLB and preview inspection reports are included in workflow trace, validation report, API status,
  and output artifacts.
- Geometry validation reports are included in workflow trace, validation report, API status, quality
  gates, and output artifacts.
- Requirements, SceneSpec, asset manifests, and knowledge index hashes are included in metrics.
- Asset registry cache invalidates when manifest hash changes.
- RAG query cache uses TTL and includes knowledge index hash in the key.

Fallback:

- Cache misses fall back to normal manifest loading or Qdrant query.
- Quality gates fail closed and route to `quality_gate_failure_handler`.
- GLB parsing failure uses explicit metadata fallback only when metadata exists.

Known limitations:

- Caches are process-local.
- Qdrant local mode can still lock when multiple API processes use the same local path.
- Quality gates do not perform semantic visual inspection.
- Geometry QA validates counts, sector object presence, heights, azimuth metadata, and a
  bounding-box proxy. It does not yet parse exact GLB node transforms or materials.

## Reserved integrations

- Qdrant retrieval provides context but does not bypass rules.
- SQLite memory stores compact workflow summaries and validation patterns, not large GLB/PNG files.
- FastEmbed/BGE-M3 can replace the hashing embedder behind the RAG provider interface.
- Real GLB asset imports can replace procedural primitives inside the controlled Blender worker.
