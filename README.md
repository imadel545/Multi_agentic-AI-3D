# Agentic AI 3D Telecom Design Studio

Local-first pipeline for transforming telecom requirements into a validated `SceneSpec`, controlled 3D generation artifacts, and compliance reports.

> **Frontend product rework in progress.**<br>
> `apps/frontend` is connected to the real `/designs` + `workflow_id` contract, but it is not an accepted product gate yet. The rejected dashboard-like kernel must not be treated as final UI.<br>
> See `docs/PROJECT_SOURCE_OF_TRUTH.md` for the single source of truth, `docs/BACKEND_CAPABILITY_MATRIX.md` for backend capabilities, and `docs/KNOWN_LIMITATIONS.md` for honest limitations.

---

## What it does

- Takes a technical brief, several direct technical files, or a ZIP document
  pack (PDF/DXF/images/tables) as input.
- Extracts structured requirements (`RequirementSpec`) with typed field evidence,
  assumptions and conflict gates, or a provenance-backed design spec
  (`ProjectDesignSpec`).
- Produces a typed `DesignBlueprint`, a scored multi-candidate `AssemblyPlan`,
  and a controlled 3D scene (`SceneSpec`).
- For requested components absent from the qualified catalog, GPT-OSS may author
  a bounded declarative `GeometryProgram`; deterministic contracts validate its
  units, topology graph, transforms, requested envelope and aggregate resource
  budget before the fixed Blender compiler executes it.
- Generates a real `design.glb`, `preview.png`, and reports via headless Blender.
- Runs structural and geometry QA.
- Current mesh QA reaches `mesh_level_spatial_basic` when semantic transforms and
  primary-equipment bounds are complete, `mesh_level_transform_basic` when only
  transforms are complete, otherwise `mesh_level_basic`. It screens real GLB
  AABBs with a bounded same-sector antenna/RRU contact tolerance, but it is not
  exact triangle/BVH, RF, structural, or vendor-grade QA.
- Supports prompt edits, versioning, and rollback.
- The frontend product vocabulary maps to existing backend concepts: a "run" is
  a `workflow_id`, and a "scene plan" is the `scene_spec` artifact.

## What it does not do yet

- It is not a polished end-user product.
- It does not guarantee vendor-grade visual realism (current assets are internal/CC-BY).
- It does not run without a local Blender install for real 3D output.
- It does not provide a production-ready frontend today.
- It is not an unrestricted arbitrary-shape generator: the current
  `GeometryProgram` vocabulary is limited to validated primitives, polygonal
  curves, instances, materials and transforms. It does not provide CSG,
  triangle/BVH engineering QA or vendor certification.

---

## Run locally

### Full Docker stack

Docker Compose runs the frontend, API, Blender 4.5.12 LTS, Qdrant, coherent
SQLite snapshots and Adminer without importing the host runtime databases or
outputs. Copy `.env.example` to `.env`, add the Groq and NVIDIA keys at runtime,
then run:

```bash
docker compose -p agentic-3d-studio -f infra/docker-compose.yml --env-file .env up --build -d
docker compose -p agentic-3d-studio -f infra/docker-compose.yml --env-file .env ps
```

- Studio: `http://127.0.0.1:5173`
- API and Swagger: `http://127.0.0.1:8000/docs`
- Adminer: `http://127.0.0.1:8080`
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`

In Adminer, choose SQLite and open one of these read-only snapshot databases:

- `file:/db/telecom_studio.db?mode=ro&immutable=1`
- `file:/db/checkpoints.db?mode=ro&immutable=1`

Adminer never mounts the live API database. The snapshot sidecar publishes a
verified backup every five seconds and preserves the last valid copy if a
backup fails. Vector collections are inspected in Qdrant, not Adminer.

```bash
# Stop containers and preserve all named volumes.
docker compose -p agentic-3d-studio -f infra/docker-compose.yml --env-file .env down

