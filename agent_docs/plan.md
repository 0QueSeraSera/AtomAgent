# Daemon + Proactive Messaging Plan

## Overview

This plan defines how AtomAgent should run silently in the background and proactively message users from workspace configuration.

The design keeps file-based context as the source of truth and introduces `PROACTIVE.md` per workspace for proactive behavior and scheduling.

## Goals

1. Run AtomAgent as a long-lived daemon process.
2. Support proactive messages with two scheduling styles:
   - Human-like occasional messages (randomized cadence)
   - Precise timestamp tasks (alarm-clock style)
3. Reuse existing workspace/session/memory/context infrastructure.
4. Support multiple workspaces in one daemon process.
5. Keep behavior observable and debuggable via logs and task state.

## Non-Goals (Initial)

1. Implementing every external channel adapter in this milestone.
2. Distributed multi-host scheduling.
3. Cloud-hosted orchestration.

## Product Requirements

1. A new `PROACTIVE.md` exists in each workspace and is empty/default-safe after workspace init.
2. Daemon scans all registered workspaces and only activates workspaces with enabled valid proactive tasks.
3. Tasks can be disabled/enabled without code change by editing workspace files.
4. Scheduler supports both randomized scheduling and exact-time scheduling.
5. Tasks survive daemon restart without duplicate firing.
6. Proactive runs use the same file-based context as interactive chat (`IDENTITY.md`, `SOUL.md`, `AGENTS.md`, `USER.md`, `TOOLS.md`, memory files).

## Architecture

### High-Level Flow

```text
Workspace Registry -> Workspace Scanner -> PROACTIVE.md Parser -> Due Task Evaluator
      -> Task Dispatcher -> AgentLoop Invocation -> Outbound Delivery
```

### Core Components

1. `atom_agent/proactive/models.py`
   - Dataclasses for proactive config and task definitions.

2. `atom_agent/proactive/parser.py`
   - Read `PROACTIVE.md`
   - Extract structured task config
   - Validate and return clear errors

3. `atom_agent/proactive/scheduler.py`
   - Determine next run and due tasks
   - Support `once`, `cron`, `interval` with optional jitter

4. `atom_agent/proactive/state.py`
   - Persist task runtime state per workspace (e.g., `.proactive/state.json`)
   - Track `last_run`, `next_run`, `last_status`, `last_error`

5. `atom_agent/daemon/service.py`
   - Main long-running process
   - Scan workspaces, evaluate schedules, dispatch due tasks

6. `atom_agent/daemon/runtime.py`
   - Per-workspace runtime wrapper around `MessageBus + AgentLoop`
   - Reuse loaded runtime to avoid re-init per task

7. CLI integration (`atom_agent/cli/__main__.py`)
   - `atom-agent daemon run [--once] [--poll-sec N]`
   - `atom-agent proactive validate [--workspace PATH]`
   - `atom-agent proactive show [--workspace PATH]`

## `PROACTIVE.md` Design

The file is markdown with a machine-readable JSON block.

Normative rules for parser/scheduler/daemon behavior are defined in:
- `agent_docs/proactive-task-rules.md`

~~~markdown
# Proactive Configuration

Optional policy notes:
- tone and personality rules
- safety and quiet-hours constraints

```json
{
  "version": 1,
  "enabled": true,
  "timezone": "Asia/Shanghai",
  "tasks": [
    {
      "id": "wake-up-alarm",
      "kind": "once",
      "at": "2026-03-10T07:30:00+08:00",
      "session_key": "telegram:123456",
      "prompt": "Send a wake-up reminder."
    },
    {
      "id": "daily-checkin",
      "kind": "cron",
      "cron": "0 10 * * *",
      "jitter_sec": 900,
      "session_key": "telegram:123456",
      "prompt": "Send a short friendly check-in."
    },
    {
      "id": "casual-ping",
      "kind": "interval",
      "every_sec": 21600,
      "jitter_sec": 5400,
      "session_key": "telegram:123456",
      "prompt": "Occasionally start a natural conversation."
    }
  ]
}
```
~~~

## Scheduling Semantics

1. `once`
   - Fires exactly once when `now >= at` and not already completed.
   - After a successful fire, scheduler marks it completed and it is no longer eligible.

2. `cron`
   - Evaluated using workspace timezone.
   - Optional `jitter_sec` adds bounded randomization to avoid robotic timing.

3. `interval`
   - Repeats every `every_sec`.
   - Optional `jitter_sec` shifts each run by random offset.

Your interpretation is correct:
- `once`: one-time and auto-disabled after firing.
- `cron`: periodic at calendar timestamps.
- `interval`: continuous periodic loop with configurable gaps.

## Normative Schedule Contract (Drift Prevention)

### Common Rules

