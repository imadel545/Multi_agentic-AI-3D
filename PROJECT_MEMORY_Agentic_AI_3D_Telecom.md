# PROJECT MEMORY — Agentic AI 3D Telecom Design Studio

> Fichier de contexte, mémoire et guide d’exécution pour Codex Agent.  
> Ce document doit être lu avant toute modification du projet.  
> Objectif : développer une plateforme locale, robuste et professionnelle de génération 3D télécom/réseau par IA multi-agent, sans bricolage, sans génération floue, sans fusion avec image réelle.

---

## Current Backend Truth — 2026-06-08

Implemented now:

- Initial generation pipeline with Groq/deterministic extraction, RAG recall, SQLite memory,
  domain validation agents, SceneSpec planning, Blender generation, GLB/geometry/preview QA,
  quality gates, reports, and artifacts.
- Prompt edit pipeline with typed `ScenePatch`, patch validation, diff, version creation,
  full revision QA, per-version artifact directory, active version pointer, events, and rollback.
- API endpoints for status, events/SSE, versions, rollback, asset inventory, RAG, memory stats,
  downloads, and validation.

Available with fallback:

- Groq `openai/gpt-oss-120b` falls back visibly to deterministic extraction/patching.
- Blender absence/failure creates explicit fallback artifacts that still go through QA.
- Qdrant local deterministic embedding is available but is not production-grade semantic search.

Known limitations:

- Real vendor GLB files are not present; current asset library is manifest-only.
- Blender output is controlled procedural geometry until imported GLB assets are added.
- Frontend is not implemented in this repository state.
- Visual semantic QA and exact GLB transform/material validation remain future work.

---

## 0. Résumé exécutif

Le projet vise à créer un **Agentic AI 3D Telecom Design Studio** : une application locale capable de transformer un cahier des charges télécom/réseau en **modèle 3D technique vérifiable**, basé sur une bibliothèque d’assets 3D contrôlés et un moteur Blender automatisé.

Le système doit générer des designs 3D de :

- pylônes treillis ;
- monopoles ;
- mâts rooftop ;
- small-cell poles ;
- antennes 4G/5G ;
- antennes sectorielles ;
- massive MIMO ;
- antennes microwave dish ;
- radios/RRU ;
- armoires ;
- câbles ;
- supports/brackets ;
- faisceaux sectoriels ;
- flèches d’azimut ;
- labels techniques ;
- marqueurs de hauteur ;
- rapports de conformité.

Le système ne doit pas produire une simple image “waaw”. Il doit produire un **modèle 3D structuré, contrôlé, exportable, reproductible et validé**.

---

## 1. Périmètre strict du projet

### Inclus

Le projet doit couvrir :

1. Lecture d’un cahier des charges texte ou structuré.
2. Extraction des exigences techniques.
3. Normalisation des données réseau/3D.
4. Recherche RAG dans la mémoire technique locale.
5. Sélection d’assets 3D validés.
6. Génération d’un `SceneSpec` strict.
7. Validation métier et géométrique.
8. Exécution d’un worker Blender headless.
9. Export du modèle en `.glb/.gltf`.
10. Génération d’une preview 3D.
11. Génération d’un rapport de conformité.
12. Génération optionnelle de variantes.
13. Scoring et comparaison des variantes.
14. Téléchargement direct des artefacts.
15. Nettoyage automatique des sorties temporaires.

### Exclu explicitement pour cette version

Ne pas implémenter pour l’instant :

- fusion avec image réelle ;
- insertion du design dans une photo ;
- Google Maps / Google Earth ;
- géolocalisation terrain avancée ;
- réalité augmentée mobile ;
- simulation radio complète RF ;
- SaaS multi-utilisateur ;
- PostgreSQL ;
- Kubernetes ;
- microservices lourds inutiles ;
- génération libre de code Blender par LLM.

Le cœur du projet est uniquement :

```text
cahier des charges / données utilisateur
→ agents
→ RAG local
→ règles
→ SceneSpec
→ Blender
→ modèle 3D GLB
→ validation
→ rapport
```

---

## 2. Vision produit

