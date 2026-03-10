# Gateway-Centric IM Integration Progress

Date: 2026-03-10
Status: Phase 1 Commenced (Channel + Gateway Skeleton Landed)

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
5. [ ] Move proactive ticking into gateway runtime path.
6. [x] Add `atom-agent gateway run` command.
7. [ ] Remove daemon package and daemon CLI command.
8. [ ] Extend proactive schema for optional explicit transport target.
9. [ ] Update tests from daemon-focused to gateway-focused coverage (including Feishu paths).
10. [ ] Run real runtime verification with Feishu adapter and real model response.
11. [x] Publish Feishu connection guide and troubleshooting in docs.

## Open Items

1. Proactive delivery policy default in gateway:
   - final response only (default) vs optional progress relay.
2. Channel offline behavior for proactive sends:
   - fail-fast vs retry/backoff.
3. Exact schema shape for optional target metadata in `PROACTIVE.md`.
4. Feishu transport mode choice for v1:
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
