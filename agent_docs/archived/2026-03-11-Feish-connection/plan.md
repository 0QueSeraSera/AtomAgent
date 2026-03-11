# Gateway-Centric IM Integration Plan

Date: 2026-03-10
Status: Active
Branch: `feat/connect-to-im-apps`

## Objective

Implement IM integration with a single long-running gateway host process and remove the standalone daemon runtime.
Deliver Feishu as the first supported third-party channel with clear operator setup guidance.

## Agreed Product Decisions

1. Gateway is the central runtime host for IM mode:
   - channel ingress/egress
   - `AgentLoop` hosting
   - proactive task ticking/dispatch
2. Standalone daemon runtime and CLI command are removed.
3. v1 isolation model: one gateway process serves one workspace.
4. Session semantics:
   - `session_key` is memory scope
   - delivery target is transport scope (`channel/chat_id`, plus optional reply/thread metadata)
5. Proactive scheduling has one canonical active path in gateway mode (no dual schedulers).

## Non-Goals (v1)

1. Multi-workspace routing inside one gateway process.
2. Group/thread-perfect semantics for every IM platform.
3. Advanced retry/backoff orchestration for offline channels.

## v1 Channel Commitment

1. Feishu is mandatory in v1:
   - inbound message receive
   - outbound message send
   - basic allowlist/auth validation
2. WhatsApp remains optional/follow-up after Feishu baseline is stable.

## Architecture Target

Inbound path:
`IM Adapter -> ChannelManager -> MessageBus.inbound -> AgentLoop.run`

Outbound path:
`AgentLoop -> MessageBus.outbound -> ChannelManager -> IM Adapter send`

Proactive path:
`Gateway proactive ticker -> due task -> MessageBus.inbound/system trigger -> AgentLoop -> outbound -> ChannelManager`

## Implementation Phases

### Phase 1: Gateway Skeleton and Channel Runtime

1. Add `atom_agent/channels/base.py` adapter contract:
   - `start()`, `stop()`, `send()`
   - inbound callback wiring to bus publish
2. Add `atom_agent/channels/manager.py`:
   - lifecycle management for adapters
   - outbound dispatcher loop consuming bus outbound
3. Add `atom_agent/gateway/runtime.py`:
   - create bus + agent loop + channel manager
   - start/stop orchestration and graceful shutdown
4. Add `atom_agent/gateway/__init__.py`.

### Phase 1.5: Feishu Channel Delivery (Required v1)

1. Add Feishu adapter implementation under `atom_agent/channels/feishu.py`.
2. Support required config inputs (manual secrets provided by operator):
   - `app_id`
   - `app_secret`
   - optional `verification_token` / signing secret (based on transport mode)
   - optional allowlist and group policy settings
3. Map Feishu events to internal `InboundMessage`:
   - stable `channel="feishu"`
   - stable `chat_id` strategy for session continuity
4. Implement Feishu outbound send path in channel adapter.
5. Add dedup/basic guard for repeated webhook/event delivery.

### Phase 2: Proactive Migration into Gateway

1. Extract reusable proactive ticking engine from daemon service into proactive module runtime helpers.
2. Integrate proactive loop into gateway runtime.
3. Ensure due-task dispatch enters same agent path as normal messages.
4. Disable dual scheduling behavior in gateway mode.

### Phase 3: CLI Surface and Daemon Removal

1. Add `atom-agent gateway run` command and runtime options.
2. Remove `atom-agent daemon ...` CLI commands.
3. Delete `atom_agent/daemon/` package.
4. Update docs and command help to gateway-only runtime model.
5. Add connection readiness checks for Feishu config (fail-fast with actionable errors).

### Phase 4: Proactive Routing Hardening

1. Extend proactive task schema to support optional explicit target fields:
   - `target.channel`
   - `target.chat_id`
   - optional `target.reply_to`
   - optional `target.thread_id`
2. Keep backward compatibility with current `session_key` parsing fallback.
3. Ensure transport routing is not inferred from memory key when explicit target exists.

### Phase 5: Validation and E2E

1. Unit tests:
   - channel manager lifecycle and dispatch
   - proactive parser/validation for new target fields
   - gateway startup/shutdown behavior
   - Feishu adapter config validation and event mapping
2. Integration tests:
   - inbound IM -> agent -> outbound IM path
   - proactive due task dispatch exactly once
   - no duplicate sends when legacy scheduler is inactive
   - Feishu inbound/outbound flow with adapter-level mocks/fakes
3. Real runtime verification:
   - run gateway with real provider and Feishu adapter
   - verify inbound reply and proactive delivery in actual interface

## File-Level Change Plan

Add:
1. `atom_agent/channels/base.py`
2. `atom_agent/channels/manager.py`
3. `atom_agent/channels/feishu.py`
4. `atom_agent/gateway/__init__.py`
5. `atom_agent/gateway/runtime.py`
6. Feishu setup guide (README section and/or `agent_docs/notes/feishu-connection-guide.md`)
7. Gateway-focused tests (`tests/test_gateway_*.py`, `tests/test_channels_*.py`)

Modify:
1. `atom_agent/cli/__main__.py` (add gateway cmd, remove daemon cmd)
2. `atom_agent/agent/loop.py` (ensure scheduler interplay is unambiguous in gateway mode)
3. `atom_agent/proactive/models.py` and `atom_agent/proactive/parser.py` (target fields)
4. `README.md` (Feishu setup and connection troubleshooting)

Delete:
1. `atom_agent/daemon/__init__.py`
2. `atom_agent/daemon/runtime.py`
3. `atom_agent/daemon/service.py`
4. `tests/test_daemon_service.py`

## Risks and Mitigations

1. Duplicate proactive dispatch:
   - mitigation: single scheduler ownership in gateway mode; explicit tests.
2. Misrouting outbound on complex channel semantics:
   - mitigation: target fields + per-channel metadata contract.
2.1. Feishu credential/setup errors causing startup failures:
   - mitigation: startup validation + explicit connection checklist in docs.
3. Regression in existing CLI workflows:
   - mitigation: preserve direct CLI chat path and add coverage for chat + session commands.
4. Incomplete runtime shutdown:
   - mitigation: structured start/stop ordering and cancellation tests.

## Acceptance Criteria

1. No daemon command/package remains.
2. Gateway command can run continuously and host agent + channel IO + proactive ticking.
3. IM inbound and proactive outbound both deliver through channel manager.
4. Feishu can be connected using manually provided credentials with documented steps.
5. Gateway provides actionable guidance/errors when Feishu config is incomplete/invalid.
6. Existing workspace/session persistence behavior remains intact.
7. Test suite updated and passing for replaced runtime model.

## Feishu Connection Guidance Deliverables

1. Operator setup document includes:
   - Feishu developer console steps
   - required permissions/events
   - webhook or socket mode configuration
   - required AtomAgent config/env entries
2. Gateway startup output includes a concise Feishu readiness summary.
3. Troubleshooting section includes common errors:
   - invalid app credentials
   - signature/token verification mismatch
   - missing event subscriptions/permissions
