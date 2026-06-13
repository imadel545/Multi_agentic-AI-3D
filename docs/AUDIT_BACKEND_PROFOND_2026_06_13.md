# Audit Profond — Backend Agentic AI 3D Telecom Studio

**Date** : 2026-06-13  
**Périmètre** : `apps/api`, `core`, `apps/blender_worker`, `tests`, `apps/frontend` (contexte)  
**Méthode** : Lecture statique du code, exécution des tests, analyse architecturale, revue SOLID, inspection des pipelines LLM/RAG/3D.  
**Verdict global** : Le backend est un **MVP techniquement cohérent sur le papier mais incapable de produire une valeur réelle de manière fiable**. Il est conçu pour “réussir” en fallback : sans Blender, il génère des artefacts invalides mais les valide avec un `qa_score` de 1.0. Les “agents” sont des fonctions déterministes, le RAG est un hash lexical, la mémoire est un matching exact, et l’extraction documentaire est un empilement de regex. Cela explique parfaitement la frustration exprimée : “rien ne fonctionne vraiment”.

---

## 1. Vue d’ensemble et architecture

### 1.1 Décomposition en couches

Le découpage en modules est logique en apparence :

- `apps/api/telecom_studio_api/` : FastAPI + modèles Pydantic + service workflow.
- `core/orchestration/` : LangGraph.
- `core/agents/` : agents nominaux.
- `core/services/` : registry, versioning, events, Blender runner, etc.
- `core/contracts/` : modèles Pydantic.
- `core/document_pack/` : ingestion ZIP/OCR/CAD.

**Problème fondamental** : la séparation des responsabilités est faible. Plusieurs fichiers encombrent des rôles multiples.

| Fichier | Taille | Responsabilités | Problème |
|---------|--------|-----------------|----------|
| `apps/api/telecom_studio_api/main.py` | 501 lignes | Instancie tous les services globalement, définit les routes, middleware, lifespan. | Pas d’injection de dépendances. Services singletons mutables. |
| `apps/api/telecom_studio_api/workflow.py` | 1069 lignes | Orchestration, persistance fichier, versioning, events, archivage ZIP, reporting. | Violation flagrante du SRP. |
| `core/orchestration/langgraph_orchestrator.py` | 1670 lignes | Graphe LangGraph + deux exécutions impératives qui dupliquent la logique du graphe. | Le checkpointing est inutile pour les chemins impératifs. |
| `core/services/blender_runner.py` | 482 lignes | Lancement sous-processus, fallback PNG/GLB, metadata. | Mélange exécution, fallback et génération d’artefacts bidons. |

### 1.2 SOLID

- **SRP** : violé par `WorkflowService`, `DesignOrchestrator`, `BlenderRunner`, `DocumentPackService`.
- **OCP** : les agents ne sont pas extensibles. Aucune abstraction de provider LLM utilisable partout.
- **LSP** : `RequirementProvider` Protocol est mentionné dans la doc mais jamais utilisé pour brancher plusieurs implémentations.
- **DIP** : `main.py` dépend directement des implémentations concrètes (`AssetRegistry`, `RagService`, `MemoryService`, etc.).

### 1.3 State LangGraph

Le state est un `TypedDict(total=False)` (`langgraph_orchestrator.py:38-84`) :

```python
class WorkflowState(TypedDict, total=False):
    workflow_id: str
    requirements: RequirementSpec
    ...
```

- Aucune garantie à la compilation que les clés existent.
- Les nodes accèdent fréquemment à `state["requirements"]` sans vérification préalable (`KeyError` possible).
- Les fonctions de routing partent du principe que certaines clés sont présentes.

---

## 2. API FastAPI

### 2.1 Endpoints synchrones et gestion des tâches longues

