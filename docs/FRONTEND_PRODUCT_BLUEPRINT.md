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
│  Context drawers (QA / Documents / Timeline / Versions)     │
└─────────────────────────────────────────────────────────────┘
```

## Règles UX

- **Chat-first** : la conversation est la zone de commande principale.
- **3D-first** : le viewer occupe la majorité de l'écran.
- **Simple** : l'utilisateur comprend quoi faire en moins de 5 secondes.
- **Drawers contextuels** : les détails (QA, documents, versions) sont dans des drawers, jamais en panneaux fixes vides.
- **No dashboard** : pas de 4 zones fixes, pas de grids resizable comme IDE.
- **No dev logs** : pas de JSON brut, pas de codes techniques comme UI principale.
- **Fallbacks visibles** : Blender manquant, asset fallback, LLM fallback sont expliqués en langage utilisateur.
- **Temps réel sur opération active** : progression visible uniquement pendant une opération.

## Fonctions obligatoires

1. Générer un design depuis un prompt.
2. Uploader un document pack (ZIP avec PDF/DXF/images).
3. Générer depuis un document pack corrigé.
4. Éditer un design par prompt.
5. Voir l'historique des versions et rollback.
6. Télécharger les artefacts (GLB, PNG, rapports).
7. Voir le modèle 3D grand et bien cadré.
8. Voir les warnings/explications en langage utilisateur.

## Non-inclus

- Dashboard multi-panneaux fixes.
- Raw event timeline comme UI principale.
- JSON technique visible par défaut.
- Mobile-first (desktop d'abord).

## Statut

- Le kernel dashboard précédent reste rejeté. La baseline active utilise un
  compositeur unifié, un viewer dominant et des drawers métier à la demande.
- Les endpoints produit backend sont prêts pour une construction frontend:
  `push_sse`, current operation, timeline lisible, viewer bundle, user issues,
  edit/version/rollback, document-pack capabilities.
- Le smoke visuel/runtime du 2026-07-24 est passé sur un GLB Blender réel avec
  drawers agentique, QA, alertes, livrables et bibliothèque branchés au backend.
  Le smoke Product API couvre aussi génération Groq/Blender, édition,
  version/rollback et document-pack avec correction bloquante. Le replay de
  toutes ces mutations depuis les contrôles navigateur reste nécessaire avant
  l'acceptation frontend finale.