L’utilisateur fournit par exemple :

```text
Créer un site 5G sur pylône treillis 30m.
Installer 3 secteurs à 24m.
Azimuts : 0°, 120°, 240°.
Ajouter une RRU sous chaque antenne.
Ajouter câbles, supports, faisceaux sectoriels et labels techniques.
Niveau de détail : élevé.
```

Le système doit produire :

```text
/design_outputs/{workflow_id}/design.glb
/design_outputs/{workflow_id}/preview.png
/design_outputs/{workflow_id}/scene_spec.json
/design_outputs/{workflow_id}/validation_report.json
/design_outputs/{workflow_id}/technical_report.md ou .pdf
```

Le système doit aussi expliquer :

- ce qu’il a compris ;
- quelles règles ont été appliquées ;
- quels assets ont été choisis ;
- quelles valeurs ont été inférées ;
- quelles incohérences ont été détectées ;
- quel est le score de conformité ;
- pourquoi une variante est recommandée.

---

## 3. Principes d’architecture obligatoires

### 3.1 Principe fondamental

Le LLM ne doit pas piloter directement Blender par code libre.

Architecture correcte :

```text
LLM / agent
→ RequirementSpec
→ RAG retrieval
→ Rule Engine
→ Asset Selection
→ SceneSpec JSON
→ SceneSpec Validator
→ Blender Worker contrôlé
→ QA
→ artefacts
```

Architecture interdite :

```text
Prompt utilisateur
→ LLM écrit du Python Blender libre
→ exécution directe
→ résultat non contrôlé
```

### 3.2 Source de vérité

La source de vérité de génération est le `SceneSpec`, pas le prompt utilisateur, pas une réponse libre du LLM.

### 3.3 Local-first

Le projet doit être pensé pour fonctionner localement :

- mono-utilisateur ;
- sans PostgreSQL ;
- sans cloud obligatoire ;
- avec stockage local temporaire ;
- avec Qdrant local ou Docker ;
- avec SQLite local ;
- avec Blender local/headless ;
- avec API Groq externe uniquement pour le raisonnement LLM.

### 3.4 Anti-bricolage

Codex doit éviter :

- créer des fichiers dupliqués sans inspecter l’existant ;
- mélanger prototype et architecture finale ;
- générer du code non testé ;
- hardcoder des chemins absolus ;
- faire dépendre la logique métier du prompt ;
- supprimer la validation ;
- stocker des résultats utilisateurs définitivement sans raison ;
- complexifier avec PostgreSQL/Kubernetes/Temporal si non nécessaire au lot courant.

---

## 4. Stack cible validée

### Backend local

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy ou SQLModel
- SQLite avec WAL
- Uvicorn
- pytest
- ruff
- mypy ou pyright si possible

### Orchestration agentique

- LangGraph
- état de workflow explicite
- checkpoints locaux possibles
- boucles de correction contrôlées
- human-in-the-loop optionnel pour ambiguïtés critiques

### LLM principal

- Groq API
- modèle principal : `openai/gpt-oss-120b`
- modèle fallback configurable
- model router obligatoire à moyen terme
- structured outputs JSON obligatoires pour les agents critiques

### RAG / mémoire sémantique

- Qdrant local ou Docker
- collections séparées :
  - `telecom_rules`
  - `asset_manifests`
  - `scene_templates`
  - `validation_cases`
  - `design_patterns`
  - `blender_generation_guides`
- embeddings :
  - démarrage : FastEmbed
  - avancé : BGE-M3 ou modèle embedding local équivalent
- retrieval hybride recommandé à moyen terme

### Base locale

- SQLite pour :
  - workflows ;
  - jobs Blender ;
  - metadata des artefacts ;
  - logs courts ;
  - états de génération ;
  - rapports de validation ;
  - registry technique local minimal.

### Stockage fichiers

- filesystem local :
  - assets 3D ;
  - manifests JSON ;
  - sorties temporaires ;
  - previews ;
  - rapports.
- TTL/cleanup obligatoire pour les sorties utilisateur.

### Moteur 3D

