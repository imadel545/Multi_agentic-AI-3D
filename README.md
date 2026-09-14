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
- Runs GLB structural-integrity and geometry QA; this is not a structural-load calculation.
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
  `GeometryProgram` vocabulary is a bounded DSL with profiles/extrusion,
  revolution, sweep, arrays, booleans, modifiers, terrain, hierarchy,
  anchors and connectors. It does not provide CAD B-Rep, triangle/BVH
  engineering QA, semantic intent certification or vendor certification.

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

The default ports are shown below. To retain an existing native workspace,
set `TELECOM_STUDIO_FRONTEND_PORT=15173` and `TELECOM_STUDIO_API_PORT=18000`
in `.env`; allowed browser origins follow the frontend port. Docker keeps
separate persistent volumes; it does not migrate historical native certificates.

- Studio: `http://127.0.0.1:5173`
- API and Swagger: `http://127.0.0.1:8000/docs`
- Adminer: `http://127.0.0.1:8080`
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`

If Docker Desktop requires its internal HTTP proxy for outbound provider calls,
set `TELECOM_STUDIO_HTTP_PROXY` and `TELECOM_STUDIO_HTTPS_PROXY` in the local
`.env` (for the standard Desktop proxy, `http://http.docker.internal:3128`).
Compose passes these values only to the API container and keeps Qdrant and the
other local services in `TELECOM_STUDIO_NO_PROXY`. TLS verification remains on.

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

Open the studio at `http://127.0.0.1:5173` and create its local owner account.
API docs at `http://127.0.0.1:8000/docs` require that session.

Default CORS is local only: `http://127.0.0.1:5173,http://localhost:5173`.
Override with `TELECOM_STUDIO_CORS_ORIGINS` when a future frontend uses a different local origin.
Trusted hosts default to `127.0.0.1`, `localhost`, and `testserver`; configure
`TELECOM_STUDIO_TRUSTED_HOSTS` only for another explicit local hostname. A
state-changing browser request with a foreign `Origin` is rejected before the
service runs. A separate local owner account protects data and artifacts with
a revocable, expiring `HttpOnly` session cookie. Registration asks for a name,
email address and password; it does not introduce a multi-user SaaS or JWT storage
in the browser.

### Optional: Blender

Real `design.glb` generation requires a locally operational Blender. Pin
**Blender 4.5 LTS** for this production-style pipeline instead of treating any
newer executable as qualified. The runner searches:

- `BLENDER_BINARY` env var
- `TELECOM_STUDIO_BLENDER_BINARY` env var
- `blender` in `PATH`
- `/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender`
- `/Applications/Blender.app/Contents/MacOS/Blender` as a last generic macOS candidate

Executable presence is not runtime proof. The certifiable local runtime is
exactly **Blender 4.5.12 LTS** with a successful background/factory-startup
probe; a newer installed executable such as Blender 5.1.2 is rejected rather
than silently creating a version. A Blender crash remains a failed workflow and
is never converted into a completed placeholder. The Docker service fixes both
`BLENDER_BINARY` and `TELECOM_STUDIO_BLENDER_BINARY` to
`/opt/blender/blender`, so a host `.env` path cannot override its governed
runtime.

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
# Optional independent-account failover pool (comma or semicolon separated):
TELECOM_STUDIO_GROQ_API_KEYS=...
```

The API uses `openai/gpt-oss-120b` by default. Use `options.use_llm=false` to
force deterministic extraction. Components outside the qualified catalog require
the enabled Groq geometry specialist; there is no fabricated deterministic
geometry fallback when that specialist cannot return a valid program.
The shared transport distributes requests across distinct configured accounts,
prefers the least-loaded credential, quarantines authentication failures, and
fails over immediately when one account is rate-limited (`429` or Groq's
`413/rate_limit_exceeded` TPM response). It never sleeps a
workflow on `Retry-After`; if every account is unavailable, the existing visible
fallback/fail-closed capability policy applies. Multiple accounts do not protect
against a global Groq, network, or model outage.

### Product intelligence: NVIDIA RAG embeddings

Product RAG uses NVIDIA API `nvidia/nemotron-3-embed-1b` at 2048 dimensions.
The hosted NVIDIA text rerankers checked on 2026-09-14 were unavailable, so the
current default is explicit passthrough and the API does not report neural
reranking. Static documents are embedded by one cross-collection
operation, sent to NVIDIA in bounded batches of at most 32 passages, and the
synchronous path performs no SDK retry. If NVIDIA indexing or
query embedding times out, retrieval falls back to lexical ranking over the
real local corpus and exposes `degraded_local_lexical`; it never substitutes a
hash embedding and never labels that fallback as vector retrieval.

```bash
NVIDIA_API_KEY=...
# or TELECOM_STUDIO_NVIDIA_API_KEY=...
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b
TELECOM_STUDIO_EMBEDDING_DIMENSIONS=2048
TELECOM_STUDIO_EMBEDDING_TIMEOUT_S=30
TELECOM_STUDIO_RERANKER_PROVIDER=passthrough
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

