# PROJECT_SOURCE_OF_TRUTH.md

Document unique de vérité du projet.  
Toute autre documentation doit être alignée avec ce fichier.

---

## What this project is

Un studio local, mono-utilisateur, qui transforme un cahier des charges télécom (texte, PDF, ZIP, DXF) en un modèle 3D technique contrôlé (`GLB`) via :

1. Extraction structurée des exigences (`RequirementSpec`).
2. Intelligence documentaire optionnelle (`ProjectDesignSpec`) pour les packs ZIP.
3. Planification contrôlée d'une scène 3D (`SceneSpec`).
4. Génération headless par Blender.
5. QA structurale et géométrique.
6. Versioning, rollback, et rapports.

Le cœur est le pipeline backend Python/FastAPI. Le frontend est un client React qui doit être reconstruit.

## What this project is not

- Ce n'est pas un outil SaaS multi-utilisateur.
- Ce n'est pas un générateur d'images "waaw".
- Ce n'est pas un système qui écrit du code Blender libre par LLM.
- Ce n'est pas un dashboard de logs techniques.
- Ce n'est pas un produit avec des assets vendor-grade complets aujourd'hui.
- Ce n'est pas un moteur de simulation RF avancée.

## Current backend truth

- **FastAPI** expose les endpoints de design, document pack, assets, RAG, mémoire.
- **LangGraph** orchestre extraction, RAG, assets, validation, planification, Blender, QA, mémoire.
- **Extraction** : Groq structuré quand une clé est configurée ; fallback déterministe par regex sinon.
- **Document pack** : ZIP indexing, classification par extension/mots-clés, extraction PDF/OCR/CAD, consolidation, conflits, corrections, QA.
- **Blender** : génère vraiment des GLB/PNG quand Blender est installé et trouvé.
- **QA** : validation Pydantic, règles métier, quality gates, inspection GLB, géométrie métadonnées, preview PNG.
- **Mémoire** : SQLite local + Qdrant optionnel.
- **RAG** : Qdrant local avec embedding déterministe par défaut ; FastEmbed optionnel.

## Current frontend truth

- Un frontend React/Vite existe sous `apps/frontend`.
- **Il est refusé** : layout dashboard 4 zones, pas chat-first, viewer non dominant, pas de vrai SSE.
- Le frontend actuel ne sera pas patché. Il sera supprimé/reconstruit.
- Seuls `api/types.ts` et `api/client.ts` peuvent être conservés comme base.

## Current 3D truth

- `SceneSpec` est la source de vérité de génération.
- Blender génère un `design.glb`, `preview.png`, et `scene_metadata.json`.
- Sans Blender, le backend produit des artefacts fallback (GLB texte, PNG procédural) qui **ne doivent pas être considérés comme des designs valides**.
- La QA actuelle valide parfois ces fallback ; c'est une faille connue.

## Current document intelligence truth

- Le document pack fonctionne pour des ZIP contenant PDF texte, images scannées (OCR limité), DXF.
- DWG nécessite un convertisseur local (`dwgread`) ; souvent non disponible.
- Docling est installable mais non utilisé par défaut.
- L'extraction est pattern-based ; elle ne comprend pas sémantiquement les plans complexes.
- Les conflits entre documents bloquent la génération jusqu'à correction manuelle.

## Current asset truth

- 12 manifests existent.
- Tous les manifests ont des fichiers GLB locaux.
- Un seul asset externe (CC-BY) : `TOWER_LATTICE_30M`.
- Les autres sont des assets internes générés/projet.
- La bibliothèque n'est **pas vendor-grade**.

## Current limitations

- Embedding RAG par défaut = hash déterministe, pas sémantique.
- Mémoire = matching exact, pas de recall sémantique.
- Les "agents" sont principalement des fonctions déterministes ou des wrappers LLM.
- Le SSE backend fait du polling ; le frontend ne l'utilise même pas.
- Le document pack est synchrone, limité à 80 Mo, chargé en mémoire.
- La QA ne valide pas la géométrie exacte des meshes (transforms, matériaux).
- L'extraction déterministe est fragile pour des cahiers des charges complexes.

## Rejected approaches

- Dashboard dev à 4 panneaux fixes.
- Patcher le frontend actuel.
- Présenter les fallback Blender comme des succès.
- Utiliser des embeddings déterministes comme RAG de production.
- Laisser les codes techniques comme interface utilisateur principale.

## Next correct sequence

1. Nettoyer la documentation et établir cette source de vérité.
2. Corriger le backend : empêcher les fallback d'être validés comme succès.
3. Renforcer l'extraction (LLM structuré, validation) pour les vrais cahiers des charges.
4. Remplacer l'embedding déterministe par un vrai modèle d'embedding.
5. Reconstruire le frontend chat-first / 3D-first.