- Blender 4.5 LTS recommandé
- exécution headless :
  - `blender -b --python generate_scene.py -- scene_spec.json output_dir`
- Blender Python API
- export GLB/glTF
- preview PNG
- génération procédurale de faisceaux, câbles, labels, flèches et marqueurs.

### Frontend

- React ou Next.js
- Three.js ou React Three Fiber
- viewer GLB
- formulaire cahier des charges
- statut workflow
- téléchargement des artefacts
- affichage validation report

---

## 5. Architecture logique cible

```text
User Interface
  ↓
FastAPI Local Gateway
  ↓
LangGraph Orchestrator
  ↓
Requirement Understanding Agent
  ↓
Qdrant RAG Retrieval Agent
  ↓
Technical Normalization Agent
  ↓
Rule Engine Agent
  ↓
Asset Selection Agent
  ↓
Scene Planning Agent
  ↓
SceneSpec Validator
  ↓
SQLite Workflow State
  ↓
Blender Worker
  ↓
3D QA Agent
  ↓
Report Agent
  ↓
GLB / Preview / Reports / Direct Download
```

---

## 6. Agents à implémenter

### 6.1 Requirement Understanding Agent

Responsabilité :

- lire le cahier des charges ;
- extraire les paramètres techniques ;
- produire `RequirementSpec`.

Champs à extraire :

- `network_type`
- `site_type`
- `tower_type`
- `tower_height_m`
- `sector_count`
- `antenna_type`
- `antenna_install_height_m`
- `azimuths_deg`
- `mechanical_tilt_deg`
- `electrical_tilt_deg`
- `beamwidth_deg`
- `include_rru`
- `include_cables`
- `include_beams`
- `include_labels`
- `detail_level`

Sortie attendue : JSON validé par Pydantic.

---

### 6.2 RAG Retrieval Agent

Responsabilité :

- interroger Qdrant ;
- retrouver règles, templates, assets et cas similaires ;
- retourner des références contextualisées ;
- ne jamais remplacer le Rule Engine.

Sources à indexer :

- règles métier télécom ;
- manifests d’assets 3D ;
- templates SceneSpec ;
- exemples de designs validés ;
- guides Blender internes ;
- erreurs fréquentes ;
- décisions d’architecture.

---

### 6.3 Technical Normalization Agent

Responsabilité :

- convertir unités ;
- normaliser synonymes ;
- vérifier valeurs manquantes ;
- appliquer valeurs par défaut contrôlées ;
- marquer toute inférence.

Exemples :

```text
"pylône treillis" → "lattice_tower"
"3 secteurs classiques" → sector_count=3, azimuths=[0,120,240] si absent
"antenne panneau 5G" → "panel_5g"
```

---

### 6.4 Rule Engine Agent

Responsabilité :

Appliquer les règles métier avant génération.

Règles minimales :

1. `antenna_install_height_m <= tower_height_m`
2. `sector_count == len(azimuths_deg)`
3. chaque azimut doit être entre 0 et 360
4. chaque asset doit être compatible avec `network_type`
5. une RRU doit être attachée à une antenne si `include_rru=true`
6. un câble doit exister si `include_cables=true`
7. faisceau sectoriel aligné avec l’azimut
8. unités en mètres
9. les valeurs inférées doivent produire un warning
10. aucune scène ne passe sans `SceneSpec` valide

---

### 6.5 Asset Selection Agent

Responsabilité :

- choisir les assets GLB depuis la bibliothèque ;
- utiliser les manifests ;
- justifier les choix ;
- bloquer les assets non validés.

Types d’assets :

- `tower`
- `antenna`
- `radio`
- `cable`
- `bracket`
- `cabinet`
- `beam`
- `marker`
- `label`

---

### 6.6 Scene Planning Agent

Responsabilité :

- construire le `SceneSpec` complet ;
- positionner les objets ;
- organiser la hiérarchie ;
- calculer rotations, hauteurs, azimuts ;
- demander correction si conflit.

Le `SceneSpec` est le contrat central du système.

---

### 6.7 Procedural Geometry Agent

Responsabilité :

Créer les éléments géométriques variables :

