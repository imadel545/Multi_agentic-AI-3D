# Current State Audit - 2026-06-13

## Environment

- macOS Apple Silicon validated with Python 3.12.7 in `.venv`.
- Homebrew is installed under `/opt/homebrew`.
- Blender is installed at `/Applications/Blender.app/Contents/MacOS/Blender`.
- Tesseract 5.5.2 and `tesseract-lang` are installed; 163 OCR languages are available.
- LibreDWG `dwgread` is installed for local DWG conversion attempts.
- FastEmbed is installed and the local RAG index uses `BAAI/bge-small-en-v1.5`.
- Docling is installed and wired as a fallback after PyMuPDF/pdfplumber/OCR produce no evidence.

## Runtime Architecture

The project is a local-first FastAPI + React/Vite monorepo.

Primary flow:

```text
React Studio
-> FastAPI
-> WorkflowService
-> LangGraph DesignOrchestrator
-> RequirementExtractor
-> RAG + memory recall
-> asset registry + domain agents
-> SceneSpec
-> quality gates
-> BlenderRunner
-> GLB / preview / metadata
-> GLB, geometry, preview QA
-> versioned artifacts + memory writeback
```

Document-pack flow:

```text
ZIP
-> safe inventory
-> classification
-> text/table/OCR/CAD extraction
-> optional Groq bounded extraction when a real key is configured
-> ProjectDesignSpec consolidation
-> QA + provenance
-> memory writeback
-> RequirementSpec mapping
-> normal design workflow
```

## Agents And Routing

- `RequirementExtractor`: Groq structured extraction when configured; deterministic fallback is
  explicit.
- `TowerEngineerAgent`: tower/domain validation.
- `RfEngineerAgent`: RF validation.
- `ScenePlanner`: controlled `SceneSpec` generation from validated requirements, RAG, memory, and
  selected assets.
- `SceneEditAgent`: typed patch creation for edits; never writes arbitrary Blender Python.
- `DesignOrchestrator`: LangGraph routing for extraction, RAG, memory, assets, validation, repair,
  Blender, QA, quality gates, and memory writeback.
- `DocumentPackOrchestrator`: graph-based document indexing, extraction, Groq, consolidation, QA,
  and memory.

Routes fail closed:

- Missing requirements block or require repair.
- Asset selection can route through compatible fallback, but fallback is visible.
- Pre-Blender gate failure blocks Blender.
- Blender failure/fallback routes to QA with explicit generation mode.
- Post-Blender gate requires real Blender GLB parsing for real generation.

## Real Backend And Artifacts

- Frontend uses FastAPI endpoints, not local file paths.
- Artifact routes are whitelisted by API keys such as `glb`, `preview`, `metadata`, `qa_report`,
  and `trace`.
- Versioned workflows store active version state and ZIP archives.
- Browser smoke validated backend `ok`, `real_blender`, QA 100%, and a rendered Three.js canvas.
- Small-cell smoke validated `TOWER_SMALL_CELL_10M`, GPS, power cabinet, `real_blender`, and
  7/7 imported GLBs with zero procedural fallback.

## RAG And Memory

- Static RAG collections are indexed with FastEmbed:
  - telecom rules
  - asset manifests
  - scene templates
  - validation cases
  - design patterns
  - Blender generation guides
- SQLite memory stores compact workflow/design/error/document-pack summaries.
- Qdrant runtime memory indexing is best-effort; SQLite writeback remains durable locally.
- RAG and memory provide context only; deterministic contracts/rules remain authoritative.

## Assets

- Inventory is now `ready_for_import`.
- All 12 manifests have local GLB files.
- Monopole, rooftop mast, and small-cell tower GLBs were generated as project-owned internal assets
  with a reproducible Blender script under `tools/`.
- The project is still not vendor-grade: several assets are internal cleaned/minimal or CC-BY.
- This is visible through asset source, license, attribution, warnings, inventory, metadata, and UI.

## Document Intelligence

- PDF text: PyMuPDF.
- PDF tables: pdfplumber.
- OCR: Tesseract + Apple Vision fallback on macOS.
- Layout fallback: Docling.
- DXF: ezdxf.
- DWG: LibreDWG `dwgread` conversion to DXF, then ezdxf parsing.
- Coordinates: pyproj.
- Groq bounded extraction: requires a real active key in `.env` or environment.

## Current Secret State

The active `.env` exists, but the checked `GROQ_API_KEY` value is empty at the time of this audit.
The API therefore cannot use real Groq until the key is added under one of the supported names:

- `GROQ_API_KEY`
- `TELECOM_STUDIO_GROQ_API_KEY`
- `groq_api`

Secrets are intentionally not logged or committed.

## Closed Weaknesses In This Pass

- Homebrew/Tesseract/Tesseract languages installed.
- Shell `pyenv` startup errors fixed with backups.
- OCR no longer breaks when Tesseract is absent; Apple Vision fallback exists.
- FastEmbed cache moved to a stable user cache with safe fallback on cache corruption.
- Vite/esbuild audit fixed by upgrading Vite to 8.0.16.
- API CORS wildcard removed; local frontend origins are allowed by default.
- Docling is no longer import-only; it is a real fallback.
- DWG detection is no longer only informational; `dwgread` conversion is attempted.
- Missing tower GLB files removed by generating local GLBs.
- Deterministic requirement parsing now handles English long-form units such as `10 meter`,
  azimuth phrases such as `90 and 270 degrees`, and explicit GPS/power-cabinet requests.
- GitHub Actions CI added for backend lint/tests and frontend audit/typecheck/tests/build.

## Remaining Truths

- A real Groq smoke test needs the user-provided key to be present in active `.env` or shell env.
- Vendor-grade visual realism still requires licensed telecom equipment assets.
- Some internal assets remain minimal and are intentionally labeled as non-vendor-grade.
- Qdrant local mode is acceptable for local single-user work; server-mode Qdrant is better for
  concurrent/multi-process operation.
- Formal exhaustive security scan with Codex Security requires explicit authorization for
  subagents before starting that workflow.
