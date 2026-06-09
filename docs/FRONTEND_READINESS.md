# Frontend Readiness

## Implemented

The backend exposes the data needed for an advanced local-first frontend:

- `POST /designs` starts a workflow and writes pending status immediately.
- `GET /designs/{workflow_id}` returns active version status, artifacts, QA summaries, quality
  gates, LLM provider/fallback state, RAG/memory counts, event trace path, and asset import
  metadata.
- `GET /designs/{workflow_id}/events` returns the append-only workflow timeline.
- `GET /designs/{workflow_id}/events/stream` streams events with clean `404` behavior for unknown
  workflows and a bounded idle timeout.
- `POST /designs/{workflow_id}/edit` applies a prompt as a validated patch, generates a new
  version, reruns QA, and activates the version only when it passes.
- `GET /designs/{workflow_id}/versions` exposes version history, active flag, artifacts, QA score,
  generation mode, and diff summary.
- `POST /designs/{workflow_id}/versions/{version_id}/rollback` changes the active version without
  deleting history.
- `GET /assets/inventory` exposes GLB readiness and fallback state for every manifest.
- `POST /document-packs` ingests a ZIP as raw `application/zip` bytes and stores index/extraction
  JSON, not the original archive.
- `GET /document-packs/{pack_id}/documents`, `/extractions`, `/consolidated-spec`, `/conflicts`,
  and `/missing-fields` expose document intelligence panels for the future studio.
- `GET /document-packs/{pack_id}/provenance` exposes evidence by field.
- `GET /document-packs/{pack_id}/qa` exposes document-pack QA checks and score.
- `GET /document-packs/capabilities` exposes local OCR/PDF/CAD/coordinate/Groq document-pack
  capability status.
- `GET /document-packs/{pack_id}/processing` exposes per-document extraction status, tools, and
  warnings.
- `GET /document-packs/{pack_id}/trace` and `/events` expose document-pack orchestration timeline
  data for an agent-studio panel.
- `GET /document-packs/{pack_id}/memory-summary` exposes a compact no-large-file summary for
  future memory/RAG panels.
- `POST /document-packs/{pack_id}/corrections` applies a manual correction, rebuilds the
  consolidated spec, and stores `user_correction` provenance.
- `POST /document-packs/{pack_id}/generate-design` maps a provenance-backed `ProjectDesignSpec`
  to `RequirementSpec` and launches the design workflow without prompt text reparsing.
- Confirmed document-pack GPS antenna and power-cabinet evidence is preserved into
  `SceneSpec.visual_elements` and manifest-backed `SceneSpec.accessory_assets`; confirmed uniform
  mechanical tilt is preserved into `RequirementSpec.mechanical_tilt_deg`; unsupported extracted
  fields remain visible as mapper warnings and `mapping_loss_report`.

## Asset Data Exposed

Workflow status includes:

- `asset_import_summary`
- `asset_imports`
- `artifacts.metadata` pointing to `scene_metadata.json`

Each asset import record reports:

- `asset_id`
- `asset_file`
- `asset_source`
- `asset_metadata`
- `object_role`
- `asset_file_exists`
- `asset_import_success`
- `asset_dimensions_checked`
- `import_mode`
- `effective_generation_mode`
- `warnings`

The frontend should render `cc_by`, `internal_cleaned`, `internal_test_minimal`, and
`procedural_fallback` as visible limitations, not as vendor-grade imported assets. `cc_by`
entries must expose attribution.

## Available With Fallback

- Groq `openai/gpt-oss-120b` extraction/editing can fall back to deterministic logic, and fallback
  state is visible.
- Blender can fall back to explicit non-GLB artifacts when missing or failing.
- Missing asset files can fall back to controlled procedural geometry only when the manifest allows
  it.

## Known Limitations

- Document-pack intelligence is operational but still bounded: PDF text/table, selected OCR, DXF,
  Groq bounded extraction when configured, corrections, provenance, QA, processing reports, trace,
  events, direct generation, and memory writeback are implemented. Docling layout and DWG conversion
  are not default runtime paths.
- Asset library is `partial_import_ready`: nine GLBs are present, including one CC Attribution
  tower and internal cleaned/minimal telecom assets. Monopole, rooftop mast, and small-cell tower
  vendor GLBs are still missing.
- GPS and power-cabinet accessories are imported as GLB placements when explicitly requested and
  their files exist. Mounting bracket and cable-tray manifests are inventory-ready but not yet
  automatically placed as standalone requested accessories.
- Preview inspection is structural/image-stat based, not semantic design judging.
- The API is synchronous for edit application. A separate preview-only edit workflow can be added
  later if the UI needs apply/reject before generation.
- Events are file-backed and local-first; they are suitable for one local frontend session, not a
  distributed multi-user stream.

## Future

- Add frontend viewer routes that serve artifacts by version without exposing raw filesystem paths.
- Add patch preview/apply endpoints if the UX needs non-committed edit previews.
- Add vendor-grade asset replacement, exact pivot/mount-point validation, and stricter
  imported-GLB dimension QA.
- Add asynchronous document-pack ingestion events if OCR/CAD processing becomes long-running.
