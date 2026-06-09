# API Contract

## Implemented

Core backend surfaces for the future Agentic 3D Studio:

- `POST /designs`
- `GET /designs`
- `GET /designs/{workflow_id}`
- `GET /designs/{workflow_id}/events`
- `GET /designs/{workflow_id}/events/stream`
- `POST /designs/{workflow_id}/edit`
- `GET /designs/{workflow_id}/versions`
- `POST /designs/{workflow_id}/versions/{version_id}/rollback`
- `GET /designs/{workflow_id}/download`
- `GET /assets/inventory`
- `POST /document-packs`
- `GET /document-packs`
- `GET /document-packs/capabilities`
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
- `GET /memory/stats`
- `POST /rag/reindex`
- `GET /rag/search`

Errors use JSON responses. The global `500` response includes `request_id` and an `x-request-id`
header.

## Available With Fallback

- `events/stream` returns `404` for unknown workflows and closes after terminal events or bounded
  idle timeout.
- Design status exposes fallback information for LLM, Blender, asset import, QA, RAG, and memory.
- Document-pack status exposes unavailable OCR/PDF/CAD/coordinate tooling instead of hiding it.
- `POST /document-packs/{pack_id}/generate-design` uses `ProjectDesignSpec -> RequirementSpec`
  directly and returns `extraction_report.prompt_text_reparse = false`.
- Document-pack trace/events are normal JSON endpoints for frontend timeline display; they are not
  SSE yet.

## Known Limitations

- Artifact serving by version still uses status paths and download archives; dedicated
  `/artifacts/...` routes can be added for the frontend.
- Document-pack upload currently accepts raw ZIP bytes, not multipart metadata.
- Edit is apply-and-generate, not a separate preview-only patch flow.
- Document-pack ingestion remains synchronous; large packs may justify async processing later.

## Future

- Add version-scoped artifact routes for GLB, preview, reports, and archives.
- Add patch preview/apply endpoints if the frontend needs a non-committed edit review step.
- Add document-pack SSE events if ingestion becomes asynchronous.
