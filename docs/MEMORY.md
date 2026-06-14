# Memory

La mémoire est locale et mono-utilisateur.

## Stockage

- SQLite sous `data/sqlite`.
- Qdrant optionnel pour certains points runtime quand RAG est configuré.
- Ces répertoires sont des artefacts runtime ignorés par Git.

## Ce qui fonctionne

- Writeback de résumés de workflow.
- Writeback de résumés document-pack compacts.
- Statistiques mémoire.
- Recall basé sur champs structurés et contexte limité.

## Limites

- Recall encore peu sémantique.
- Pas de mémoire conversationnelle produit.
- Pas de politique avancée de purge, scoring ou déduplication.
- La mémoire ne doit jamais remplacer les validations SceneSpec/QA.

## Règle frontend

Le futur frontend peut afficher une synthèse mémoire, mais ne doit pas exposer SQLite/Qdrant ou
des payloads bruts comme UI principale.
