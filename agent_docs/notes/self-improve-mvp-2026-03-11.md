# Self-Improve MVP Notes (2026-03-11)

## Decisions
- Self-improvement behavior is not hard-coded into `AgentLoop`.
- Trigger surfaces are:
  - user-invoked tool calls (explicit action)
  - proactive scheduled prompts via `PROACTIVE.md`

## Memory Strategy
- Memory structure supports:
  - `memory/global/`
  - `memory/projects/<project_id>/`
- Prompt injection is brief-first:
  - global brief + active project brief only
  - no full project memory dump into system prompt
- Full retrieval is progressive:
  - `memory_search` -> handles/snippets
  - `memory_read` -> full entry by handle

## Operational Pattern
1. Identify candidate improvement from project memory and recent outcomes.
2. Delegate code changes to external coding assistant in isolated worktree.
3. Verify with tests/lint.
4. Record outcome back into project memory artifacts.
