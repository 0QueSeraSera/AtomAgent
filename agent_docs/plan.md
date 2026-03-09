# Daemon Proactive Messaging Implementation Plan

## Objective

Implement a workspace-driven daemon mode so AtomAgent can proactively send messages without an interactive CLI session.

This plan turns `PROACTIVE.md` into executable behavior while reusing existing `AgentLoop`, session storage, memory, and workspace context files.

## Definition of Done

1. `PROACTIVE.md` is included in workspace initialization and can be validated from CLI.
2. A daemon command scans registered workspaces and schedules proactive tasks.
3. Supported task kinds in v1: `once`, `cron`, `interval` with delay-only jitter.
4. Task runtime state is persisted and restart-safe (no duplicate once sends).
5. Dispatched proactive runs use the same context + session pipeline as interactive chat.
6. End-to-end run is verified using a real provider and runtime logs.

## Scope

### In Scope

1. Parser + validation for markdown file with machine-readable JSON block.
2. Scheduling engine for due-time computation and jitter handling.
3. Daemon service loop with workspace scanning and task dispatch.
4. CLI commands for daemon run and proactive config inspection.
5. Runtime state persistence under workspace-local `.proactive/`.

### Out of Scope (v1)

1. Distributed scheduling across multiple hosts.
2. External coordinator/queue dependencies.
3. Channel-specific delivery plugins beyond existing session routing path.

## Existing Baseline

Relevant modules already present in repository:

1. `atom_agent/agent/loop.py` for message processing lifecycle.
2. `atom_agent/bus/events.py` and `atom_agent/bus/queue.py` for inbound/outbound events.
3. `atom_agent/session/manager.py` for session persistence.
4. `atom_agent/workspace/manager.py` and workspace template system.
5. `atom_agent/cli/__main__.py` and CLI command groups.

## Architecture Direction

### Control Flow

```text
Workspace Registry -> PROACTIVE.md Load/Validate -> Scheduler Due Check
-> Daemon Dispatch -> AgentLoop Run -> Outbound Message -> State Persist
```

### New Modules

1. `atom_agent/proactive/models.py`
   - Typed structures for config + tasks + runtime metadata.
2. `atom_agent/proactive/parser.py`
   - Parse markdown/JSON block and return normalized config.
3. `atom_agent/proactive/scheduler.py`
   - Compute eligibility and next fire times for `once`/`cron`/`interval`.
4. `atom_agent/proactive/state.py`
   - Load/save `.proactive/state.json` with atomic writes.
5. `atom_agent/daemon/service.py`
   - Long-running poll loop and workspace orchestration.
6. `atom_agent/daemon/runtime.py`
   - Workspace runtime wrapper around shared `AgentLoop` execution path.

## Implementation Phases

### Phase 1: Config Surface and Validation

1. Add `PROACTIVE.md` template to workspace templates.
2. Ensure workspace init creates default-safe file.
3. Implement parser and strict validation errors.
4. Add CLI: `atom-agent proactive validate`.
5. Add CLI: `atom-agent proactive show`.

### Phase 2: Scheduler and Runtime State

1. Implement per-kind scheduling rules (`once`, `cron`, `interval`).
2. Implement delay-only jitter and deterministic `next_run` persistence.
3. Persist runtime state at `.proactive/state.json`.
4. Enforce non-overlap per task ID.

### Phase 3: Daemon Loop and Dispatch

1. Add CLI: `atom-agent daemon run --once`.
2. Add continuous mode with `--poll-sec`.
3. Scan all registered workspaces each cycle.
4. Dispatch due tasks using canonical `session_key` target.
5. Keep invalid workspace configs isolated (log + skip).

### Phase 4: Verification and Hardening

1. Unit tests for parser/scheduler/state.
2. Integration tests for one-cycle and multi-workspace daemon runs.
3. Real provider verification with runtime logs.
4. Validate restart behavior and duplicate-send prevention.

## Detailed Work Packages

### Work Package A: Workspace Template + CLI Surface

1. Add `atom_agent/workspace/templates/PROACTIVE.md` with default disabled config.
2. Update workspace init logic to always materialize template.
3. Extend CLI command tree with `proactive validate` and `proactive show`.
4. Ensure CLI output shows parse errors with task IDs and offending fields.

### Work Package B: Proactive Config Parsing

1. Implement JSON block extraction from markdown content.
2. Enforce required schema for top-level and task-specific fields.
3. Normalize defaults (`enabled=true`, timezone fallback) in parser output.
4. Return machine-usable error objects for CLI and daemon logging.

### Work Package C: Schedule Engine + Runtime State

1. Build due-check API with `now` injection for deterministic tests.
2. Persist per-task runtime fields (`next_run`, `last_run`, `last_status`, `last_error`).
3. Implement jitter sampling per occurrence and persist effective timestamp.
4. Guarantee atomic state writes to avoid corruption on interrupted process.

### Work Package D: Daemon Service and Dispatch

1. Implement one-cycle service entrypoint (`--once`) for integration tests.
2. Implement poll loop with workspace reload on each cycle.
3. Convert due task to normal `InboundMessage` against canonical `session_key`.
4. Serialize task execution per task ID to prevent overlap.
5. Log per-task lifecycle with structured fields for auditability.

### Work Package E: Context and Behavior Consistency

1. Inject compact proactive brief into context build path.
2. Keep brief informational only; runtime state remains in `.proactive/state.json`.
3. Ensure daemon uses same memory/session persistence files as interactive mode.

## Acceptance Gates

### Gate 1 (After Phase 1)

1. New workspace contains `PROACTIVE.md`.
2. `atom-agent proactive validate` exits non-zero on malformed config.
3. `atom-agent proactive show` prints normalized task summary for valid config.

### Gate 2 (After Phase 2)

1. Scheduler test suite covers `once`, `cron`, `interval`, jitter, and restart cases.
2. `.proactive/state.json` survives repeated daemon cycles without schema drift.
3. Re-running schedule computation with same state does not duplicate `once` dispatch.

### Gate 3 (After Phase 3)

1. `atom-agent daemon run --once` dispatches only due enabled tasks.
2. Invalid config in one workspace does not block other workspaces in same cycle.
3. Two due tasks for different IDs can run independently; same ID is non-overlapping.

### Gate 4 (After Phase 4)

1. Real provider run confirms proactive output reaches target session.
2. Restart test confirms no duplicate sends for completed `once` task.
3. Runtime logs include enough fields to reconstruct task timeline.

## Contract Source

Normative behavioral rules remain in [agent_docs/proactive-task-rules.md](./proactive-task-rules.md). This plan maps those rules into implementation tasks and milestones.
