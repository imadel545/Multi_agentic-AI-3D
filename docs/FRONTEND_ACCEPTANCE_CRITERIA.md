# Frontend Acceptance Criteria

Critères obligatoires pour accepter le futur frontend.  
Si un critère échoue, le frontend n'est pas accepté.

---

## 1. Compréhension immédiate

- [ ] Un nouvel utilisateur comprend quoi faire en moins de 5 secondes.
- [ ] Le chat et la dropzone sont visibles sans scroll.

## 2. Viewer 3D dominant

- [ ] Le viewer 3D prend la majorité de l'espace horizontal et vertical.
- [ ] Le modèle est visible, grand et bien cadré au premier chargement.
- [ ] La tour est lisible, pas coupée ni noyée dans le sol.

## 3. Chat comme zone de commande

- [ ] Le chat est la zone de commande principale.
- [ ] L'utilisateur peut générer, éditer, uploader, et voir l'état depuis le chat.
- [ ] Les réponses de l'agent sont en langage utilisateur, pas en codes techniques.

## 4. Document dropzone

- [ ] Une dropzone claire accepte ZIP/PDF/PNG/DXF.
- [ ] L'état du document pack (conflits, champs manquants) est visible sans JSON brut.

## 5. Pas de panneaux vides

- [ ] Aucun grand panneau vide ou placeholder permanent.
- [ ] Les drawers ne s'ouvrent que quand ils ont du contenu utile.

## 6. Pas de JSON brut comme UI principale

- [ ] Les rapports QA, warnings, et assets sont traduits en cartes/summaries.
- [ ] Le JSON brut reste accessible dans un détail collapsé, jamais par défaut.

## 7. Warnings utilisateur

- [ ] Les warnings sont traduits en langage utilisateur avec impact et action suggérée.
- [ ] Les modes fallback (Blender, asset, LLM) sont explicitement visibles.

## 8. Timeline cachée

- [ ] La timeline complète des events est dans un drawer, pas affichée par défaut.
- [ ] Seule l'opération active et son état courant sont visibles dans le chat.

## 9. Temps réel

- [ ] La progression d'une opération active est visible en temps réel (SSE ou polling visible).
- [ ] L'utilisateur voit clairement quand une génération est en cours.

## 10. Fonctions testées

- [ ] Generate design from prompt.
- [ ] Upload document pack.
- [ ] Generate from document pack.
- [ ] Edit design by prompt.
- [ ] Version rollback.
- [ ] Download artifacts.

## 11. Qualité technique

- [ ] `npm run typecheck` passe.
- [ ] `npm run test` passe.
- [ ] `npm run build` passe.
- [ ] Console navigateur sans erreurs sur les flows principaux.

## 12. Preuve visuelle

- [ ] Screenshot final du studio avec un design réel `real_blender` chargé.
- [ ] Preuve que le GLB est visible et grand.

## Rejet automatique

Le frontend est rejeté si :

- le layout ressemble à un dashboard dev ;
- le viewer 3D n'occupe pas la majorité de l'écran ;
- des codes techniques sont affichés comme UI principale ;
- un grand panneau vide est présent par défaut ;
- les tests/build échouent.
