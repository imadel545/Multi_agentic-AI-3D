# RAG Strategy

RAG improves context for planning, but it is not the source of truth. The
generation source of truth remains `RequirementSpec -> SceneSpec -> Blender`.

## Product Provider

- Product embedding provider: NVIDIA API `baai/bge-m3`.
- Configure with `NVIDIA_API_KEY` or `TELECOM_STUDIO_NVIDIA_API_KEY`.
- Default API config:

```text
TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia
TELECOM_STUDIO_EMBEDDING_MODEL=baai/bge-m3
```

If `TELECOM_STUDIO_EMBEDDING_PROVIDER=nvidia` cannot reach NVIDIA or lacks a
key, startup should fail instead of silently degrading.

## Non-Product Modes

- `TELECOM_STUDIO_EMBEDDING_PROVIDER=deterministic` is for tests/bootstrap only.
- `TELECOM_STUDIO_EMBEDDING_PROVIDER=auto` may fall back to deterministic hash
  for local bootstrap, but it is not acceptable as product-quality RAG.
- `sentence-transformers` is an explicit developer override only, not an
  automatic product fallback.

## Reranker

- Default reranker: `passthrough_no_rerank`.
- Local `BAAI/bge-reranker-v2-m3` is an explicit developer override only:

```text
TELECOM_STUDIO_RERANKER_PROVIDER=local
TELECOM_STUDIO_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

The backend exposes `rag_reranker` and `rag_reranker_status` in
`/studio/summary`.

## How RAG Enters The Pipeline

```text
Requirement extraction
-> structured RAG query from RequirementSpec + original text
-> Qdrant search over knowledge, docs, assets, templates
-> optional reranker
-> ScenePlanner consumes only payload.planning_hints
-> deterministic validation and quality gates remain mandatory
```

RAG is not used for `RequirementSpec` extraction in v1. GPT-OSS extraction and
RAG retrieval are separate surfaces.

## Storage And Indexing

- Qdrant local default: `data/qdrant`.
- Optional external Qdrant: `TELECOM_STUDIO_QDRANT_URL`.
- Static collections: telecom rules, asset manifests, scene templates,
  validation cases, design patterns, Blender generation guides.
- Runtime collections: design memory, error memory, document-pack memory.
- Rebuild after provider/dimension/knowledge changes with `POST /rag/reindex`.

## What Can Influence SceneSpec

Only structured `payload.planning_hints` can affect planning. Current supported
hints:

- `antenna_install_height_m`
- `beamwidth_deg`
- `include_cables`
- `include_sector_beams`
- `include_labels`

Free text retrieved by RAG is audit context. It must not mutate the 3D plan
silently.

## Public Truth Fields

Workflow and viewer surfaces expose:

- `rag_context_count`: number of retrieved contexts.
- `rag_planning_summary.rag_used_for_extraction=false`.
- `rag_planning_summary.rag_used_for_planning`: true only when structured hints
  were present.
- `rag_planning_summary.rag_planning_mode`: `structured_planning_hints` or
  `context_only_no_structured_hints`.
- `rag_planning_summary.candidate_hint_fields`.
- `rag_planning_summary.top_contexts` with repo-relative source paths.

The frontend must not treat `rag_context_count > 0` as proof that RAG changed
the design.

## Known Weaknesses

- Knowledge files are still seed-level, not a vendor-grade telecom knowledge
  base.
- RAG does not yet perform claim-level citation into `SceneSpec`.
- RAG does not yet run conflict resolution against document-pack evidence.
- Reranker is passthrough by default unless explicitly enabled.
- No hybrid sparse/BM25 engine beyond the current lexical boost.

## Quality Bar Before Calling RAG Advanced

RAG can be called advanced only after:

- NVIDIA BGE-M3 retrieval is verified with French telecom queries.
- Chunks are source-specific and not giant whole-doc blobs.
- Retrieved contexts include citations/provenance safe for frontend display.
- Scene changes caused by RAG are explainable through structured hints.
- Contradictions between documents, memory, and user prompt are surfaced as
  warnings or conflicts, not hidden.
