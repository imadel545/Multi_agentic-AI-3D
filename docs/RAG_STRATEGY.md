# RAG Strategy

RAG is implemented with Qdrant through `core/rag`. The default mode uses Qdrant local
storage at `data/qdrant`; setting `TELECOM_STUDIO_QDRANT_URL` switches the service to a
running Qdrant instance, such as the Docker service in `infra/docker-compose.yml`.

Target collections:

- `telecom_rules`
- `asset_manifests`
- `scene_templates`
- `validation_cases`
- `design_patterns`
- `blender_generation_guides`

RAG will supply context to agents, but final decisions remain controlled by:

```text
Rule Engine -> Asset Registry -> SceneSpec Validator -> QA Agent
```

## Embedding Provider

Completed:

- Qdrant local mode under `data/qdrant`.
- Optional Qdrant URL through `TELECOM_STUDIO_QDRANT_URL`.
- Reindexing of knowledge files, asset manifests, and project docs.
- Search across all collections.
- Filtered search by `network_type`, `tower_type`, and `doc_type`.
- Deterministic hashing embedding as the local fallback.

Available with fallback:

- `TELECOM_STUDIO_EMBEDDING_PROVIDER=fastembed` attempts to use FastEmbed when installed.
- If FastEmbed is unavailable, the service falls back to deterministic hashing.

Settings:

```bash
TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic|fastembed
TELECOM_STUDIO_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

The deterministic provider is an MVP fallback, not semantic production embedding quality.

## API

- `POST /rag/reindex`: indexes knowledge files, asset manifests, and project docs.
- `GET /rag/search?q=5G+lattice+tower+3+sectors`: searches all RAG collections.
- `GET /rag/search?...&network_type=5G&tower_type=lattice_tower&doc_type=asset_manifest`
  applies metadata filters.
