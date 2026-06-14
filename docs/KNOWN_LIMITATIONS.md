# Known Limitations

Limitations actives à garder visibles dans l'API, les rapports et le futur frontend.

## Bloquants avant frontend avancé

- Product API encore à surveiller: elle doit refléter les vrais warnings, assets et events.
- Aucun frontend opérationnel; ancien dashboard refusé.
- `events/stream` est `polling_sse`, pas vrai streaming push.
- Timeline runtime dépend des events de nœuds + trace fichier; pas encore de reprise/replay robuste.
- Les 3 tours monopole/rooftop/small-cell n'ont pas de GLB local.

## Backend et agents

- Extraction déterministe fragile sur cahiers des charges complexes.
- Groq améliore l'extraction seulement si une clé réelle est configurée.
- Les agents sont majoritairement des fonctions déterministes ou wrappers LLM.
- Certains chemins contournent le graphe LangGraph compilé.
- Pas de cancellation/retry manager robuste; exécution async par thread local.

## RAG et mémoire

- NVIDIA `baai/bge-m3` est le provider principal.
- Fallback local `sentence-transformers`, puis hash en dernier recours; le hash n'est pas une
  qualité production.
- Après changement de provider/dimension, l'index Qdrant local doit être reconstruit avec
  `POST /rag/reindex`; sinon `/rag/search` retourne `409 RAG_INDEX_DIMENSION_MISMATCH`.
- Reranker local best-effort; passthrough si modèle indisponible.
- Mémoire encore limitée, avec recall sémantique incomplet.

## Documents

- Document-pack synchrone, 80 Mo max.
- OCR limité et dépendant de Tesseract + langues installées.
- Docling est import-only/non actif par défaut.
- DXF extrait texte/couches; DWG dépend d'un convertisseur local.

## 3D et QA

- Blender réel est requis pour un vrai GLB.
- Fallback Blender est refusé par défaut, mais des assets manquants peuvent encore devenir
  géométrie procédurale visible pendant une génération Blender réelle.
- QA actuelle:
  - `glb_parse_structural`
  - `object_name_based_geometry`
  - `metadata_based_height_azimuth`
  - `preview_luminance_only`
- Pas encore de validation exacte des transforms, matériaux ou dimensions mesh.
- Assets internes/CC-BY non vendor-grade.

## Ce qui peut attendre

- WebSocket.
- Queue/job manager.
- Refonte LangGraph complète.
- Mesh-level QA avancée.
- Docling production.
- Nouveau frontend.
