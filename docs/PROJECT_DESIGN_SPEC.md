# ProjectDesignSpec

## Implemented

`ProjectDesignSpec` is the provenance-backed bridge between document intelligence and the existing
3D design pipeline.

It stores:

- site, coordinate, tower, foundation, cabling, grounding, and compound fields;
- sector-level radio design values;
- inventory placeholders for antennas, RRU, and cabinets;
- document references with classification and processing status;
- missing fields, conflicts, assumptions, and confidence summary;
- provenance map;
- processing capabilities and warnings;
- source mode, Groq provider/fallback state, and rejected Groq fields.

`ProjectDesignSpecMapper` maps to `RequirementSpec` only when blocking missing fields and conflicts
are absent.

The current mapper carries confirmed GPS antenna and power-cabinet requests into
`RequirementSpec` and then `SceneSpec.visual_elements`. It also carries confirmed uniform
mechanical tilt into `RequirementSpec.mechanical_tilt_deg`. Those values are not enabled by RAG text
matches or by decorative defaults.

## Available With Fallback

- User corrections become authoritative `user_correction` evidence during consolidation.
- Coordinate conversion status is explicit even when conversion cannot run.
- Pack-to-design generation uses `RequirementSpec` directly via
  `WorkflowService.create_design_from_requirements()` and `DesignOrchestrator.run_requirements()`.
  The generated text is only a readable summary, not the parsed source of truth.
- Groq document-pack fields are accepted only with valid source evidence; rejected fields remain
  visible in the spec and processing report.
- Mapper warnings expose confirmed document fields that are not yet represented in SceneSpec, such
  as site name, coordinates, grounding/adduction, and tower color/RAL.

## Known Limitations

- `ProjectDesignSpec` is still mapped to `RequirementSpec` before SceneSpec planning; direct
  SceneSpec synthesis from `ProjectDesignSpec` is future work.
- Antenna/cabinet inventories are still minimal and do not yet preserve vendor-grade equipment rows.
- GPS antenna and power cabinet can be enabled from confirmed document evidence and are carried as
  manifest-backed SceneSpec accessory placements. When their GLB files exist, the Blender worker
  imports them and reports `imported_glb`.
- Per-sector mechanical tilt is not represented by `RequirementSpec`; non-uniform sector tilt
  remains a future SceneSpec-direct mapping case.
- `mapping_loss_report` is returned with pack-to-design mapping so the frontend can distinguish
  `mapped`, `not_modeled`, `missing`, `conflict`, `fallback`, and `lost_field`.

## Future

- Make SceneSpec synthesis consume richer `ProjectDesignSpec` inventory sections directly.
- Preserve table equipment rows as typed inventory objects.
- Use document-pack memory recall to suggest recurring corrections and missing-field defaults.
