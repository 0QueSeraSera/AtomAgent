# Gateway-Centric IM Integration Progress

Date: 2026-03-10
Status: Phase 3 In Progress (Gateway Proactive Runtime + Daemon Removal Landed)

## Current Scope

Replace daemon-based proactive runtime with gateway-centric hosting for IM integration.
Deliver Feishu connectivity as the first supported IM channel, including operator connection guidance.

## Confirmed Decisions

1. Runtime owner: gateway process is the only long-running IM host.
2. v1 isolation: one gateway process per workspace.
3. Daemon runtime: remove completely (code + CLI command + tests).
4. Proactive ownership: proactive ticking happens inside gateway runtime.
5. Session/delivery split:
   - `session_key` => memory scope
   - channel target metadata => transport delivery scope
6. Feishu is required for v1 channel support; credentials can be manually provided.

## Plan Link

See: `agent_docs/plan.md`

## Execution Checklist

1. [x] Add channel runtime primitives (`channels/base.py`, `channels/manager.py`).
2. [x] Implement Feishu adapter (`channels/feishu.py`) for inbound/outbound messaging.
3. [x] Add Feishu config validation and startup readiness checks.
4. [x] Add gateway runtime host (`gateway/runtime.py`) and lifecycle wiring.
5. [x] Move proactive ticking into gateway runtime path.
6. [x] Add `atom-agent gateway run` command.
7. [x] Remove daemon package and daemon CLI command.
8. [x] Extend proactive schema for optional explicit transport target.
9. [x] Update tests from daemon-focused to gateway-focused coverage (including Feishu paths).
10. [ ] Run real runtime verification with Feishu adapter and real model response.
11. [x] Publish Feishu connection guide and troubleshooting in docs.

## Open Items

1. Proactive delivery policy default in gateway:
   - final response only (default) vs optional progress relay.
2. Channel offline behavior for proactive sends:
   - fail-fast vs retry/backoff.
3. Feishu transport mode choice for v1:
   - webhook vs socket mode.

## Implementation Notes (2026-03-10)

1. Landed channel runtime primitives:
   - `atom_agent/channels/base.py`
   - `atom_agent/channels/manager.py`
   - `atom_agent/channels/__init__.py`
2. Landed gateway runtime skeleton:
   - `atom_agent/gateway/runtime.py`
   - `atom_agent/gateway/__init__.py`
3. Added tests:
   - `tests/test_channels_manager.py`
   - `tests/test_gateway_runtime.py`
4. Validation run:
   - `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider tests/test_channels_manager.py tests/test_gateway_runtime.py`
   - Result: 5 passed.
5. Commits created in this commencement pass:
   - `0190f1e` feat(channels): add channel adapter contract and manager
   - `17351ce` feat(gateway): add runtime host for channels and agent loop
6. Phase 1.5 Feishu delivery implementation landed:
   - `atom_agent/channels/feishu.py`
   - `tests/test_channels_feishu.py`
   - webhook mapping, outbound send path, token fetch cache, dedup, allowlist checks
7. Gateway CLI command landed:
   - `atom_agent/cli/__main__.py` -> `atom-agent gateway run [--once]`
   - Feishu readiness checks with actionable startup errors
8. Feishu operator docs added:
   - `agent_docs/notes/feishu-connection-guide.md`
   - `README.md` gateway+Feishu quickstart section
9. Validation run (unit + integration-lite):
   - `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_channels_feishu.py tests/test_cli_gateway.py tests/test_channels_manager.py tests/test_gateway_runtime.py`
   - Result: 12 passed.
10. Real CLI readiness verification:
   - `atom-agent gateway run --once --workspace /tmp/atomagent-gw-verify-<pid>`
   - Result: gateway starts/stops and prints Feishu readiness summary.
11. Proactive schema extension landed:
   - `atom_agent/proactive/models.py` (`target` support on task and due models)
   - `atom_agent/proactive/parser.py` (validation for `target.channel/chat_id/reply_to/thread_id`)
   - `atom_agent/proactive/runtime.py` (session_key parsing + due message builder)
   - `atom_agent/agent/context.py` and `atom_agent/cli/__main__.py` render explicit target info
   - Commit: `f8eea88` `feat(proactive): add optional explicit target routing schema`
12. Gateway proactive ticking migrated from daemon path:
   - `atom_agent/gateway/runtime.py` polls `PROACTIVE.md`, evaluates due tasks, publishes to bus, persists runtime state
   - `atom_agent/agent/loop.py` system path now preserves `session_key_override` and proactive metadata
   - Commit: `a5ef909` `feat(gateway): run proactive polling and due-task dispatch`
13. Daemon package and CLI command removed:
   - deleted `atom_agent/daemon/` package
   - removed `atom-agent daemon ...` command from `atom_agent/cli/__main__.py`
   - removed `tests/test_daemon_service.py`, replaced coverage with gateway runtime proactive tests
   - Commit: `914571d` `refactor(runtime): remove daemon service and CLI command`
14. Validation run (gateway/proactive focused):
   - `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_cli_gateway.py tests/test_gateway_runtime.py tests/test_channels_feishu.py tests/test_channels_manager.py tests/test_proactive_parser.py tests/test_proactive_scheduler_state.py tests/test_proactive_runtime.py tests/test_context_proactive_brief.py tests/test_cli_proactive.py`
   - Result: 34 passed.
15. Real runtime verification status:
   - pending operator-provided real Feishu credentials and real model API key.
