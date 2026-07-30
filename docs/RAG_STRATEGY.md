# RAG Strategy

RAG improves context for planning, but it is not the source of truth. The
generation source of truth remains `RequirementSpec -> SceneSpec -> Blender`.

## Product Provider

- Product embedding provider: NVIDIA API
  `nvidia/llama-nemotron-embed-1b-v2`, requested at 1024 dimensions.
- Configure with `NVIDIA_API_KEY` or `TELECOM_STUDIO_NVIDIA_API_KEY`.
- Default API config:

```text
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-1b-v2
TELECOM_STUDIO_EMBEDDING_DIMENSIONS=1024
```

If `TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia` lacks a key, startup fails instead
of silently degrading. Network reachability is established only by the first
real index/search/write operation and its failure is exposed explicitly.

The 2026-07-28 live probe proved that the local NVIDIA key is valid:
`GET /v1/models` returned 200 and listed `baai/bge-m3`. BGE-M3 itself returned
500 for both scalar and batched requests. The selected Nemotron model returned
200 and a 1024-dimensional vector with the same key. This distinguishes a
model-serving incident from an authentication failure.

Construction of the provider is network-free and therefore is not an
operational health proof. `/studio/summary` reports `configured_unverified`
until a real index/search/write succeeds, and
`configured_but_last_operation_failed` after a real provider failure.

## Non-Product Modes

- `TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic` is for tests/bootstrap only.
- `TELECOM_STUDIO_EMBEDDING_PROVIDER=auto` may fall back to deterministic hash
  for local bootstrap, but it is not acceptable as product-quality RAG.
- `sentence-transformers` is an explicit developer override only, not an
  automatic product fallback.

## Reranker

- Product reranker provider: NVIDIA API.
- Default API config:

```text
TELECOM_STUDIO_RERANKER_PROVIDER=nvidia
TELECOM_STUDIO_RERANKER_MODEL=nvidia/llama-nemotron-rerank-1b-v2
```

If the NVIDIA reranker is unavailable, retrieval falls back to vector order and
the API exposes `degraded_passthrough` plus `rag_reranker_degraded_reason`.
This is a visible degraded state, not a silent success.

Local `BAAI/bge-reranker-v2-m3` is an explicit developer override only:

```text
TELECOM_STUDIO_RERANKER_PROVIDER=local
TELECOM_STUDIO_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

The backend exposes `rag_reranker_provider`, `rag_reranker_model`,
`rag_reranker_status`, and `rag_reranker_degraded_reason` in `/studio/summary`
and `/viewer-bundle`.

## How RAG Enters The Pipeline

```text
Requirement extraction
-> structured RAG query from RequirementSpec + original text
-> NVIDIA Nemotron query embedding against passage-embedded controlled corpus
-> Qdrant search over knowledge files and asset manifests
-> NVIDIA reranker
-> bounded GPT-OSS decision over validated candidate hints
-> ScenePlanner consumes only accepted payload.planning_hints
-> deterministic validation and quality gates remain mandatory
```

RAG is not used for `RequirementSpec` extraction in v1. GPT-OSS extraction and
RAG retrieval are separate surfaces.

## Storage And Indexing

- Qdrant local default: `data/qdrant`.
- Optional external Qdrant: `TELECOM_STUDIO_QDRANT_URL`.
- Static collections: the five controlled `data/knowledge` files and asset
  manifests. Library catalog entries join `asset_manifests` only when both
  `validated=true` and `generation_eligible=true`; quarantined/raw CAD never
  enters planning retrieval. Developer documentation is deliberately excluded
  from retrieval.
- NVIDIA indexing uses `input_type=passage`; retrieval queries use
  `input_type=query`. The embedding profile is part of index identity so an old
  index is rebuilt instead of mixed silently.
- Runtime collections: design memory, error memory, document-pack memory.
- Runtime collection dimensions are checked before use. If a legacy collection
  is incompatible, it is preserved and new writes are routed to a
  provider/dimension-versioned physical collection. SQLite remains the durable
  local memory source during this migration.
- Rebuild after provider/dimension/knowledge changes with `POST /rag/reindex`.

## What Can Influence SceneSpec

Only structured `payload.planning_hints` can affect planning. Current applied
hints are:

- `antenna_install_height_m`
- `beamwidth_deg`
- `mechanical_tilt_deg`
- `electrical_tilt_deg`
- `include_cables`
- `include_sector_beams`

Free text retrieved by RAG is audit context. It must not mutate the 3D plan
silently.

RAG must not overwrite an explicit user/document value. A hint can replace only
a field carrying the matching explicit default-warning code; every applied,
rejected or no-op candidate remains visible in `rag_evidence.json`. Foundation,
equipment presence, labels, GPS and cabinet decisions remain outside this
bounded six-field authority.

## Public Truth Fields

Workflow and viewer surfaces expose:

- `rag_context_count`: number of retrieved contexts.
- `rag_planning_summary.rag_used_for_extraction=false`.
- `rag_planning_summary.rag_used_for_planning`: true only when a validated hint
  was actually applied, not merely retrieved.
- `rag_planning_summary.rag_planning_mode`: `structured_planning_hints` or
  `context_only_no_structured_hints`.
- `rag_planning_summary.candidate_hint_fields`.
- `rag_planning_summary.controlled_hint_fields`.
- `rag_planning_summary.top_contexts` with repo-relative source paths.
- `rag_evidence_url` from `/viewer-bundle`.
- `rag_evidence.json` with retrieved sources, controlled hints, rejected hints,
  reranker status, policy, and limitations.

The frontend must not treat `rag_context_count > 0` as proof that RAG changed
the design.

## Known Weaknesses

- Knowledge files are still seed-level, not a vendor-grade telecom knowledge
  base.
- RAG does not yet perform claim-level citation into `SceneSpec`.
- RAG does not yet run conflict resolution against document-pack evidence.
- Reranker is fail-open: if NVIDIA reranking fails, retrieval still returns
  vector-ranked results and the degraded status is visible.
- Embedding retrieval is not fail-open as a product-quality success: a provider
  HTTP error is recorded as failed and RAG remains advisory/unavailable for that
  operation.
- No hybrid sparse/BM25 engine beyond the current lexical boost.

## Quality Bar Before Calling RAG Advanced

RAG can be called advanced only after:

- The configured NVIDIA embedding model is verified with French telecom
  queries and a measured retrieval evaluation, not only a successful API call.
- Chunks are source-specific and not giant whole-doc blobs.
- Retrieved contexts include citations/provenance safe for frontend display.
- Scene changes caused by RAG are explainable through structured hints.
- Contradictions between documents, memory, and user prompt are surfaced as
  warnings or conflicts, not hidden.
