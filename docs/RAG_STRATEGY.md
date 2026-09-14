# RAG Strategy

RAG improves context for planning, but it is not the source of truth. The
generation source of truth remains `RequirementSpec -> SceneSpec -> Blender`.

## Product Provider

- Product embedding provider: NVIDIA API
  `nvidia/nemotron-3-embed-1b`, at its native 2048 dimensions.
- Configure with `NVIDIA_API_KEY` or `TELECOM_STUDIO_NVIDIA_API_KEY`.
- Default API config:

```text
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b
TELECOM_STUDIO_EMBEDDING_DIMENSIONS=2048
TELECOM_STUDIO_EMBEDDING_TIMEOUT_S=30
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

The hosted NVIDIA text rerankers checked on 2026-09-14 returned HTTP 410 or
404. The default is therefore explicit passthrough; the API exposes that state
and does not label it as neural reranking.

Default API config:

```text
TELECOM_STUDIO_RERANKER_PROVIDER=passthrough
```

If a future NVIDIA reranker is explicitly configured and becomes unavailable,
retrieval falls back to vector order and the API exposes
`degraded_passthrough` plus `rag_reranker_degraded_reason`. Explicit passthrough
reports `rag_reranker_provider=passthrough`, `rag_reranker_model=null` and
`rag_reranker_status=passthrough_no_rerank`; neither state is a silent neural
success.

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
-> explicit passthrough ranking while hosted NVIDIA rerankers are unavailable
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
  manifests. A manifest enters `asset_manifests` only when an effective runtime
  route exists: exact GLB bytes must be present, hash-matched and structurally
  valid, while a professional claim must additionally pass its full evidence
  and rights gate. Library catalog entries join only when both `validated=true`
  and `generation_eligible=true`; quarantined/raw CAD never enters planning
  retrieval. Developer documentation is deliberately excluded from retrieval.
- NVIDIA indexing uses `input_type=passage`; retrieval queries use
  `input_type=query`. The embedding profile is part of index identity so an old
  index is rebuilt instead of mixed silently.
- Runtime collections: design memory, error memory, document-pack memory.
- Runtime collection dimensions are checked before use. If a legacy collection
  is incompatible, it is preserved and new writes are routed to a
  provider/model/dimension-versioned physical collection. SQLite remains the durable
  local memory source during this migration.
- Rebuild after provider/model/dimension/knowledge changes with `POST /rag/reindex`.

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
- An explicitly configured remote reranker is fail-open: if it fails, retrieval
  preserves the incoming vector or lexical order and exposes degraded status.
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

## Verified Runtime Boundary — 2026-09-14

A bounded host probe sent one synthetic French telecom query to
`nvidia/nemotron-3-embed-1b` and received one 2048-dimensional vector. The
Docker runtime then indexed the 25 controlled static documents and returned
five vector results for one French query. `/studio/summary` reported the NVIDIA
embedding path as operational and the reranker as explicit passthrough. These
checks establish provider transport plus index/search execution for that corpus;
they do not establish representative retrieval quality.

The replaced embedding model and the hosted rerankers tested that day returned
HTTP 410 or 404. Those retirement diagnostics remain in
`docs/KNOWN_LIMITATIONS.md`; they are not active provider alternatives.