- faisceaux sectoriels ;
- flèches d’azimut ;
- câbles courbes ;
- labels ;
- marqueurs de hauteur ;
- axes ;
- supports simples si nécessaires.

---

### 6.8 Blender Generation Agent / Worker

Responsabilité :

- lire `SceneSpec`;
- importer assets ;
- créer géométrie procédurale ;
- appliquer matériaux ;
- configurer caméra/lumière preview ;
- exporter GLB ;
- rendre preview ;
- produire metadata.

Ce worker doit être isolé du process API.

---

### 6.9 3D QA Agent

Responsabilité :

Valider après génération :

- fichier GLB existe ;
- taille > seuil minimal ;
- nombre de secteurs correct ;
- antennes présentes ;
- hauteurs respectées ;
- azimuts appliqués ;
- RRU présentes si demandées ;
- câbles présents si demandés ;
- metadata complète ;
- score de conformité calculé.

---

### 6.10 Documentation / Report Agent

Responsabilité :

Produire un rapport lisible :

- résumé du cahier des charges ;
- paramètres extraits ;
- assets sélectionnés ;
- règles appliquées ;
- warnings ;
- score ;
- chemins artefacts ;
- recommandations.

---

## 7. Contrats de données

### 7.1 RequirementSpec

```json
{
  "network_type": "5G",
  "site_type": "telecom_site",
  "tower_type": "lattice_tower",
  "tower_height_m": 30,
  "sector_count": 3,
  "antenna_install_height_m": 24,
  "azimuths_deg": [0, 120, 240],
  "include_rru": true,
  "include_cables": true,
  "include_beams": true,
  "include_labels": true,
  "detail_level": "high"
}
```

### 7.2 AssetManifest

```json
{
  "asset_id": "TOWER_LATTICE_30M",
  "type": "tower",
  "file": "assets/towers/tower_lattice_30m.glb",
  "height_m": 30,
  "dimensions_m": {
    "width": 4,
    "depth": 4,
    "height": 30
  },
  "compatible_networks": ["4G", "5G"],
  "mount_zones": [
    {
      "name": "upper_mount_zone",
      "min_height_m": 20,
      "max_height_m": 29
    }
  ],
  "status": "validated",
  "version": "1.0.0"
}
```

### 7.3 SceneSpec

```json
{
  "schema_version": "1.0.0",
  "scene_id": "SITE_DESIGN_001",
  "units": "meters",
  "network_type": "5G",
  "tower": {
    "asset_id": "TOWER_LATTICE_30M",
    "position": [0, 0, 0],
    "rotation_deg": [0, 0, 0],
    "scale": [1, 1, 1],
    "height_m": 30
  },
  "sectors": [
    {
      "sector_id": "S1",
      "antenna_asset_id": "ANT_PANEL_5G_001",
      "radio_asset_id": "RRU_SMALL_001",
      "install_height_m": 24,
      "azimuth_deg": 0,
      "mechanical_tilt_deg": 3,
      "beamwidth_deg": 65,
      "beam_radius_m": 8,
      "include_cable": true,
      "include_label": true
    }
  ],
  "visual_elements": {
    "include_sector_beams": true,
    "include_azimuth_arrows": true,
    "include_height_markers": true,
    "include_labels": true
  },
  "preview": {
    "camera": "isometric",
    "resolution": [1920, 1080]
  },
  "export": {
    "formats": ["glb", "png", "json_report"]
  }
}
```

### 7.4 ValidationReport

```json
{
  "design_id": "SITE_DESIGN_001",
  "status": "passed",
  "score": 0.96,
  "checks": {
    "tower_asset_valid": true,
    "tower_height_valid": true,
    "sector_count_valid": true,
    "antenna_height_valid": true,
    "azimuths_valid": true,
    "rru_present": true,
    "cables_present": true,
    "glb_export_valid": true
  },
  "warnings": [
    {
      "code": "DEFAULT_BEAMWIDTH_USED",
      "message": "Beamwidth 65° utilisé par défaut."
    }
  ]
}
```

---

## 8. Organisation recommandée du projet

Codex doit d’abord inspecter l’existant. Si le projet est vide, il peut créer une structure proche de celle-ci :

