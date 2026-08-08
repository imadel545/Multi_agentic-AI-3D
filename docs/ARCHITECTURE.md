# Architecture

Pipeline local-first mono-utilisateur. Les contrats Pydantic et validations déterministes
sont la base; les couches agentiques et RAG restent contrôlées.

## Flow

```text
FastAPI
  -> requirements text or document pack
  -> RequirementSpec / ProjectDesignSpec
  -> LangGraph-orchestrated generation pipeline
  -> Groq extraction or deterministic fallback
  -> NVIDIA API Nemotron query/passage retrieval + NVIDIA reranker evidence
  -> bounded GPT-OSS planning decision over validated RAG candidates
  -> SQLite memory recall
  -> asset registry + inventory
  -> qualified asset-library retrieval only (raw CAD stays quarantined)
  -> fidelity-aware scored asset candidates + bounded LLM selection
  -> AssemblyPlan/connectors
  -> routed DesignBlueprint specialists
  -> SceneSpec planner
  -> optional bounded GPT-OSS GeometryProgram
  -> SceneSpec validation + quality gates
  -> deterministic Blender builders / GeometryProgram compiler
  -> GLB/preview/metadata artifacts
  -> structural/proxy geometry/preview QA
  -> memory writeback
  -> Product API summaries
```

Une révision par prompt suit d'abord un graphe spécialisé:

```text
active SceneSpec + prompt
  -> resolve manifest capability profiles
  -> route standard adaptation or generated-component rebuild
  -> bounded Groq JSON-Schema plan or visible standard-capability fallback
  -> capability/path/tool/value/grounding validation
  -> GeometryProgram contract/envelope validation when targeted
  -> SceneSpec mutation
  -> main revision graph -> Blender -> QA -> certified version activation
```

## Modules

- `apps/api`: FastAPI gateway, Product API, workflow lifecycle.
- `apps/blender_worker`: SceneSpec-driven Blender script, fixed parametric
  builders and deterministic GeometryProgram compiler.
- `core/contracts`: strict contracts, including `GeometryRequest` and
  `GeometryProgram`.
- `core/document_pack`: bounded direct-file/ZIP intake, PDF/OCR/DXF extraction,
  and `ProjectDesignSpec`.
- `core/orchestration`: LangGraph workflow and route logic.
- `core/agents`: deterministic/LLM wrappers for extraction, planning, editing,
  RF/tower checks and bounded GeometryProgram authorship.
- `core/rag`: Qdrant, NVIDIA API multilingual embeddings, NVIDIA reranker with visible
  degraded passthrough, deterministic test/bootstrap mode, explicit local override.
- `core/memory`: SQLite workflow/document-pack memory.
- `core/services`: assets, events, versioning, Blender runner, cleanup.
- `core/services/asset_library.py`: immutable-source catalog, SHA-256
  deduplication, metadata search, deterministic CAD-to-source-preview links and
  isolated LibreDWG probes. Preview links are retrieval evidence only. The
  probe accepts LibreDWG's observed Latin-1/non-finite JSON dialect, reports
  every normalization, and resolves scale from `INSUNITS` while exposing unit
  metadata conflicts. The service does not promote or tessellate a raw CAD
  asset.
- `core/qa`: GLB structural parse, mesh/accessor/transform basic QA, proxy
  geometry, preview pixel/framing QA.

## Runtime truths

### Docker runtime

- `infra/docker-compose.yml` is the only authoritative Compose stack.
- Nginx serves the compiled frontend on loopback and proxies the stable FastAPI
  routes same-origin. SSE buffering is disabled only for the design event
  stream and document uploads retain the backend 200 MB limit.
- The API runs as UID/GID `10001`, one Uvicorn worker and `linux/amd64` with an
  archive-hash-pinned Blender 4.5.12 LTS. Startup fails unless the Blender
  background/factory-startup smoke reports that release. Docker selects the
  governed EEVEE engine with 8 samples to keep five-view technical previews
  within the 600-second emulation budget; unsupported engine/sample overrides
  fail closed.
- SQLite remains canonical in `sqlite_data`; artifacts use `outputs_data`.
  `sqlite-snapshot` uses SQLite's online backup API and atomically publishes
  integrity-checked, read-only copies to `sqlite_preview` for Adminer.
- Qdrant `v1.18.0` is a derived vector store in `qdrant_data`; its REST port is
  loopback-only and gRPC remains internal. The local index identity files live
  in a writable API state directory, not the read-only application image.
- The CAD library is a read-only bind mount. It is not copied into images and
  is not mass-converted by container startup.
- Vite publishes compiled bundles below `/static`; `/assets` therefore remains
  exclusively the FastAPI asset-library contract in the same-origin proxy.

