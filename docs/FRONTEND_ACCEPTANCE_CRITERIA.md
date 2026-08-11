# Frontend Acceptance Criteria

Critères obligatoires pour accepter le futur frontend.  
Si un critère échoue, le frontend n'est pas accepté.

Dernière synchronisation ciblée: 2026-08-11. La baseline visuelle réelle est validée; les
cases non cochées exigent encore une preuve fonctionnelle enregistrée et
empêchent de déclarer la Gate finale complète.

Le smoke Product API du 2026-07-24 couvre génération Groq/Blender, édition,
version, rollback, upload ZIP, blocage/correction de fondation et génération
depuis document-pack. Les cases de mutation restent ouvertes tant que ces mêmes
actions ne sont pas toutes rejouées depuis les contrôles du navigateur. Le
smoke navigateur du 2026-07-28 prouve l'upload direct, la revue des champs avec
provenance et la restauration du même `pack_id` après rechargement. Les données
du pack sont relues depuis le backend; seul un pointeur local versionné est
conservé par l'interface.

Le smoke de clôture du 2026-07-29 a aussi restauré
`wf_a6660b81b929` sur le contrat API courant, vérifié le modèle réel en
desktop/mobile et la preview backend explicite sous Chrome headless sans
WebGL. Il ne ferme pas les cases de mutations navigateur encore ouvertes.

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
- [x] L'état du document pack (conflits, champs manquants) est visible sans JSON brut.

## 5. Pas de panneaux vides

- [x] Aucun grand panneau vide ou placeholder permanent.
- [x] Les drawers ne s'ouvrent que quand ils ont du contenu utile.

## 6. Pas de JSON brut comme UI principale

- [x] Les rapports QA, warnings, et assets sont traduits en cartes/summaries.
- [x] Aucun JSON brut n'est rendu dans la surface produit.

## 7. Warnings utilisateur

- [x] Les warnings sont traduits en langage utilisateur avec impact et action suggérée.
- [x] Les modes fallback (Blender, asset, LLM) sont explicitement visibles.
- [x] Une sortie GeometryProgram réparée est distinguée d'une sortie JSON
  strictement décodée.

## 8. Timeline cachée

- [x] La timeline complète des events est dans un drawer, pas affichée par défaut.
- [ ] Seule l'opération active et son état courant sont visibles dans le chat.

## 9. Temps réel

- [x] La progression d'une opération active est visible en temps réel par SSE,
  avec fallback polling prévu par le contrat.
- [x] L'utilisateur voit clairement quand une génération est en cours.

## 10. Fonctions testées

- [x] Generate design from prompt.
- [x] Upload document pack.
- [ ] Generate from document pack.
- [ ] Edit design by prompt.
- [ ] Version rollback.
- [ ] Download artifacts.
- [ ] Comprendre et confirmer un composant hors catalogue avant génération.
- [x] Afficher modèle, mode, hash, enveloppe et ajustements GeometryProgram après
  génération.
- [ ] Modifier un composant généré et constater la nouvelle version.
- [ ] Expliquer un échec du spécialiste géométrique avant tout lancement Blender.

## 11. Qualité technique

- [x] `npm run typecheck` passe le 2026-07-31.
- [x] `npm run test -- --run` passe avec 125 tests le 2026-07-31.
- [x] `npm run build` passe le 2026-07-31; tous les chunks JavaScript restent
  sous 371 kB non compressés.
- [x] Console navigateur sans erreurs sur le smoke de restauration et d'inspection.
- [x] Le 2026-08-11, `npm run test -- --run` passe avec 170 tests; typecheck et
  build passent aussi sur le current tree.
- [x] Le smoke layout current-tree en lecture seule charge le GLB certifié à
  1440 x 1000 et 1047 x 2748 sans scroll desktop concurrent; ce contrôle ne
  remplace pas le replay navigateur des mutations ni un smoke de conversion CAD.

## 12. Preuve visuelle

- [x] Screenshot final du studio avec un design réel `real_blender` chargé.
- [x] Preuve que le GLB est visible et grand.
- [ ] Smoke visuel du parcours GeometryProgram initial + révision. Le backend
  réel `wf_ead2456914b2` et `v2e0a4faf` a produit `real_blender`, QA 1.0,
  certificat, GLB et preview, mais cette preuve backend ne remplace pas le smoke
  navigateur.

## Rejet automatique

Le frontend est rejeté si :

- le layout ressemble à un dashboard dev ;
- le viewer 3D n'occupe pas la majorité de l'écran ;
- des codes techniques sont affichés comme UI principale ;
- un grand panneau vide est présent par défaut ;
- les tests/build échouent.
