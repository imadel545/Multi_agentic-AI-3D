# Asset Registry

Le registre est manifest-first. Blender ne sélectionne que des assets décrits dans
`assets/manifests`.

## Vérité actuelle

- 12 manifests.
- 9 fichiers GLB locaux présents.
- 3 fichiers GLB manquants:
  - `TOWER_MONOPOLE_30M`
  - `TOWER_ROOFTOP_12M`
  - `TOWER_SMALL_CELL_10M`
- `/assets/inventory` doit retourner `status = partial_import_ready`.
- Les entrées manquantes ont `effective_generation_mode = procedural_fallback` quand le manifest
  l'autorise.

## Sources

- `cc_by`: attribution requise, non vendor-grade.
- `internal_cleaned`: importable mais interne, non vendor-grade.
- `internal_test_minimal`: asset minimal de validation pipeline, non vendor-grade.

## Règles

- Ne pas présenter un fallback procédural comme un asset réel.
- Ne pas sélectionner un asset absent sans warning utilisateur.
- Garder `entries`, `missing_files`, `real_glb_asset_count` et `missing_file_count` stables
  pour le frontend.
- Remplacer les tours manquantes par des GLB réels avant validation produit.