```text
agentic-3d-telecom-studio/
  apps/
    api/
    frontend/
    blender_worker/

  core/
    agents/
    contracts/
    rules/
    orchestration/
    rag/
    services/
    validation/

  assets/
    towers/
    antennas/
    radios/
    accessories/
    visualization/
    manifests/

  data/
    sqlite/
    qdrant/
    knowledge/

  outputs/
    temp/

  docs/
    PROJECT_MEMORY.md
    ARCHITECTURE.md
    SCENE_SPEC.md
    ASSET_REGISTRY.md
    RAG_STRATEGY.md
    QA_STRATEGY.md

  tests/
    unit/
    integration/
    golden_scenes/

  infra/
    docker-compose.yml
    Dockerfile.api
    Dockerfile.blender-worker
```

Important : si une structure existe déjà, ne pas recréer des doublons. Adapter proprement.

---

## 9. API locale minimale

### `POST /designs`

Créer un workflow de génération.

Entrée :

```json
{
  "requirements_text": "Créer un site 5G sur pylône treillis 30m avec 3 secteurs...",
  "options": {
    "detail_level": "high",
    "generate_variants": false
  }
}
```

Sortie :

```json
{
  "workflow_id": "wf_001",
  "status": "queued"
}
```

### `GET /designs/{workflow_id}`

Retourne statut, erreurs, warnings, artefacts.

### `GET /designs/{workflow_id}/download`

Télécharge l’archive finale.

### `POST /scene-spec/validate`

Valide un `SceneSpec`.

### `GET /assets`

Liste les assets disponibles.

### `POST /rag/reindex`

Réindexe la base Qdrant locale.

---

## 10. Stratégie RAG Qdrant

### Collections

```text
telecom_rules
asset_manifests
scene_templates
validation_cases
design_patterns
blender_generation_guides
```

### Payload minimal

```json
{
  "doc_id": "template_5g_lattice_3sector",
  "type": "scene_template",
  "network_type": "5G",
  "tower_type": "lattice_tower",
  "sector_count": 3,
  "version": "1.0.0",
  "status": "validated"
}
```

### Règle d’utilisation

Le RAG ne décide jamais seul. Il fournit du contexte. Les décisions finales passent par :

```text
Rule Engine
→ Asset Registry
→ SceneSpec Validator
→ QA Agent
```

---

## 11. Blender Worker

### Responsabilités

Le worker doit :

1. lire `SceneSpec`;
2. charger les assets GLB ;
3. appliquer échelle, position, rotation ;
4. générer les objets procéduraux ;
5. ajouter matériaux/labels ;
6. exporter `.glb`;
7. rendre preview `.png`;
8. produire `scene_metadata.json`.

### Commande cible

```bash
blender -b --python generate_scene.py -- scene_spec.json output_dir
```

### Contraintes

- pas de code LLM direct ;
- timeout par job ;
- logs structurés ;
- chemins contrôlés ;
- erreurs explicites ;
- sortie déterministe autant que possible.

---

## 12. Tests et critères de qualité

### Tests unitaires

- parsing requirement ;
- validation contracts ;
- règles métier ;
- sélection assets ;
- génération SceneSpec ;
- validation report.

### Tests d’intégration

- cahier des charges → RequirementSpec ;
- RequirementSpec → SceneSpec ;
- SceneSpec → Blender Worker ;
- Blender Worker → GLB ;
- GLB → QA.

### Golden scenes obligatoires

Créer des scènes de référence :

1. `golden_5g_lattice_30m_3sector`
2. `golden_4g_rooftop_2sector`
3. `golden_small_cell_pole`
4. `golden_microwave_dish_site`

Chaque golden scene doit avoir :

- input requirement ;
- expected RequirementSpec ;
- expected SceneSpec ;
- validation expectations ;
- output GLB vérifiable.

---

## 13. Observabilité locale

Chaque workflow doit avoir :

```text
workflow_id
trace_id
agent_step
duration_ms
selected_assets
scene_spec_path
blender_job_status
validation_score
warnings
errors
artifact_paths
```

