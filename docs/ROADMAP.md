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
- Asset pipeline MVP: inventory detects present/missing GLBs, all twelve GLBs are present, the
  lattice tower is an integrated CC Attribution asset, the three remaining towers are project-
  generated Blender GLBs, accessory/internal cleaned GLBs are exposed, Blender imports selected
  GLBs, procedural fallback is explicit, and API status exposes asset import metadata.
- Document-pack intelligence: ZIP indexing, LangGraph document-pack orchestration, document
  classification, PDF text/table extraction, selected OCR, DXF parsing with layer provenance,
  bounded Groq document extraction when configured, conflict/missing detection,
  `ProjectDesignSpec`, manual corrections, document-pack QA, direct `RequirementSpec` generation,
  trace/events, and backend endpoints available for a future frontend.
- Document-pack accessory mapping: confirmed GPS antenna and power-cabinet evidence is carried into
  `RequirementSpec`, `SceneSpec.visual_elements`, and manifest-backed `SceneSpec.accessory_assets`
  without RAG-driven decorative activation.
- Document-pack tilt mapping: confirmed uniform mechanical tilt is carried into `RequirementSpec`
  instead of silently using the default.
- Final real 3D acceptance path: document-pack GPS/power-cabinet/tilt/RRU/cables smoke-tested
  through FastAPI, real Blender, GLB inspection, geometry QA, preview QA, and API status.
- Document-pack memory writeback: compact `memory_summary.json`, SQLite
  `document_pack_memory`/`document_pack_issue_memory`, optional Qdrant runtime
  `document_pack_memory`, and `/memory/stats` counts.

## Available With Fallback

- Groq extraction falls back to deterministic parser.
- NVIDIA BGE-M3 embedding falls back to local `sentence-transformers`, then deterministic hash as
  emergency/test fallback.
- Blender generation falls back explicitly if Blender is absent or fails; fallback is not a valid
  product result by default.
- Missing asset files fall back to procedural geometry only when the manifest allows it, and the
  fallback is visible in `scene_metadata.json`, QA, and API status.
- Current internal cleaned/minimal assets support MVP visuals but are not vendor-grade.
- PDF text extraction is opportunistic through local PyMuPDF when installed; otherwise PDFs are
  recorded without pretending extraction succeeded.
- PDF table extraction is opportunistic through `pdfplumber` when installed.
- Selected OCR is opportunistic through Tesseract/`pytesseract`/`PIL` and exposes page/confidence
  provenance.
- DXF parsing is optional through `ezdxf`; otherwise DXF remains inventory-only.
- Groq document-pack extraction is optional and accepts only evidence-backed bounded JSON fields.
- DWG files are inventoried with explicit unsupported status unless local conversion is wired.
- Coordinate conversion is optional through `pyproj`; otherwise source coordinates are preserved
  with `unavailable_pyproj` or `unsupported_crs`.
- GLB inspection falls back to `metadata_fallback` only for explicit non-GLB fallback artifacts
  with `scene_metadata.json`.

## Requires Local Blender Install

- Real `design.glb` and `preview.png` generation requires Blender.
- Recommended install: Blender 4.5 LTS or newer.

## Future

- Replace internal cleaned/minimal GLBs and missing tower manifests with vendor-grade or
  project-owned production GLB assets.
- Wire standalone prompt/document controls for mounting bracket and cable-tray accessory placement.
- Add exact imported-asset bounding-box, pivot, mount-point, material, and LOD validation.
- Wire cleanup TTL into an explicit CLI/admin action and add SQLite row cleanup.
- Rebuild frontend from scratch as chat-first / 3D-first after backend truth surfaces are stable.
- Add Docling layout extraction only with timeout/cost controls.
- Add production-grade table extraction for equipment inventories.
- Use document-pack memory recall to suggest recurring corrections and APD conflict resolutions.
- Add non-committed edit preview/apply workflow if the frontend needs preview before activation.
- Replace internal/minimal assets with licensed vendor-grade telecom GLBs where possible and keep
  attribution/source metadata visible.
- Add richer Qdrant payload filters and evaluate domain-specific retrieval quality.
- Add comparative design variants.
- Add exact GLB transform, bounding-box, and material validation for imported vendor assets.
- Add rendered preview visual semantic checks.
- Add richer accessory-specific dimensional QA beyond current presence/count/import-mode checks.