- `outputs/temp` contains ignored workflow artifacts.
- `data/sqlite` and `data/qdrant` are local ignored runtime stores.
- Workflow mutations check free local storage before persistence. Startup
  recovery restores the last valid active version after an interrupted edit,
  while an interrupted initial generation remains failed.
- `active_design.json` is the canonical commit marker. Reads resolve the
  verified version manifest even if a compatibility root-status or terminal
  event projection failed after commit.
- Blender executes a per-attempt immutable copy of every Python worker source;
  the build lock hashes that executed copy, the SceneSpec, runtime profile and
  generated artifacts.
- Workflow/version identifiers are validated at the HTTP boundary before local
  path lookup. Qdrant Docker ports are loopback-only.
- `.env` contains real secrets and must never be committed.
- `.env.example` contains placeholders only.
- `apps/frontend` is a real-backend product rework, not an accepted final gate.

## Known weak points

- Artifact copying and version bookkeeping remain service-level. Edit planning,
  validation and SceneSpec mutation now run inside a dedicated checkpointed
  LangGraph graph before the main revision graph.
- Revision preparation rebinds tower/equipment assets and recalculates derived
  GPS/cabinet placements before validation and Blender generation. Existing
  accessory rotation/scale are preserved; explicitly moved positions are marked
  `user_defined`, while derived positions continue to follow tower geometry.
- Events are frontend-readable and `/events/stream` is `push_sse` local-process, but there is
  no broker, cancellation manager, or durable resume yet. Cursor replay and
  sequence-gap catch-up are durable through the JSONL log within this
  single-process scope.
- The orchestration trace distinguishes bounded LLM decisions, deterministic
  specialists, services, quality gates and external tools. A routed specialist
  registry exists, but its domains and dependencies remain declared
  deterministically; it is not an autonomous supervisor.
- Asset import fallback can still create procedural geometry if an import fails, but the active
  inventory has 13 manifests and 12 GLB files: 12 manifests are
  generation-eligible, 3 authorize exact hash-pinned GLB import, 9 use bounded
  parametric generation, and 1 remains reference-only.
- The separate 11,974-file CAD library is not part of that active inventory.
  Its 11,531 unique contents remain quarantined until licence, units, B-Rep
  conversion and geometry QA produce a validated manifest. Only validated,
  generation-eligible catalog rows may enter the asset RAG collection.
- Candidate ordering is deterministic and weights declared geometry fidelity
  separately from compatibility, dimensions and execution strategy. The bounded
  LLM receives those factors but may select only a supplied qualified ID and an
  authorized strategy; `ScenePlanner` then consumes that exact AssemblyPlan
  decision instead of recomputing a conflicting strategy.
- Geometry QA combines binary accessor checks, semantic role transforms and a
  real-vertex AABB interference screen for primary equipment. It is not exact
  triangle/BVH collision, RF, structural or vendor-grade QA.
- GeometryProgram envelopes and a 1024-node aggregate budget are deterministic.
  One uniform bounded adapter may only reduce a program that exceeds its
  requested maximum envelope. Placement prose is preserved, not interpreted or
  independently validated, and free generated roles are outside the current
  primary-equipment AABB gate.
- Generic panel/RRU generation is manifest-profiled and LOD-aware, and GLB QA
  requires declared technical sub-parts. These profiles remain generic rather
  than vendor-qualified.
- RAG is not used for extraction in v1; only structured, whitelisted
  `payload.planning_hints` can influence planning, and `rag_planning_summary`
  plus `rag_evidence.json` expose whether that happened.
- Document-pack locks are process-local. Atomic JSON replacements prevent
  partial files and concurrent readers cannot observe an in-flight correction,
  but a crash can still split a multi-file pack revision.
- Native Python dependency ranges have explicit advisory-driven security floors
  but are not accompanied by a native-environment resolution lock. Docker has
  a committed Linux/Python 3.12 lock; Qdrant server and client are aligned on
  `v1.18.0`.

## Generic cognitive extension V1

La route générique est une extension du monolithe local-first existant:
`CognitiveDesignPlanner` produit un plan borné, `CognitiveSupervisor` ferme le
DAG des spécialistes, `CapabilityRegistry` autorise les opérations, puis
`CognitiveSceneCompiler` produit le même `SceneSpec` consommé par le même
`BlenderRunner`, les mêmes gates, le même certificat et le même versioning.
Le LLM ne possède ni filesystem, ni `bpy`, ni exécution de code; les programmes
géométriques sont des contrats JSON validés et compilés déterministiquement.

Cette extension reste partielle: la route d'assets génériques est procédurale,
la résolution spatiale arbitraire n'est pas un solveur de contraintes complet,
et la disponibilité/validité JSON du provider Groq reste une dépendance externe
non maîtrisée.