Backend fast gate (default, no Blender subprocess, provider, or browser):

```bash
.venv/bin/python -m pytest -q
```

Audit the collection without executing any runtime test:

```bash
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest --collect-only -q -m blender_runtime
.venv/bin/python -m pytest --collect-only -q -m provider_live
```

Real Blender gate (serialized and explicit):

```bash
BLENDER_BINARY="/Applications/Blender 4.5 LTS.app/Contents/MacOS/Blender" \
  .venv/bin/python -m pytest -q -m blender_runtime --durations=30
```

External-provider tests are opt-in only and must be marked `provider_live`:

```bash
TELECOM_STUDIO_TEST_LIVE_PROVIDERS=1 \
  .venv/bin/python -m pytest -q -m provider_live --durations=30
```

The test harness rejects resolved Groq/NVIDIA credentials by default and fails
immediately if an unmarked test attempts to launch a real Blender subprocess.
`browser_smoke` is a reserved marker with zero automated pytest cases today.
The current browser proof is a recorded interactive real-API/WebGL smoke;
jsdom tests do not count as WebGL evidence.

---

## Core flow

```text
requirements_text or document pack
→ LangGraph orchestrator
→ Groq structured RequirementSpec or deterministic fallback
→ NVIDIA Nemotron multilingual query/passage embeddings + Qdrant retrieval
  or visible lexical retrieval over the real local corpus
→ explicit passthrough ranking + bounded GPT-OSS planning decision
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
→ post-export AssemblyPlan constraint evidence
→ completion certificate + atomic version activation
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

- Backend: local-first workflow with bounded Groq decisions, real Blender output,
  versioning, QA and certificate revalidation.
- Frontend: chat-first and 3D-first rework connected to the real Product API;
  remaining acceptance items stay explicit in
  [`docs/FRONTEND_ACCEPTANCE_CRITERIA.md`](docs/FRONTEND_ACCEPTANCE_CRITERIA.md).
- Assets: `qualified_mixed_catalog`; the generation catalog is technical and
  internal, while manufacturer and raw-CAD candidates remain excluded until
  their rights, geometry and integration evidence pass.
- RAG: NVIDIA `nvidia/nemotron-3-embed-1b` with explicit local lexical
  degradation and passthrough reranking. Configuration alone is never reported
  as provider availability.
- The bounded Docker/Groq/NVIDIA/Blender evidence from 2026-09-14, together
  with its limits and runtime-reset boundary, is recorded once in
  [`docs/PROJECT_SOURCE_OF_TRUTH.md`](docs/PROJECT_SOURCE_OF_TRUTH.md).
- Current test commands and proof levels are defined in
  [`docs/QA_STRATEGY.md`](docs/QA_STRATEGY.md); frozen suite counts are not used
  as current-tree evidence.
