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

## Contract Source

Normative behavioral rules remain in [agent_docs/proactive-task-rules.md](./proactive-task-rules.md). This plan maps those rules into implementation tasks and milestones.