- `create_design`, `parse_requirements`, etc. sont des fonctions **synchrones** qui retournent immédiatement `{"workflow_id": ..., "status": "pending"}`.
- Le travail est lancé dans un `threading.Thread` sans file d’attente, sans pool, sans supervision.
- Aucune validation que le thread a démarré correctement.
- Pas de gestion de la charge : une attaque par 100 requêtes de création lance 100 threads qui exécutent Blender.

### 2.2 Streaming / SSE

Le backend expose `GET /designs/{workflow_id}/events/stream`, mais :

```python
def event_generator():
    seen = 0
    idle_ticks = 0
    while True:
        events = workflow_service.get_events(workflow_id)
        for event in events[seen:]:
            yield f"data: {json.dumps(event)}\n\n"
            ...
        time.sleep(1)
```

- C’est du **polling actif toutes les secondes**, pas du vrai push SSE.
- Le frontend n’utilise même pas ce SSE : il utilise `useDesignEvents` avec un polling toutes les 2.5s.
- Résultat : aucune sensation de temps réel, pas de “streaming” malgré l’apparence.

### 2.3 Uploads

- `POST /document-packs` lit `request.body()` en mémoire.
- Limite codée en dur à 80 Mo (`MAX_PACK_SIZE_BYTES = 80 * 1024 * 1024`).
- Limite par membre à 15 Mo.
- Pas de streaming, pas de rate-limiting, pas d’authentification, pas de validation MIME.
- Impossible d’ingérer un vrai cahier des charges avec DWG, photos haute résolution, PDF volumineux.

### 2.4 CORS

```python
allow_methods=["*"]
allow_headers=["*"]
```

Trop permissif pour une API de production.

### 2.5 Gestion d’erreurs

- Handler global qui ne loggue **pas** l’exception :

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(status_code=500, content={"error": "Internal server error", ...})
```

- En production, les erreurs seraient silencieuses.
- Le lifespan est un simple `yield` sans startup check (Blender, Qdrant, SQLite).

---

## 3. Orchestration LangGraph

### 3.1 Le graphe est contourné

`_build_graph` construit un graphe correct avec routes conditionnelles, mais `run_requirements` (ligne 170) et `run_scene_revision` (ligne 260) **contournent le graphe** et exécutent la même séquence en impératif.

Conséquences :
- Le `checkpointer` SQLite passé à `graph.compile()` est inutile pour ces chemins.
- La logique de routing est dupliquée.
- Impossible de reprendre un workflow en cas de crash.

### 3.2 State mutable

```python
@staticmethod
def _apply_update(state: WorkflowState, update: dict) -> None:
    state.update(update)
```

Pas d’état immuable, pas de rollback partiel.

### 3.3 “Repair” illusoire

```python
def _scene_repair_handler(self, state: WorkflowState) -> dict:
    repair_events = [event.model_dump() for event in state["requirements"].repair_events if event.success]
    if repair_events and report.status == "passed" and not state.get("scene_repair_recorded"):
        ...
```

Le repair handler ne répare pas. Il vérifie si quelqu’un d’autre a déjà réparé (`repair_events` dans `requirements`). C’est une logique de contournement, pas de correction autonome.

### 3.4 Résilience

- `_retrieve_rag_context` catch `Exception` et continue silencieusement avec `rag_context: []`.
- `_generate_blender` n’a pas de retry au niveau du graphe (le retry est dans `BlenderRunner`).
- Pas de circuit breaker, pas de backoff exponentiel.

---

## 4. Les “agents” ne sont pas agentiques

### 4.1 Verdict global

Les agents sont des fonctions déterministes ou des wrappers LLM sans boucle réflexive, sans tool use, sans mémoire de travail.

### 4.2 `RequirementExtractor`

```python
def extract(...):
    if self.provider is None or not effective_enabled:
        return ExtractionResult(
            requirements=parse_requirements_text(...), provider="deterministic", fallback_used=True
        )
    try:
        requirements = self.provider.extract_requirements(...)
    except Exception as exc:
        requirements = parse_requirements_text(...)
