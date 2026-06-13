# Backend Capability Matrix

Matrice des capacités backend avec statut précis, preuve, limitation et signification frontend.

Légende des status :

- `IMPLEMENTED` : opérationnel dans le code et les tests.
- `IMPLEMENTED_LIMITED` : opérationnel mais avec des limites significatives.
- `IMPORT_ONLY` : dépendance installable/importable mais non active par défaut.
- `UNSUPPORTED_WITHOUT_TOOL` : nécessite un outil externe non inclus.
- `ADVISORY` : fournit du contexte mais ne décide pas.
- `FUTURE` : pas implémenté.
- `REJECTED` : explicitement hors scope.

---

| Capability | Status | Evidence | Limitation | Frontend Meaning |
|---|---|---|---|---|
| requirements_text generation | IMPLEMENTED_LIMITED | `POST /designs`, `core/services/requirement_parser.py` | Parser déterministe basé sur regex ; Groq structuré optionnel. | L'utilisateur peut saisir un brief, mais des cahiers des charges complexes peuvent être mal extraits. |
| document pack upload | IMPLEMENTED_LIMITED | `POST /document-packs`, `core/document_pack/service.py` | 80 Mo max, chargement synchrone en mémoire. | Upload ZIP possible pour des packs modestes ; pas de streaming. |
| PDF text extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | PyMuPDF optionnel ; pas de layout structuré. | Texte PDF extrait si outil installé ; tableaux mal normalisés. |
| PDF table extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | pdfplumber optionnel ; extraction texte brute. | Tables converties en texte `\|` ; pas de sémantique d'équipement. |
| OCR selected extraction | IMPLEMENTED_LIMITED | `core/document_pack/text_extractor.py` | 8 pages max par document, Tesseract optionnel. | PDF/images scannées partiellement lues ; limites visibles. |
| Docling | IMPORT_ONLY | `core/document_pack/text_extractor.py` | Installable via `[document-layout]` mais non utilisé par défaut. | Non fiable en production sans config modèle/cache. |
| DXF parsing | IMPLEMENTED_LIMITED | `core/document_pack/cad.py` | `ezdxf` optionnel ; extraction de texte/couches uniquement. | DXF lu si outil installé ; géométrie CAD non exploitée. |
| DWG parsing/conversion | UNSUPPORTED_WITHOUT_TOOL | `core/document_pack/cad.py` | Nécessite `dwgread`/LibreDWG ou ODA/FreeCAD. | DWG reste inventory-only sans convertisseur local. |
| pyproj coordinates | IMPLEMENTED_LIMITED | `core/document_pack/coordinates.py` | `pyproj` optionnel ; conversion CRS limitée. | Coordonnées converties si outil + CRS connus. |
| Groq bounded extraction | IMPLEMENTED_LIMITED | `core/document_pack/groq_extractor.py` | Nécessite clé Groq ; 12 chunks max, 2500 car/chunk. | Champs extraits par LLM uniquement avec preuve documentaire. |
| ProjectDesignSpec | IMPLEMENTED | `core/contracts/document_pack.py`, `core/document_pack/extractor.py` | Mapping vers RequirementSpec, pas synthèse directe SceneSpec. | Spec consolidée visible avec preuves, conflits, champs manquants. |
| RequirementSpec | IMPLEMENTED | `core/contracts/requirements.py` | Construit par parser déterministe ou Groq. | Contrat d'entrée pour la génération 3D. |
| SceneSpec | IMPLEMENTED | `core/contracts/scene.py` | Source de vérité de la génération. | Description complète de la scène 3D. |
| Asset inventory | IMPLEMENTED | `GET /assets/inventory`, `core/services/asset_inventory.py` | Assets non vendor-grade. | État d'import GLB, fallback, licences, warnings. |
| GLB import | IMPLEMENTED | `apps/blender_worker/generate_scene.py` | Dépend de l'existence et de la qualité des GLB. | GLB importés quand présents ; fallback procédural sinon. |
| Blender generation | IMPLEMENTED | `core/services/blender_runner.py` | Nécessite Blender installé localement. | Génération réelle si Blender trouvé ; fallback si absent. |
| Geometry QA | IMPLEMENTED_LIMITED | `core/qa/glb_geometry_validator.py` | Vérifie counts, présence, hauteurs, azimuts ; pas de transforms exacts. | QA structurelle mais pas de validation mesh fine. |
| Preview QA | IMPLEMENTED_LIMITED | `core/qa/preview_inspector.py` | Stats image (résolution, luminance) ; pas de jugement visuel sémantique. | Preview PNG vérifié mais pas esthétiquement. |
| Document QA | IMPLEMENTED | `core/document_pack/service.py` | Vérifie preuves, conflits, champs bloquants, plausibilité. | Pack prêt ou bloqué avec raisons. |
| Edit prompt | IMPLEMENTED_LIMITED | `POST /designs/{id}/edit` | Apply-and-generate, pas de preview non commitée. | Édition par prompt crée une nouvelle version. |
| Versioning | IMPLEMENTED | `core/services/scene_versioning.py` | Local filesystem. | Historique des versions avec active flag. |
| Rollback | IMPLEMENTED | `POST /designs/{id}/versions/{vid}/rollback` | Change le pointeur actif. | Retour à une version antérieure. |
| Events/SSE | IMPLEMENTED_LIMITED | `GET /designs/{id}/events`, `/events/stream` | SSE backend fait du polling ; frontend utilise aussi du polling. | Pas de vrai temps réel. |
| Memory writeback | IMPLEMENTED_LIMITED | `core/memory/service.py` | SQLite + Qdrant optionnel ; recall par matching exact. | Apprentissage limité des cas passés. |
| RAG | IMPLEMENTED_LIMITED | `core/rag/service.py` | Embedding déterministe par défaut ; FastEmbed optionnel. | Recherche lexicale/hash, pas sémantique. |
| Artifact downloads | IMPLEMENTED | `GET /designs/{id}/artifacts/{name}` | Whitelist de noms d'artifacts. | Téléchargement des GLB, PNG, rapports. |
| Product-oriented API | IMPLEMENTED | `GET /studio/summary`, `GET /designs/{id}/user-summary`, `/current-operation`, `/user-issues`, `/viewer-bundle`, `/timeline-summary` | Couche de présentation au-dessus du statut technique ; ne résout pas les problèmes de fond (fallback Blender, etc.). | Le frontend peut afficher un résumé utilisateur sans parser du JSON technique. |

---

## Synthèse

Le backend a une surface riche et fonctionnelle en local, mais plusieurs capabilities clés restent limitées ou dépendantes d'outils/configurations optionnels. Avant une reconstruction frontend, il faut corriger la validation des fallback Blender et améliorer l'extraction pour les vrais cahiers des charges.
