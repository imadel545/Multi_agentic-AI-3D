# E2E Telecom Generation Proof

This proof uses the existing `/designs` contract. It does not add `/projects`,
`/runs`, or a new state model.

## Scenario

```text
Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m.
Azimuts : 0°, 120°, 240°.
Ajouter RRU, câbles, boîte alimentation, dalle béton, labels,
couleurs professionnelles et export GLB.
```

## Proof Command

```bash
.venv/bin/python -m pytest tests/e2e/test_telecom_generation_proof.py -q
```

## What The Test Proves

- `POST /designs` accepts the input and returns a `workflow_id`.
- Requirement extraction captures 5G, lattice tower, 30 m height, 3 sectors,
  24 m antenna height, azimuths 0/120/240, RRU, cables, labels, power cabinet,
  and concrete foundation.
- LangGraph node events include extraction, RAG, asset selection, scene
  planning, Blender generation, and QA.
- `scene_spec.json` is available and is the scene-plan artifact for the UI.
- Viewer bundle exposes GLB, preview, metadata, SceneSpec, QA, generation and
  geometry validation URLs.
- `/events/stream` replays to a terminal workflow event.
- Public responses do not expose local filesystem paths.

## Blender Truth

If Blender is available, the workflow must complete with `generation_mode =
real_blender`. If Blender is absent, fallback must be explicit and user issues
must explain that the result is degraded/non-product-grade.

## Current Limitations

- `SceneSpec` is the source of truth; `scene plan` is a frontend label.
- Mesh QA is `mesh_level_basic`, not RF/collision/structural engineering.
- RAG is advisory; retrieval quality remains limited.
