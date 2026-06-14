# RAG Embedding Strategy

## Goal

Provide high-quality semantic retrieval for French telecom requirements and documents.

## Primary model

**`baai/bge-m3`** via NVIDIA API (`https://integrate.api.nvidia.com/v1`)

- 1024-dimensional dense embeddings.
- Strong multilingual performance, including French.
- ColBERT-style late interaction for long documents (not fully exploited yet).
- Served by NVIDIA: no local GPU or large download required.

## Fallback chain

1. **NVIDIA API** for `baai/bge-m3` — default.
2. **Local `sentence-transformers`** with `baai/bge-m3` — offline fallback.
3. **Deterministic hash embedding** — emergency / test fallback only.

## Configuration

```text
NVIDIA_API_KEY=nvapi-...
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=baai/bge-m3
```

To refuse hash fallback in production:

```text
TELECOM_STUDIO_EMBEDDING_STRICT_QUALITY=1
```

## Why not other providers

- **OpenAI/Cohere/Voyage**: not local-first, extra cost, no clear advantage over bge-m3 for this domain.
- **FastEmbed**: ONNX-only, model-cache fragile, no quality advantage.
- **Ollama**: extra local service to manage; NVIDIA API is simpler and faster.
- **Hash**: only for tests and emergency bootstrap.

## Future improvements

- Add a cross-encoder re-ranker (e.g. `BAAI/bge-reranker-v2-m3`).
- Fine-tune an embedding adapter on telecom documents.
- Hybrid dense + BM25 retrieval.
