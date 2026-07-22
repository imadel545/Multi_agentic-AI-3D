# Bibliothèque CAD telecom locale

Cette zone reçoit la copie locale de `MAJ des Blocs` sans l'ajouter à Git.

- `raw/` conserve les fichiers source sans modification.
- `index/` contient le catalogue reproductible et les empreintes SHA-256.
- `converted/` est réservé aux conversions CAD contrôlées.
- un fichier brut reste `quarantined_unverified` tant que sa licence, ses unités,
  sa géométrie et sa conversion n'ont pas été vérifiées;
- la présence sous un dossier nommé `3D` est une indication de provenance, pas
  une preuve qu'un maillage Blender exploitable existe;
- aucun DWG brut n'est ajouté automatiquement aux manifests de production.

La bibliothèque source ne contient pas de fichier de licence global détecté.
Elle est donc utilisable localement pour inventaire et qualification, mais ne
doit pas être redistribuée ou annoncée comme vendor-grade sans revue de droits.
