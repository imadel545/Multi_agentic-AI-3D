# Known Limitations

Liste honnête des limitations actuelles.  
Ces limitations sont connues et doivent rester visibles pour les utilisateurs et les agents.

---

## Backend

- **Fallback Blender non bloquant** : sans Blender, le backend génère des artefacts fallback (GLB texte, PNG procédural) et la QA peut les valider. C'est une faille critique.
- **Extraction déterministe fragile** : `core/services/requirement_parser.py` repose sur des regex. Les cahiers des charges complexes, les synonymes, et les tableaux sont mal traités.
- **RAG non sémantique** : l'embedding par défaut est un hash déterministe. FastEmbed est optionnel.
- **Mémoire par matching exact** : le recall mémoire utilise `network_type`, `tower_type`, `sector_count`, pas de similarité sémantique.
- **Agents non agentiques** : la plupart des "agents" sont des fonctions déterministes ou des wrappers LLM sans réflexion multi-étapes.
- **LangGraph contourné** : `run_requirements` et `run_scene_revision` exécutent la logique en impératif hors graphe.
- **Document pack synchrone** : upload 80 Mo max, tout chargé en mémoire.
- **DWG non supporté nativement** : nécessite `dwgread` ou un convertisseur externe.
- **Docling non actif par défaut** : installable mais non utilisé par défaut à cause du poids/cache.
- **OCR limité** : 8 pages max par document.
- **QA géométrique limitée** : vérifie counts, présence, hauteurs, azimuts ; pas de transforms/mesh exacts.

## Frontend

- **Aucun frontend opérationnel** : l'ancien frontend sous `apps/frontend` a été supprimé.
- **Pas de vrai SSE** : le backend fait du polling ; le futur frontend devra gérer cette limitation.
- L'API produit backend est prête, mais le frontend chat-first / 3D-first n'est pas encore reconstruit.

## Assets

- **Non vendor-grade** : la plupart des assets sont internes/CC-BY.
- **Monopole/rooftop/small-cell** : générés en interne, pas des modèles vendor.

## 3D

- **Visual realism limitée** : dépend de la bibliothèque d'assets internes.
- **Preview Blender** : cadrage basique, pas de jugement esthétique automatique.

## Correctifs prioritaires

1. Empêcher les fallback d'être validés comme succès.
2. Renforcer l'extraction par LLM structuré pour les vrais cahiers des charges.
3. Passer à un vrai embedding sémantique.
4. Reconstruire le frontend chat-first / 3D-first.