```

- Router LLM/déterministe, pas un agent.
- Le parser déterministe est un empilement de regex fragiles (voir §5).

### 4.3 `ScenePlanner`

- Fonction pure qui place des secteurs à 120° par défaut et lit le RAG pour quelques hints.
- Aucune décision autonome, aucune négociation de contraintes.

### 4.4 `SceneEditAgent`

```python
def create_patch(...):
    if self.groq is not None:
        try:
            return self._llm_patch(scene, edit_prompt)
        except Exception:
            pass
    return self._fallback_patch(scene, edit_prompt)
```

- `except Exception: pass` ligne 22-23 : l’erreur LLM est totalement perdue, sans log.
- Le fallback `_fallback_patch` est une collection de regex extrêmement fragile.

### 4.5 `TowerEngineerAgent` / `RfEngineerAgent`

- Validateurs de règles simples.
- Pas d’agentivité, pas de capacité à proposer des corrections.

### 4.6 Prompting

- Les prompts sont des strings inline.
- Pas de registry, pas de versioning, pas d’A/B testing, pas d’évaluation LLM-as-a-judge.

---

## 5. Extraction des requirements : le point de rupture

### 5.1 Parser déterministe

`core/services/requirement_parser.py` est entièrement basé sur des regex et des inférences arbitraires.

Exemples de fragilités :

```python
network_type = _extract_network_type(text)
if network_type == "5G" and "5g" not in text and "4g" not in text and "mw" not in text:
    warnings.append(WarningItem(code="DEFAULT_NETWORK_USED", ...))
```

- Si le texte ne contient pas explicitement “5g”, “4g” ou “mw”, il infère quand même 5G.
- Un cahier des charges réel (PDF scanné, tableaux, abréviations) ne sera pas compris.

```python
tower_type = next(
    (normalized for token, normalized in TOWER_SYNONYMS.items() if token in text),
    "lattice_tower",
)
```

- Recherche de sous-chaînes. “Monopole” devient `monopole`, mais “pylône autoportant” ou “tour tubulaire” retombera sur `lattice_tower`.

```python
default_install_height = _default_install_height(tower_height_m)
install_height = _extract_install_height(text, default=default_install_height)
```

- `_extract_install_height` prend le **deuxième nombre** trouvé dans le texte. Si le cahier des charges mentionne d’abord la hauteur du pylône, puis une distance au sol, puis la hauteur d’antenne, le résultat sera faux.

### 5.2 Groq extraction

`core/llm/groq.py` utilise un JSON Schema strict, ce qui est bien. Mais :

- Le modèle par défaut est `openai/gpt-oss-120b` via Groq. Ce modèle n’est pas spécialisé telecom.
- Le prompt est court et ne fournit pas de few-shot sur des cahiers des charges complexes.
- La réparation après échec de validation retombe sur le parser déterministe.
- Aucune chaîne de pensée (CoT), aucune vérification structurelle multi-étapes.

---

## 6. Document Pack Intelligence

### 6.1 Ingestion

- Limite 80 Mo, tout chargé en mémoire (`BytesIO(state["content"])`).
- Pas de streaming, pas de traitement asynchrone.
- Pour un gros cahier des charges avec plusieurs PDF, images et DWG, c’est inacceptable.

### 6.2 Classification

`core/document_pack/classifier.py` utilise des règles par extension + mots-clés dans le nom de fichier.

- Très fragile : `plan_antennes.pdf` sans le mot “antenne” dans les 12 Ko sera classé `unknown`.
- Pas de ML/NLP, pas de compréhension sémantique.

### 6.3 Extraction texte / OCR

`core/document_pack/text_extractor.py` :

- PyMuPDF, pdfplumber, Docling, Tesseract, Apple Vision sont optionnels.
- Aucune extraction de layout structuré : les tableaux deviennent du texte brut avec ` | `.
- OCR limité à 8 pages par document (`MAX_OCR_PAGES_PER_DOCUMENT = 8`).
- Si les dépendances ne sont pas installées, le fichier est marqué `unsupported` ou `inventory_only`.

### 6.4 Extraction CAD

`core/document_pack/cad.py` :

- DXF via `ezdxf` (optionnel).
- DWG via conversion locale (`dwgread`, `ODAFileConverter`, `FreeCAD`). En pratique, ces outils ne sont probablement pas installés.
- L’extraction DXF se contente de lister les entités TEXT/MTEXT/INSERT. Pas de compréhension sémantique du dessin.

### 6.5 Consolidation et conflits

`core/document_pack/extractor.py` :

- Si une seule valeur unique → `confirmed`.
- Sinon → `conflict` avec `resolution: "needs_user_review"`.
- **Pas de résolution automatique par LLM**, pas de pondération par fiabilité du document, pas de gestion des unités.
- Les champs manquants critiques sont définis en dur (`tower_type`, `tower_height_m`, `sector_count`, `azimuths_deg`, `hba_m`).

### 6.6 Groq document extraction

`core/document_pack/groq_extractor.py` :

- Envoi de chunks limités (12 chunks, 2500 caractères, 20000 total).
- Mais `groq_bounded_extraction_enabled=False` par défaut.

---

## 7. Pipeline de génération 3D

### 7.1 SceneSpec

`core/contracts/scene.py` est le point fort du backend : modèle Pydantic bien structuré avec validateurs.

### 7.2 Blender runner : le coeur du problème

`core/services/blender_runner.py` :

```python
blender_path = self._resolve_blender_binary()
if blender_path is None:
    self._write_fallback_artifacts(output_dir, scene, mode="fallback_no_blender")
    return self._result(started, output_dir, "fallback", "fallback_no_blender", False, ...)
