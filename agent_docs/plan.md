# MVP Plan: Self-Improve Orchestration + Progressive Memory

Date: 2026-03-11

## Goal
Implement an MVP that enables:
1. Self-improvement to be triggered via proactive tasks and explicit tools (not hard-coded in agent loop policy).
2. Memory/experience to support project scope with brief-first prompt injection and on-demand expansion.

## Scope (This Iteration)

### Commit 1: Project-scoped memory + brief-first context
- Introduce structured memory directories:
  - `memory/global/`
  - `memory/projects/<project_id>/`
- Keep existing `memory/MEMORY.md` + `memory/HISTORY.md` behavior as compatibility.
- Add helpers in `MemoryStore` for project memory paths and compact brief generation.
- Update context builder to inject only compact brief(s), not full project memory.

### Commit 2: Progressive memory tools
- Add model-facing tools:
  - `memory_search` (returns memory handles/snippets)
  - `memory_read` (returns full content for selected handle)
- Register them as default tools.
- Ensure tools read from project/global memory safely with bounded output.

### Commit 3: Proactive template/docs/tests
- Update `PROACTIVE.md` template with a safe self-improvement task example.
- Add tests for:
  - brief-first context behavior
  - memory tool behavior
  - default tool registration updates
- Update `agent_docs/progress.md` with outcomes.

## Non-Goals
- No hard-coded self-improvement loop in `AgentLoop`.
- No autonomous merge/push behavior.
- No full-blown ranking/learning policy in this MVP.

## Safety Constraints
- Brief-first prompt design to avoid context bloat.
- On-demand memory expansion only via explicit tool calls.
- No destructive shell actions introduced by this plan.
