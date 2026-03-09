# Progress Tracking

## Current Status: Feature Planning Active (Daemon + Proactive Messaging)

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

## Next Implementation Steps

### Phase 1: Config + Validation
- [ ] Add `PROACTIVE.md` template under `atom_agent/workspace/templates/`.
- [ ] Include `PROACTIVE.md` in workspace initialization behavior.
- [ ] Implement markdown+JSON parser for proactive task configuration.
- [ ] Add validation command: `atom-agent proactive validate`.
- [ ] Add inspection command: `atom-agent proactive show`.

### Phase 2: Daemon Core
- [ ] Add daemon runtime module (`atom_agent/daemon/`).
- [ ] Add one-cycle mode: `atom-agent daemon run --once`.
- [ ] Add loop mode with polling interval.
- [ ] Add workspace scanning across registered workspaces.

### Phase 3: Scheduler + State
- [ ] Implement task kinds: `once`, `cron`, `interval`.
- [ ] Implement jitter support for random/lively behavior.
- [ ] Persist per-task runtime state for restart safety.
- [ ] Add duplicate-send protection and retry/cooldown policy.

### Phase 4: Verification
- [ ] Unit tests: parser, schedule calculations, state persistence.
- [ ] Integration tests: multi-workspace daemon cycle and dispatch.
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
