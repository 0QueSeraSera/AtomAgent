# Proactive Task Rules (Normative)

## Purpose

This document defines the authoritative rules for proactive task behavior in AtomAgent.
It is the implementation contract for parser, scheduler, daemon loop, and context loading.

## Scope

This applies to:
1. `PROACTIVE.md` authoring and parsing.
2. Scheduler behavior for `once`, `cron`, and `interval`.
3. Daemon runtime execution and state updates.
4. Agent permissions to read and edit proactive configuration.
5. Context injection of proactive task brief into model input.

## Source of Truth

1. Static config: workspace `PROACTIVE.md`.
2. Runtime state: workspace `.proactive/state.json`.
3. In case of conflict:
   - `PROACTIVE.md` controls desired configuration.
   - `.proactive/state.json` controls runtime progress (`last_run`, `next_run`, completion, cooldown).

## `PROACTIVE.md` Contract

1. File format:
   - Markdown text plus exactly one JSON configuration block.
2. Required top-level fields:
   - `version` (int)
   - `enabled` (bool)
   - `tasks` (array)
3. Optional top-level fields:
   - `timezone` (IANA tz, default `UTC`)
4. Task required fields:
   - `id` (unique within workspace)
   - `kind` (`once` | `cron` | `interval`)
   - `session_key` (`channel:chat_id`)
   - `prompt` (text instruction for proactive run)
5. Task type-specific required fields:
   - `once`: `at` (ISO datetime with timezone)
   - `cron`: `cron` (5-field expression)
   - `interval`: `every_sec` (integer > 0)
6. Optional task fields:
   - `enabled` (default `true`)
   - `jitter_sec` (integer >= 0)
   - `metadata` (object)

## Context Injection Rule

1. A compact proactive brief must be loaded into agent context like other workspace context files.
2. The brief is derived from parsed `PROACTIVE.md` and injected as a dedicated section:
   - Section label: `## PROACTIVE.md (brief)`
3. Brief content should include:
   - workspace proactive enabled/disabled
   - timezone
   - active task count
   - per-task summary (`id`, `kind`, target `session_key`, schedule description)
4. If parsing fails:
   - include a warning line in the brief that config is invalid
   - do not schedule invalid tasks
5. The brief is informational context, not a scheduler state source.

## Agent Authority to Edit `PROACTIVE.md`

1. The agent is explicitly allowed to create and edit `PROACTIVE.md`, same as other context files.
2. Agent edits must preserve machine-readability:
   - keep valid JSON block
   - keep required fields
   - keep unique task IDs
3. Agent should prefer minimal diffs:
   - modify only affected tasks/fields
   - avoid reformat churn that obscures review
4. Agent may perform autonomous edits only when:
   - user requested scheduling changes, or
   - existing config is invalid and repair is necessary for requested behavior
5. After editing, agent should validate and report:
   - what changed
   - whether config is valid

## Scheduler Rules

1. `once`:
   - fire once when `now >= at` (after jitter if configured)
   - mark completed after success
2. `cron`:
   - evaluate by configured timezone
   - each occurrence may apply delay-only jitter
3. `interval`:
   - repeat every `every_sec`
   - next base time is previous effective fire time plus `every_sec`
4. Common:
   - jitter is delay-only (`0..jitter_sec`)
   - no concurrent runs for same task `id`
   - due tasks while running are skipped, then next run is recalculated

## Restart and Catch-Up Rules

1. `once`: run pending missed task after restart.
2. `cron`: at most one catch-up run after restart, then continue normal cadence.
3. `interval`: do not replay all missed intervals; resume forward schedule.

## Error Handling and Cooldown

1. Failed run updates `last_error` and `last_status=failed`.
2. Scheduler may apply cooldown/backoff before next eligibility.
3. Invalid task definitions are skipped with explicit log entries.
4. One invalid workspace must not stop daemon processing of other workspaces.

## Daemon Loop Rules

Each cycle must:
1. scan registered workspaces
2. load and validate `PROACTIVE.md`
3. load runtime state
4. compute due tasks
5. dispatch eligible tasks
6. persist state atomically

Config edits must be hot-reloaded without daemon restart.

## Observability

Minimum structured fields for logs:
1. `workspace`
2. `task_id`
3. `kind`
4. `session_key`
5. `scheduled_time`
6. `dispatch_time`
7. `status`
8. `error` (if any)

## Change Control

1. Any behavior change to scheduling semantics must update this document first.
2. Parser/scheduler tests must reference this document as the contract.
