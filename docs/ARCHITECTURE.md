# Architecture

The project is a local-first mono-user generation pipeline. The deterministic core remains
the safety net, while agentic integrations are layered around it.

```text
FastAPI Local Gateway
  -> Document Pack Intelligence (optional entry, LangGraph)
  -> ProjectDesignSpec / RequirementSpec mapping
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
  -> Asset GLB Import or Explicit Procedural Fallback
  -> GLB Structural Inspector
  -> GLB Geometry Validator
  -> Preview Inspector
  -> Generation QA
  -> Post-Blender Quality Gate
  -> SQLite Memory Writeback
  -> Artifact Writer
```

Prompt edit/revision path:

```text
FastAPI /designs/{workflow_id}/edit
  -> SceneEditAgent
  -> PatchApplier
  -> DiffEngine
  -> SceneVersioningService
  -> DesignOrchestrator.run_scene_revision
  -> Rule/Tower/RF validation
  -> Pre-Blender Gate
  -> Blender Runner
  -> GLB/Geometry/Preview QA
  -> Post-Blender Gate
  -> Version artifacts/status
```

## Implemented

- `core/contracts`: strict Pydantic contracts.
- `core/contracts/document_pack.py`: document-pack, evidence, QA, capability, and
  `ProjectDesignSpec` contracts.
- `core/document_pack`: safe ZIP indexing, classification, optional PDF/CAD/coordinate capability
  adapters, selected OCR, DXF parsing, bounded Groq extraction, LangGraph orchestration,
  consolidation, corrections, QA, trace/events, processing reports, and memory writeback.
- `core/services/asset_registry.py`: manifest loading and compatibility selection.
- `core/services/asset_inventory.py`: asset file/import readiness reporting for frontend and QA.
- `core/services/requirement_parser.py`: deterministic baseline extraction.
- `core/llm/groq.py`: Groq strict JSON Schema extraction client.
- `core/agents/requirement_extractor.py`: Groq/deterministic extraction router.
- `core/agents/scene_edit_agent.py`: prompt-to-typed ScenePatch editor.
- `core/agents/tower_engineer.py` and `core/agents/rf_engineer.py`: deterministic domain
  validation agents.
- `core/orchestration`: LangGraph workflow nodes and state.
- `core/memory`: SQLite workflow memory, recall, and writeback.
- `core/performance`: local cache helpers and canonical runtime hashes.
- `core/rules/engine.py`: business rule validation before planning.
- `core/agents/scene_planner.py`: controlled SceneSpec construction.
- `core/validation/quality_gates.py`: centralized pre/post Blender gate checks.
- `core/qa/glb_geometry_validator.py`: sector/object/metadata geometry QA.
- `apps/api`: local FastAPI gateway.
- `core/services/scene_versioning.py`: active version pointer and per-version metadata/artifacts.
- `core/services/event_log.py`: append-only workflow event log for timeline/SSE consumers.
- `core/rag`: Qdrant indexing/search over rules, docs, templates, and manifests.
- `core/services/blender_runner.py`: Blender availability detection, execution, timeout, fallback.
- `apps/blender_worker`: controlled SceneSpec-driven Blender entrypoint with manifest GLB import
  when files exist and explicit procedural fallback when allowed.
- `core/qa`: generation artifact QA, GLB structural inspection, GLB geometry validation, and
  preview inspection.

## Runtime Reliability

Implemented:

- Quality gate reports are included in workflow trace and API status.
- Edits are transaction-style revisions: a patched SceneSpec becomes active only after validation,
  generation, QA, and quality gates complete successfully.
- Each successful edit version gets independent artifacts under its version artifact directory.
- Rollback switches the active version pointer and root status back to stored version artifacts
  without deleting later versions.
- `/assets/inventory` reports manifest-only versus real GLB readiness without being shadowed by
  `/assets/{asset_id}`.
- Workflow status exposes asset import metadata from `scene_metadata.json` so the frontend can
  distinguish `imported_glb`, `procedural_fallback`, and `missing_file`.
- Global API exceptions return JSON `500` with `request_id`.
- `POST /designs` writes a pending status immediately so frontend polling has no transient 404 gap.
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
- Groq edit patching falls back to deterministic patch parsing and exposes fallback state in the
  patch/result.

Known limitations:

- Caches are process-local.
- Qdrant local mode can still lock when multiple API processes use the same local path.
- Quality gates do not perform semantic visual inspection.
- Version artifacts are filesystem-local and intended for local-first mono-user workflows.
- Geometry QA validates counts, sector object presence, heights, azimuth metadata, and a
  bounding-box proxy. It does not yet parse exact GLB node transforms or materials.
- Document-pack orchestration is graph-based but synchronous. Large OCR/CAD/Groq packs may require
  async jobs/SSE later.
- The `document-intel` extra is installed and validated in the current `.venv`; Docling is installed
  separately and importable, but not used by default because it is heavy and model-cache dependent.
  Missing local tools still remain visible through capability and processing endpoints.

## Reserved integrations

- Qdrant retrieval provides context but does not bypass rules.
- SQLite memory stores compact workflow summaries and validation patterns, not large GLB/PNG files.
- FastEmbed/BGE-M3 can replace the hashing embedder behind the RAG provider interface.
- The current MVP imports available GLBs and falls back procedurally when manifests allow it.
- Vendor-grade GLB assets can replace the current internal minimal assets and missing files without
  changing stable manifest IDs.
- Document-pack memory summaries are compact local artifacts and can write compact SQLite/Qdrant
  runtime memory. They do not store source ZIP/PDF/image/GLB/PNG bytes.
