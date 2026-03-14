# Active Plan

Date: 2026-03-14
Topic: Feishu session management cleanup + proactive chitchat control

## Goal

Align Feishu session behavior with CLI multi-session controls while isolating proactive chitchat into a dedicated user-controlled session.

## Decisions

1. One-user assumption for this workspace/runtime.
2. Feishu supports CLI-like session commands: `/new`, `/sessions`, `/resume`.
3. Proactive chitchat uses a dedicated memory scope and is controlled by `/chitchat_on` and `/chitchat_off`.
4. `/next_time` remains as backward-compatible alias to `/chitchat_off`.

## Implementation Steps

1. Persisted Feishu session routing state and command handling.
2. Adapter routing integration + proactive chitchat suppression when OFF.
3. Agent slash-command responses for Feishu command workflow.
4. Gateway proactive override for Feishu chitchat memory scope.
5. Test coverage for router, adapter, and gateway runtime behaviors.

## Exit Criteria

1. Feishu messages route consistently across multiple normal sessions.
2. Chitchat proactive content only uses dedicated chitchat session scope.
3. Chitchat proactive sends are disabled when user turns chitchat OFF.
4. Tests for these mechanics pass.
