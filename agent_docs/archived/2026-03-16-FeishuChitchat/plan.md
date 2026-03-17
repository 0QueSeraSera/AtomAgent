# Active Plan

Date: 2026-03-14
Topic: Feishu proactive chitchat switch decoupled from session routing

## Goal

Decouple Feishu chitchat session routing from proactive-start permission so agent-initiated chitchat can be enabled/disabled explicitly.

## Decisions

1. One-user assumption for this workspace/runtime.
2. Feishu supports CLI-like session commands: `/new`, `/sessions`, `/resume`.
3. `/chitchat_on|off` controls only inbound routing into/out of chitchat history.
4. `/proactive_chitchat_on|off` controls whether agent may proactively start chitchat.
5. `/next_time` remains as backward-compatible alias to `/chitchat_off`.

## Implementation Steps

1. Persisted Feishu session routing state and command handling.
2. Add persisted per-chat proactive-chitchat enable flag in Feishu router.
3. Update adapter/gateway proactive path to use the new flag (not routing mode).
4. Add slash-command handling and help text for `/proactive_chitchat_on|off`.
5. Test coverage for router, adapter, and gateway runtime behaviors.

## Exit Criteria

1. Feishu messages route consistently across multiple normal sessions.
2. Chitchat proactive content only uses dedicated chitchat session scope.
3. Chitchat proactive sends are controlled by `/proactive_chitchat_on|off`.
4. `/chitchat_on|off` still controls routing independently.
5. Tests for these mechanics pass.
