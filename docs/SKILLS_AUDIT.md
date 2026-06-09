# Skills Audit

## Implemented

- Added repo-local skills under `.codex/skills`:
  - `agentic-3d-studio`
  - `backend-api-contract`
  - `threejs-telecom-viewer`

These skills are short project guardrails. They reinforce real backend integration, no permanent
mocks, GLB artifact loading, SSE/polling truth, document intelligence panels, QA visibility, asset
import modes, and required validation.

## External Skill Search

`npx skills find "react three frontend design"` found:

- `davila7/claude-code-templates@senior-frontend`
- `vercel-labs/json-render@react-three-fiber`
- `freshtechbro/claudedesignskills@react-three-fiber`
- several smaller React Three Fiber skills

## Decision

No external skill was installed in this pass.

Reason:

- the relevant external R3F skill inspection via `skills use` did not return reliably;
- project rules require reading skill content before installation;
- existing Build Web Apps, React, Browser, and project-local skills are enough for the current work;
- installing generic skills would add noise without proving alignment with this backend-first studio.

## Safe Usage Policy

- Install only repo-local or inspected external skills.
- Do not install broad frontend/design packs in bulk.
- Do not accept skills that encourage static/fake UI or ignore the real backend contract.