```

- Si Blender n’est pas installé → fallback immédiat.
- Le fallback génère un `design.glb` qui est un fichier texte :

```python
(output_dir / "design.glb").write_bytes(
    b"glTF fallback artifact generated from validated SceneSpec: " + scene.scene_id.encode()
)
```

- Et un `preview.png` procédural via `_minimal_png`.
- **Ces artefacts ne sont pas des modèles 3D réels**, mais le QA les valide parce qu’il lit les métadonnées.

### 7.3 Worker Blender

`apps/blender_worker/generate_scene.py` est assez complet : pylône treillis procédural, antennes panneaux, RRU, câbles, faisceaux, flèches azimut, etc.

**Mais** : il n’est exécuté que si Blender est installé et trouvé. Par défaut, il ne l’est pas.

### 7.4 QA génération

`core/qa/generation_qa.py` :

- Vérifie existence/fichiers, métadonnées, modes d’import.
- Beaucoup de checks valident que les **métadonnées** du fallback sont cohérentes avec le SceneSpec.
- `metadata_no_missing_asset_without_fallback` échoue si un asset est `missing_file`, mais réussit si `procedural_fallback` — ce qui est le cas par défaut sans Blender.
- **Aucune validation géométrique réelle** : pas de collision, pas de volume, pas de sanity check visuel par LLM vision.

### 7.5 GLB / Preview inspection

`core/qa/glb_inspector.py` :

- Parse le GLB (vrai ou fallback). Si le fallback texte n’est pas un GLB valide, il passe en `metadata_fallback` et utilise `procedural_objects_created` comme liste de noms.
- Cela fait croire à la QA que le modèle contient les objets attendus.

`core/qa/preview_inspector.py` :

- Analyse le PNG (signature, résolution, luminance). Le PNG fallback généré procéduralement passe ces checks.

---

## 8. Gestion des assets

### 8.1 Registry

`core/services/asset_registry.py` charge les manifests JSON du dossier `assets/manifests`.

- `select_tower` choisit le plus petit asset validé dont la hauteur est >= `min_height_m`. Cela peut choisir un asset inadapté.
- Le cache par hash de contenu du dossier est correct.

### 8.2 Import vs fallback

- Le worker Blender tente d’abord l’import GLB, puis fallback procédural.
- Le runner Python fallback génère directement des records `procedural_fallback`.
- **Le résultat par défaut est du fallback**, donc des modèles basiques (boîtes/cylindres).

---

## 9. Mémoire & RAG

### 9.1 SQLite

`core/memory/service.py` :

- Tables pour workflow_memory, design_memory, error_memory, document_pack_memory.
- WAL activé.
- `_ensure_column` pour gérer les migrations à la volée : anti-pattern qui masque un manque de migrations propres.

### 9.2 RAG

`core/rag/service.py` utilise Qdrant local ou distant.

**Mais l’embedding provider par défaut est un hash** :

```python
class HashEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
```

Ce n’est **pas un embedding sémantique**. C’est un hash de tokens. La recherche RAG est donc purement lexicale/déterministe déguisée. `fastembed` est une optional dependency rarement installée par défaut.

### 9.3 Mémoire de workflow

`MemoryService.recall` :

```python
WHERE network_type = ? AND tower_type = ? AND sector_count = ? AND qa_score >= 0.95
```

- Matching exact, pas de similarité sémantique.
- L’agent n’apprend donc pas vraiment des cas similaires.

---

## 10. Tests

### 10.1 Couverture et résultats

- 160 tests passent en ~2 minutes.
- 36 fichiers de test couvrent API, orchestration, document pack, assets, QA.

### 10.2 Qualité

**Beaucoup de tests valident le fallback/no-blender**, pas la vraie génération.

Exemple : `test_blender_runner_uses_explicit_fallback_when_binary_missing` vérifie que le fallback génère des artefacts. Cela valide le contournement, pas la feature.

Les tests avec vrai Blender sont sous `@pytest.mark.skipif`. `test_api_workflow.py` vérifie `qa_score == 1.0` même en fallback. Cela légitime un système qui produit des artefacts non valides.

### 10.3 CI

`.github/workflows/ci.yml` :

- Exécute ruff + pytest sur macOS-14 sans Blender.
- Aucun job n’installe Blender pour valider de vrais GLB.
- Aucun test de charge, aucun test d’intégration document pack réel.

---

## 11. Frontend (contexte)

Même si l’audit se concentre sur le backend, les problèmes frontend confirment l’architecture défaillante.

### 11.1 Pas de vrai streaming

`apps/frontend/src/api/hooks.ts` définit `openEventStream` avec `EventSource`, mais **il n’est jamais utilisé**. Le `StudioShell` utilise :

```typescript
const events = useDesignEvents(activeWorkflowId);
```

Qui fait du polling toutes les 2.5s :

```typescript
refetchInterval: 2500
```

Le backend expose aussi un SSE qui fait lui-même du polling toutes les secondes. Résultat : double polling, aucun vrai streaming temps réel.

### 11.2 Affichage d’artefacts invalides

`ThreeViewer.tsx` affiche le GLB via `useGLTF`. Quand le backend retourne un fallback texte (pas un GLB valide), le viewer tente de le charger et affiche un état d’erreur. L’expérience utilisateur est dégradée.

### 11.3 UI dense mais peu interactive

- 4 zones (command center, viewer, inspector, dock) sont présentes.
- Mais les actions avancées (résolution de conflits document pack, visualisation de provenance, édition guidée par la QA) sont absentes ou très basiques.

---

## 12. Pourquoi “rien ne fonctionne vraiment”

### 12.1 Le système est conçu pour réussir en fallback

Sans Blender (cas par défaut), le pipeline génère :
- Un `design.glb` qui est un fichier texte.
- Un `preview.png` généré procéduralement.
- Des métadonnées qui disent “tous les objets sont présents”.

La QA valide ces artefacts parce qu’elle vérifie les métadonnées et non la géométrie. Résultat : `qa_score == 1.0`, `status == "completed"`, mais l’utilisateur reçoit un fichier inutilisable.

### 12.2 Aucune intelligence réelle dans l’extraction

- L’extraction de requirements est regex. Un cahier des charges réel (PDF scanné, tableaux, abréviations) ne sera pas compris.
- Le document pack est classifié par mots-clés. Les synonymes, layouts complexes, images techniques sont maltraités.

### 12.3 RAG et mémoire inopérants

- Le RAG par défaut utilise un hash déterministe, pas d’embedding sémantique.
- La mémoire fait du matching exact, donc elle ne “reconnaît” jamais vraiment un cas similaire.

### 12.4 Les “agents” sont des fonctions

- Aucun agent ne prend de décision autonome, n’utilise d’outils, ne réfléchit en plusieurs étapes.
- Les corrections sont hardcodées (`scene_repair.py`).

### 12.5 Assets rarement importés

- Sans Blender, le fallback est procédural.
- Avec Blender, l’import GLB dépend de la disponibilité des fichiers. Beaucoup de scénarios mènent à des primitives géométriques basiques.

---

## 13. Recommandations par priorité

### P0 — Bloquant / rupture utilisateur

1. **Rendre Blender obligatoire et échouer proprement s’il manque**  
   Le fallback actuel produit des artefacts bidons. Soit on livre un vrai modèle 3D, soit on retourne une erreur explicative.  
   *Fichiers* : `core/services/blender_runner.py`, `core/qa/generation_qa.py`.

2. **Remplacer l’extraction regex par un LLM structuré + validation, avec fallback transparent**  
   Le parser déterministe actuel est inadapté à des cahiers des charges réels. Utiliser un LLM avec JSON schema et validation Pydantic, et indiquer clairement quand un champ est inféré vs extrait.  
   *Fichiers* : `core/services/requirement_parser.py`, `core/llm/groq.py`.

3. **Corriger le `except Exception: pass` dans `SceneEditAgent.create_patch`**  
   Loguer l’erreur et retourner un statut explicite.  
   *Fichier* : `core/agents/scene_edit_agent.py:22-23`.

4. **Ne plus valider les artefacts fallback comme des succès**  
   Le post-blender gate doit échouer si `generation.mode != "real_blender"`.  
   *Fichier* : `core/validation/quality_gates.py`.

### P1 — Architecture et fiabilité

5. **Refactorer `WorkflowService` pour séparer orchestration, persistance, versioning et events**  
   Introduire des repositories pour le filesystem, un service d’événements, un service de versioning.  
   *Fichier* : `apps/api/telecom_studio_api/workflow.py`.

6. **Supprimer les exécutions impératives `run_requirements`/`run_scene_revision` hors graphe**  
   Tout faire passer par le graphe LangGraph compilé, avec checkpointer.  
   *Fichier* : `core/orchestration/langgraph_orchestrator.py`.

7. **Utiliser un vrai embedding provider par défaut**  
   `HashEmbeddingProvider` doit être remplacé par `FastEmbedProvider` (ou un appel API).  
   *Fichier* : `core/rag/embeddings.py`.

8. **Ajouter un vrai système de files d’attente pour les tâches longues**  
   Remplacer `threading.Thread` par Celery/RQ/arq. Cela résout scalabilité et fiabilité.  
   *Fichiers* : `apps/api/telecom_studio_api/workflow.py`, `apps/api/telecom_studio_api/main.py`.

9. **Rendre l’API async et le traitement document pack asynchrone**  
   Accepter les gros uploads, retourner un `job_id`, permettre le polling/SSE sur l’état du job.

### P2 — Qualité et observabilité

10. **Logging structuré et correlation ID**  
    Remplacer les silences par `structlog` ou `logging` avec JSON, request_id, workflow_id.  
    *Fichier* : `apps/api/telecom_studio_api/main.py`.

11. **Versionner et tester les prompts LLM**  
    Externaliser les prompts, les versionner, ajouter des tests LLM-as-a-judge.  
    *Fichiers* : `core/llm/groq.py`, `core/agents/scene_edit_agent.py`.

12. **Ajouter des tests d’intégration avec Blender obligatoires en CI**  
    Les tests actuels valident le fallback. Il faut un job CI qui installe Blender et valide de vrais GLB.  
    *Fichiers* : `.github/workflows/`, `tests/unit/test_blender_runner.py`.

13. **Valider la géométrie GLB réelle**  
    Vérifier que le GLB contient bien les meshes attendus, leurs dimensions, l’absence de NaN, les UVs, etc.  
    *Fichiers* : `core/qa/glb_geometry_validator.py`, `core/qa/glb_inspector.py`.

### P3 — Maturité produit

14. **Ajouter rate-limiting, authentification, validation MIME**  
    Sécuriser les uploads et les endpoints de génération.

15. **Migrations SQLite propres**  
    Remplacer `_ensure_column` par Alembic ou un système de migration versionné.  
    *Fichier* : `core/memory/service.py`.

16. **Améliorer la résolution des conflits document pack**  
    Utiliser un LLM pour résoudre automatiquement les conflits mineurs, avec explication de la décision.  
    *Fichier* : `core/document_pack/extractor.py`.

17. **Vrai streaming frontend/backend**  
    Utiliser le SSE existant (ou un WebSocket) et le connecter réellement au frontend. Éliminer le double polling.

---

## 14. Roadmap de transformation recommandée

### Phase 1 — Véracité (2-3 semaines)
- Supprimer les fallback bidons ou les rendre explicitement des échecs.
- Rendre Blender obligatoire.
- Corriger les exceptions silencieuses.
- Ajouter des tests d’intégration avec Blender.

### Phase 2 — Intelligence d’extraction (3-4 semaines)
- Refondre `requirement_parser.py` autour d’un LLM structuré avec validation Pydantic.
- Améliorer le document pack : classification ML, extraction de layout, OCR complet.
- Résolution automatique des conflits document pack.

### Phase 3 — Architecture scalable (3-4 semaines)
- Refactorer `WorkflowService` avec des repositories et une file de tâches.
- Supprimer les exécutions impératives hors graphe.
- Rendre l’API async et le traitement document pack asynchrone.

### Phase 4 — Qualité et expérience (2-3 semaines)
- Remplacer `HashEmbeddingProvider` par un vrai modèle d’embedding.
- Ajouter validation géométrique réelle des GLB.
- Logging structuré, observabilité, correlation ID.
- Vrai streaming SSE frontend.

### Phase 5 — Maturité production (continue)
- Rate-limiting, auth, migrations DB.
- Prompt registry, LLM-as-a-judge.
- Assets vendor-grade, catalogue extensible.

---

## 15. Conclusion

Le backend est un **démonstrateur technique bien intentionné mais qui n’est pas prêt pour un usage réel**. Sa principale faiblesse est d’avoir optimisé les métriques de succès (`qa_score`, statut `"completed"`) au détriment de la qualité réelle : sans Blender, il produit des artefacts invalides mais les valide. Les agents sont des wrappers, le RAG est un hash, la mémoire est un matching exact, et l’extraction documentaire est un empilement de regex.

**Pour que “ça fonctionne vraiment”**, il faut :
1. Obliger Blender et valider la géométrie.
2. Remplacer l’extraction déterministe par du LLM structuré.
3. Utiliser de vrais embeddings.
4. Refactorer l’orchestration et la persistance.
5. Ajouter des tests d’intégration réalistes.
6. Connecter le vrai streaming SSE au frontend.

Le potentiel existe : les contrats Pydantic sont solides, le worker Blender est compétent, et l’API a une surface riche. Mais il faut une refonte profonde pour passer d’une démo à un produit.
