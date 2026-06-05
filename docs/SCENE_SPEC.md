# SceneSpec Contract

`SceneSpec` is the generation source of truth. User prompts, LLM outputs, and RAG
results are only inputs to the controlled planner.

Required properties:

- `schema_version`
- `scene_id`
- `units = meters`
- `network_type`
- `tower`
- `sectors`
- `visual_elements`
- `preview`
- `export`

Core validation rules:

- Antenna install height must not exceed tower height.
- Tower characteristics are typed and attached to `tower.characteristics`.
- Each sector has a valid antenna asset.
- Azimuths are in `[0, 360)`.
- Units are meters.
- Radio assets are present when RRU generation is requested by the current MVP flow.
- Cables are optional and valid when all sectors consistently disable them.

Geometry QA derives expected antennas, RRUs, cables, beams, azimuth arrows, heights, and azimuth
metadata from the SceneSpec. Tower metadata also carries structure, leg count, base/top width,
foundation, platforms, ladder, lightning rod, aviation light, and material.

See `core/contracts/scene.py` for the executable schema.
