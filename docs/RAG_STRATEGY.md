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

Static reindex embeds the full cross-collection corpus in one logical operation
and sends it to NVIDIA in bounded batches of at most 32 passages. The
synchronous product path sets SDK embedding retries to zero so an advisory
RAG dependency cannot multiply the workflow latency. If index construction or
query embedding fails, the backend ranks the real local documents lexically,
then still offers those candidates to the configured reranker. This path is
published as `rag_retrieval_status=degraded_local_lexical` with a sanitized
reason; it is not vector retrieval and does not use hash embeddings.

The 2026-08-11 browser smoke on convergence commit `19791be`, workflow
`wf_0843599873e7`, retrieved five
contexts with `primary_vector` and `primary_nvidia_reranker` in 1.620 s.
Provider configuration and this point-in-time success remain insufficient;
retrieval quality still requires a controlled French telecom evaluation set.

Construction of the provider is network-free and therefore is not an
operational health proof. `/studio/summary` reports `configured_unverified`
until a real index/search/write succeeds, and
`configured_but_last_operation_failed` after a real provider failure.

## Non-Product Modes

- `TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic` is for tests/bootstrap only.
- `TELECOM_STUDIO_EMBEDDING_PROVIDER=auto` may fall back to deterministic hash
  for local bootstrap, but it is not acceptable as product-quality RAG.
- No local neural embedding model is part of the product path. This avoids a
  hidden download, a second unqualified retrieval profile and CPU contention
  with Blender in the local runtime.

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

The backend exposes `rag_retrieval_status`, `rag_retrieval_degraded_reason`,
`rag_reranker_provider`, `rag_reranker_model`, `rag_reranker_status`, and
`rag_reranker_degraded_reason` in workflow/viewer evidence. The frontend loads
`rag_evidence.json` automatically in the contextual Intelligence drawer.

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

Within the RAG authority, only structured `payload.planning_hints` can affect
planning. Current applied hints are:

- `antenna_install_height_m`
- `beamwidth_deg`
- `mechanical_tilt_deg`
- `electrical_tilt_deg`
- `include_cables`
- `include_sector_beams`

Free text retrieved by RAG is audit context. It must not mutate the 3D plan
silently.

The GeometryProgram specialist does not currently receive retrieved RAG passages
or claim-level citations directly. It receives the typed request, selected asset
IDs, assembly roles and bounded design context. Its `source_description`,
`placement_context`, model/mode and hashes are preserved, but this is not
claim-level RAG grounding of generated geometry.

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
- Out-of-catalog GeometryProgram nodes are not directly grounded in retrieved
  passages or vendor citations.
- Reranker is fail-open: if NVIDIA reranking fails, retrieval preserves the
  incoming vector or lexical order and the degraded status is visible.
- Embedding retrieval is not fail-open as a product-quality success: a provider
  failure produces real local lexical candidates but remains visibly degraded.
- The lexical continuity path is token overlap, not a trained sparse/BM25
  engine and not equivalent to multilingual semantic retrieval.

## Quality Bar Before Calling RAG Advanced

RAG can be called advanced only after:

- The configured NVIDIA embedding model is verified with French telecom
  queries and a measured retrieval evaluation, not only a successful API call.
- Chunks are source-specific and not giant whole-doc blobs.
- Retrieved contexts include citations/provenance safe for frontend display.
- Scene changes caused by RAG are explainable through structured hints.
- Contradictions between documents, memory, and user prompt are surfaced as
  warnings or conflicts, not hidden.

## Recovery and provider availability — 2026-09-10

SQLite memory now persists origin/eligibility under an idempotent migration.
Historical rows become UNKNOWN/ineligible. Product recall and runtime documents
filter PRODUCT plus eligibility; the source fingerprint includes this policy and
row provenance. An ID cannot cross origin through normal writeback. The host
runtime memory projection has been rebuilt with zero eligible historic documents.

Actual static rebuild failed with NVIDIA HTTP410 for
`nvidia/llama-nemotron-embed-1b-v2`, retired on 2026-08-25 per the response. The
[official retrieval API list](https://docs.api.nvidia.com/nim/re/reference/retrieval-apis)
contains Nemotron 3 and VL alternatives, also returned by live model discovery.
Both timed out on a 25-document/six-query bounded comparison; one separate
Nemotron 3 query returned 2,048 dimensions in 19.58 seconds. No quality comparison
completed, so default configuration has not been changed. Static vectors remain
subject to compatibility checks and visible lexical degradation. This is an
external availability limitation, not successful provider qualification.
