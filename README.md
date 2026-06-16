# Agentic AI 3D Telecom Design Studio

Local-first pipeline for transforming telecom requirements into a validated `SceneSpec`, controlled 3D generation artifacts, and compliance reports.

> ⚠️ **Frontend removed.**<br>
> The old frontend has been deleted/refused. `apps/frontend` is not an operational app. A chat-first / 3D-first frontend will be rebuilt later against the frozen `/designs` + `workflow_id` backend/frontend contract.<br>
> See `docs/PROJECT_SOURCE_OF_TRUTH.md` for the single source of truth, `docs/BACKEND_CAPABILITY_MATRIX.md` for backend capabilities, and `docs/KNOWN_LIMITATIONS.md` for honest limitations.

---

## What it does

- Takes a technical brief or a document pack (ZIP with PDF/DXF/images) as input.
- Extracts structured requirements (`RequirementSpec`) or a provenance-backed design spec (`ProjectDesignSpec`).
- Plans a controlled 3D scene (`SceneSpec`).
- Generates a real `design.glb`, `preview.png`, and reports via headless Blender.
- Runs structural and geometry QA.
- Current mesh QA is `mesh_level_transform_basic` when GLB node transforms are readable, otherwise `mesh_level_basic`. It parses GLB accessors/bounding boxes and basic role transforms, but it is not exact per-antenna RF/azimuth/collision QA.
- Supports prompt edits, versioning, and rollback.
- The frontend product vocabulary maps to existing backend concepts: a "run" is
  a `workflow_id`, and a "scene plan" is the `scene_spec` artifact.

## What it does not do yet

- It is not a polished end-user product.
- It does not guarantee vendor-grade visual realism (current assets are internal/CC-BY).
- It does not run without a local Blender install for real 3D output.
- It does not provide a production-ready frontend today.

---

## Run locally

### Backend

```bash
uv python install 3.12.7
uv venv --python 3.12.7
source .venv/bin/activate
uv pip install -e ".[dev,rag,document-intel]"
uvicorn apps.api.telecom_studio_api.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

Default CORS is local only: `http://127.0.0.1:5173,http://localhost:5173`.
Override with `TELECOM_STUDIO_CORS_ORIGINS` when a future frontend uses a different local origin.

### Optional: Blender

Real `design.glb` generation requires Blender 4.5+ installed locally. The runner searches:

- `BLENDER_BINARY` env var
- `TELECOM_STUDIO_BLENDER_BINARY` env var
- `blender` in `PATH`
- `/Applications/Blender.app/Contents/MacOS/Blender`

### Optional: Qdrant

```bash
docker compose -f infra/docker-compose.yml up -d qdrant
TELECOM_STUDIO_QDRANT_URL=http://127.0.0.1:6333 uvicorn apps.api.telecom_studio_api.main:app --reload
```

Without `TELECOM_STUDIO_QDRANT_URL`, the API uses Qdrant local mode under `data/qdrant`.

### Optional: Groq

```bash
GROQ_API_KEY=...
# or TELECOM_STUDIO_GROQ_API_KEY=...
```

The API uses `openai/gpt-oss-120b` by default. Use `options.use_llm=false` to force deterministic extraction.

### Optional: NVIDIA RAG embeddings

Product RAG uses NVIDIA API `baai/bge-m3`. Product reranking uses the NVIDIA
reranker configured by `TELECOM_STUDIO_RERANKER_MODEL`; if the reranker is not
available, the API exposes a degraded passthrough status instead of pretending
reranking happened.

```bash
NVIDIA_API_KEY=...
# or TELECOM_STUDIO_NVIDIA_API_KEY=...
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=baai/bge-m3
TELECOM_STUDIO_RERANKER_PROVIDER=nvidia
TELECOM_STUDIO_RERANKER_MODEL=nvidia/llama-nemotron-rerank-1b-v2
```

`TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic` is for tests/bootstrap only.

### Optional: document-intelligence tooling

```bash
uv pip install -e ".[document-intel,document-layout]"
brew install tesseract tesseract-lang
brew install libredwg
```

The backend reports each capability explicitly and does not pretend extraction succeeded when a tool is missing.

---

## Test

Backend:

```bash
.venv/bin/python -m pytest -q
```

---

## Core flow

```text
requirements_text or document pack
→ LangGraph orchestrator
→ Groq structured RequirementSpec or deterministic fallback
→ NVIDIA BGE-M3 + Qdrant RAG context (advisory structured hints)
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

---

## Key documentation

- `AGENTS.md` — rules for Codex agents.
- `docs/PROJECT_SOURCE_OF_TRUTH.md` — what the project is and is not.
- `docs/BACKEND_CAPABILITY_MATRIX.md` — backend capabilities and limits.
- `docs/FRONTEND_PRODUCT_BLUEPRINT.md` — target frontend vision.
- `docs/FRONTEND_ACCEPTANCE_CRITERIA.md` — criteria to accept a future frontend.
- `docs/KNOWN_LIMITATIONS.md` — honest limitations.
- `docs/API_FRONTEND_CONTRACT.md` — product API contract for the frontend.
- `docs/RAG_STRATEGY.md` — NVIDIA BGE-M3 RAG strategy and limitations.
- `docs/ARCHITECTURE.md` — backend flow and module boundaries.
- `docs/QA_STRATEGY.md` — honest QA levels and limits.
- `docs/LANGGRAPH_WORKFLOW.md` — orchestration/runtime truth.

---

## Status

- Backend: functional local-first pipeline with real Blender output when Blender is installed.
- Assets: 12 manifests, 12 local GLBs, 0 missing tower GLBs, `ready_for_import`, not vendor-grade.
- Product API: `/studio/summary`, `/designs/{id}`, `/designs/{id}/user-summary`, `/current-operation`, `/user-issues`, `/viewer-bundle`, `/timeline-summary`, `/versions`, and `/edit` are frontend-safe and expose artifact URLs, not local filesystem paths.
- E2E proof: `.venv/bin/python -m pytest tests/e2e/test_telecom_generation_proof.py -q`.
- Markdown context is intentionally small: `AGENTS.md`, `README.md`, and 10 active docs under `docs/`.
- Frontend: old dashboard frontend deleted; rebuild planned as chat-first / 3D-first.
