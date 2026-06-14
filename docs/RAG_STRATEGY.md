# RAG Strategy

RAG est advisory: il enrichit le contexte, mais ne contourne jamais le rule engine,
l'asset registry, le `SceneSpec` validator ou les quality gates.

## Provider principal

- Provider: NVIDIA API.
- Modèle: `baai/bge-m3`.
- Objectif: recherche sémantique multilingue, notamment cahiers des charges français.
- Dimension attendue: 1024.

Configuration publique sans secret:

```text
NVIDIA_API_KEY=<your-nvidia-api-key>
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=baai/bge-m3
```

## Fallback chain

1. NVIDIA API `baai/bge-m3`.
2. Local `sentence-transformers` avec `baai/bge-m3`.
3. Hash déterministe d'urgence/test uniquement.

`TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY=1` refuse le fallback hash quand la qualité
sémantique est obligatoire.

## Reranker

- `core/rag/reranker.py` tente `BAAI/bge-reranker-v2-m3` en local.
- Si le modèle ou ses dépendances ne sont pas disponibles, le reranker devient passthrough.
- Ce mode est best-effort et doit rester visible dans les diagnostics.

## Stockage

- Qdrant local par défaut sous `data/qdrant`.
- `TELECOM_STUDIO_QDRANT_URL` permet une instance Qdrant externe.
- Collections statiques: règles telecom, manifests assets, templates, cas validation,
  patterns design, guides Blender.
- Collection runtime possible: `document_pack_memory`.

## Ce que RAG peut faire

- Retrouver des assets, règles et exemples proches d'une demande.
- Fournir des `payload.planning_hints` structurés au planner.
- Améliorer les requêtes françaises et mixtes via BGE-M3.

## Ce que RAG ne doit pas faire

- Muter silencieusement la scène par texte libre.
- Ajouter GPS/cabinet/câbles sans signal structuré.
- Masquer un fallback embedding.
- Remplacer les validations déterministes.

## Tests attendus

- Recherche française avec NVIDIA BGE-M3 quand la clé est présente.
- Fallback explicite quand NVIDIA est indisponible.
- Filtrage par `network_type`, `tower_type`, `doc_type`.
- Rejet des hints décoratifs non structurés.

## Index compatibility

Un index Qdrant local créé avec un ancien provider ou une ancienne dimension d'embedding
est incompatible avec NVIDIA BGE-M3 (`1024` dimensions). Dans ce cas, `/rag/search` doit
retourner `409 RAG_INDEX_DIMENSION_MISMATCH` avec action recommandée `POST /rag/reindex`,
pas un 500 et pas un fallback silencieux.
