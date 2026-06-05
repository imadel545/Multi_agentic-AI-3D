# Agentic AI 3D Telecom Design Studio

Local-first platform foundation for transforming telecom requirements into a validated
`SceneSpec`, controlled 3D generation artifacts, and compliance reports.

This repository currently implements the local-first controlled generation pipeline:

- Pydantic contracts for `RequirementSpec`, `AssetManifest`, `SceneSpec`, and validation reports.
- Deterministic requirement normalization for common telecom prompts.
- Typed pylon characteristics extraction for structure, legs, base/top width, foundation,
  platforms, ladder, lightning rod, aviation light, and material.
- Groq structured extraction with strict JSON Schema and deterministic fallback.
- LangGraph orchestration with typed trace nodes, timings, and workflow metrics.
- Durable SQLite memory for workflow recall and writeback.
- Rule engine and SceneSpec validator.
- Local asset manifest registry.
- FastAPI endpoints for design creation, status, validation, assets, and artifact download.
- Controlled Blender runner that executes Blender when available and falls back explicitly otherwise.
- Generation QA checks for GLB, preview, geometry metadata, sector count, and fallback warnings.
- Geometry validation for expected antennas, beams, RRUs, cables, azimuths, and tower/antenna
  heights.
- Local Qdrant RAG indexing and search over rules, docs, templates, and asset manifests.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn apps.api.telecom_studio_api.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

Optional Qdrant Docker service:

```bash
docker compose -f infra/docker-compose.yml up -d qdrant
TELECOM_STUDIO_QDRANT_URL=http://127.0.0.1:6333 uvicorn apps.api.telecom_studio_api.main:app --reload
```

Without `TELECOM_STUDIO_QDRANT_URL`, the API uses Qdrant local mode under `data/qdrant`.

Groq extraction:

```bash
# Supported names, in environment or .env:
GROQ_API_KEY=...
groq_api=...
TELECOM_STUDIO_GROQ_API_KEY=...
```

The API uses `openai/gpt-oss-120b` by default. Per request, set
`options.use_llm=false` to force deterministic extraction.

## Test

```bash
pytest
```

Focused eval suites:

```bash
pytest tests/rag_eval tests/memory_eval
```

## Core flow

```text
requirements_text
→ LangGraph orchestrator
→ Groq structured RequirementSpec or deterministic fallback
→ Qdrant RAG context
→ SQLite memory recall
→ asset registry
→ rule engine
→ SceneSpec
→ SceneSpec validator
→ Blender runner
→ GLB structural + geometry validation
→ generation QA
→ SQLite memory writeback
→ compliance report
```

FastEmbed/BGE-M3 and richer Blender asset imports remain extension points. Qdrant,
Groq structured extraction, LangGraph orchestration, controlled Blender execution, and
generation QA are implemented. SQLite memory is stored under `data/sqlite` by default.
Current asset files are manifest-only; the Blender worker uses controlled procedural geometry until
real GLB assets are added.
