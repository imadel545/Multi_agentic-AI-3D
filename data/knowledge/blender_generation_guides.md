# Blender Generation Guides Seed

The Blender worker must consume `SceneSpec` only. It may import validated GLB assets and
create controlled procedural geometry for:

- sector beams;
- azimuth arrows;
- cables;
- height markers;
- labels.

The worker must not execute arbitrary LLM-generated Python code.
