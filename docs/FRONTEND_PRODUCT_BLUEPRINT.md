# Frontend Product Blueprint

Vision du frontend cible. `apps/frontend` est une rework connectée au backend
réel, encore non acceptée comme produit. Ce blueprint reste son contrat UX.

---

## Principe directeur

Le frontend est un **studio de design 3D agentique**, pas un dashboard de développeur.

## Layout cible

```text
┌─────────────────────────────────────────────────────────────┐
│  Top bar minimal (backend status, workflow, QA, mode)       │
├──────────────────────┬──────────────────────────────────────┤
│                      │                                      │
│  AI Chat Workspace   │      Grand Viewer 3D (majoritaire)   │
│  (zone de commande)  │                                      │
│                      │                                      │
│  - prompt generate   │                                      │
│  - drop documents    │                                      │
│  - edit prompts      │                                      │
│  - version/rollback  │                                      │
│  - current operation │                                      │
│                      │                                      │
├──────────────────────┴──────────────────────────────────────┤
│  Context drawers (QA / Composition / Assets / Versions)     │
└─────────────────────────────────────────────────────────────┘
```

## Règles UX

- **Chat-first** : la conversation est la zone de commande principale.
- **3D-first** : le viewer occupe la majorité de l'écran.
- **Simple** : l'utilisateur comprend quoi faire en moins de 5 secondes.
- **Drawers contextuels** : les détails utiles du résultat (QA, composition,
  assets, versions) sont dans des drawers, jamais en panneaux fixes vides. Les
  extractions documentaires et diagnostics d'ingestion restent hors de la
  surface produit.
- **No dashboard** : pas de 4 zones fixes, pas de grids resizable comme IDE.
- **No dev logs** : pas de JSON brut, pas de codes techniques comme UI principale.
- **Fallbacks visibles** : Blender manquant, asset fallback, LLM fallback sont expliqués en langage utilisateur.
- **Temps réel sur opération active** : progression visible uniquement pendant une opération.
- **Géométrie explicable** : les composants hors catalogue compris, leur
  enveloppe demandée, le modèle auteur, le mode structuré/réparé et les
  ajustements déterministes restent visibles sans exposer le JSON brut.

## Fonctions obligatoires

1. Générer un design depuis un prompt.
2. Joindre directement plusieurs PDF/DXF/images/tableaux, ou un ZIP, depuis le
   composeur de conversation et pouvoir les retirer avec `×`.
3. Combiner des pièces jointes avec un prompt; l'import seul ne génère rien.
4. Éditer un design par prompt.
5. Voir l'historique des versions et rollback.
6. Télécharger les artefacts (GLB, PNG, rapports).
7. Voir le modèle 3D grand et bien cadré.
8. Voir les warnings/explications en langage utilisateur.
9. Confirmer les composants hors catalogue compris avant génération.
10. Voir la provenance d'un GeometryProgram et régénérer un composant ciblé
    dans une nouvelle version.

## Non-inclus

- Dashboard multi-panneaux fixes.
- Raw event timeline comme UI principale.
- JSON technique visible par défaut.
- Mobile-first (desktop d'abord).

## Statut

- Le kernel dashboard précédent reste rejeté. La baseline active utilise un
  compositeur de commande unifié, un viewer dominant et des drawers métier à la
  demande. La cible reste une vraie conversation; la Gate chat complète n'est
  pas encore déclarée.
- Les endpoints produit backend sont prêts pour une construction frontend:
  `push_sse`, current operation, timeline lisible, viewer bundle, user issues,
  edit/version/rollback, document-pack capabilities.
- Le smoke visuel/runtime du 2026-07-24 est passé sur un GLB Blender réel avec
  drawers agentique, QA, alertes, livrables et bibliothèque branchés au backend.
  Le smoke Product API couvre aussi génération Groq/Blender, édition,
  version/rollback et contexte document-pack. Le replay de
  toutes ces mutations depuis les contrôles navigateur reste nécessaire avant
  l'acceptation frontend finale.
- Le smoke du 2026-07-28 prouve le composeur multi-fichiers réel: sélection
  multiple, file d'attente, retrait individuel, limites backend et envoi
  multipart. L'analyse complète depuis le navigateur reste une mutation à
  rejouer avec un pack métier dédié avant la Gate finale. La surface active ne
  rend plus les extractions, contrôles ou formulaires de correction du pack.
- Le chemin backend réel `wf_ead2456914b2` puis révision `v2e0a4faf` prouve la
  génération et la modification d'un composant GeometryProgram avec
  `real_blender`, QA 1.0, certificat, GLB et preview. Le frontend rend désormais
  l'intent, l'enveloppe et la provenance. Le smoke navigateur a confirmé ce
  résumé et la distinction des sorties réparées; la mutation complète depuis
  le contrôle navigateur reste ouverte.
- Le smoke du commit de convergence `19791be` le 2026-08-11
  (`wf_0843599873e7`, version
  `v8995acb1`) prouve depuis le frontend réel une création chat-first, la
  progression SSE, le chargement du GLB Blender réel et les drawers RAG,
  Bibliothèque, Intelligence et QA, sans warning/error console. La preuve
  post-export mesure 3/3 liaisons mécaniques et observe un support mesh; la
  route RF exportée reste explicitement non évaluée. Ce smoke ne rejoue pas
  l'édition, le rollback, l'upload ou la génération avec contexte documentaire.
