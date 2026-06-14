# QA Strategy

QA doit dire ce qu'elle vérifie vraiment. Ne pas utiliser "advanced geometry" pour les
checks actuels.

## Niveaux actuels

- Contract QA: validation Pydantic des contrats.
- Requirement QA: règles métier sur `RequirementSpec`.
- Scene QA: validation `SceneSpec`, compatibilité assets, règles tower/RF.
- Quality gates: pre-Blender et post-Blender.
- Generation QA: cohérence metadata, artefacts, mode génération, warnings fallback.
- GLB structural QA: `glb_parse_structural`.
- Geometry QA: `object_name_based_geometry`.
- Height/azimuth QA: `metadata_based_height_azimuth`.
- Preview QA: `preview_luminance_only`.
- Document-pack QA: preuves, conflits, champs bloquants, plausibilité, OCR/CAD limits.

## Ce qui est réel

- GLB/GLTF JSON parse vérifie nodes, meshes, materials et noms d'objets.
- Geometry validator vérifie présence/counts, hauteurs et azimuts via metadata/proxies.
- Preview inspector vérifie PNG, résolution, luminance, contraste, ratio non sombre.
- Asset import QA vérifie `asset_imports`, modes, fichiers manquants et fallbacks visibles.
- Fallback Blender est refusé par défaut via policy qualité.

## Ce qui n'est pas encore réel

- Pas de validation exacte des transforms node par node.
- Pas de validation mesh/material vendor-grade.
- Pas de jugement visuel sémantique de la preview.
- Pas de validation CAD géométrique complète.

## Fallbacks

- Blender absent/erreur produit des artefacts fallback explicites, non valides comme résultat
  produit par défaut.
- Asset GLB manquant peut produire `procedural_fallback` si le manifest l'autorise.
- Tout fallback doit remonter dans `status.json`, Product API, rapports et futur frontend.

## Tests attendus

- Un workflow lattice avec GLB réel reste vert.
- Un workflow sélectionnant une tour sans GLB expose fallback/degraded.
- Les bundles viewer ne contiennent aucun chemin filesystem.
- Les QA reports nomment les modes proxy correctement.
