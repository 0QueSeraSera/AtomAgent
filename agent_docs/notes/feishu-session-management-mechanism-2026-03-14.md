# Feishu Session Management: Current Mechanism and Requested Feature

Date: 2026-03-14  
Workspace: `AtomAgent`

## 1. Purpose

This document summarizes:
1. the current Feishu session/proactive mechanism implemented in AtomAgent, and
2. the requested feature contract from product requirements.

## 2. Requested Feature Contract (User Requirements)

The requested behavior is:

1. Single-user assumption:
   - Only one human user is considered.
   - No multi-human interaction arbitration is required.

2. Feishu multi-session behavior should mirror CLI:
   - Feishu supports multiple sessions per chat.
   - Session lifecycle uses command semantics similar to CLI (`/new`, `/sessions`, `/resume`).

3. Proactive chitchat must have isolated session scope and explicit control commands:
   - Chitchat proactive messages use their own dedicated memory session.
   - Chitchat session routing is enabled with `/chitchat_on` and disabled with `/chitchat_off`.
   - Agent-initiated chitchat starts are controlled independently with `/proactive_chitchat_on` and `/proactive_chitchat_off`.
   - Legacy `/next_time` remains as compatibility alias to turn chitchat off.

## 3. Current Mechanism (As Implemented)

### 3.1 Session Scope Model

1. Normal Feishu session scope (memory key):
   - `feishu:<chat_id>` (default normal session)
   - `feishu:<chat_id>__<session_id>` (named/UUID normal session)

2. Dedicated chitchat session scope:
   - `feishu:<chat_id>__chitchat`

3. Backward compatibility:
   - Legacy key style `feishu:chitchat:<chat_id>` is still parse-compatible.

### 3.2 Persisted Router State

1. Feishu router persists chat session state in workspace:
   - `<workspace>/.feishu_sessions.json`
2. Stored data includes:
   - active normal session id
   - known normal session ids
   - chitchat routing enabled flag
   - proactive chitchat enabled flag
   - chitchat activity metadata
3. State is loaded on startup and updated atomically on changes.

### 3.3 Feishu Command Semantics

Commands are intercepted by the Feishu session router and forwarded with structured metadata.

1. `/new`:
   - creates and activates a new normal session for this Feishu chat.
2. `/sessions`:
   - requests session listing for this Feishu chat scope.
3. `/resume <session-id|session-key>`:
   - activates an existing normal session.
4. `/chitchat_on`:
   - enables chitchat mode for the chat and routes future inbound chat to chitchat session.
5. `/chitchat_off`:
   - disables chitchat mode and routes back to active normal session.
6. `/proactive_chitchat_on`:
   - allows agent-initiated proactive chitchat delivery for this chat.
7. `/proactive_chitchat_off`:
   - suppresses agent-initiated proactive chitchat delivery for this chat.
8. `/next_time`:
   - compatibility alias of `/chitchat_off`.

### 3.4 Agent-Level Response Behavior

Agent slash-command handling returns deterministic responses for Feishu session commands:

1. `/new` -> acknowledge started session id
2. `/sessions` -> return session list with active marker
3. `/resume` -> success/error response
4. `/chitchat_on` -> confirm routing ON
5. `/chitchat_off` and `/next_time` -> confirm routing OFF or already OFF
6. `/proactive_chitchat_on` -> confirm proactive start ON or already ON
7. `/proactive_chitchat_off` -> confirm proactive start OFF or already OFF
8. `/help` -> includes Feishu-specific session/chitchat commands

### 3.5 Proactive Chitchat Routing

1. Proactive tasks marked `chitchat_mode: true` are routed to Feishu chitchat session scope (`feishu:<chat_id>__chitchat`).
2. If proactive chitchat is OFF, Feishu chitchat proactive delivery is suppressed (not sent), even when normal/chitchat routing mode changes.
3. Suppressed tasks are marked finished in runtime state to avoid repeated immediate retrigger.
4. Non-chitchat proactive behavior remains unchanged for other channels and normal Feishu tasks.

### 3.6 Gateway Integration

1. `atom-agent gateway run` now auto-attaches FeishuSessionRouter to FeishuAdapter.
2. Gateway readiness output includes the session-state file path when available.

## 4. Mapping: Requested vs Current

1. One-user-only assumption: satisfied.
2. Feishu multi-session + command control mirroring CLI: satisfied.
3. Dedicated proactive chitchat session + independent proactive-start switch: satisfied.
4. `/chitchat_on|off` routing and proactive ON/OFF controls are decoupled to avoid command ambiguity.
5. `/next_time` ambiguity: resolved by treating it as compatibility alias to routing OFF behavior.

## 5. Operational Notes

1. Use `/sessions` to inspect per-chat Feishu session keys.
2. Use `/resume` to move between normal memory sessions.
3. Use `/proactive_chitchat_on` when agent-initiated topic starts are desired.
4. Use `/chitchat_on` only when you want inbound replies routed into chitchat history.
5. For debugging routing state, inspect `<workspace>/.feishu_sessions.json`.

## 6. Relevant Source Files

1. `atom_agent/channels/feishu_session.py`
2. `atom_agent/channels/feishu.py`
3. `atom_agent/agent/loop.py`
4. `atom_agent/gateway/runtime.py`
5. `atom_agent/cli/__main__.py`
6. `tests/test_feishu_session_router.py`
7. `tests/test_channels_feishu.py`
8. `tests/test_gateway_runtime.py`
