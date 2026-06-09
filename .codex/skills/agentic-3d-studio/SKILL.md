---
name: agentic-3d-studio
description: Use when designing, auditing, or modifying the Agentic Telecom 3D Studio frontend in this repo. Enforces real-backend UX, agent workflow visibility, QA transparency, document intelligence panels, edit/version/rollback flows, and no permanent mock studio screens.
---

# Agentic 3D Studio

Use this skill for `apps/frontend` changes that affect the studio shell, command center, inspector,
viewer, document intelligence dock, or product UX.

## Non-Negotiables

- Connect to the real FastAPI backend; do not add permanent fake workflow, QA, asset, or GLB data.
- Treat `SceneSpec`, backend status, events, versions, QA reports, and artifact endpoints as source of truth.
- Make fallback states visible: missing GLB, procedural asset, LLM fallback, SSE fallback, backend offline.
- Keep the app desktop-first, dense, readable, and operator-focused. Avoid marketing layout patterns.
- Do not hide warnings/errors behind raw JSON only; provide a readable product surface first.

## Workflow

1. Audit the endpoint/data shape before UI changes.
2. Keep generation, edit, version, rollback, download, events, document-pack, and asset inventory flows connected.
3. Prefer small focused React components over a monolithic studio screen.
4. Add UI state only for interaction, not for invented backend facts.
5. Validate with typecheck, tests, build, and a browser smoke against `127.0.0.1:5173`.

## UX Bar

- Top bar: backend, workflow, QA, version, generation mode, LLM/fallback, issues, downloads.
- Command center: real commands, useful quick actions, current operation, agent stages from events.
- Viewer: real GLB artifact, stable fit, reset/focus controls when available, clear empty/error state.
- Inspector: QA, warnings, assets, versions, diff, downloads in readable summaries before JSON.
- Dock: documents, provenance, events, memory with raw JSON only as a secondary detail.
