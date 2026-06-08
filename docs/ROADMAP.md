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
- Prompt edit flow with typed patch, diff, transaction-style version generation, QA rerun,
  per-version artifacts, event log, active version pointer, and rollback.
- API fixes for `/assets/inventory`, JSON exception handling, and unknown SSE workflow handling.
- RAG/memory planning hardening through structured hints and `error_patterns`.
- Asset pipeline MVP: inventory detects present/missing GLBs, two internal minimal GLBs are present,
  Blender imports available GLBs, procedural fallback is explicit, and API status exposes asset
  import metadata.

## Available With Fallback

- Groq extraction falls back to deterministic parser.
- FastEmbed setting falls back to deterministic hashing if FastEmbed is not installed.
- Blender generation falls back explicitly if Blender is absent or fails.
- Missing asset files fall back to procedural geometry only when the manifest allows it, and the
  fallback is visible in `scene_metadata.json`, QA, and API status.
- GLB inspection falls back to `metadata_fallback` only for explicit non-GLB fallback artifacts
  with `scene_metadata.json`.

## Requires Local Blender Install

- Real `design.glb` and `preview.png` generation requires Blender.
- Recommended install: Blender 4.5 LTS or newer.

## Future

- Replace internal minimal GLBs and missing manifests with vendor-grade GLB assets.
- Add exact imported-asset bounding-box, pivot, mount-point, material, and LOD validation.
- Wire cleanup TTL into an explicit CLI/admin action and add SQLite row cleanup.
- Add frontend React/Three.js viewer.
- Add non-committed edit preview/apply workflow if the frontend needs preview before activation.
- Add richer Qdrant payload filters and semantic embeddings as default.
- Add comparative design variants.
- Add exact GLB transform, bounding-box, and material validation for imported vendor assets.
- Add rendered preview visual semantic checks.
- Add dedicated manifest-backed GPS/power-cabinet assets and QA checks.
