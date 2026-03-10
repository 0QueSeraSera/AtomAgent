# Gateway-Centric IM Integration Progress

Date: 2026-03-10
Status: Planning Complete, Implementation Not Started

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

1. [ ] Add channel runtime primitives (`channels/base.py`, `channels/manager.py`).
2. [ ] Implement Feishu adapter (`channels/feishu.py`) for inbound/outbound messaging.
3. [ ] Add Feishu config validation and startup readiness checks.
4. [ ] Add gateway runtime host (`gateway/runtime.py`) and lifecycle wiring.
5. [ ] Move proactive ticking into gateway runtime path.
6. [ ] Add `atom-agent gateway run` command.
7. [ ] Remove daemon package and daemon CLI command.
8. [ ] Extend proactive schema for optional explicit transport target.
9. [ ] Update tests from daemon-focused to gateway-focused coverage (including Feishu paths).
10. [ ] Run real runtime verification with Feishu adapter and real model response.
11. [ ] Publish Feishu connection guide and troubleshooting in docs.

## Open Items

1. Proactive delivery policy default in gateway:
   - final response only (default) vs optional progress relay.
2. Channel offline behavior for proactive sends:
   - fail-fast vs retry/backoff.
3. Exact schema shape for optional target metadata in `PROACTIVE.md`.
4. Feishu transport mode choice for v1:
   - webhook vs socket mode.

## Notes

The repository had no active `agent_docs/plan.md` or `agent_docs/progress.md` prior to this update; both are now created for this workstream.
