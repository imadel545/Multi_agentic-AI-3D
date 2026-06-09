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
- Asset inventory/import metadata with explicit `imported_glb`, `procedural_fallback`, and
  `missing_file` modes.
- FastAPI endpoints for design creation, status, validation, assets, and artifact download.
- Prompt-based SceneSpec editing with patch validation, per-version artifacts, QA rerun, diff,
  rollback, and event logging.
- React/Vite Agentic 3D Studio frontend under `apps/frontend` with document-pack upload, agent
  console, event timeline, GLB viewer, QA/assets/versions/diff/download panels, and real backend
  artifact links.
- Controlled Blender runner that executes Blender when available and falls back explicitly otherwise.
- Generation QA checks for GLB, preview, geometry metadata, sector count, and fallback warnings.
- Geometry validation for expected antennas, beams, RRUs, cables, GPS, power cabinet, azimuths,
  tilt metadata, and tower/antenna heights.
- Local Qdrant RAG indexing and search over rules, docs, templates, and asset manifests.
- Document-pack intelligence for ZIP ingestion, classification, deterministic extraction,
  provenance, missing/conflict detection, manual corrections, QA, processing capabilities, and
  mapping into the existing design workflow. Confirmed GPS antenna and power-cabinet evidence is
  preserved into SceneSpec visual flags, and confirmed uniform mechanical tilt is preserved in
  requirements; unsupported fields stay visible as warnings.

## Run locally

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn apps.api.telecom_studio_api.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

Frontend:

```bash
cd apps/frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Set `VITE_API_BASE_URL` if the FastAPI backend is not running on
`http://127.0.0.1:8000`.

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

Optional document-intelligence tooling:

```bash
pip install -e ".[document-intel]"
```

This enables optional local adapters when available (`fitz`, `pdfplumber`, `ezdxf`, `pyproj`,
`pytesseract`, `PIL`). The backend still reports each capability explicitly and does not pretend
OCR/CAD/conversion succeeded when a tool is missing.

## Test

```bash
pytest
```

Frontend checks:

```bash
cd apps/frontend
npm run typecheck
npm run test
npm run build
```

Focused eval suites:

```bash
pytest tests/rag_eval tests/memory_eval
```

## API surface

Implemented:

- `POST /designs`: start a design workflow.
- `GET /designs/{workflow_id}`: active workflow/version status, reports, artifacts, QA summaries,
  LLM provider/fallback state, RAG/memory counts, asset import summary, and download URL.
  A pending status file is available immediately after creation, so polling does not need to
  tolerate a transient `404`.
- `GET /designs/{workflow_id}/events`: agentic event log.
- `GET /designs/{workflow_id}/events/stream`: SSE event stream; unknown workflows return `404`.
- `GET /designs/{workflow_id}/artifacts/{artifact_name}`: whitelisted GLB, preview, reports,
  metadata, patch/diff, trace and archive artifact serving for active or versioned artifacts.
- `POST /designs/{workflow_id}/edit`: create a structured patch from a prompt, validate it,
  generate a new version, rerun QA, and activate it only if the revision passes.
- `GET /designs/{workflow_id}/versions`: version history with active flag, artifacts, QA score,
  generation mode, and diff summary.
- `POST /designs/{workflow_id}/versions/{version_id}/rollback`: set an existing version active
  without deleting history.
- `GET /assets/inventory`: GLB readiness inventory with missing/present files, source, fallback
  policy, and warnings.
- `POST /document-packs`: ingest a ZIP as raw bytes and write JSON-only pack artifacts.
- `GET /document-packs/capabilities`: local PDF/OCR/CAD/coordinate/Groq document-pack tool status.
- `GET /document-packs/{pack_id}/documents`: classified document inventory.
- `GET /document-packs/{pack_id}/consolidated-spec`: provenance-backed `ProjectDesignSpec`.
- `GET /document-packs/{pack_id}/processing`: per-document extraction status/tools/warnings.
- `GET /document-packs/{pack_id}/qa`: document-pack QA score, checks, and blocking issues.
- `POST /document-packs/{pack_id}/corrections`: apply a manual correction with provenance.
- `GET /document-packs/{pack_id}/memory-summary`: compact no-large-file memory summary artifact.
- `POST /document-packs/{pack_id}/generate-design`: map an unblocked pack into the design flow.

Available with fallback:

- Groq `openai/gpt-oss-120b` extraction and edit patching fall back to deterministic logic when
  provider access fails or `options.use_llm=false` is set for creation.
- Blender fallback artifacts are explicit and still pass through QA/gates.
- PDF/OCR/CAD/coordinate tooling is optional and reported through `/document-packs/capabilities`.

Known limitations:

- The current asset library is `partial_import_ready`: a CC-BY lattice tower and internal
  cleaned/minimal telecom assets exist, but they are not a complete vendor-grade library.
- The Blender worker imports available GLBs and uses controlled procedural fallback for missing
  assets only when fallback is allowed and visible in metadata. GPS and power-cabinet accessories
  are manifest-backed placements when explicitly requested.
- Preview QA is structural/image-stat based, not semantic visual judging.
- Document-pack PDF text/table, selected OCR, DXF parsing, coordinate conversion, and Groq bounded
  extraction are capability-gated and report unavailable tools explicitly. Docling is currently
  `installed_import_only`, not part of the default extraction path. DWG remains
  `unsupported_without_converter` unless a local ODA/FreeCAD/dwgread converter is installed.

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

Document-pack flow:

```text
zip pack
→ safe inventory
→ document classification
→ optional local text/table/CAD capability checks
→ deterministic telecom extraction
→ coordinate conversion status
→ ProjectDesignSpec resolver
→ document-pack QA
→ user corrections when needed
→ RequirementSpec mapping with provenance warnings
→ existing design workflow
```

Edit flow:

```text
edit prompt
→ SceneEditAgent structured patch
→ PatchApplier
→ SceneSpec validation
→ revision orchestration from patched SceneSpec
→ Tower/RF/rule validation
→ Blender generation
→ GLB/geometry/preview QA
→ quality gates
→ version artifacts + status
→ active version switch only on success
```

FastEmbed/BGE-M3 and vendor-grade Blender assets remain extension points. Qdrant,
Groq structured extraction, LangGraph orchestration, controlled Blender execution, GLB import
metadata, and generation QA are implemented. SQLite memory is stored under `data/sqlite` by
default.
