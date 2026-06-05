# Roadmap

## Completed

- Deterministic MVP contracts, parser, rules, asset registry, SceneSpec planner.
- Qdrant local RAG with reindex/search/filtering.
- Groq structured extraction with fallback and repair reporting.
- LangGraph workflow with persisted trace.
- Controlled Blender runner and procedural Blender worker.
- Real Blender proof on macOS when Blender is installed.
- Generation QA and four golden scenes.
- API status enrichment.
- SQLite workflow memory with recall, writeback, stats, typed trace, and node timings.
- Centralized quality gates and process-local safe cache.
- GLB structural inspection, preview dimension inspection, and golden GLB structure expectations.
- GLB geometry validation with object count, sector object, height, azimuth, and bounding-box proxy
  checks.
- RAG and memory eval tests for core local-first scenarios.
- Safe output cleanup service for old managed workflow folders.

## Available With Fallback

- Groq extraction falls back to deterministic parser.
- FastEmbed setting falls back to deterministic hashing if FastEmbed is not installed.
- Blender generation falls back explicitly if Blender is absent or fails.
- GLB inspection falls back to `metadata_fallback` only for explicit non-GLB fallback artifacts
  with `scene_metadata.json`.

## Requires Local Blender Install

- Real `design.glb` and `preview.png` generation requires Blender.
- Recommended install: Blender 4.5 LTS or newer.

## Future

- Replace procedural geometry with validated GLB asset imports.
- Wire cleanup TTL into an explicit CLI/admin action and add SQLite row cleanup.
- Add frontend React/Three.js viewer.
- Add richer Qdrant payload filters and semantic embeddings as default.
- Add comparative design variants.
- Add exact GLB transform, bounding-box, and material validation.
- Add rendered preview visual semantic checks.
