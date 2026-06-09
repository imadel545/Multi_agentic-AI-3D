# QA Strategy

Current checks:

- Contract validation with Pydantic.
- Requirement business rules.
- SceneSpec structural and geometry checks.
- Artifact presence through local workflow output generation.
- Generation QA for GLB, preview, metadata, sector count, and generation fallback warnings.
- GLB structural inspection through `core/qa/glb_inspector.py`.
- GLB geometry validation through `core/qa/glb_geometry_validator.py`.
- Preview PNG inspection through `core/qa/preview_inspector.py`.
- Centralized pre-Blender quality gate for requirements, rules, asset compatibility, SceneSpec
  validity, repair attempts, and critical upstream errors.
- Centralized post-Blender quality gate for generation mode, artifact presence, artifact size,
  GLB structure, expected objects, preview dimensions, QA score, and error-severity QA warnings.
- Repair QA for antenna-height repair, azimuth normalization, sector-count repair, and
  non-repairable scene failure before Blender.
- Asset fallback QA for compatible tower/antenna selection and explicit fallback failure.
- Edit/revision QA: prompt edits create a patch, diff, version artifact directory, and full QA rerun
  before the version becomes active.
- Non-fake visual asset checks: GPS antenna and power cabinet are disabled by default, appear only
  when requested/patched/confirmed by document evidence, and require manifest-backed accessory
  placements for SceneSpec validation.
- Asset import QA: generation metadata must include import records, valid import modes, import
  success evidence for `imported_glb`, visible warnings for procedural fallback, and no
  `missing_file` record without allowed fallback.
- Document-pack QA: provenance on critical fields, no blocking missing values, resolved conflicts,
  average confidence, useful documents, numeric plausibility, visible OCR/PDF/CAD limits, explicit
  coordinate conversion status, HBA/tower consistency, and sector/azimuth consistency.
- Golden scene fixture for `golden_5g_lattice_30m_3sector`.
- Pytest coverage for parsing, registry selection, validation, API flow, RAG, Groq fallback,
  LangGraph orchestration, Blender fallback, edit/version artifacts, API errors, and golden scene
  consistency.

Next checks:

- Visual semantic inspection of generated scenes.
- Exact GLB transform/material inspection beyond object metadata.
- OCR layout bounding boxes, table row semantics, and CAD geometry semantics beyond extracted text
  and layer provenance.

## Quality Gates

Implemented:

- `pre_blender_gate` blocks `generate_blender` when critical preconditions fail.
- `post_blender_gate` blocks completion when generated artifacts or QA score fail.
- `post_blender_gate` includes `glb_structure_valid`, `expected_objects_present`,
  `minimum_node_count_valid`, `real_blender_glb_parse_required`,
  `geometry_validation_valid`, and `preview_resolution_valid`.
- Reports are written to `quality_gates.json`, `status.json`, and `workflow_trace.json`.
- For edit versions, quality gates and all QA reports are written under the version artifact
  directory and the root workflow status points to the active version.
- Pytest covers direct gate behavior and the route that prevents Blender execution.

Fallback:

- Blender fallback artifacts still go through QA and the post-Blender gate.
- The gate reports warning codes but does not hide fallback modes.
- When a fallback artifact is not a valid GLB, inspection mode is `metadata_fallback`.

Future:

- Add visual semantic inspection of rendered previews.
- Add GLB parser checks for transforms, bounding boxes, and material assignment.
- Tighten vendor GLB dimension/material validation once real vendor assets are available.

Known limitations:

- Gates validate contracts and artifacts, not visual aesthetics.
- Real Blender model size threshold is a local minimum byte-size guard.
- `metadata_fallback` validates expected procedural object metadata, not GLB binary structure.
- GPS/power-cabinet presence is checked by GLB inspection and geometry validation when requested.
- Document-pack QA validates selected OCR and DXF extraction when the local adapters are available,
  but it does not yet validate OCR layout bounding boxes or CAD geometry dimensions.

## Structural 3D QA

Implemented:

- `GLBInspector` parses GLB/GLTF JSON and extracts node, mesh, material, and object names.
- The inspector verifies expected tower, antenna, radio/RRU, cable, beam, azimuth-arrow, GPS, and
  power-cabinet objects from the SceneSpec.
- Empty, missing, or malformed GLB files fail structural QA unless explicit metadata fallback is
  available.
- `PreviewInspector` parses PNG headers and verifies width/height against SceneSpec preview
  resolution, luminance, contrast, and non-dark pixel ratio.
- `glb_inspection.json` and `preview_inspection.json` are written for completed generation runs.
- `geometry_validation.json` is written for completed generation runs.
- `qa_report.json` includes asset import metadata checks, so a missing non-fallback asset fails
  generation QA instead of silently passing.

## Geometry 3D QA

Implemented:

- `GLBGeometryValidator` verifies:
  - tower presence
  - antenna count
  - beam count
  - RRU count
  - cable count
  - GPS antenna count
  - power cabinet count
  - azimuth-arrow count
  - sector object presence
  - object names/metadata match the SceneSpec assets
  - tower height within `0.5m`
  - tower characteristics metadata matches the SceneSpec
  - antenna heights within `0.5m`
  - azimuth metadata within `5deg`
  - mechanical tilt metadata
  - bounding box reasonableness
- Geometry QA is included in `validation_report.json`, `quality_gates.json`,
  `workflow_trace.json`, API status, and `geometry_validation.json`.
- Edit-generated versions include their own `geometry_validation.json` and do not reuse the
  previous version's QA reports.

Fallback:

- If parsed GLB bounding-box data is unavailable, the validator uses file/object counts and
  metadata as a conservative proxy and emits `BOUNDING_BOX_GEOMETRY_NOT_PARSED`.

Fallback:

- `metadata_fallback` is used only when GLB parsing fails and `scene_metadata.json` contains
  procedural object names.
- The fallback is visible in API status, workflow trace, QA report, and quality gate details.

Future:

- Validate GLB node transforms and rough object placement.
- Validate object dimensions against asset manifests.
- Validate imported GLB bounding boxes directly against `dimensions_m`.

Known limitations:

- GLB parsing currently inspects JSON structure only.
- Preview inspection validates PNG dimensions and basic visibility metrics, not full aesthetic or
  semantic visual correctness.
- Current imported GLBs are internal minimal assets, not vendor-grade assets.

## Golden Scenes

Completed:

- `golden_5g_lattice_30m_3sector`
- `golden_4g_rooftop_2sector`
- `golden_small_cell_pole`
- `golden_microwave_dish_site`

Each fixture contains:

- `input_requirements.txt`
- `expected_requirement_spec.json`
- `expected_scene_spec.json`
- `expected_validation.json`
- `expected_glb_structure.json`
