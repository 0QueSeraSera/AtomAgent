# Progress Tracking

## Current Status: Implementation Active (Daemon + Proactive Messaging)

## Scope

Feature: background daemon runtime with proactive message scheduling (randomized and precise timestamp tasks), driven by workspace `PROACTIVE.md`.

## Worktree / Branch

- Worktree: `/Users/alive/workspace/OSS_contribute/AtomAgent-Workspace/atomAgent-worktree-feat-daemon-proactive`
- Branch: `feat/daemon-proactive-messaging`

## Completed in This Planning Pass (2026-03-09)

- [x] Created isolated worktree and branch for this feature.
- [x] Reviewed current architecture:
  - `AgentLoop`
  - `MessageBus` / `ProactiveScheduler`
  - workspace/config/session management
  - CLI entry points
- [x] Archived deprecated docs:
  - `agent_docs/plan.md` -> `agent_docs/archived/file-based-context/plan.md`
  - `agent_docs/progress.md` -> `agent_docs/archived/file-based-context/progress.md`
- [x] Replaced planning docs with new daemon/proactive-focused plan.
- [x] Clarified normative scheduling contract in `agent_docs/plan.md` to prevent drift across implementations:
  - precise `once`/`cron`/`interval` semantics
  - jitter behavior
  - downtime catch-up behavior
  - non-overlap and daemon loop rules
- [x] Added authoritative proactive rules document:
  - `agent_docs/proactive-task-rules.md`
  - includes context-brief injection policy and agent edit authority for `PROACTIVE.md`

## Planning Refresh Update (2026-03-09)

- [x] Rebuilt `agent_docs/plan.md` with a tighter implementation-focused structure.
- [x] Added file-level work packages and phase acceptance gates.
- [x] Added explicit stepped commit sequence for implementation execution.
- [x] Committed planning refresh in stepped commits:
  - `c110f67` docs(plan): rebuild daemon proactive implementation skeleton
  - `e5cbefb` docs(plan): add work packages and phase acceptance gates

## Implementation Update (2026-03-09)

- [x] Added workspace proactive template and bootstrap integration:
  - `atom_agent/workspace/templates/PROACTIVE.md`
  - workspace init now creates `PROACTIVE.md`
- [x] Added proactive config parser/models package:
  - `atom_agent/proactive/models.py`
  - `atom_agent/proactive/parser.py`
  - structured validation errors for CLI/daemon
- [x] Added proactive CLI commands:
  - `atom-agent proactive validate`
  - `atom-agent proactive show`
- [x] Added scheduler and persistent runtime state:
  - `atom_agent/proactive/scheduler.py`
  - `atom_agent/proactive/state.py`
  - state persisted at `.proactive/state.json`
- [x] Added daemon runtime and service:
  - `atom_agent/daemon/runtime.py`
  - `atom_agent/daemon/service.py`
  - CLI: `atom-agent daemon run [--once] [--poll-sec N]`
- [x] Added proactive brief injection into agent context:
  - `## PROACTIVE.md (brief)` section in system prompt
  - includes parse warnings when config is invalid
- [x] Fixed CLI package entry-point exit-code propagation:
  - `python -m atom_agent` now returns subcommand non-zero exit codes
- [x] Added tests:
  - parser: `tests/test_proactive_parser.py`
  - CLI proactive: `tests/test_cli_proactive.py`
  - scheduler/state: `tests/test_proactive_scheduler_state.py`
  - daemon integration: `tests/test_daemon_service.py`
  - context brief: `tests/test_context_proactive_brief.py`

### Implementation Commits (Stepped)

- `fb96906` feat(proactive): add PROACTIVE template and parser models
- `d385d55` feat(cli): add proactive validate/show commands
- `cbbdc50` feat(proactive): add scheduler and persistent runtime state
- `92b52bf` feat(daemon): add daemon run --once and polling loop
- `d84fe01` feat(agent): inject proactive brief into system context

## Next Implementation Steps

### Phase 1: Config + Validation
- [x] Add `PROACTIVE.md` template under `atom_agent/workspace/templates/`.
- [x] Include `PROACTIVE.md` in workspace initialization behavior.
- [x] Implement markdown+JSON parser for proactive task configuration.
- [x] Add validation command: `atom-agent proactive validate`.
- [x] Add inspection command: `atom-agent proactive show`.

### Phase 2: Daemon Core
- [x] Add daemon runtime module (`atom_agent/daemon/`).
- [x] Add one-cycle mode: `atom-agent daemon run --once`.
- [x] Add loop mode with polling interval.
- [x] Add workspace scanning across registered workspaces.

### Phase 3: Scheduler + State
- [x] Implement task kinds: `once`, `cron`, `interval`.
- [x] Implement jitter support for random/lively behavior.
- [x] Persist per-task runtime state for restart safety.
- [ ] Add duplicate-send protection and retry/cooldown policy.

### Phase 4: Verification
- [x] Unit tests: parser, schedule calculations, state persistence.
- [x] Integration tests: multi-workspace daemon cycle and dispatch.
- [ ] Real runtime verification with live provider and logs.
- [ ] Manual verification of exact timestamp alarms and randomized proactive cadence.

## Key Risks

1. Duplicate proactive sends on restart.
2. Invalid/ambiguous `PROACTIVE.md` authoring by users.
3. Outbound routing mismatch between daemon and interactive mode.
4. Timezone and DST edge cases for precise tasks.

## Mitigation Notes

1. Persist task state atomically and track idempotency markers.
2. Use strict schema validation plus CLI validator.
3. Route via canonical `session_key` (`channel:chat_id`) and shared `AgentLoop` path.
4. Enforce explicit timezone in config with deterministic schedule calculations.

## Blockers

- No hard blocker for implementation start.
- Product decision needed: first supported outbound channel(s) for daemon besides local CLI display.
