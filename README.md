# Agentic AI 3D Telecom Design Studio

Local-first pipeline for transforming telecom requirements into a validated `SceneSpec`, controlled 3D generation artifacts, and compliance reports.

> ⚠️ **Frontend removed.**<br>
> The old frontend under `apps/frontend` has been deleted. A chat-first / 3D-first frontend will be rebuilt later.<br>
> See `docs/PROJECT_SOURCE_OF_TRUTH.md` for the single source of truth, `docs/BACKEND_CAPABILITY_MATRIX.md` for backend capabilities, and `docs/KNOWN_LIMITATIONS.md` for honest limitations.

---

## What it does

- Takes a technical brief or a document pack (ZIP with PDF/DXF/images) as input.
- Extracts structured requirements (`RequirementSpec`) or a provenance-backed design spec (`ProjectDesignSpec`).
- Plans a controlled 3D scene (`SceneSpec`).
- Generates a real `design.glb`, `preview.png`, and reports via headless Blender.
- Runs structural and geometry QA.
- Supports prompt edits, versioning, and rollback.

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
pytest
```

---

## Core flow

```text
requirements_text or document pack
→ LangGraph orchestrator
→ Groq structured RequirementSpec or deterministic fallback
→ Qdrant RAG context (advisory)
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
- `docs/API_FRONTEND_CONTRACT.md` — minimal API contract for the frontend.

---

## Status

- Backend: functional local-first pipeline with real Blender output when Blender is installed.
- Assets: 12 manifests with local GLBs, mostly internal/CC-BY, not vendor-grade.
- Product API: `/studio/summary`, `/designs/{id}/user-summary`, `/current-operation`, `/user-issues`, `/viewer-bundle`, `/timeline-summary` are available.
- Frontend: old dashboard frontend deleted; rebuild planned as chat-first / 3D-first.