1. All scheduler comparisons use timezone-aware datetimes.
2. Workspace `timezone` is required for `cron`; if missing, default to `UTC`.
3. `session_key` format is always `channel:chat_id`.
4. Task-level `enabled=false` excludes task from scheduling without deleting config.
5. Daemon stores per-task runtime state in `.proactive/state.json`.

### Jitter Rules

1. `jitter_sec` is delay-only (`0..jitter_sec`), never early-fire.
2. Jitter is sampled per occurrence, not once globally.
3. The sampled scheduled fire time is persisted as `next_run` to remain stable across restart.

### Downtime / Catch-Up Rules

1. `once`
   - If missed while daemon was down, run on next startup if `now >= at` and task not completed.
2. `cron`
   - On restart, run at most one catch-up execution (latest missed occurrence), then continue normal schedule.
3. `interval`
   - On restart, do not replay multiple missed intervals; schedule next run from current time plus interval/jitter.

### Non-Overlap Rules

1. Same task ID cannot run concurrently.
2. If a task is due while previous run is still in progress, skip that due tick and compute the next schedule point.
3. Execution status transitions:
   - `idle -> running -> success|failed -> idle`
4. Failed runs update `last_error` and can apply cooldown/backoff before next eligibility.

### Per-Type Deterministic Behavior

1. `once`
   - Inputs: `at`, optional `jitter_sec`.
   - Effective fire time: `at + sampled_delay`.
   - Post-success: mark `completed_at`, set `enabled=false` in runtime state.

2. `cron`
   - Inputs: `cron`, `timezone`, optional `jitter_sec`.
   - Base schedule is cron timestamp.
   - Effective fire time per occurrence: `base_time + sampled_delay`.
   - Next occurrence computed from cron expression, not from completion time.

3. `interval`
   - Inputs: `every_sec`, optional `jitter_sec`.
   - Next base time is previous effective fire time + `every_sec`.
   - Effective fire time: `base_time + sampled_delay`.
   - This keeps cadence consistent and avoids drift from variable task execution duration.

## Daemon Loop Contract

1. Poll cadence (`poll_sec`) controls how often due checks run.
2. For each cycle:
   - load/refresh workspace proactive config
   - load runtime state
   - compute due tasks
   - dispatch eligible tasks
   - persist updated state atomically
3. Config edits should be picked up without daemon restart.
4. Invalid workspace config should not crash daemon; it should be logged and skipped.

## Dispatch and Session Routing

### Decision
Use existing session key format (`channel:chat_id`) as the canonical target.

### Execution Path
1. Daemon selects due task with `session_key`.
2. Daemon creates inbound job targeting that session.
3. AgentLoop processes with normal context/memory/session history.
4. Outbound message is delivered through configured outbound dispatcher.

## Shared Context Strategy

Background daemon and interactive CLI share:
1. Workspace bootstrap files
2. Session files (`sessions/*.jsonl`)
3. Memory consolidation (`memory/MEMORY.md`, `memory/HISTORY.md`)

No separate context format for daemon mode.

## Phased Implementation

### Phase 1: Planning + Parsing
1. Add `PROACTIVE.md` template to workspace init.
2. Implement parser + validation.
3. Add `proactive validate/show` commands.

### Phase 2: Daemon Skeleton
1. Add `daemon run --once` for single evaluation cycle.
2. Add continuous loop (`--poll-sec`).
3. Persist state and ensure restart-safe behavior.

### Phase 3: Full Scheduling
1. Implement `once`, `cron`, `interval + jitter`.
2. Implement retry policy and error cooldown.
3. Add workspace-level enable/disable controls.

### Phase 4: Runtime Verification
1. Run with real LLM provider.
2. Verify timestamp correctness and randomization behavior.
3. Verify session continuity and proactive delivery in real interface.

## Testing Strategy

1. Unit tests
   - Parser validation and error cases
   - Scheduler due-time calculations
   - State persistence/idempotency

2. Integration tests
   - Daemon cycle dispatches due tasks into AgentLoop
   - Workspace scan behavior across multiple workspaces

3. Real runtime checks (required)
   - Run daemon with real provider and inspect logs
   - Verify actual proactive messages are emitted at expected times

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Duplicate sends after restart | Persist and atomically update task state |
| Invalid PROACTIVE format | Strict parser + CLI validate command |
| Robotic behavior | Use bounded jitter and random intervals |
| Drift between CLI and daemon behavior | Reuse AgentLoop and same workspace files |
| Silent failures | Structured logging + last_error in task state |

## Open Questions

1. What default outbound channel(s) should daemon support first beyond CLI?
2. Should overdue precise tasks fire immediately on restart or be skipped past tolerance?
3. Should task-level quiet hours be part of `PROACTIVE.md` v1 or v2?
