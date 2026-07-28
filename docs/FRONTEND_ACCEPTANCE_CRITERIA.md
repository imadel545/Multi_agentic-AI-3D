# Frontend Acceptance Criteria

Critères obligatoires pour accepter le futur frontend.  
Si un critère échoue, le frontend n'est pas accepté.

Dernier audit ciblé: 2026-07-24. La baseline visuelle réelle est validée; les
cases non cochées exigent encore une preuve fonctionnelle enregistrée et
empêchent de déclarer la Gate finale complète.

Le smoke Product API du 2026-07-24 couvre génération Groq/Blender, édition,
version, rollback, upload ZIP, blocage/correction de fondation et génération
depuis document-pack. Les cases de mutation restent ouvertes tant que ces mêmes
actions ne sont pas toutes rejouées depuis les contrôles du navigateur.

---

## 1. Compréhension immédiate

- [x] Un nouvel utilisateur comprend quoi faire en moins de 5 secondes.
- [ ] Le chat et la dropzone sont visibles sans scroll.

## 2. Viewer 3D dominant

- [x] Le viewer 3D prend la majorité de l'espace horizontal et vertical.
- [x] Le modèle est visible, grand et bien cadré au premier chargement.
- [x] La tour est lisible, pas coupée ni noyée dans le sol.

## 3. Chat comme zone de commande

- [x] Le chat est la zone de commande principale.
- [ ] L'utilisateur peut générer, éditer, uploader, et voir l'état depuis le chat.
- [x] Les réponses de l'agent sont en langage utilisateur, pas en codes techniques.

## 4. Document dropzone

- [x] Une dropzone claire accepte plusieurs fichiers directs ou un ZIP, affiche
  la file d'attente, permet le retrait individuel et applique les limites
  exposées par le backend.
- [ ] L'état du document pack (conflits, champs manquants) est visible sans JSON brut.

## 5. Pas de panneaux vides

- [x] Aucun grand panneau vide ou placeholder permanent.
- [x] Les drawers ne s'ouvrent que quand ils ont du contenu utile.

## 6. Pas de JSON brut comme UI principale

- [x] Les rapports QA, warnings, et assets sont traduits en cartes/summaries.
- [x] Aucun JSON brut n'est rendu dans la surface produit.

## 7. Warnings utilisateur

- [x] Les warnings sont traduits en langage utilisateur avec impact et action suggérée.
- [x] Les modes fallback (Blender, asset, LLM) sont explicitement visibles.

## 8. Timeline cachée

- [x] La timeline complète des events est dans un drawer, pas affichée par défaut.
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

- [x] `npm run typecheck` passe (via `npm run build`).
- [x] `npm run test` passe (93 tests).
- [x] `npm run build` passe.
- [x] Console navigateur sans erreurs sur le smoke de restauration et d'inspection.

## 12. Preuve visuelle

- [x] Screenshot final du studio avec un design réel `real_blender` chargé.
- [x] Preuve que le GLB est visible et grand.

## Rejet automatique

Le frontend est rejeté si :

- le layout ressemble à un dashboard dev ;
- le viewer 3D n'occupe pas la majorité de l'écran ;
- des codes techniques sont affichés comme UI principale ;
- un grand panneau vide est présent par défaut ;
- les tests/build échouent.
