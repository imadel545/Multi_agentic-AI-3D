# Known Limitations

Active limitations that must remain visible in the API, reports, and future
frontend.

## Visible during frontend build

- No operational frontend yet; old dashboard rejected.
- `events/stream` is `push_sse` inside the local FastAPI process, with JSONL
  replay and queue live events. It is not a cross-process broker.
- Runtime timeline depends on node events + trace file; robust cancellation,
  retry, and durable resume are not yet implemented.
- LangGraph checkpointing currently emits compatibility warnings for custom
  Pydantic/dataclass types during msgpack deserialization; this is not blocking
  local runtime, but should be cleaned before relying on strict checkpoint mode.

## Backend and agents

- Deterministic extraction is fragile on complex requirements.
- Groq improves extraction only when a real key is configured.
- Agents are mostly deterministic functions or LLM wrappers.
- Prompt workflows, document-pack generated requirements, and scene revisions enter the
  compiled LangGraph graph; edit patch creation and version bookkeeping remain service-level.
- No robust cancellation/retry manager; async execution uses local threads.

## RAG and memory

- NVIDIA `baai/bge-m3` is the primary provider.
- Local `sentence-transformers` fallback, then hash as last resort; hash is not
  production quality.
- After a provider/dimension change, the local Qdrant index must be rebuilt with
  `POST /rag/reindex`; otherwise `/rag/search` returns `409 RAG_INDEX_DIMENSION_MISMATCH`.
- Local reranker is best-effort; passthrough if the model is unavailable.
- Memory is still limited, with incomplete semantic recall.

## Documents

- Document-pack is synchronous, 80 MB max.
- `/document-packs/capabilities` is honest and reports
  `document_pack_status=limited`.
- OCR is limited and depends on installed Tesseract + languages.
- Docling is import-only / not active by default.
- DXF extracts text/layers; DWG depends on a local converter.

## 3D and QA

- Real Blender is required for a real GLB.
- Blender fallback is rejected by default, but missing assets can still become
  visible procedural geometry during a real Blender generation.
- Geometry source of truth is `SceneSpec + parametric generator`; GLB is only
  the exported viewer result.
- Mesh QA v1 (`mesh_level_basic`) computes real bounding boxes from GLB
  accessors, but does **not** verify individual antenna HBA/azimuth from
  vertices and does **not** perform collision detection.
- No exact transform, material, or vendor-grade mesh dimension validation yet.
- Internal/CC-BY assets are not vendor-grade.

## Can wait

- WebSocket.
- Queue/job manager.
- Full LangGraph redesign.
- Advanced mesh-level QA.
- Production Docling.
- New frontend.
