# Blender Worker

`core/services/blender_runner.py` lance Blender headless avec
`apps/blender_worker/generate_scene.py`. Le worker consomme uniquement `SceneSpec`.

## Résolution Blender

Ordre de recherche:

- `BLENDER_BINARY`
- `TELECOM_STUDIO_BLENDER_BINARY`
- `blender` dans le `PATH`
- `/Applications/Blender.app/Contents/MacOS/Blender`
- chemins macOS versionnés connus

Sur ce poste, Blender est disponible sous `/Applications/Blender.app/Contents/MacOS/Blender`.

## Artefacts

- `design.glb`
- `preview.png`
- `scene_metadata.json`
- `glb_inspection.json`
- `geometry_validation.json`
- `preview_inspection.json`
- `quality_gates.json`
- `workflow_trace.json`

## Generation modes

- `real_blender`: Blender réel a produit les artefacts requis.
- `fallback_no_blender`, `fallback_blender_error`, `fallback_blender_timeout`,
  `fallback_blender_missing_artifacts`: fallback explicite.

`TELECOM_STUDIO_ALLOW_BLENDER_FALLBACK=0` est le défaut qualité. Les fallbacks Blender ne doivent
pas être présentés comme design valide.

## Asset imports

Le worker importe les GLB manifest-backed si le fichier existe et si l'import réussit.
Sinon, il peut créer une géométrie procédurale contrôlée seulement si
`import_fallback_allowed = true`.

Chaque record `asset_imports` doit exposer:

- `asset_id`
- `asset_file`
- `asset_source`
- `asset_file_exists`
- `asset_import_success`
- `import_mode`
- `effective_generation_mode`
- `warnings`

## Limites

- Les tours monopole, rooftop et small-cell n'ont pas encore de GLB.
- Les assets actuels ne sont pas vendor-grade.
- La QA lit structure/metadata/proxies, pas mesh transforms exacts.