Logs JSON recommandés.

Metrics locales utiles :

```text
generation_success_rate
average_generation_time
blender_failure_rate
scene_validation_failure_rate
rag_hit_rate
asset_missing_rate
average_validation_score
```

---

## 14. Roadmap d’implémentation

### Lot 0 — Bootstrap propre

- créer structure ;
- installer FastAPI ;
- config SQLite ;
- config Qdrant local ;
- config settings ;
- healthcheck ;
- tests de base.

### Lot 1 — Contrats de données

- RequirementSpec ;
- AssetManifest ;
- SceneSpec ;
- ValidationReport ;
- validators Pydantic ;
- tests unitaires.

### Lot 2 — Asset Registry

- manifests JSON ;
- chargement assets ;
- validation compatibilité ;
- listing API.

### Lot 3 — RAG Qdrant

- ingestion docs ;
- embeddings ;
- collections ;
- retrieval ;
- tests de recherche.

### Lot 4 — LangGraph Orchestrator

- state ;
- nodes ;
- routing ;
- correction loops ;
- persistence locale.

### Lot 5 — Scene Planning

- génération SceneSpec ;
- rule engine ;
- validation ;
- warnings.

### Lot 6 — Blender Worker

- script Blender ;
- import GLB ;
- objets procéduraux ;
- export GLB ;
- preview PNG.

### Lot 7 — QA Agent

- post-generation checks ;
- rapport JSON ;
- score ;
- golden scenes.

### Lot 8 — Frontend Viewer

- upload cahier des charges ;
- statut workflow ;
- viewer GLB ;
- rapports ;
- téléchargement.

### Lot 9 — Hardening

- cleanup TTL ;
- logs ;
- retries ;
- fallback LLM ;
- tests e2e ;
- docs.

---

## 15. Critères d’acceptation MVP

Le MVP est accepté si :

1. l’utilisateur saisit un cahier des charges ;
2. le système extrait un `RequirementSpec`;
3. le RAG récupère un contexte utile ;
4. le Rule Engine valide ou bloque ;
5. le système génère un `SceneSpec`;
6. Blender produit un `.glb`;
7. une preview est générée ;
8. un rapport QA est généré ;
9. l’utilisateur télécharge les artefacts ;
10. les sorties temporaires sont nettoyées ;
11. les tests essentiels passent.

---

## 16. Critères d’acceptation avancés

La version avancée est acceptée si :

1. support de plusieurs types de pylônes ;
2. support de plusieurs antennes ;
3. support RRU/câbles/faisceaux/labels ;
4. génération de variantes ;
5. scoring comparatif ;
6. RAG Qdrant fonctionnel ;
7. fallback LLM ;
8. golden scenes ;
9. validation GLB ;
10. viewer 3D frontend ;
11. logs/traces exploitables ;
12. documentation technique maintenue.

---

## 17. Règles de travail pour Codex

Codex doit :

1. scanner le projet avant action ;
2. comprendre l’architecture existante ;
3. éviter les doublons ;
4. éviter les fichiers morts ;
5. prioriser les contrats et tests ;
6. implémenter par lots ;
7. garder les docs à jour ;
8. ne pas masquer les erreurs ;
9. fournir preuves de tests ;
10. ne jamais prétendre qu’une étape est validée sans preuve.

Codex doit agir comme :

```text
architecte full stack
+ tech lead backend
+ ingénieur IA agentique
+ ingénieur 3D pipeline
+ reviewer qualité
```

---

## 18. Décision finale

Architecture cible validée :

```text
SQLite = état local exact
Qdrant = mémoire RAG avancée
LangGraph = orchestration agentique
Groq GPT-OSS-120B = LLM principal
Blender 4.5 LTS = moteur de génération 3D
GLB/glTF = format de sortie
React/Three.js = viewer frontend
Filesystem local = assets et outputs temporaires
```

Le système doit rester local-first, robuste, testable, évolutif et traçable.

Le projet ne doit pas être une démo IA fragile. Il doit être une **plateforme agentique de génération 3D télécom fiable**, capable de transformer une exigence métier en modèle 3D vérifié.
