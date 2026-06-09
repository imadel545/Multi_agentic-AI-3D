# Document Pack Intelligence

## Implemented

The document-pack backend is now an operational local-first intelligence layer, not only an
observable MVP.

```text
ZIP bytes
-> safe member inventory
-> LangGraph document-pack orchestration
-> classification
-> PDF text/table extraction
-> selected OCR for high-value scanned evidence
-> DXF parsing when ezdxf is available
-> optional Groq bounded extraction with mandatory evidence
-> deterministic + Groq candidate consolidation
-> ProjectDesignSpec
-> QA, trace, events, memory writeback
-> direct RequirementSpec generation path
```

Core modules:

- `core/contracts/document_pack.py`
- `core/document_pack/classifier.py`
- `core/document_pack/text_extractor.py`
- `core/document_pack/cad.py`
- `core/document_pack/groq_extractor.py`
- `core/document_pack/orchestrator.py`
- `core/document_pack/extractor.py`
- `core/document_pack/mapper.py`
- `core/document_pack/service.py`

API endpoints:

- `POST /document-packs`
- `GET /document-packs`
- `GET /document-packs/capabilities`
- `GET /document-packs/{pack_id}`
- `GET /document-packs/{pack_id}/documents`
- `GET /document-packs/{pack_id}/extractions`
- `GET /document-packs/{pack_id}/consolidated-spec`
- `GET /document-packs/{pack_id}/conflicts`
- `GET /document-packs/{pack_id}/missing-fields`
- `GET /document-packs/{pack_id}/provenance`
- `GET /document-packs/{pack_id}/qa`
- `GET /document-packs/{pack_id}/processing`
- `GET /document-packs/{pack_id}/trace`
- `GET /document-packs/{pack_id}/events`
- `GET /document-packs/{pack_id}/memory-summary`
- `POST /document-packs/{pack_id}/corrections`
- `POST /document-packs/{pack_id}/generate-design`

`POST /document-packs` accepts raw ZIP bytes. The original ZIP is not stored durably; only compact
JSON artifacts are written under `outputs/temp/document_packs/{pack_id}`.

## Extraction And Provenance

Every source has explicit provenance:

- `source_type = text` for selectable text/plain text.
- `source_type = table` for `pdfplumber` table text.
- `source_type = ocr` for selected Tesseract evidence.
- `source_type = cad` for DXF layer/entity evidence.
- `source_type = coordinate_conversion` for computed WGS84 coordinates.
- `source_type = groq` for bounded LLM fields with verified evidence.
- `source_type = user_correction` for manual corrections.

Confirmed fields without source evidence are rejected by contracts and QA.

The deterministic extractor handles site, tower, radio sector, HBA, azimuth, RRU, cable, GPS,
cabinet, grounding, coordinate, and foundation signals. Cross-document differences become conflicts;
missing critical fields remain blocking.

## Groq Bounded Extraction

Groq document-pack extraction is separate from the requirements extractor.

Rules:

- max 12 chunks;
- max 2,500 characters per chunk;
- max 20,000 characters total;
- high/medium priority documents only;
- text/table/OCR/CAD chunks only;
- strict JSON fields: `field`, `value`, `confidence`, `document_id`, `page`, `evidence`;
- rejected if field prefix is unsupported, document id is invalid, confidence is invalid, evidence
  is empty, or evidence is not found in the chunk.

Groq candidates merge as normal `FieldCandidate` values. If they conflict with deterministic values,
the conflict stays visible and blocks mapping until corrected.

## ProjectDesignSpec To Generation

`POST /document-packs/{pack_id}/generate-design` no longer reparses a generated prompt.

The path is:

```text
ProjectDesignSpec
-> ProjectDesignSpecMapper
-> RequirementSpec
-> WorkflowService.create_design_from_requirements()
-> DesignOrchestrator.run_requirements()
-> RAG/memory/rules/planning/Blender/QA
```

The generated requirements text remains available only as a human-readable mapping summary, not as
the source of truth for generation.

## QA

Document-pack QA checks:

- critical fields have sources;
- no blocking missing fields;
- conflicts are resolved;
- average confidence is reasonable;
- useful documents are present;
- numeric values are plausible;
- no confirmed field lacks evidence;
- unsupported/unavailable processing limits are visible;
- coordinate conversion status is explicit;
- HBA does not exceed tower height;
- sector count aligns with azimuths;
- selected OCR documents were handled or exposed as limited;
- Groq fields without valid evidence were rejected visibly.

The QA report exposes `ready_confidence`, `recommended_user_actions`, `tool_failures`, and
`memory_writeback`.

## Available With Fallback

- PDF text: PyMuPDF/`fitz`.
- PDF tables: `pdfplumber`.
- OCR: local `tesseract` + `pytesseract` + `PIL`, selected only for high-value scanned evidence.
- Layout: Docling is installed/importable, but not used by default because it is heavy and
  model-driven. Model-based conversion needs enough free disk to hydrate its local cache.
- DXF: `ezdxf` parses layers, TEXT, MTEXT, INSERT, DIMENSION, POINT, LINE, and LWPOLYLINE evidence.
- DWG: unsupported without a local converter; no cloud conversion is attempted.
- Coordinates: `pyproj` converts recognized Lambert 93/Lambert II to WGS84.
- Groq: enabled only when a Groq client/key is configured; deterministic fallback is visible.

## Known Limitations

- OCR is selected and bounded, not a full layout understanding engine.
- Docling is not part of the default ingestion path yet.
- DWG conversion is still not executed without ODA/FreeCAD/dwgread.
- DXF geometry is exposed as evidence, not yet transformed into mount-zone geometry.
- Groq evidence is useful but never bypasses contracts, rules, conflicts, or QA.
- The document-pack flow is synchronous; endpoints expose trace/events after ingestion, not SSE.

## Future

- Add asynchronous document-pack processing and SSE if ingestion grows heavier.
- Add Docling layout region provenance only after a bounded runtime policy is implemented.
- Add DWG-to-DXF conversion when a local converter exists.
- Add richer table semantics for equipment lists.
- Add CAD geometry QA for mount zones, antenna levels, cable routes, and compound layouts.
