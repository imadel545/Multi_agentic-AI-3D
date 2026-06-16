# Backend Product Readiness Report

Date: 2026-06-16.

## Verdict

`BACKEND_TRUTH_GATE_CONSOLIDATED`

The backend product contract is consolidated for Gate 2A frontend preparation
with visible limitations. It is based on the existing `/designs` workflow API
and `workflow_id`. No `/projects`, `/runs`, `job_id`, or new persistent state
is required for the next frontend.

This verdict does not mean the backend is vendor-grade or fully advanced. It
means the current truth surfaces are coherent enough for a frontend to consume
without inventing backend facts, provided the UI displays every limitation and
fallback explicitly.

## Product Mapping

| Product concept | Backend source | Status |
|---|---|---|
| Frontend project context | UI-level grouping around one or more designs | FUTURE |
| Run / generation | `workflow_id` | IMPLEMENTED_AND_TESTED |
| Scene plan | `SceneSpec` via `scene_spec.json` | IMPLEMENTED_AND_TESTED |
| Live timeline | `/designs/{workflow_id}/events/stream` + `/timeline-summary` | IMPLEMENTED_AND_TESTED |
| Viewer bundle | `/designs/{workflow_id}/viewer-bundle` | IMPLEMENTED_AND_TESTED |
| User issues | `/designs/{workflow_id}/user-issues` | IMPLEMENTED_AND_TESTED |
| Edit / rollback | `/edit`, `/versions`, rollback endpoint | IMPLEMENTED_AND_TESTED |

## Capability Classification

| Capability | Classification | Evidence |
|---|---|---|
| Prompt design workflow | IMPLEMENTED_AND_TESTED | `tests/e2e/test_telecom_generation_proof.py` |
| Requirement extraction | IMPLEMENTED_AND_TESTED | Deterministic parser + Groq path tests |
| RAG context | IMPLEMENTED_AND_TESTED_LIMITED | NVIDIA BGE-M3 API is tested with French telecom queries; only structured planning hints can influence `SceneSpec` |
| LangGraph orchestration | IMPLEMENTED_AND_TESTED | Runtime node events and workflow trace |
| Blender GLB generation | IMPLEMENTED_AND_TESTED | Golden parametric tests when Blender is available |
| Fallback Blender path | PARTIAL | Explicit, rejected by default for product quality |
| Mesh QA | PARTIAL | `mesh_level_basic`; no collision/RF/structural engineering |
| Document-pack ingestion | PARTIAL | Synchronous ZIP/PDF/OCR/DXF with limits |
| Vendor-grade assets | MISSING | Current assets are internal/CC-BY, not vendor-grade |
| Frontend app | MISSING | Old dashboard refused; rebuild pending |
| Permanent fake/demo output | MISSING | No placeholder GLB is accepted as product success |
| Runtime broker/cancellation | MISSING | SSE is local-process `push_sse` |

## Readiness Notes

- Public API responses expose backend URLs, not local filesystem paths.
- `workflow_trace.json` remains an audit artifact; it is not the primary UI
  contract.
- `SceneSpec` remains the source of truth. The future UI may label it "scene
  plan" but must consume `/artifacts/scene_spec`.
- Blender absence must be shown as degraded/non-product-grade.
- RAG retrieval must be shown honestly: `rag_context_count` is context volume,
  while `rag_planning_summary` tells whether structured hints influenced the
  plan. RAG is not used for extraction in v1.

## Verification Command

```bash
.venv/bin/python -m pytest tests/e2e/test_telecom_generation_proof.py -q
```