# Destructive, intentional reset of SQLite, outputs, Qdrant and previews.
docker compose -p agentic-3d-studio -f infra/docker-compose.yml --env-file .env down -v
```

On Apple Silicon, the API image is intentionally `linux/amd64` because the
qualified official Blender archive is x86-64. Real renders are consequently
slower under Docker Desktop emulation; the workflow concurrency is limited to
one and Blender has a 600-second timeout. The container uses the governed EEVEE
profile with 8 render samples for responsive technical previews; native runs
keep their existing quality default.

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

Real `design.glb` generation requires a locally operational Blender. Pin
**Blender 4.5 LTS** for this production-style pipeline instead of treating any
newer executable as qualified. The runner searches:

- `BLENDER_BINARY` env var
- `TELECOM_STUDIO_BLENDER_BINARY` env var
- `blender` in `PATH`
- `/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender`
- `/Applications/Blender.app/Contents/MacOS/Blender` as a last generic macOS candidate

Executable presence is not runtime proof. Validate the chosen binary with a
background/factory-startup smoke; a Blender crash remains a failed workflow and
is never converted into a completed placeholder.

### Optional: Qdrant

```bash
docker compose -f infra/docker-compose.yml up -d qdrant
TELECOM_STUDIO_QDRANT_URL=http://127.0.0.1:6333 uvicorn apps.api.telecom_studio_api.main:app --reload
```

Without `TELECOM_STUDIO_QDRANT_URL`, the API uses Qdrant local mode under `data/qdrant`.
The Compose service is bound to `127.0.0.1` only. Its server pin matches the
Python client at Qdrant `v1.18.0`. Do not expose it to a LAN or upgrade a
non-empty volume without following Qdrant's supported migration path.

### Dependency reproducibility

`package-lock.json` pins the frontend dependency tree.
`infra/requirements-docker.lock` pins the Linux Python 3.12 Docker resolution;
the API image installs only that lock. Native editable development installs
remain range-based in `pyproject.toml` and are not bit-for-bit reproducible.

### Product intelligence: Groq

```bash
GROQ_API_KEY=...
# or TELECOM_STUDIO_GROQ_API_KEY=...
```

The API uses `openai/gpt-oss-120b` by default. Use `options.use_llm=false` to
force deterministic extraction. Components outside the qualified catalog require
the enabled Groq geometry specialist; there is no fabricated deterministic
geometry fallback when that specialist cannot return a valid program.

### Product intelligence: NVIDIA RAG embeddings

Product RAG uses NVIDIA API `nvidia/llama-nemotron-embed-1b-v2` at 1024
dimensions. Product reranking uses the NVIDIA
reranker configured by `TELECOM_STUDIO_RERANKER_MODEL`; if the reranker is not
available, the API exposes a degraded passthrough status instead of pretending
reranking happened.

```bash
NVIDIA_API_KEY=...
# or TELECOM_STUDIO_NVIDIA_API_KEY=...
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-1b-v2
TELECOM_STUDIO_EMBEDDING_DIMENSIONS=1024
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
→ NVIDIA Nemotron multilingual query/passage embeddings + Qdrant retrieval
→ NVIDIA reranking + bounded GPT-OSS planning decision
→ SQLite memory recall
→ scored qualified asset candidates + AssemblyPlan
→ rule engine
→ DesignBlueprint + routed deterministic specialists
→ SceneSpec
→ optional bounded GPT-OSS GeometryProgram
→ SceneSpec validator
→ deterministic Blender builders / GeometryProgram compiler
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
- `docs/RAG_STRATEGY.md` — NVIDIA multilingual retrieval strategy and limitations.
- `docs/ARCHITECTURE.md` — backend flow and module boundaries.
- `docs/QA_STRATEGY.md` — honest QA levels and limits.
- `docs/LANGGRAPH_WORKFLOW.md` — orchestration/runtime truth.

---

## Status

- Backend: functional local-first pipeline with real Blender output when Blender is installed.
- Assets: 13 manifests, 12 local GLBs, 13 generation-eligible, 3 exact imports,
  10 parametric generation profiles, 0 reference-only, and 0 professional M1
  evidence asset after runtime byte verification; `qualified_mixed_catalog`,
  not vendor-grade.
- Product API: `/studio/summary`, `/designs/{id}`, `/designs/{id}/user-summary`, `/current-operation`, `/user-issues`, `/viewer-bundle`, `/timeline-summary`, `/versions`, and `/edit` are frontend-safe and expose artifact URLs, not local filesystem paths.
- E2E proof: `.venv/bin/python -m pytest tests/e2e/test_telecom_generation_proof.py -q`.
- Markdown context is intentionally small: `AGENTS.md`, `README.md`, and 10 active docs under `docs/`.
- Frontend: `apps/frontend` contains a real-backend product rework in progress.
  The previous dashboard-like kernel is rejected; acceptance requires a
  chat-first / 3D-first smoke with visible GLB or explicit fallback.
- Latest real GeometryProgram proof: workflow `wf_ead2456914b2` and revision
  `v2e0a4faf` completed with `real_blender`, QA 1.0, an issued certificate, GLB
  and preview. This proves that scenario only. The current frontend gate passes
  157 tests, typecheck, production build and a 2026-08-10 real-API browser smoke
  of the truthful 0/13 professional asset state.
